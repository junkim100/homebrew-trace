"""
Data Directory Structure Management for Trace

This module defines and manages the data directory structure for Trace.
All paths are relative to the DATA_ROOT (~/Trace by default).

Directory structure:
    Trace/
    ├── notes/YYYY/MM/DD/          # Durable Markdown notes
    │   ├── hour-YYYYMMDD-HH.md
    │   └── day-YYYYMMDD.md
    ├── db/trace.sqlite            # SQLite database (source of truth)
    ├── index/                     # Vector embeddings (if not in SQLite)
    └── cache/                     # Temporary, deleted daily after revision
        ├── screenshots/YYYYMMDD/
        ├── text_buffers/YYYYMMDD/
        └── ocr/YYYYMMDD/
"""

import logging
import os
from datetime import date, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Allow override via environment variable for testing
_data_root_override = os.environ.get("TRACE_DATA_ROOT")
DATA_ROOT: Path = Path(_data_root_override) if _data_root_override else Path.home() / "Trace"

# Primary directories
NOTES_DIR: Path = DATA_ROOT / "notes"
DB_DIR: Path = DATA_ROOT / "db"
INDEX_DIR: Path = DATA_ROOT / "index"
CACHE_DIR: Path = DATA_ROOT / "cache"

# Database file path
DB_PATH: Path = DB_DIR / "trace.sqlite"

# Cache subdirectories
SCREENSHOTS_CACHE_DIR: Path = CACHE_DIR / "screenshots"
TEXT_BUFFERS_CACHE_DIR: Path = CACHE_DIR / "text_buffers"
OCR_CACHE_DIR: Path = CACHE_DIR / "ocr"

# All directories that should exist
_REQUIRED_DIRS: tuple[Path, ...] = (
    NOTES_DIR,
    DB_DIR,
    INDEX_DIR,
    CACHE_DIR,
    SCREENSHOTS_CACHE_DIR,
    TEXT_BUFFERS_CACHE_DIR,
    OCR_CACHE_DIR,
)


def ensure_data_directories() -> dict[str, bool]:
    """
    Ensure all required data directories exist.

    Creates the directory structure on first run. This function is idempotent
    and safe to call multiple times.

    Returns:
        Dictionary mapping directory names to whether they were created (True)
        or already existed (False).
    """
    results: dict[str, bool] = {}

    for dir_path in _REQUIRED_DIRS:
        try:
            created = not dir_path.exists()
            dir_path.mkdir(parents=True, exist_ok=True)
            results[str(dir_path.relative_to(DATA_ROOT))] = created
            if created:
                logger.info(f"Created directory: {dir_path}")
        except OSError as e:
            logger.error(f"Failed to create directory {dir_path}: {e}")
            raise

    return results


def get_note_path(dt: datetime | date, note_type: str = "hour") -> Path:
    """
    Get the path for a note file based on date/time and type.

    Args:
        dt: The datetime or date for the note
        note_type: Either "hour" or "day"

    Returns:
        Full path to the note file

    Raises:
        ValueError: If note_type is not "hour" or "day"
    """
    if note_type not in ("hour", "day"):
        raise ValueError(f"note_type must be 'hour' or 'day', got '{note_type}'")

    if isinstance(dt, datetime):
        d = dt.date()
        hour = dt.hour
    else:
        d = dt
        hour = 0

    # Build the directory path: notes/YYYY/MM/DD/
    note_dir = NOTES_DIR / f"{d.year:04d}" / f"{d.month:02d}" / f"{d.day:02d}"

    # Build the filename
    date_str = f"{d.year:04d}{d.month:02d}{d.day:02d}"
    if note_type == "hour":
        filename = f"hour-{date_str}-{hour:02d}.md"
    else:
        filename = f"day-{date_str}.md"

    return note_dir / filename


def get_daily_cache_dirs(dt: datetime | date | None = None) -> dict[str, Path]:
    """
    Get the cache directory paths for a specific date.

    Cache directories are organized by date (YYYYMMDD) to enable
    easy cleanup after daily revision.

    Args:
        dt: The datetime or date. Defaults to today.

    Returns:
        Dictionary with 'screenshots', 'text_buffers', and 'ocr' paths
    """
    if dt is None:
        dt = date.today()
    elif isinstance(dt, datetime):
        dt = dt.date()

    date_str = f"{dt.year:04d}{dt.month:02d}{dt.day:02d}"

    return {
        "screenshots": SCREENSHOTS_CACHE_DIR / date_str,
        "text_buffers": TEXT_BUFFERS_CACHE_DIR / date_str,
        "ocr": OCR_CACHE_DIR / date_str,
    }


def ensure_daily_cache_dirs(dt: datetime | date | None = None) -> dict[str, Path]:
    """
    Ensure the cache directories for a specific date exist.

    Args:
        dt: The datetime or date. Defaults to today.

    Returns:
        Dictionary with paths that were created/verified
    """
    dirs = get_daily_cache_dirs(dt)

    for _name, dir_path in dirs.items():
        dir_path.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Ensured cache directory exists: {dir_path}")

    return dirs


def ensure_note_directory(dt: datetime | date) -> Path:
    """
    Ensure the note directory for a specific date exists.

    Args:
        dt: The datetime or date

    Returns:
        Path to the note directory
    """
    if isinstance(dt, datetime):
        d = dt.date()
    else:
        d = dt

    note_dir = NOTES_DIR / f"{d.year:04d}" / f"{d.month:02d}" / f"{d.day:02d}"
    note_dir.mkdir(parents=True, exist_ok=True)
    return note_dir


if __name__ == "__main__":
    import fire

    def init():
        """Initialize all data directories."""
        results = ensure_data_directories()
        created_count = sum(1 for created in results.values() if created)
        return {
            "data_root": str(DATA_ROOT),
            "directories": results,
            "created": created_count,
            "total": len(results),
        }

    def show():
        """Show all data directory paths."""
        return {
            "data_root": str(DATA_ROOT),
            "notes": str(NOTES_DIR),
            "db": str(DB_DIR),
            "db_file": str(DB_PATH),
            "index": str(INDEX_DIR),
            "cache": str(CACHE_DIR),
            "screenshots_cache": str(SCREENSHOTS_CACHE_DIR),
            "text_buffers_cache": str(TEXT_BUFFERS_CACHE_DIR),
            "ocr_cache": str(OCR_CACHE_DIR),
        }

    def verify():
        """Verify all required directories exist."""
        missing = [str(d) for d in _REQUIRED_DIRS if not d.exists()]
        return {
            "valid": len(missing) == 0,
            "missing": missing,
        }

    fire.Fire(
        {
            "init": init,
            "show": show,
            "verify": verify,
        }
    )
