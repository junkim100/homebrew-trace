"""
Backfill Detection and Execution for Trace

Detects missing hourly notes where activity data exists and
triggers automatic summarization to fill gaps.

This runs on startup and periodically to ensure no activity
goes unsummarized.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from src.core.paths import DB_PATH
from src.db.migrations import get_connection
from src.platform.notifications import send_backfill_notification, send_error_notification
from src.summarize.summarizer import HourlySummarizer, SummarizationResult

logger = logging.getLogger(__name__)

# Default lookback period for backfill detection
DEFAULT_LOOKBACK_HOURS = 4

# Minimum number of screenshots/events to consider an hour "active"
MIN_ACTIVITY_THRESHOLD = 5


@dataclass
class BackfillResult:
    """Result of a backfill operation."""

    hours_checked: int
    hours_missing: int
    hours_backfilled: int
    hours_failed: int
    results: list[SummarizationResult]


class BackfillDetector:
    """
    Detects and fills gaps in hourly notes.

    Scans recent hours for activity data (screenshots, events) that
    doesn't have a corresponding note, and triggers summarization.
    """

    def __init__(
        self,
        db_path: Path | str | None = None,
        api_key: str | None = None,
        lookback_hours: int = DEFAULT_LOOKBACK_HOURS,
    ):
        """
        Initialize the backfill detector.

        Args:
            db_path: Path to SQLite database
            api_key: OpenAI API key for summarization
            lookback_hours: How many hours back to check for gaps
        """
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.api_key = api_key
        self.lookback_hours = lookback_hours
        self._summarizer: HourlySummarizer | None = None

    def _get_summarizer(self) -> HourlySummarizer:
        """Get or create the summarizer (lazy initialization)."""
        if self._summarizer is None:
            self._summarizer = HourlySummarizer(db_path=self.db_path, api_key=self.api_key)
        return self._summarizer

    def find_missing_hours(self, lookback_hours: int | None = None) -> list[datetime]:
        """
        Find hours with activity but no notes.

        Args:
            lookback_hours: Override default lookback period

        Returns:
            List of hour start times that need backfilling
        """
        lookback = lookback_hours or self.lookback_hours
        now = datetime.now()
        missing = []

        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()

            for i in range(1, lookback + 1):  # Skip current hour (still accumulating)
                hour_start = (now - timedelta(hours=i)).replace(minute=0, second=0, microsecond=0)
                hour_end = hour_start + timedelta(hours=1)

                # Check if note exists
                if self._note_exists(cursor, hour_start):
                    continue

                # Check if activity exists
                if self._has_activity(cursor, hour_start, hour_end):
                    missing.append(hour_start)
                    logger.debug(f"Found missing note for hour: {hour_start.isoformat()}")

        finally:
            conn.close()

        if missing:
            logger.info(f"Found {len(missing)} hours with activity but no notes")

        return missing

    def _note_exists(self, cursor, hour_start: datetime) -> bool:
        """Check if a note exists for the given hour."""
        cursor.execute(
            """
            SELECT 1 FROM notes
            WHERE note_type = 'hour'
            AND start_ts = ?
            LIMIT 1
            """,
            (hour_start.isoformat(),),
        )
        return cursor.fetchone() is not None

    def _has_activity(self, cursor, hour_start: datetime, hour_end: datetime) -> bool:
        """Check if there's meaningful activity in the given hour."""
        # Check for screenshots
        cursor.execute(
            """
            SELECT COUNT(*) FROM screenshots
            WHERE ts >= ? AND ts < ?
            """,
            (hour_start.isoformat(), hour_end.isoformat()),
        )
        screenshot_count = cursor.fetchone()[0]

        # Check for events
        cursor.execute(
            """
            SELECT COUNT(*) FROM events
            WHERE start_ts >= ? AND start_ts < ?
            """,
            (hour_start.isoformat(), hour_end.isoformat()),
        )
        event_count = cursor.fetchone()[0]

        total_activity = screenshot_count + event_count
        has_activity = total_activity >= MIN_ACTIVITY_THRESHOLD

        if has_activity:
            logger.debug(
                f"Hour {hour_start.isoformat()}: {screenshot_count} screenshots, "
                f"{event_count} events"
            )

        return has_activity

    def trigger_backfill(
        self,
        hours: list[datetime] | None = None,
        notify: bool = True,
    ) -> BackfillResult:
        """
        Generate notes for missing hours.

        Args:
            hours: List of hours to backfill (uses find_missing_hours if not provided)
            notify: Whether to send macOS notifications

        Returns:
            BackfillResult with statistics
        """
        if hours is None:
            hours = self.find_missing_hours()

        if not hours:
            logger.info("No hours to backfill")
            return BackfillResult(
                hours_checked=self.lookback_hours,
                hours_missing=0,
                hours_backfilled=0,
                hours_failed=0,
                results=[],
            )

        if notify:
            send_backfill_notification(len(hours), "started")

        logger.info(f"Starting backfill for {len(hours)} hours")

        summarizer = self._get_summarizer()
        results = []
        successful = 0
        failed = 0

        # Process in chronological order
        for hour in sorted(hours):
            logger.info(f"Backfilling note for {hour.isoformat()}")

            try:
                result = summarizer.summarize_hour(hour, force=False)
                results.append(result)

                if result.success:
                    successful += 1
                    logger.info(f"Successfully backfilled {hour.isoformat()}")
                else:
                    failed += 1
                    logger.error(f"Failed to backfill {hour.isoformat()}: {result.error}")
                    if notify:
                        send_error_notification(
                            f"Backfill failed for {hour.strftime('%H:%M')}",
                            result.error,
                        )

            except Exception as e:
                failed += 1
                logger.error(f"Exception during backfill for {hour.isoformat()}: {e}")
                if notify:
                    send_error_notification(
                        f"Backfill error for {hour.strftime('%H:%M')}",
                        str(e),
                    )

        if notify and successful > 0:
            send_backfill_notification(successful, "completed")

        logger.info(f"Backfill complete: {successful} successful, {failed} failed")

        return BackfillResult(
            hours_checked=self.lookback_hours,
            hours_missing=len(hours),
            hours_backfilled=successful,
            hours_failed=failed,
            results=results,
        )

    def check_and_backfill(self, notify: bool = True) -> BackfillResult:
        """
        Convenience method to find and backfill missing hours.

        Args:
            notify: Whether to send macOS notifications

        Returns:
            BackfillResult with statistics
        """
        missing = self.find_missing_hours()
        if missing:
            return self.trigger_backfill(missing, notify=notify)
        return BackfillResult(
            hours_checked=self.lookback_hours,
            hours_missing=0,
            hours_backfilled=0,
            hours_failed=0,
            results=[],
        )


if __name__ == "__main__":
    import fire

    def check(lookback: int = DEFAULT_LOOKBACK_HOURS, db_path: str | None = None):
        """Check for missing hours without backfilling."""
        detector = BackfillDetector(db_path=db_path, lookback_hours=lookback)
        missing = detector.find_missing_hours()

        return {
            "lookback_hours": lookback,
            "missing_hours": len(missing),
            "hours": [h.isoformat() for h in missing],
        }

    def backfill(
        lookback: int = DEFAULT_LOOKBACK_HOURS,
        db_path: str | None = None,
        notify: bool = False,
    ):
        """Find and backfill missing hours."""
        import os

        api_key = os.environ.get("OPENAI_API_KEY")
        detector = BackfillDetector(db_path=db_path, api_key=api_key, lookback_hours=lookback)
        result = detector.check_and_backfill(notify=notify)

        return {
            "hours_checked": result.hours_checked,
            "hours_missing": result.hours_missing,
            "hours_backfilled": result.hours_backfilled,
            "hours_failed": result.hours_failed,
        }

    fire.Fire({"check": check, "backfill": backfill})
