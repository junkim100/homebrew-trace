"""
Database Migration Runner for Trace

Handles versioned schema migrations for the SQLite database.
Migrations are stored as numbered SQL files in the migrations/ directory.
"""

import logging
import re
import sqlite3
from pathlib import Path

from src.core.paths import DB_PATH

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
DEFAULT_DB_PATH = DB_PATH


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """
    Get a connection to the SQLite database.

    Args:
        db_path: Path to the database file. Defaults to ~/Trace/db/trace.sqlite

    Returns:
        sqlite3.Connection with foreign keys enabled
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH

    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def get_current_version(conn: sqlite3.Connection) -> int:
    """
    Get the current schema version from the database.

    Args:
        conn: Database connection

    Returns:
        Current version number, or 0 if no migrations applied
    """
    try:
        cursor = conn.execute("SELECT MAX(version) FROM schema_version")
        row = cursor.fetchone()
        return row[0] if row[0] is not None else 0
    except sqlite3.OperationalError:
        return 0


class MigrationRunner:
    """
    Manages database schema migrations.

    Migrations are SQL files in the migrations/ directory named like:
    - 001_initial_schema.sql
    - 002_add_feature.sql

    Each migration file should contain valid SQL that can be executed
    as a script, and should insert a record into schema_version.
    """

    def __init__(self, db_path: Path | None = None):
        """
        Initialize the migration runner.

        Args:
            db_path: Path to the database file
        """
        self.db_path = db_path or DEFAULT_DB_PATH
        self.migrations_dir = MIGRATIONS_DIR

    def get_pending_migrations(self) -> list[tuple[int, Path]]:
        """
        Get list of migrations that haven't been applied yet.

        Returns:
            List of (version, path) tuples for pending migrations
        """
        if not self.migrations_dir.exists():
            return []

        migration_files = sorted(self.migrations_dir.glob("*.sql"))
        pending = []

        with get_connection(self.db_path) as conn:
            current_version = get_current_version(conn)

        for migration_file in migration_files:
            match = re.match(r"^(\d+)_", migration_file.name)
            if match:
                version = int(match.group(1))
                if version > current_version:
                    pending.append((version, migration_file))

        return sorted(pending, key=lambda x: x[0])

    def apply_migration(self, conn: sqlite3.Connection, migration_path: Path) -> None:
        """
        Apply a single migration file.

        Args:
            conn: Database connection
            migration_path: Path to the migration SQL file
        """
        logger.info(f"Applying migration: {migration_path.name}")

        sql = migration_path.read_text()
        conn.executescript(sql)
        conn.commit()

        logger.info(f"Successfully applied migration: {migration_path.name}")

    def run_migrations(self) -> int:
        """
        Run all pending migrations.

        Returns:
            Number of migrations applied
        """
        pending = self.get_pending_migrations()

        if not pending:
            logger.info("No pending migrations")
            return 0

        logger.info(f"Found {len(pending)} pending migration(s)")

        with get_connection(self.db_path) as conn:
            for _version, migration_path in pending:
                try:
                    self.apply_migration(conn, migration_path)
                except sqlite3.Error as e:
                    logger.error(f"Migration failed: {migration_path.name}: {e}")
                    raise

        return len(pending)

    def get_status(self) -> dict:
        """
        Get the current migration status.

        Returns:
            Dictionary with version info and pending migrations
        """
        with get_connection(self.db_path) as conn:
            current_version = get_current_version(conn)

        pending = self.get_pending_migrations()

        return {
            "current_version": current_version,
            "pending_migrations": len(pending),
            "pending_files": [p.name for _, p in pending],
            "database_path": str(self.db_path),
        }


def init_database(db_path: Path | None = None) -> sqlite3.Connection:
    """
    Initialize the database by running all pending migrations.

    Args:
        db_path: Path to the database file

    Returns:
        Database connection
    """
    runner = MigrationRunner(db_path)
    applied = runner.run_migrations()

    if applied > 0:
        logger.info(f"Applied {applied} migration(s)")

    return get_connection(db_path)


def verify_schema(conn: sqlite3.Connection) -> dict:
    """
    Verify that all expected tables exist in the database.

    Args:
        conn: Database connection

    Returns:
        Dictionary with verification results
    """
    expected_tables = [
        "schema_version",
        "notes",
        "entities",
        "note_entities",
        "edges",
        "events",
        "screenshots",
        "text_buffers",
        "jobs",
        "aggregates",
        "embeddings",
        "deletion_log",
    ]

    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    existing_tables = [row[0] for row in cursor.fetchall()]

    missing = [t for t in expected_tables if t not in existing_tables]
    extra = [t for t in existing_tables if t not in expected_tables and not t.startswith("sqlite_")]

    return {
        "valid": len(missing) == 0,
        "expected": expected_tables,
        "existing": existing_tables,
        "missing": missing,
        "extra": extra,
    }


if __name__ == "__main__":
    import fire

    def status(db_path: str | None = None):
        """Show migration status."""
        path = Path(db_path) if db_path else None
        runner = MigrationRunner(path)
        return runner.get_status()

    def migrate(db_path: str | None = None):
        """Run pending migrations."""
        path = Path(db_path) if db_path else None
        runner = MigrationRunner(path)
        count = runner.run_migrations()
        return {"applied": count}

    def verify(db_path: str | None = None):
        """Verify database schema."""
        path = Path(db_path) if db_path else None
        with get_connection(path) as conn:
            return verify_schema(conn)

    fire.Fire(
        {
            "status": status,
            "migrate": migrate,
            "verify": verify,
        }
    )
