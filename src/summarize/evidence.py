"""
Evidence Aggregation for Hourly Summarization

Builds a comprehensive evidence package for the LLM summarizer:
- Timeline of events for the hour
- Selected keyframe screenshots
- Text snippets from buffers (within token budget)
- Now playing timeline
- Location information

P5-03: Evidence aggregation for hour
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import tiktoken

from src.core.paths import DB_PATH
from src.db.migrations import get_connection
from src.summarize.keyframes import SelectedKeyframe

logger = logging.getLogger(__name__)

# Token budget for text evidence
DEFAULT_MAX_TEXT_TOKENS = 4000
DEFAULT_MAX_SNIPPET_TOKENS = 500  # Max tokens per individual snippet

# Encoding for token counting
DEFAULT_ENCODING = "cl100k_base"


@dataclass
class EventSummary:
    """Summary of an activity event."""

    event_id: str
    start_ts: datetime
    end_ts: datetime
    duration_seconds: int
    app_id: str | None
    app_name: str | None
    window_title: str | None
    url: str | None
    page_title: str | None
    file_path: str | None
    location_text: str | None
    now_playing: dict | None  # {track, artist, album, app}


@dataclass
class TextSnippet:
    """A text snippet from buffers for evidence."""

    text_id: str
    timestamp: datetime
    source_type: str
    ref: str | None
    text: str
    token_count: int
    event_id: str | None


@dataclass
class NowPlayingSpan:
    """A span of now playing activity."""

    start_ts: datetime
    end_ts: datetime
    track: str
    artist: str
    album: str | None
    app: str


@dataclass
class HourlyEvidence:
    """Complete evidence package for hourly summarization."""

    # Time range
    hour_start: datetime
    hour_end: datetime

    # Events timeline
    events: list[EventSummary] = field(default_factory=list)

    # Selected keyframes
    keyframes: list[SelectedKeyframe] = field(default_factory=list)

    # Text snippets (within token budget)
    text_snippets: list[TextSnippet] = field(default_factory=list)
    total_text_tokens: int = 0

    # Now playing timeline
    now_playing_spans: list[NowPlayingSpan] = field(default_factory=list)

    # Location summary
    locations: list[str] = field(default_factory=list)

    # Statistics
    total_screenshots: int = 0
    total_events: int = 0
    total_text_buffers: int = 0

    # App usage summary
    app_durations: dict[str, int] = field(default_factory=dict)  # app_name -> seconds

    # Category breakdown
    category_durations: dict[str, int] = field(default_factory=dict)  # category -> seconds


class EvidenceAggregator:
    """
    Aggregates evidence from various sources for hourly summarization.

    Pulls data from the database and builds a structured evidence package
    within specified token budgets.
    """

    def __init__(
        self,
        db_path: Path | str | None = None,
        max_text_tokens: int = DEFAULT_MAX_TEXT_TOKENS,
        max_snippet_tokens: int = DEFAULT_MAX_SNIPPET_TOKENS,
    ):
        """
        Initialize the evidence aggregator.

        Args:
            db_path: Path to SQLite database
            max_text_tokens: Maximum total tokens for text evidence
            max_snippet_tokens: Maximum tokens per individual snippet
        """
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.max_text_tokens = max_text_tokens
        self.max_snippet_tokens = max_snippet_tokens

        try:
            self._encoding = tiktoken.get_encoding(DEFAULT_ENCODING)
        except Exception:
            logger.warning("Failed to load tiktoken encoding")
            self._encoding = None

    def aggregate(
        self,
        hour_start: datetime,
        keyframes: list[SelectedKeyframe] | None = None,
    ) -> HourlyEvidence:
        """
        Aggregate all evidence for an hour.

        Args:
            hour_start: Start of the hour (will be normalized to hour boundary)
            keyframes: Pre-selected keyframes (if already computed)

        Returns:
            HourlyEvidence with all aggregated data
        """
        # Normalize to hour boundaries
        hour_start = hour_start.replace(minute=0, second=0, microsecond=0)
        hour_end = hour_start + timedelta(hours=1)

        evidence = HourlyEvidence(
            hour_start=hour_start,
            hour_end=hour_end,
        )

        conn = get_connection(self.db_path)
        try:
            # Get events
            evidence.events = self._get_events(conn, hour_start, hour_end)
            evidence.total_events = len(evidence.events)

            # Calculate app durations
            evidence.app_durations = self._calculate_app_durations(evidence.events)

            # Get screenshot count
            evidence.total_screenshots = self._count_screenshots(conn, hour_start, hour_end)

            # Get text buffers count
            evidence.total_text_buffers = self._count_text_buffers(conn, hour_start, hour_end)

            # Get text snippets within budget
            evidence.text_snippets = self._get_text_snippets(conn, hour_start, hour_end)
            evidence.total_text_tokens = sum(s.token_count for s in evidence.text_snippets)

            # Get now playing timeline
            evidence.now_playing_spans = self._get_now_playing(conn, hour_start, hour_end)

            # Get locations
            evidence.locations = self._get_locations(evidence.events)

            # Add provided keyframes
            if keyframes:
                evidence.keyframes = keyframes

        finally:
            conn.close()

        return evidence

    def _get_events(
        self,
        conn,
        start_ts: datetime,
        end_ts: datetime,
    ) -> list[EventSummary]:
        """Get events within the time range."""
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT event_id, start_ts, end_ts, app_id, app_name, window_title,
                   url, page_title, file_path, location_text, now_playing_json
            FROM events
            WHERE start_ts < ? AND end_ts > ?
            ORDER BY start_ts
            """,
            (end_ts.isoformat(), start_ts.isoformat()),
        )

        events = []
        for row in cursor.fetchall():
            try:
                event_start = datetime.fromisoformat(row["start_ts"])
                event_end = datetime.fromisoformat(row["end_ts"])
            except (ValueError, TypeError):
                continue

            # Clip to hour boundaries
            clipped_start = max(event_start, start_ts)
            clipped_end = min(event_end, end_ts)
            duration = int((clipped_end - clipped_start).total_seconds())

            if duration <= 0:
                continue

            # Parse now playing JSON
            now_playing = None
            if row["now_playing_json"]:
                try:
                    import json

                    now_playing = json.loads(row["now_playing_json"])
                except (json.JSONDecodeError, TypeError):
                    pass

            events.append(
                EventSummary(
                    event_id=row["event_id"],
                    start_ts=clipped_start,
                    end_ts=clipped_end,
                    duration_seconds=duration,
                    app_id=row["app_id"],
                    app_name=row["app_name"],
                    window_title=row["window_title"],
                    url=row["url"],
                    page_title=row["page_title"],
                    file_path=row["file_path"],
                    location_text=row["location_text"],
                    now_playing=now_playing,
                )
            )

        return events

    def _calculate_app_durations(self, events: list[EventSummary]) -> dict[str, int]:
        """Calculate total duration per app."""
        durations: dict[str, int] = {}
        for event in events:
            app_name = event.app_name or event.app_id or "Unknown"
            durations[app_name] = durations.get(app_name, 0) + event.duration_seconds
        return durations

    def _count_screenshots(
        self,
        conn,
        start_ts: datetime,
        end_ts: datetime,
    ) -> int:
        """Count screenshots in time range."""
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT COUNT(*) as count
            FROM screenshots
            WHERE ts >= ? AND ts < ?
            """,
            (start_ts.isoformat(), end_ts.isoformat()),
        )
        row = cursor.fetchone()
        return row["count"] if row else 0

    def _count_text_buffers(
        self,
        conn,
        start_ts: datetime,
        end_ts: datetime,
    ) -> int:
        """Count text buffers in time range."""
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT COUNT(*) as count
            FROM text_buffers
            WHERE ts >= ? AND ts < ?
            """,
            (start_ts.isoformat(), end_ts.isoformat()),
        )
        row = cursor.fetchone()
        return row["count"] if row else 0

    def _get_text_snippets(
        self,
        conn,
        start_ts: datetime,
        end_ts: datetime,
    ) -> list[TextSnippet]:
        """Get text snippets within token budget."""
        import zlib

        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT text_id, ts, source_type, ref, compressed_text, token_estimate, event_id
            FROM text_buffers
            WHERE ts >= ? AND ts < ?
            ORDER BY ts
            """,
            (start_ts.isoformat(), end_ts.isoformat()),
        )

        snippets = []
        total_tokens = 0

        for row in cursor.fetchall():
            token_estimate = row["token_estimate"]

            # Check if we have budget
            if total_tokens + token_estimate > self.max_text_tokens:
                # Try to fit a truncated version
                remaining_budget = self.max_text_tokens - total_tokens
                if remaining_budget < 100:
                    break

            try:
                text = zlib.decompress(row["compressed_text"]).decode("utf-8")
            except Exception as e:
                logger.warning(f"Failed to decompress text buffer: {e}")
                continue

            # Truncate if needed
            actual_tokens = self._count_tokens(text)
            if actual_tokens > self.max_snippet_tokens:
                text = self._truncate_to_tokens(text, self.max_snippet_tokens)
                actual_tokens = self._count_tokens(text)

            if total_tokens + actual_tokens > self.max_text_tokens:
                remaining = self.max_text_tokens - total_tokens
                text = self._truncate_to_tokens(text, remaining)
                actual_tokens = self._count_tokens(text)

            try:
                timestamp = datetime.fromisoformat(row["ts"])
            except (ValueError, TypeError):
                continue

            snippets.append(
                TextSnippet(
                    text_id=row["text_id"],
                    timestamp=timestamp,
                    source_type=row["source_type"],
                    ref=row["ref"],
                    text=text,
                    token_count=actual_tokens,
                    event_id=row["event_id"],
                )
            )

            total_tokens += actual_tokens

            if total_tokens >= self.max_text_tokens:
                break

        return snippets

    def _get_now_playing(
        self,
        conn,
        start_ts: datetime,
        end_ts: datetime,
    ) -> list[NowPlayingSpan]:
        """Extract now playing spans from events."""
        import json

        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT start_ts, end_ts, now_playing_json
            FROM events
            WHERE start_ts < ? AND end_ts > ? AND now_playing_json IS NOT NULL
            ORDER BY start_ts
            """,
            (end_ts.isoformat(), start_ts.isoformat()),
        )

        spans = []
        current_span: NowPlayingSpan | None = None

        for row in cursor.fetchall():
            try:
                event_start = datetime.fromisoformat(row["start_ts"])
                event_end = datetime.fromisoformat(row["end_ts"])
                np_data = json.loads(row["now_playing_json"])
            except (ValueError, TypeError, json.JSONDecodeError):
                continue

            track = np_data.get("track", "")
            artist = np_data.get("artist", "")
            album = np_data.get("album")
            app = np_data.get("app", "")

            if not track or not artist:
                continue

            # Clip to hour boundaries
            clipped_start = max(event_start, start_ts)
            clipped_end = min(event_end, end_ts)

            # Check if this continues the current span
            if current_span and current_span.track == track and current_span.artist == artist:
                # Extend the span
                current_span.end_ts = clipped_end
            else:
                # Start a new span
                if current_span:
                    spans.append(current_span)
                current_span = NowPlayingSpan(
                    start_ts=clipped_start,
                    end_ts=clipped_end,
                    track=track,
                    artist=artist,
                    album=album,
                    app=app,
                )

        if current_span:
            spans.append(current_span)

        return spans

    def _get_locations(self, events: list[EventSummary]) -> list[str]:
        """Extract unique locations from events."""
        locations = set()
        for event in events:
            if event.location_text:
                locations.add(event.location_text)
        return sorted(locations)

    def _count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        if self._encoding:
            return len(self._encoding.encode(text))
        return len(text) // 4

    def _truncate_to_tokens(self, text: str, max_tokens: int) -> str:
        """Truncate text to fit within token budget."""
        if self._encoding:
            tokens = self._encoding.encode(text)
            if len(tokens) <= max_tokens:
                return text
            truncated_tokens = tokens[:max_tokens]
            return self._encoding.decode(truncated_tokens) + "..."
        else:
            # Fallback: estimate 4 chars per token
            max_chars = max_tokens * 4
            if len(text) <= max_chars:
                return text
            return text[:max_chars] + "..."

    def build_timeline_text(self, evidence: HourlyEvidence) -> str:
        """
        Build a text representation of the events timeline.

        Args:
            evidence: HourlyEvidence to render

        Returns:
            Formatted timeline text for LLM context
        """
        lines = []
        lines.append(
            f"## Activity Timeline: {evidence.hour_start.strftime('%Y-%m-%d %H:00')} - {evidence.hour_end.strftime('%H:00')}"
        )
        lines.append("")

        for event in evidence.events:
            time_str = event.start_ts.strftime("%H:%M:%S")
            duration_min = event.duration_seconds // 60
            duration_sec = event.duration_seconds % 60

            app_str = event.app_name or event.app_id or "Unknown"
            line = f"- [{time_str}] ({duration_min}m{duration_sec}s) {app_str}"

            if event.window_title:
                line += f" - {event.window_title[:60]}"
            if event.url:
                line += f" | URL: {event.url[:80]}"
            if event.file_path:
                line += f" | File: {event.file_path}"

            lines.append(line)

        # Add now playing summary
        if evidence.now_playing_spans:
            lines.append("")
            lines.append("## Media Playing")
            for span in evidence.now_playing_spans:
                duration = int((span.end_ts - span.start_ts).total_seconds())
                lines.append(f"- {span.artist} - {span.track} ({duration}s via {span.app})")

        # Add location if available
        if evidence.locations:
            lines.append("")
            lines.append(f"## Location: {', '.join(evidence.locations)}")

        # Add app usage summary
        if evidence.app_durations:
            lines.append("")
            lines.append("## App Usage Summary")
            sorted_apps = sorted(evidence.app_durations.items(), key=lambda x: x[1], reverse=True)
            for app, seconds in sorted_apps[:10]:
                minutes = seconds // 60
                if minutes > 0:
                    lines.append(f"- {app}: {minutes}m")

        return "\n".join(lines)


