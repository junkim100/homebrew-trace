"""
Event Span Tracking for Trace

Tracks activity spans (events) that represent continuous activity in the same
context. An event span is created when the user:
- Switches to a different application
- Switches to a different window within the same app
- Changes to a different browser URL

Events are stored in the database and linked to screenshots and other evidence.

P3-04: Event span tracking
"""

import json
import logging
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from src.capture.foreground import ForegroundApp
from src.db.migrations import get_connection

logger = logging.getLogger(__name__)


@dataclass
class EventSpan:
    """Represents a continuous activity span."""

    event_id: str
    start_ts: datetime
    end_ts: datetime
    app_id: str | None
    app_name: str | None
    window_title: str | None
    focused_monitor: int | None
    url: str | None = None
    page_title: str | None = None
    file_path: str | None = None
    location_text: str | None = None
    now_playing_json: str | None = None
    evidence_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "event_id": self.event_id,
            "start_ts": self.start_ts.isoformat(),
            "end_ts": self.end_ts.isoformat(),
            "app_id": self.app_id,
            "app_name": self.app_name,
            "window_title": self.window_title,
            "focused_monitor": self.focused_monitor,
            "url": self.url,
            "page_title": self.page_title,
            "file_path": self.file_path,
            "location_text": self.location_text,
            "now_playing_json": self.now_playing_json,
            "evidence_ids": self.evidence_ids,
        }


def _is_context_change(
    current: ForegroundApp,
    previous: ForegroundApp | None,
    current_url: str | None = None,
    previous_url: str | None = None,
) -> bool:
    """
    Determine if there's been a context change that should start a new event.

    A context change occurs when:
    - The bundle_id changes (different app)
    - The window_title changes significantly
    - The URL changes (for browsers)
    """
    if previous is None:
        return True

    # App change
    if current.bundle_id != previous.bundle_id:
        return True

    # Window title change (but not minor changes)
    if current.window_title != previous.window_title:
        # Don't trigger on None -> something or vice versa for same app
        if current.window_title and previous.window_title:
            return True

    # URL change for browser apps
    browser_bundle_ids = {
        "com.apple.Safari",
        "com.google.Chrome",
        "org.mozilla.firefox",
        "com.microsoft.Edge",
        "com.brave.Browser",
        "com.operasoftware.Opera",
    }

    if current.bundle_id in browser_bundle_ids:
        if current_url != previous_url:
            return True

    return False


class EventTracker:
    """
    Tracks and manages event spans based on foreground app changes.

    Events are automatically created and closed as the user switches between
    applications and windows.
    """

    def __init__(self, db_path: str | None = None):
        """
        Initialize the event tracker.

        Args:
            db_path: Path to the SQLite database (uses default if None)
        """
        self.db_path = db_path
        self._current_event: EventSpan | None = None
        self._previous_foreground: ForegroundApp | None = None
        self._previous_url: str | None = None

    def update(
        self,
        foreground: ForegroundApp,
        url: str | None = None,
        page_title: str | None = None,
        now_playing_json: str | None = None,
        location_text: str | None = None,
    ) -> EventSpan | None:
        """
        Update the event tracker with new foreground information.

        If a context change is detected, the current event is closed and a new
        one is started.

        Args:
            foreground: Current foreground app information
            url: Current URL (for browser apps)
            page_title: Page title (for browser apps)
            now_playing_json: JSON string of now playing info
            location_text: Current location as text

        Returns:
            The newly closed event if a context change occurred, otherwise None
        """
        timestamp = foreground.timestamp

        context_changed = _is_context_change(
            foreground, self._previous_foreground, url, self._previous_url
        )

        closed_event = None

        if context_changed:
            # Close the current event if one exists
            if self._current_event is not None:
                self._current_event.end_ts = timestamp
                closed_event = self._current_event
                self._save_event(closed_event)

            # Start a new event
            self._current_event = EventSpan(
                event_id=str(uuid.uuid4()),
                start_ts=timestamp,
                end_ts=timestamp,
                app_id=foreground.bundle_id,
                app_name=foreground.app_name,
                window_title=foreground.window_title,
                focused_monitor=foreground.focused_monitor,
                url=url,
                page_title=page_title,
                now_playing_json=now_playing_json,
                location_text=location_text,
            )
        else:
            # Update the current event's end time and metadata
            if self._current_event is not None:
                self._current_event.end_ts = timestamp
                # Update window title if it changed
                if foreground.window_title:
                    self._current_event.window_title = foreground.window_title
                if now_playing_json:
                    self._current_event.now_playing_json = now_playing_json
                if location_text:
                    self._current_event.location_text = location_text

        # Store for next comparison
        self._previous_foreground = foreground
        self._previous_url = url

        return closed_event

    def add_evidence(self, evidence_id: str) -> None:
        """
        Add an evidence ID (screenshot, text buffer) to the current event.

        Args:
            evidence_id: ID of the evidence to link
        """
        if self._current_event is not None:
            self._current_event.evidence_ids.append(evidence_id)

    def get_current_event(self) -> EventSpan | None:
        """Get the current active event."""
        return self._current_event

    def close_current_event(self, end_ts: datetime | None = None) -> EventSpan | None:
        """
        Force close the current event.

        Args:
            end_ts: End timestamp (defaults to now)

        Returns:
            The closed event, or None if no event was active
        """
        if self._current_event is None:
            return None

        if end_ts is None:
            end_ts = datetime.now()

        self._current_event.end_ts = end_ts
        closed_event = self._current_event
        self._save_event(closed_event)

        self._current_event = None
        self._previous_foreground = None
        self._previous_url = None

        return closed_event

    def _save_event(self, event: EventSpan) -> None:
        """Save an event to the database."""
        try:
            conn = get_connection(self.db_path)
            try:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO events (
                        event_id, start_ts, end_ts, app_id, app_name,
                        window_title, focused_monitor, url, page_title,
                        file_path, location_text, now_playing_json, evidence_ids
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.event_id,
                        event.start_ts.isoformat(),
                        event.end_ts.isoformat(),
                        event.app_id,
                        event.app_name,
                        event.window_title,
                        event.focused_monitor,
                        event.url,
                        event.page_title,
                        event.file_path,
                        event.location_text,
                        event.now_playing_json,
                        json.dumps(event.evidence_ids) if event.evidence_ids else None,
                    ),
                )
                conn.commit()
                logger.debug(f"Saved event {event.event_id}")
            finally:
                conn.close()
        except sqlite3.Error as e:
            logger.error(f"Failed to save event: {e}")


