"""
Text Buffer Storage for Trace

Stores compressed text buffers linked to time spans.
Buffers are transient and deleted daily after successful revision.

Source types:
- pdf_extract: Text extracted directly from PDF files
- ocr: Text extracted from screenshots via LLM OCR
- web_content: Text captured from web pages (if applicable)

P4-04: Text buffer storage
"""

import logging
import uuid
import zlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import tiktoken

from src.db.migrations import get_connection

logger = logging.getLogger(__name__)

# Default encoding for token estimation
DEFAULT_ENCODING = "cl100k_base"

# Compression level for zlib (1-9, higher = more compression but slower)
COMPRESSION_LEVEL = 6


@dataclass
class TextBuffer:
    """A stored text buffer with metadata."""

    text_id: str
    timestamp: datetime
    source_type: str  # 'pdf_extract', 'ocr', 'web_content'
    ref: str | None  # Reference (file path, screenshot ID, URL)
    text: str
    token_estimate: int
    event_id: str | None


@dataclass
class TextBufferSummary:
    """Summary of text buffers for a time range."""

    total_buffers: int
    total_tokens: int
    by_source: dict[str, int]  # source_type -> count
    time_range: tuple[datetime, datetime] | None


class TextBufferStorage:
    """
    Manages storage and retrieval of text buffers.

    Text buffers are:
    - Compressed using zlib for storage efficiency
    - Stored in SQLite with metadata
    - Linked to events via event_id
    - Deleted daily after successful revision
    """

    def __init__(self, db_path: Path | str | None = None):
        """
        Initialize text buffer storage.

        Args:
            db_path: Path to SQLite database (uses default if None)
        """
        self.db_path = Path(db_path) if db_path else None

        # Token encoder
        try:
            self._encoding = tiktoken.get_encoding(DEFAULT_ENCODING)
        except Exception:
            logger.warning("Failed to load tiktoken encoding")
            self._encoding = None

    def store(
        self,
        text: str,
        source_type: str,
        ref: str | None = None,
        event_id: str | None = None,
        timestamp: datetime | None = None,
    ) -> TextBuffer:
        """
        Store a text buffer.

        Args:
            text: The text content to store
            source_type: Type of source ('pdf_extract', 'ocr', 'web_content')
            ref: Reference identifier (file path, screenshot ID, etc.)
            event_id: Associated event ID
            timestamp: Buffer timestamp (defaults to now)

        Returns:
            TextBuffer with stored data

        Raises:
            ValueError: If source_type is invalid
        """
        valid_sources = ("pdf_extract", "ocr", "web_content")
        if source_type not in valid_sources:
            raise ValueError(f"source_type must be one of {valid_sources}, got '{source_type}'")

        if timestamp is None:
            timestamp = datetime.now()

        text_id = str(uuid.uuid4())
        token_estimate = self._count_tokens(text)
        compressed_text = self._compress(text)

        # Store in database
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO text_buffers (
                    text_id, ts, source_type, ref, compressed_text,
                    token_estimate, event_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    text_id,
                    timestamp.isoformat(),
                    source_type,
                    ref,
                    compressed_text,
                    token_estimate,
                    event_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        return TextBuffer(
            text_id=text_id,
            timestamp=timestamp,
            source_type=source_type,
            ref=ref,
            text=text,
            token_estimate=token_estimate,
            event_id=event_id,
        )

    def get(self, text_id: str) -> TextBuffer | None:
        """
        Retrieve a text buffer by ID.

        Args:
            text_id: The buffer ID

        Returns:
            TextBuffer or None if not found
        """
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT text_id, ts, source_type, ref, compressed_text,
                       token_estimate, event_id
                FROM text_buffers
                WHERE text_id = ?
                """,
                (text_id,),
            )
            row = cursor.fetchone()

            if row is None:
                return None

            text = self._decompress(row["compressed_text"])

            return TextBuffer(
                text_id=row["text_id"],
                timestamp=datetime.fromisoformat(row["ts"]),
                source_type=row["source_type"],
                ref=row["ref"],
                text=text,
                token_estimate=row["token_estimate"],
                event_id=row["event_id"],
            )
        finally:
            conn.close()

    def get_by_event(self, event_id: str) -> list[TextBuffer]:
        """
        Get all text buffers for an event.

        Args:
            event_id: The event ID

        Returns:
            List of TextBuffers for the event
        """
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT text_id, ts, source_type, ref, compressed_text,
                       token_estimate, event_id
                FROM text_buffers
                WHERE event_id = ?
                ORDER BY ts
                """,
                (event_id,),
            )
            rows = cursor.fetchall()

            buffers = []
            for row in rows:
                text = self._decompress(row["compressed_text"])
                buffers.append(
                    TextBuffer(
                        text_id=row["text_id"],
                        timestamp=datetime.fromisoformat(row["ts"]),
                        source_type=row["source_type"],
                        ref=row["ref"],
                        text=text,
                        token_estimate=row["token_estimate"],
                        event_id=row["event_id"],
                    )
                )
            return buffers
        finally:
            conn.close()

    def get_by_time_range(
        self,
        start_ts: datetime,
        end_ts: datetime,
        source_type: str | None = None,
        max_tokens: int | None = None,
    ) -> list[TextBuffer]:
        """
        Get text buffers within a time range.

        Args:
            start_ts: Start of time range
            end_ts: End of time range
            source_type: Filter by source type
            max_tokens: Maximum total tokens to return

        Returns:
            List of TextBuffers within the range
        """
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()

            if source_type:
                cursor.execute(
                    """
                    SELECT text_id, ts, source_type, ref, compressed_text,
                           token_estimate, event_id
                    FROM text_buffers
                    WHERE ts >= ? AND ts < ? AND source_type = ?
                    ORDER BY ts
                    """,
                    (start_ts.isoformat(), end_ts.isoformat(), source_type),
                )
            else:
                cursor.execute(
                    """
                    SELECT text_id, ts, source_type, ref, compressed_text,
                           token_estimate, event_id
                    FROM text_buffers
                    WHERE ts >= ? AND ts < ?
                    ORDER BY ts
                    """,
                    (start_ts.isoformat(), end_ts.isoformat()),
                )

            rows = cursor.fetchall()

            buffers = []
            total_tokens = 0

            for row in rows:
                token_estimate = row["token_estimate"]

                # Check token budget
                if max_tokens and total_tokens + token_estimate > max_tokens:
                    break

                text = self._decompress(row["compressed_text"])
                buffers.append(
                    TextBuffer(
                        text_id=row["text_id"],
                        timestamp=datetime.fromisoformat(row["ts"]),
                        source_type=row["source_type"],
                        ref=row["ref"],
                        text=text,
                        token_estimate=token_estimate,
                        event_id=row["event_id"],
                    )
                )
                total_tokens += token_estimate

            return buffers
        finally:
            conn.close()

    def get_summary(
        self,
        start_ts: datetime | None = None,
        end_ts: datetime | None = None,
    ) -> TextBufferSummary:
        """
        Get a summary of text buffers.

        Args:
            start_ts: Start of time range (optional)
            end_ts: End of time range (optional)

        Returns:
            TextBufferSummary with statistics
        """
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()

            # Build query based on time range
            if start_ts and end_ts:
                cursor.execute(
                    """
                    SELECT COUNT(*) as count, SUM(token_estimate) as tokens,
                           source_type, MIN(ts) as min_ts, MAX(ts) as max_ts
                    FROM text_buffers
                    WHERE ts >= ? AND ts < ?
                    GROUP BY source_type
                    """,
                    (start_ts.isoformat(), end_ts.isoformat()),
                )
            else:
                cursor.execute(
                    """
                    SELECT COUNT(*) as count, SUM(token_estimate) as tokens,
                           source_type, MIN(ts) as min_ts, MAX(ts) as max_ts
                    FROM text_buffers
                    GROUP BY source_type
                    """
                )

            rows = cursor.fetchall()

            total_buffers = 0
            total_tokens = 0
            by_source: dict[str, int] = {}
            min_ts = None
            max_ts = None

            for row in rows:
                count = row["count"]
                tokens = row["tokens"] or 0
                source_type = row["source_type"]

                total_buffers += count
                total_tokens += tokens
                by_source[source_type] = count

                row_min = row["min_ts"]
                row_max = row["max_ts"]

                if row_min and (min_ts is None or row_min < min_ts):
                    min_ts = row_min
                if row_max and (max_ts is None or row_max > max_ts):
                    max_ts = row_max

            time_range = None
            if min_ts and max_ts:
                time_range = (datetime.fromisoformat(min_ts), datetime.fromisoformat(max_ts))

            return TextBufferSummary(
                total_buffers=total_buffers,
                total_tokens=total_tokens,
                by_source=by_source,
                time_range=time_range,
            )
        finally:
            conn.close()

    def delete_by_date(self, date: datetime) -> int:
        """
        Delete all text buffers for a specific date.

        Args:
            date: The date to delete buffers for

        Returns:
            Number of buffers deleted
        """
        # Calculate date range
        start_ts = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_ts = start_ts.replace(hour=23, minute=59, second=59, microsecond=999999)

        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                DELETE FROM text_buffers
                WHERE ts >= ? AND ts <= ?
                """,
                (start_ts.isoformat(), end_ts.isoformat()),
            )
            deleted = cursor.rowcount
            conn.commit()
            return deleted
        finally:
            conn.close()

    def link_to_event(self, text_id: str, event_id: str) -> bool:
        """
        Link a text buffer to an event.

        Args:
            text_id: The buffer ID
            event_id: The event ID to link to

        Returns:
            True if updated successfully
        """
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE text_buffers
                SET event_id = ?
                WHERE text_id = ?
                """,
                (event_id, text_id),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def _compress(self, text: str) -> bytes:
        """Compress text using zlib."""
        return zlib.compress(text.encode("utf-8"), level=COMPRESSION_LEVEL)

    def _decompress(self, data: bytes) -> str:
        """Decompress text from zlib."""
        return zlib.decompress(data).decode("utf-8")

    def _count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        if self._encoding:
            return len(self._encoding.encode(text))
        return len(text) // 4