if __name__ == "__main__":
    import fire

    def aggregate(hour: str | None = None, db_path: str | None = None):
        """
        Aggregate evidence for an hour.

        Args:
            hour: Hour in ISO format (e.g., '2025-01-15T14:00:00'), defaults to previous hour
            db_path: Path to database
        """
        if hour:
            hour_start = datetime.fromisoformat(hour)
        else:
            now = datetime.now()
            hour_start = (now - timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)

        aggregator = EvidenceAggregator(db_path=db_path)
        evidence = aggregator.aggregate(hour_start)

        return {
            "hour_start": evidence.hour_start.isoformat(),
            "hour_end": evidence.hour_end.isoformat(),
            "total_events": evidence.total_events,
            "total_screenshots": evidence.total_screenshots,
            "total_text_buffers": evidence.total_text_buffers,
            "total_text_tokens": evidence.total_text_tokens,
            "text_snippets": len(evidence.text_snippets),
            "now_playing_spans": len(evidence.now_playing_spans),
            "locations": evidence.locations,
            "app_durations": evidence.app_durations,
        }

    def timeline(hour: str | None = None, db_path: str | None = None):
        """Print the timeline text for an hour."""
        if hour:
            hour_start = datetime.fromisoformat(hour)
        else:
            now = datetime.now()
            hour_start = (now - timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)

        aggregator = EvidenceAggregator(db_path=db_path)
        evidence = aggregator.aggregate(hour_start)
        print(aggregator.build_timeline_text(evidence))

    fire.Fire({"aggregate": aggregate, "timeline": timeline})