def get_events_in_range(
    start_ts: datetime, end_ts: datetime, db_path: str | None = None
) -> list[EventSpan]:
    """
    Get all events within a time range.

    Args:
        start_ts: Start of the time range
        end_ts: End of the time range
        db_path: Path to the database

    Returns:
        List of EventSpan objects
    """
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT event_id, start_ts, end_ts, app_id, app_name,
                   window_title, focused_monitor, url, page_title,
                   file_path, location_text, now_playing_json, evidence_ids
            FROM events
            WHERE end_ts >= ? AND start_ts <= ?
            ORDER BY start_ts
            """,
            (start_ts.isoformat(), end_ts.isoformat()),
        )

        events = []
        for row in cursor.fetchall():
            evidence_ids = json.loads(row["evidence_ids"]) if row["evidence_ids"] else []
            events.append(
                EventSpan(
                    event_id=row["event_id"],
                    start_ts=datetime.fromisoformat(row["start_ts"]),
                    end_ts=datetime.fromisoformat(row["end_ts"]),
                    app_id=row["app_id"],
                    app_name=row["app_name"],
                    window_title=row["window_title"],
                    focused_monitor=row["focused_monitor"],
                    url=row["url"],
                    page_title=row["page_title"],
                    file_path=row["file_path"],
                    location_text=row["location_text"],
                    now_playing_json=row["now_playing_json"],
                    evidence_ids=evidence_ids,
                )
            )
        return events
    finally:
        conn.close()


if __name__ == "__main__":
    from datetime import timedelta

    import fire

    from src.capture.foreground import capture_foreground_app

    def track(interval: float = 1.0, duration: int = 60):
        """Track events for a duration."""
        import time

        tracker = EventTracker()
        events_created = []
        end_time = datetime.now() + timedelta(seconds=duration)

        print(f"Tracking events for {duration} seconds...")

        while datetime.now() < end_time:
            foreground = capture_foreground_app()
            closed_event = tracker.update(foreground)

            if closed_event:
                events_created.append(closed_event.to_dict())
                print(f"Event closed: {closed_event.app_name} - {closed_event.window_title}")

            current = tracker.get_current_event()
            if current:
                print(f"Current: {current.app_name} - {current.window_title}")

            time.sleep(interval)

        # Close final event
        final_event = tracker.close_current_event()
        if final_event:
            events_created.append(final_event.to_dict())

        return {"events_created": len(events_created), "events": events_created}

    def list_events(hours: int = 1):
        """List events from the past N hours."""
        end_ts = datetime.now()
        start_ts = end_ts - timedelta(hours=hours)
        events = get_events_in_range(start_ts, end_ts)
        return [e.to_dict() for e in events]

    fire.Fire(
        {
            "track": track,
            "list": list_events,
        }
    )
