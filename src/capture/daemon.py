"""
Capture Daemon Orchestrator for Trace

Coordinates all capture activities at 1-second intervals:
- Multi-monitor screenshot capture
- Foreground app/window metadata
- Screenshot deduplication
- Event span tracking
- Now playing (via macOS MediaRemote - works with any media app)
- Location snapshots
- Browser URLs

All captured data is written to SQLite and cache directories.

P3-10: Capture daemon orchestrator
"""

import logging
import signal
import sqlite3
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.capture.blocklist import BlocklistManager
from src.capture.dedup import DuplicateTracker
from src.capture.events import EventTracker
from src.capture.foreground import ForegroundApp, capture_foreground_app
from src.capture.location import LocationCapture
from src.capture.media_remote import MediaRemoteCapture
from src.capture.screenshots import CapturedScreenshot, MultiMonitorCapture
from src.capture.urls import URLCapture
from src.core.paths import ensure_data_directories
from src.db.migrations import get_connection, init_database

logger = logging.getLogger(__name__)

# Default capture interval (seconds)
DEFAULT_CAPTURE_INTERVAL = 1.0

# Location capture interval (seconds) - less frequent than other captures
LOCATION_CAPTURE_INTERVAL = 60.0


@dataclass
class CaptureStats:
    """Statistics about capture daemon activity."""

    captures_total: int = 0
    screenshots_captured: int = 0
    screenshots_deduplicated: int = 0
    events_created: int = 0
    errors: int = 0
    start_time: datetime | None = None


@dataclass
class CaptureSnapshot:
    """A single capture snapshot with all collected data."""

    timestamp: datetime
    foreground: ForegroundApp
    screenshots: list[CapturedScreenshot]
    deduplicated_count: int
    url: str | None
    page_title: str | None
    now_playing_json: str | None
    location_text: str | None
    event_closed: bool
    blocked: bool = False
    blocked_reason: str | None = None


