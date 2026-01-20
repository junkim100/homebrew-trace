"""
Capture Blocklist Manager for Trace

Allows users to selectively block apps and domains from being captured.
This helps protect sensitive activities (banking, medical, etc.) from
being recorded.

P10-01: Selective capture blocklist
"""

import logging
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from src.db.migrations import get_connection

logger = logging.getLogger(__name__)


@dataclass
class BlocklistEntry:
    """A single blocklist entry."""

    blocklist_id: str
    block_type: str  # 'app' or 'domain'
    pattern: str  # bundle_id for apps, domain pattern for domains
    display_name: str | None
    enabled: bool
    block_screenshots: bool
    block_events: bool
    created_ts: datetime
    updated_ts: datetime

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "blocklist_id": self.blocklist_id,
            "block_type": self.block_type,
            "pattern": self.pattern,
            "display_name": self.display_name,
            "enabled": self.enabled,
            "block_screenshots": self.block_screenshots,
            "block_events": self.block_events,
            "created_ts": self.created_ts.isoformat(),
            "updated_ts": self.updated_ts.isoformat(),
        }


class BlocklistManager:
    """
    Manages the capture blocklist.

    Provides methods to:
    - Add/remove apps and domains from blocklist
    - Check if an app or domain is blocked
    - Enable/disable blocklist entries
    - List all blocklist entries
    """

    def __init__(self, db_path: Path | str | None = None):
        """
        Initialize the blocklist manager.

        Args:
            db_path: Path to SQLite database (uses default if None)
        """
        self.db_path = Path(db_path) if db_path else None
        self._cache: dict[str, BlocklistEntry] = {}
        self._cache_valid = False

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection."""
        return get_connection(self.db_path)

    def _invalidate_cache(self) -> None:
        """Invalidate the in-memory cache."""
        self._cache_valid = False
        self._cache.clear()

    def _load_cache(self) -> None:
        """Load all blocklist entries into cache."""
        if self._cache_valid:
            return

        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT blocklist_id, block_type, pattern, display_name, enabled,
                       block_screenshots, block_events, created_ts, updated_ts
                FROM blocklist
                WHERE enabled = 1
                """
            )

            self._cache.clear()
            for row in cursor.fetchall():
                entry = BlocklistEntry(
                    blocklist_id=row[0],
                    block_type=row[1],
                    pattern=row[2],
                    display_name=row[3],
                    enabled=bool(row[4]),
                    block_screenshots=bool(row[5]),
                    block_events=bool(row[6]),
                    created_ts=datetime.fromisoformat(row[7]),
                    updated_ts=datetime.fromisoformat(row[8]),
                )
                # Use composite key for cache
                cache_key = f"{entry.block_type}:{entry.pattern}"
                self._cache[cache_key] = entry

            self._cache_valid = True
            logger.debug(f"Loaded {len(self._cache)} blocklist entries")
        finally:
            conn.close()

    def is_app_blocked(self, bundle_id: str | None) -> bool:
        """
        Check if an app is blocked.

        Args:
            bundle_id: The app's bundle identifier (e.g., com.apple.Safari)

        Returns:
            True if the app is blocked
        """
        if not bundle_id:
            return False

        self._load_cache()
        cache_key = f"app:{bundle_id}"
        return cache_key in self._cache

    def is_domain_blocked(self, url: str | None) -> bool:
        """
        Check if a URL's domain is blocked.

        Args:
            url: The full URL to check

        Returns:
            True if the domain is blocked
        """
        if not url:
            return False

        domain = self._extract_domain(url)
        if not domain:
            return False

        self._load_cache()

        # Check for exact match
        cache_key = f"domain:{domain}"
        if cache_key in self._cache:
            return True

        # Check for parent domain match (e.g., blocking example.com blocks sub.example.com)
        parts = domain.split(".")
        for i in range(len(parts)):
            parent_domain = ".".join(parts[i:])
            cache_key = f"domain:{parent_domain}"
            if cache_key in self._cache:
                return True

        return False

    def should_block_capture(
        self,
        bundle_id: str | None = None,
        url: str | None = None,
    ) -> tuple[bool, str | None]:
        """
        Check if capture should be blocked for the current context.

        Args:
            bundle_id: Current app's bundle identifier
            url: Current URL (if in browser)

        Returns:
            Tuple of (should_block, reason)
        """
        # Check app blocklist
        if bundle_id and self.is_app_blocked(bundle_id):
            return True, f"App blocked: {bundle_id}"

        # Check domain blocklist
        if url and self.is_domain_blocked(url):
            domain = self._extract_domain(url)
            return True, f"Domain blocked: {domain}"

        return False, None

    def add_app(
        self,
        bundle_id: str,
        display_name: str | None = None,
        block_screenshots: bool = True,
        block_events: bool = True,
    ) -> BlocklistEntry:
        """
        Add an app to the blocklist.

        Args:
            bundle_id: The app's bundle identifier
            display_name: Human-readable name for the app
            block_screenshots: Whether to block screenshot capture
            block_events: Whether to block event recording

        Returns:
            The created blocklist entry
        """
        return self._add_entry(
            block_type="app",
            pattern=bundle_id,
            display_name=display_name,
            block_screenshots=block_screenshots,
            block_events=block_events,
        )

    def add_domain(
        self,
        domain: str,
        display_name: str | None = None,
        block_screenshots: bool = True,
        block_events: bool = True,
    ) -> BlocklistEntry:
        """
        Add a domain to the blocklist.

        Args:
            domain: The domain to block (e.g., example.com)
            display_name: Human-readable name for the domain
            block_screenshots: Whether to block screenshot capture
            block_events: Whether to block event recording

        Returns:
            The created blocklist entry
        """
        # Normalize domain (remove protocol, path, etc.)
        normalized = self._normalize_domain(domain)
        return self._add_entry(
            block_type="domain",
            pattern=normalized,
            display_name=display_name,
            block_screenshots=block_screenshots,
            block_events=block_events,
        )

    def _add_entry(
        self,
        block_type: str,
        pattern: str,
        display_name: str | None,
        block_screenshots: bool,
        block_events: bool,
    ) -> BlocklistEntry:
        """Add a blocklist entry to the database."""
        blocklist_id = f"block-{uuid.uuid4().hex[:8]}"
        now = datetime.now()

        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO blocklist (
                    blocklist_id, block_type, pattern, display_name,
                    enabled, block_screenshots, block_events,
                    created_ts, updated_ts
                ) VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?)
                ON CONFLICT(block_type, pattern) DO UPDATE SET
                    display_name = excluded.display_name,
                    enabled = 1,
                    block_screenshots = excluded.block_screenshots,
                    block_events = excluded.block_events,
                    updated_ts = excluded.updated_ts
                RETURNING blocklist_id
                """,
                (
                    blocklist_id,
                    block_type,
                    pattern,
                    display_name,
                    int(block_screenshots),
                    int(block_events),
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
            result = cursor.fetchone()
            actual_id = result[0] if result else blocklist_id
            conn.commit()

            self._invalidate_cache()

            logger.info(f"Added {block_type} to blocklist: {pattern}")

            return BlocklistEntry(
                blocklist_id=actual_id,
                block_type=block_type,
                pattern=pattern,
                display_name=display_name,
                enabled=True,
                block_screenshots=block_screenshots,
                block_events=block_events,
                created_ts=now,
                updated_ts=now,
            )
        finally:
            conn.close()

    def remove_entry(self, blocklist_id: str) -> bool:
        """
        Remove an entry from the blocklist.

        Args:
            blocklist_id: The ID of the entry to remove

        Returns:
            True if entry was removed
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM blocklist WHERE blocklist_id = ?",
                (blocklist_id,),
            )
            conn.commit()

            removed = cursor.rowcount > 0
            if removed:
                self._invalidate_cache()
                logger.info(f"Removed blocklist entry: {blocklist_id}")

            return removed
        finally:
            conn.close()

    def set_enabled(self, blocklist_id: str, enabled: bool) -> bool:
        """
        Enable or disable a blocklist entry.

        Args:
            blocklist_id: The ID of the entry
            enabled: Whether to enable the entry

        Returns:
            True if entry was updated
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE blocklist
                SET enabled = ?, updated_ts = ?
                WHERE blocklist_id = ?
                """,
                (int(enabled), datetime.now().isoformat(), blocklist_id),
            )
            conn.commit()

            updated = cursor.rowcount > 0
            if updated:
                self._invalidate_cache()
                logger.info(
                    f"{'Enabled' if enabled else 'Disabled'} blocklist entry: {blocklist_id}"
                )

            return updated
        finally:
            conn.close()

    def list_entries(self, include_disabled: bool = True) -> list[BlocklistEntry]:
        """
        List all blocklist entries.

        Args:
            include_disabled: Whether to include disabled entries

        Returns:
            List of blocklist entries
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            if include_disabled:
                cursor.execute(
                    """
                    SELECT blocklist_id, block_type, pattern, display_name, enabled,
                           block_screenshots, block_events, created_ts, updated_ts
                    FROM blocklist
                    ORDER BY block_type, pattern
                    """
                )
            else:
                cursor.execute(
                    """
                    SELECT blocklist_id, block_type, pattern, display_name, enabled,
                           block_screenshots, block_events, created_ts, updated_ts
                    FROM blocklist
                    WHERE enabled = 1
                    ORDER BY block_type, pattern
                    """
                )

            entries = []
            for row in cursor.fetchall():
                entries.append(
                    BlocklistEntry(
                        blocklist_id=row[0],
                        block_type=row[1],
                        pattern=row[2],
                        display_name=row[3],
                        enabled=bool(row[4]),
                        block_screenshots=bool(row[5]),
                        block_events=bool(row[6]),
                        created_ts=datetime.fromisoformat(row[7]),
                        updated_ts=datetime.fromisoformat(row[8]),
                    )
                )

            return entries
        finally:
            conn.close()

    def get_entry(self, blocklist_id: str) -> BlocklistEntry | None:
        """
        Get a specific blocklist entry.

        Args:
            blocklist_id: The ID of the entry

        Returns:
            The blocklist entry or None
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT blocklist_id, block_type, pattern, display_name, enabled,
                       block_screenshots, block_events, created_ts, updated_ts
                FROM blocklist
                WHERE blocklist_id = ?
                """,
                (blocklist_id,),
            )

            row = cursor.fetchone()
            if not row:
                return None

            return BlocklistEntry(
                blocklist_id=row[0],
                block_type=row[1],
                pattern=row[2],
                display_name=row[3],
                enabled=bool(row[4]),
                block_screenshots=bool(row[5]),
                block_events=bool(row[6]),
                created_ts=datetime.fromisoformat(row[7]),
                updated_ts=datetime.fromisoformat(row[8]),
            )
        finally:
            conn.close()

    @staticmethod
    def _extract_domain(url: str) -> str | None:
        """Extract domain from a URL."""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc or parsed.path.split("/")[0]
            # Remove port if present
            domain = domain.split(":")[0]
            return domain.lower() if domain else None
        except Exception:
            return None

    @staticmethod
    def _normalize_domain(domain: str) -> str:
        """Normalize a domain string."""
        # Remove protocol if present
        if "://" in domain:
            domain = domain.split("://", 1)[1]
        # Remove path if present
        domain = domain.split("/")[0]
        # Remove port if present
        domain = domain.split(":")[0]
        # Lowercase
        return domain.lower()


# Default common sensitive apps and domains
DEFAULT_BLOCKLIST = {
    "apps": [
        ("com.apple.Keychain-Access", "Keychain Access"),
        ("com.1password.1password", "1Password"),
        ("com.agilebits.onepassword7", "1Password 7"),
        ("com.lastpass.LastPass", "LastPass"),
        ("com.bitwarden.desktop", "Bitwarden"),
        ("com.dashlane.Dashlane", "Dashlane"),
    ],
    "domains": [
        ("chase.com", "Chase Bank"),
        ("bankofamerica.com", "Bank of America"),
        ("wellsfargo.com", "Wells Fargo"),
        ("citi.com", "Citibank"),
        ("capitalone.com", "Capital One"),
        ("schwab.com", "Charles Schwab"),
        ("fidelity.com", "Fidelity"),
        ("vanguard.com", "Vanguard"),
        ("robinhood.com", "Robinhood"),
        ("coinbase.com", "Coinbase"),
        ("paypal.com", "PayPal"),
        ("venmo.com", "Venmo"),
        ("mint.com", "Mint"),
        ("mychart.com", "MyChart"),
        ("patient.portal", "Patient Portal"),
    ],
}


def initialize_default_blocklist(db_path: Path | str | None = None) -> int:
    """
    Initialize the blocklist with common sensitive apps and domains.

    This is meant to be called on first run to provide sensible defaults.

    Args:
        db_path: Path to SQLite database

    Returns:
        Number of entries added
    """
    manager = BlocklistManager(db_path)
    count = 0

    for bundle_id, display_name in DEFAULT_BLOCKLIST["apps"]:
        try:
            manager.add_app(bundle_id, display_name)
            count += 1
        except Exception as e:
            logger.debug(f"Could not add default app {bundle_id}: {e}")

    for domain, display_name in DEFAULT_BLOCKLIST["domains"]:
        try:
            manager.add_domain(domain, display_name)
            count += 1
        except Exception as e:
            logger.debug(f"Could not add default domain {domain}: {e}")

    logger.info(f"Initialized blocklist with {count} default entries")
    return count


if __name__ == "__main__":
    import fire

    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    def list_entries(include_disabled: bool = True):
        """List all blocklist entries."""
        manager = BlocklistManager()
        entries = manager.list_entries(include_disabled)
        return [e.to_dict() for e in entries]

    def add_app(bundle_id: str, name: str | None = None):
        """Add an app to the blocklist."""
        manager = BlocklistManager()
        entry = manager.add_app(bundle_id, name)
        return entry.to_dict()

    def add_domain(domain: str, name: str | None = None):
        """Add a domain to the blocklist."""
        manager = BlocklistManager()
        entry = manager.add_domain(domain, name)
        return entry.to_dict()

    def remove(blocklist_id: str):
        """Remove an entry from the blocklist."""
        manager = BlocklistManager()
        return {"removed": manager.remove_entry(blocklist_id)}

    def check(bundle_id: str | None = None, url: str | None = None):
        """Check if an app or URL is blocked."""
        manager = BlocklistManager()
        blocked, reason = manager.should_block_capture(bundle_id, url)
        return {"blocked": blocked, "reason": reason}

    def init_defaults():
        """Initialize default blocklist entries."""
        count = initialize_default_blocklist()
        return {"added": count}

    fire.Fire(
        {
            "list": list_entries,
            "add-app": add_app,
            "add-domain": add_domain,
            "remove": remove,
            "check": check,
            "init": init_defaults,
        }
    )