if __name__ == "__main__":
    import fire

    from src.db.migrations import init_database

    def store(
        text: str,
        source_type: str = "ocr",
        ref: str | None = None,
        event_id: str | None = None,
    ):
        """Store a text buffer."""
        init_database()
        storage = TextBufferStorage()
        buffer = storage.store(text, source_type, ref, event_id)
        return {
            "text_id": buffer.text_id,
            "timestamp": buffer.timestamp.isoformat(),
            "source_type": buffer.source_type,
            "token_estimate": buffer.token_estimate,
        }

    def get(text_id: str):
        """Get a text buffer by ID."""
        storage = TextBufferStorage()
        buffer = storage.get(text_id)
        if buffer is None:
            return {"error": "Buffer not found"}
        return {
            "text_id": buffer.text_id,
            "timestamp": buffer.timestamp.isoformat(),
            "source_type": buffer.source_type,
            "ref": buffer.ref,
            "token_estimate": buffer.token_estimate,
            "text_preview": buffer.text[:200] + "..." if len(buffer.text) > 200 else buffer.text,
        }

    def summary(start_date: str | None = None, end_date: str | None = None):
        """Get text buffer summary."""
        storage = TextBufferStorage()

        start_ts = datetime.fromisoformat(start_date) if start_date else None
        end_ts = datetime.fromisoformat(end_date) if end_date else None

        result = storage.get_summary(start_ts, end_ts)
        return {
            "total_buffers": result.total_buffers,
            "total_tokens": result.total_tokens,
            "by_source": result.by_source,
            "time_range": (
                (result.time_range[0].isoformat(), result.time_range[1].isoformat())
                if result.time_range
                else None
            ),
        }

    def delete_date(date: str):
        """Delete text buffers for a date."""
        storage = TextBufferStorage()
        dt = datetime.fromisoformat(date)
        count = storage.delete_by_date(dt)
        return {"deleted": count}

    fire.Fire(
        {
            "store": store,
            "get": get,
            "summary": summary,
            "delete-date": delete_date,
        }
    )