class CaptureDaemon:
    """
    Main capture daemon that orchestrates all capture activities.

    Runs a capture loop at configurable intervals, collecting:
    - Screenshots from all monitors
    - Foreground app/window information
    - Browser URLs when relevant
    - Now playing media information
    - Location data

    All data is persisted to SQLite and the cache directory structure.
    """

    def __init__(
        self,
        capture_interval: float = DEFAULT_CAPTURE_INTERVAL,
        jpeg_quality: int = 85,
        dedup_threshold: int = 5,
        location_interval: float = LOCATION_CAPTURE_INTERVAL,
        db_path: Path | str | None = None,
    ):
        """
        Initialize the capture daemon.

        Args:
            capture_interval: Seconds between captures
            jpeg_quality: JPEG quality for screenshots (1-100)
            dedup_threshold: Perceptual hash threshold for deduplication
            location_interval: Seconds between location captures
            db_path: Path to SQLite database (uses default if None)
        """
        self.capture_interval = capture_interval
        self.location_interval = location_interval
        self.db_path = Path(db_path) if db_path else None

        # Initialize capture components
        self._screenshot_capture = MultiMonitorCapture(jpeg_quality=jpeg_quality)
        self._dedup_tracker = DuplicateTracker(threshold=dedup_threshold)
        self._event_tracker = EventTracker(db_path=str(self.db_path) if self.db_path else None)
        self._now_playing_capture = MediaRemoteCapture()
        self._location_capture = LocationCapture(min_interval_seconds=location_interval)
        self._url_capture = URLCapture()
        self._blocklist = BlocklistManager(db_path=self.db_path)

        # State
        self._running = False
        self._thread: threading.Thread | None = None
        self._stats = CaptureStats()
        self._last_location_capture: datetime | None = None
        self._callbacks: list[Callable[[CaptureSnapshot], None]] = []

        # Shutdown handling
        self._shutdown_event = threading.Event()

    def add_callback(self, callback: Callable[[CaptureSnapshot], None]) -> None:
        """
        Add a callback to be called after each capture.

        Args:
            callback: Function that receives CaptureSnapshot
        """
        self._callbacks.append(callback)

    def start(self, blocking: bool = False) -> None:
        """
        Start the capture daemon.

        Args:
            blocking: If True, run in the current thread (blocks)
        """
        if self._running:
            logger.warning("Capture daemon already running")
            return

        # Ensure data directories exist
        ensure_data_directories()

        # Initialize database
        init_database(self.db_path)

        # Refresh monitor list
        self._screenshot_capture.refresh_monitors()

        self._running = True
        self._stats = CaptureStats(start_time=datetime.now())
        self._shutdown_event.clear()

        logger.info("Capture daemon starting...")

        if blocking:
            self._run_loop()
        else:
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """
        Stop the capture daemon.

        Args:
            timeout: Maximum time to wait for thread to stop
        """
        if not self._running:
            return

        logger.info("Stopping capture daemon...")
        self._running = False
        self._shutdown_event.set()

        # Close any pending event
        self._event_tracker.close_current_event()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

        logger.info("Capture daemon stopped")

    def get_stats(self) -> CaptureStats:
        """Get current capture statistics."""
        return self._stats

    def _run_loop(self) -> None:
        """Main capture loop."""
        logger.info(f"Capture loop started (interval: {self.capture_interval}s)")

        while self._running and not self._shutdown_event.is_set():
            loop_start = time.time()

            try:
                snapshot = self._capture_tick()
                self._stats.captures_total += 1

                # Notify callbacks
                for callback in self._callbacks:
                    try:
                        callback(snapshot)
                    except Exception as e:
                        logger.error(f"Callback error: {e}")

            except Exception as e:
                logger.error(f"Capture error: {e}")
                self._stats.errors += 1

            # Sleep for remaining interval
            elapsed = time.time() - loop_start
            sleep_time = max(0, self.capture_interval - elapsed)
            if sleep_time > 0:
                self._shutdown_event.wait(timeout=sleep_time)

    def _capture_tick(self) -> CaptureSnapshot:
        """Execute a single capture tick."""
        timestamp = datetime.now()

        # 1. Capture foreground app information
        foreground = capture_foreground_app(timestamp)

        # 2. Capture browser URL if active app is a browser
        url_result = self._url_capture.get_active_browser_url(foreground.bundle_id, timestamp)
        url = url_result.url if url_result else None
        page_title = url_result.title if url_result else None

        # 3. Check blocklist - skip capture if blocked
        is_blocked, blocked_reason = self._blocklist.should_block_capture(
            bundle_id=foreground.bundle_id,
            url=url,
        )

        if is_blocked:
            logger.debug(f"Capture blocked: {blocked_reason}")
            return CaptureSnapshot(
                timestamp=timestamp,
                foreground=foreground,
                screenshots=[],
                deduplicated_count=0,
                url=None,  # Don't record the URL
                page_title=None,
                now_playing_json=None,
                location_text=None,
                event_closed=False,
                blocked=True,
                blocked_reason=blocked_reason,
            )

        # 4. Capture now playing
        now_playing = self._now_playing_capture.capture(timestamp)
        now_playing_json = now_playing.to_json() if now_playing else None

        # 5. Capture location (less frequently)
        location = self._location_capture.capture(timestamp)
        location_text = location.location_text if location else None

        # 6. Update event tracker
        closed_event = self._event_tracker.update(
            foreground=foreground,
            url=url,
            page_title=page_title,
            now_playing_json=now_playing_json,
            location_text=location_text,
        )

        if closed_event:
            self._stats.events_created += 1

        # 7. Capture screenshots
        screenshots = self._screenshot_capture.capture_all(timestamp)
        deduplicated_count = 0

        # 8. Process screenshots (deduplication, store to DB)
        screenshots_to_store = []
        for screenshot in screenshots:
            try:
                result = self._dedup_tracker.check_and_update(
                    screenshot.monitor_id, screenshot.path
                )

                if result.is_duplicate:
                    # Delete the duplicate file
                    screenshot.path.unlink(missing_ok=True)
                    deduplicated_count += 1
                    self._stats.screenshots_deduplicated += 1
                else:
                    screenshots_to_store.append(
                        (screenshot, result.current_hash, result.hamming_distance or 0)
                    )
                    self._stats.screenshots_captured += 1

                    # Link screenshot to current event
                    self._event_tracker.add_evidence(screenshot.screenshot_id)

            except Exception as e:
                logger.error(f"Screenshot processing error: {e}")

        # 9. Store screenshots in database
        for screenshot, fingerprint, diff in screenshots_to_store:
            self._store_screenshot(screenshot, fingerprint, diff)

        return CaptureSnapshot(
            timestamp=timestamp,
            foreground=foreground,
            screenshots=[s for s, _, _ in screenshots_to_store],
            deduplicated_count=deduplicated_count,
            url=url,
            page_title=page_title,
            now_playing_json=now_playing_json,
            location_text=location_text,
            event_closed=closed_event is not None,
            blocked=False,
            blocked_reason=None,
        )

    def _store_screenshot(
        self,
        screenshot: CapturedScreenshot,
        fingerprint: str,
        diff_score: float,
    ) -> None:
        """Store a screenshot record in the database."""
        try:
            conn = get_connection(self.db_path)
            try:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO screenshots (
                        screenshot_id, ts, monitor_id, path, fingerprint,
                        diff_score, width, height
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        screenshot.screenshot_id,
                        screenshot.timestamp.isoformat(),
                        screenshot.monitor_id,
                        str(screenshot.path),
                        fingerprint,
                        diff_score,
                        screenshot.width,
                        screenshot.height,
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        except sqlite3.Error as e:
            logger.error(f"Failed to store screenshot: {e}")


def run_daemon(
    interval: float = DEFAULT_CAPTURE_INTERVAL,
    quality: int = 85,
    dedup_threshold: int = 5,
):
    """
    Run the capture daemon in blocking mode.

    Args:
        interval: Capture interval in seconds
        quality: JPEG quality for screenshots
        dedup_threshold: Deduplication threshold
    """
    daemon = CaptureDaemon(
        capture_interval=interval,
        jpeg_quality=quality,
        dedup_threshold=dedup_threshold,
    )

    # Handle shutdown signals
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        daemon.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Add a simple logging callback
    def log_callback(snapshot: CaptureSnapshot):
        screenshots_count = len(snapshot.screenshots)
        dedup_count = snapshot.deduplicated_count
        app = snapshot.foreground.app_name or "Unknown"
        window = snapshot.foreground.window_title or ""
        window_preview = window[:30] + "..." if len(window) > 30 else window
        logger.debug(
            f"Captured: {app} - {window_preview} | "
            f"Screenshots: {screenshots_count} (dedup: {dedup_count})"
        )

    daemon.add_callback(log_callback)

    # Start blocking
    daemon.start(blocking=True)


if __name__ == "__main__":
    import fire

    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    def start(
        interval: float = 1.0,
        quality: int = 85,
        dedup_threshold: int = 5,
        verbose: bool = False,
    ):
        """Start the capture daemon."""
        if verbose:
            logging.getLogger("src.capture").setLevel(logging.DEBUG)

        run_daemon(interval=interval, quality=quality, dedup_threshold=dedup_threshold)

    def test(duration: int = 10, interval: float = 1.0):
        """Run a short test capture."""
        daemon = CaptureDaemon(capture_interval=interval)

        captures = []

        def collect_callback(snapshot: CaptureSnapshot):
            captures.append(
                {
                    "timestamp": snapshot.timestamp.isoformat(),
                    "app": snapshot.foreground.app_name,
                    "window": snapshot.foreground.window_title,
                    "screenshots": len(snapshot.screenshots),
                    "deduplicated": snapshot.deduplicated_count,
                    "url": snapshot.url,
                    "event_closed": snapshot.event_closed,
                }
            )
            print(f"Captured: {snapshot.foreground.app_name}")

        daemon.add_callback(collect_callback)
        daemon.start()

        time.sleep(duration)
        daemon.stop()

        stats = daemon.get_stats()
        return {
            "duration": duration,
            "stats": {
                "captures_total": stats.captures_total,
                "screenshots_captured": stats.screenshots_captured,
                "screenshots_deduplicated": stats.screenshots_deduplicated,
                "events_created": stats.events_created,
                "errors": stats.errors,
            },
            "captures": captures,
        }

    def stats():
        """Show capture statistics from the database."""

        conn = get_connection()
        try:
            cursor = conn.cursor()

            # Count screenshots
            cursor.execute("SELECT COUNT(*) FROM screenshots")
            screenshot_count = cursor.fetchone()[0]

            # Count events
            cursor.execute("SELECT COUNT(*) FROM events")
            event_count = cursor.fetchone()[0]

            # Recent screenshots
            cursor.execute("SELECT ts, monitor_id, path FROM screenshots ORDER BY ts DESC LIMIT 5")
            recent_screenshots = [dict(row) for row in cursor.fetchall()]

            # Recent events
            cursor.execute(
                "SELECT start_ts, app_name, window_title FROM events ORDER BY start_ts DESC LIMIT 5"
            )
            recent_events = [dict(row) for row in cursor.fetchall()]

            return {
                "screenshot_count": screenshot_count,
                "event_count": event_count,
                "recent_screenshots": recent_screenshots,
                "recent_events": recent_events,
            }
        finally:
            conn.close()

    fire.Fire(
        {
            "start": start,
            "test": test,
            "stats": stats,
        }
    )
