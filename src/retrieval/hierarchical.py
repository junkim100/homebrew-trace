"""
Hierarchical Search for Trace

Implements two-stage retrieval:
1. Search daily summaries first (coarse filter)
2. Drill down to hourly notes for matched days (fine details)

This approach is more efficient and provides better context than
flat search across all notes.
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from src.core.paths import DB_PATH
from src.db.migrations import get_connection
from src.retrieval.search import NoteMatch, VectorSearcher
from src.retrieval.time import TimeFilter

logger = logging.getLogger(__name__)

# Default limits for hierarchical search
DEFAULT_MAX_DAYS = 5
DEFAULT_MAX_HOURS_PER_DAY = 3
DEFAULT_TOTAL_MAX_NOTES = 15


@dataclass
class DayMatch:
    """A matched daily summary with its hourly drill-downs."""

    date: date
    daily_note: NoteMatch | None  # The daily summary (index.md)
    hourly_notes: list[NoteMatch] = field(default_factory=list)  # Relevant hourly notes
    relevance_score: float = 0.0  # Combined relevance score

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "date": self.date.isoformat(),
            "daily_note": self.daily_note.to_dict() if self.daily_note else None,
            "hourly_notes": [n.to_dict() for n in self.hourly_notes],
            "relevance_score": self.relevance_score,
            "total_notes": 1 + len(self.hourly_notes)
            if self.daily_note
            else len(self.hourly_notes),
        }


@dataclass
class HierarchicalSearchResult:
    """Result of a hierarchical search operation."""

    query: str
    day_matches: list[DayMatch]
    time_filter: TimeFilter | None
    total_daily_searched: int
    total_hourly_searched: int
    search_time_ms: float

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "query": self.query,
            "day_matches": [d.to_dict() for d in self.day_matches],
            "time_filter": self.time_filter.to_dict() if self.time_filter else None,
            "total_daily_searched": self.total_daily_searched,
            "total_hourly_searched": self.total_hourly_searched,
            "search_time_ms": self.search_time_ms,
        }

    def get_all_notes(self) -> list[NoteMatch]:
        """Get all notes in a flat list (daily first, then hourly by day)."""
        notes = []
        for day_match in self.day_matches:
            if day_match.daily_note:
                notes.append(day_match.daily_note)
            notes.extend(day_match.hourly_notes)
        return notes

    def get_context_for_llm(self, max_notes: int = 10) -> list[NoteMatch]:
        """
        Get notes optimized for LLM context.

        Returns daily summaries first, then hourly details from the most
        relevant days. This gives the LLM both broad and detailed context.
        """
        notes = []
        remaining = max_notes

        # First pass: add daily summaries
        for day_match in self.day_matches:
            if remaining <= 0:
                break
            if day_match.daily_note:
                notes.append(day_match.daily_note)
                remaining -= 1

        # Second pass: add hourly details from most relevant days
        for day_match in self.day_matches:
            if remaining <= 0:
                break
            for hourly in day_match.hourly_notes:
                if remaining <= 0:
                    break
                notes.append(hourly)
                remaining -= 1

        return notes


class HierarchicalSearcher:
    """
    Two-stage hierarchical search engine.

    Stage 1: Search daily summaries to find relevant days
    Stage 2: For each matched day, search hourly notes for details

    This is more efficient than flat search because:
    - Daily summaries capture the essence of each day (fewer docs to search)
    - Hourly drill-down only happens for relevant days
    - Provides natural context hierarchy for answer synthesis
    """

    def __init__(
        self,
        db_path: Path | str | None = None,
        api_key: str | None = None,
    ):
        """
        Initialize the hierarchical searcher.

        Args:
            db_path: Path to SQLite database
            api_key: OpenAI API key for embeddings
        """
        self.db_path = Path(db_path) if db_path else DB_PATH
        self._api_key = api_key
        self._vector_searcher = VectorSearcher(db_path=self.db_path, api_key=api_key)

    def search(
        self,
        query: str,
        time_filter: TimeFilter | None = None,
        max_days: int = DEFAULT_MAX_DAYS,
        max_hours_per_day: int = DEFAULT_MAX_HOURS_PER_DAY,
        include_hourly_drilldown: bool = True,
    ) -> HierarchicalSearchResult:
        """
        Perform hierarchical search.

        Args:
            query: Search query
            time_filter: Optional time filter
            max_days: Maximum number of days to return
            max_hours_per_day: Maximum hourly notes per day
            include_hourly_drilldown: Whether to drill down into hourly notes

        Returns:
            HierarchicalSearchResult with matched days and notes
        """
        import time

        start_time = time.time()

        # Stage 1: Search daily summaries
        daily_matches = self._search_daily_notes(query, time_filter, limit=max_days * 2)

        # Group matches by date and filter to top days
        day_matches = []
        seen_dates = set()
        total_hourly_searched = 0

        for daily_note in daily_matches:
            if len(day_matches) >= max_days:
                break

            # Extract date from note
            note_date = self._extract_date_from_note(daily_note)
            if note_date is None or note_date in seen_dates:
                continue

            seen_dates.add(note_date)

            # Stage 2: Drill down to hourly notes for this day
            hourly_notes = []
            if include_hourly_drilldown:
                hourly_notes = self._search_hourly_notes_for_day(
                    query, note_date, time_filter, limit=max_hours_per_day
                )
                total_hourly_searched += len(hourly_notes)

            # Calculate combined relevance score
            relevance = daily_note.score
            if hourly_notes:
                # Boost relevance if hourly notes also match well
                avg_hourly_score = sum(h.score for h in hourly_notes) / len(hourly_notes)
                relevance = (relevance * 0.6) + (avg_hourly_score * 0.4)

            day_matches.append(
                DayMatch(
                    date=note_date,
                    daily_note=daily_note,
                    hourly_notes=hourly_notes,
                    relevance_score=relevance,
                )
            )

        # If no daily matches but we have a time filter, try direct hourly search
        if not day_matches and time_filter:
            day_matches = self._fallback_hourly_search(
                query, time_filter, max_days, max_hours_per_day
            )
            for dm in day_matches:
                total_hourly_searched += len(dm.hourly_notes)

        # Sort by relevance
        day_matches.sort(key=lambda d: d.relevance_score, reverse=True)

        search_time = (time.time() - start_time) * 1000

        return HierarchicalSearchResult(
            query=query,
            day_matches=day_matches[:max_days],
            time_filter=time_filter,
            total_daily_searched=len(daily_matches),
            total_hourly_searched=total_hourly_searched,
            search_time_ms=search_time,
        )

    def _search_daily_notes(
        self,
        query: str,
        time_filter: TimeFilter | None,
        limit: int,
    ) -> list[NoteMatch]:
        """Search only daily summary notes."""
        conn = get_connection(self.db_path)
        try:
            # Get embedding for query
            query_embedding = self._vector_searcher._embedding_computer.compute_for_query(query)
            if query_embedding is None:
                return []

            # Build time filter SQL
            time_sql = ""
            time_params = []
            if time_filter:
                time_sql = "AND n.start_ts >= ? AND n.start_ts <= ?"
                time_params = [time_filter.start.isoformat(), time_filter.end.isoformat()]

            # Search daily notes only
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT n.note_id, n.note_type, n.start_ts, n.end_ts, n.file_path,
                       n.json_payload, e.embedding,
                       vec_distance_cosine(e.embedding, ?) as distance
                FROM notes n
                JOIN embeddings e ON n.note_id = e.note_id
                WHERE n.note_type = 'day'
                {time_sql}
                ORDER BY distance ASC
                LIMIT ?
                """,
                [query_embedding, *time_params, limit],
            )

            matches = []
            for row in cursor.fetchall():
                match = self._row_to_note_match(row)
                if match:
                    matches.append(match)

            return matches

        except Exception as e:
            logger.error(f"Daily notes search failed: {e}")
            return []
        finally:
            conn.close()

    def _search_hourly_notes_for_day(
        self,
        query: str,
        day: date,
        time_filter: TimeFilter | None,
        limit: int,
    ) -> list[NoteMatch]:
        """Search hourly notes for a specific day."""
        conn = get_connection(self.db_path)
        try:
            # Get embedding for query
            query_embedding = self._vector_searcher._embedding_computer.compute_for_query(query)
            if query_embedding is None:
                return []

            # Build day filter (restrict to this specific day)
            day_start = datetime.combine(day, datetime.min.time())
            day_end = datetime.combine(day, datetime.max.time())

            # Apply time filter if it's more restrictive
            if time_filter:
                day_start = max(day_start, time_filter.start)
                day_end = min(day_end, time_filter.end)

            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT n.note_id, n.note_type, n.start_ts, n.end_ts, n.file_path,
                       n.json_payload, e.embedding,
                       vec_distance_cosine(e.embedding, ?) as distance
                FROM notes n
                JOIN embeddings e ON n.note_id = e.note_id
                WHERE n.note_type = 'hour'
                AND n.start_ts >= ? AND n.start_ts <= ?
                ORDER BY distance ASC
                LIMIT ?
                """,
                [query_embedding, day_start.isoformat(), day_end.isoformat(), limit],
            )

            matches = []
            for row in cursor.fetchall():
                match = self._row_to_note_match(row)
                if match:
                    matches.append(match)

            return matches

        except Exception as e:
            logger.error(f"Hourly notes search failed for {day}: {e}")
            return []
        finally:
            conn.close()

    def _fallback_hourly_search(
        self,
        query: str,
        time_filter: TimeFilter,
        max_days: int,
        max_hours_per_day: int,
    ) -> list[DayMatch]:
        """
        Fallback to direct hourly search when no daily notes exist.

        This handles cases where daily revision hasn't run yet.
        """
        conn = get_connection(self.db_path)
        try:
            query_embedding = self._vector_searcher._embedding_computer.compute_for_query(query)
            if query_embedding is None:
                return []

            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT n.note_id, n.note_type, n.start_ts, n.end_ts, n.file_path,
                       n.json_payload, e.embedding,
                       vec_distance_cosine(e.embedding, ?) as distance
                FROM notes n
                JOIN embeddings e ON n.note_id = e.note_id
                WHERE n.note_type = 'hour'
                AND n.start_ts >= ? AND n.start_ts <= ?
                ORDER BY distance ASC
                LIMIT ?
                """,
                [
                    query_embedding,
                    time_filter.start.isoformat(),
                    time_filter.end.isoformat(),
                    max_days * max_hours_per_day,
                ],
            )

            # Group hourly notes by date
            notes_by_date: dict[date, list[NoteMatch]] = {}
            for row in cursor.fetchall():
                match = self._row_to_note_match(row)
                if match:
                    note_date = self._extract_date_from_note(match)
                    if note_date:
                        if note_date not in notes_by_date:
                            notes_by_date[note_date] = []
                        notes_by_date[note_date].append(match)

            # Build DayMatch objects
            day_matches = []
            for note_date, hourly_notes in notes_by_date.items():
                # Limit hourly notes per day
                hourly_notes = hourly_notes[:max_hours_per_day]

                # Calculate average relevance
                avg_score = (
                    sum(h.score for h in hourly_notes) / len(hourly_notes) if hourly_notes else 0
                )

                day_matches.append(
                    DayMatch(
                        date=note_date,
                        daily_note=None,  # No daily summary available
                        hourly_notes=hourly_notes,
                        relevance_score=avg_score,
                    )
                )

            return day_matches[:max_days]

        except Exception as e:
            logger.error(f"Fallback hourly search failed: {e}")
            return []
        finally:
            conn.close()

    def _row_to_note_match(self, row) -> NoteMatch | None:
        """Convert a database row to NoteMatch."""
        try:
            import json

            # Parse JSON payload
            payload = {}
            if row["json_payload"]:
                try:
                    payload = json.loads(row["json_payload"])
                except json.JSONDecodeError:
                    pass

            # Calculate score (convert distance to similarity)
            distance = row["distance"] if "distance" in row.keys() else 1.0
            score = 1.0 - min(distance, 1.0)  # Convert distance to similarity

            return NoteMatch(
                note_id=row["note_id"],
                note_type=row["note_type"],
                start_ts=datetime.fromisoformat(row["start_ts"]),
                end_ts=datetime.fromisoformat(row["end_ts"]),
                file_path=Path(row["file_path"]) if row["file_path"] else None,
                score=score,
                summary=payload.get("summary", ""),
                entities=payload.get("entities", []),
                activities=payload.get("activities", []),
            )
        except Exception as e:
            logger.warning(f"Failed to parse note match: {e}")
            return None

    def _extract_date_from_note(self, note: NoteMatch) -> date | None:
        """Extract the date from a note."""
        try:
            return note.start_ts.date()
        except Exception:
            return None

    def get_day_context(
        self,
        day: date,
        include_hourly: bool = True,
    ) -> DayMatch | None:
        """
        Get full context for a specific day.

        Args:
            day: The date to get context for
            include_hourly: Whether to include hourly notes

        Returns:
            DayMatch with daily and hourly notes, or None if not found
        """
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()

            day_start = datetime.combine(day, datetime.min.time())
            day_end = datetime.combine(day, datetime.max.time())

            # Get daily note
            cursor.execute(
                """
                SELECT note_id, note_type, start_ts, end_ts, file_path, json_payload
                FROM notes
                WHERE note_type = 'day'
                AND start_ts >= ? AND start_ts <= ?
                LIMIT 1
                """,
                [day_start.isoformat(), day_end.isoformat()],
            )
            daily_row = cursor.fetchone()

            daily_note = None
            if daily_row:
                daily_note = self._row_to_note_match_simple(daily_row)

            # Get hourly notes
            hourly_notes = []
            if include_hourly:
                cursor.execute(
                    """
                    SELECT note_id, note_type, start_ts, end_ts, file_path, json_payload
                    FROM notes
                    WHERE note_type = 'hour'
                    AND start_ts >= ? AND start_ts <= ?
                    ORDER BY start_ts
                    """,
                    [day_start.isoformat(), day_end.isoformat()],
                )
                for row in cursor.fetchall():
                    match = self._row_to_note_match_simple(row)
                    if match:
                        hourly_notes.append(match)

            if daily_note is None and not hourly_notes:
                return None

            return DayMatch(
                date=day,
                daily_note=daily_note,
                hourly_notes=hourly_notes,
                relevance_score=1.0,  # Direct lookup, full relevance
            )

        except Exception as e:
            logger.error(f"Failed to get day context for {day}: {e}")
            return None
        finally:
            conn.close()

    def _row_to_note_match_simple(self, row) -> NoteMatch | None:
        """Convert a database row to NoteMatch (without embedding distance)."""
        try:
            import json

            payload = {}
            if row["json_payload"]:
                try:
                    payload = json.loads(row["json_payload"])
                except json.JSONDecodeError:
                    pass

            return NoteMatch(
                note_id=row["note_id"],
                note_type=row["note_type"],
                start_ts=datetime.fromisoformat(row["start_ts"]),
                end_ts=datetime.fromisoformat(row["end_ts"]),
                file_path=Path(row["file_path"]) if row["file_path"] else None,
                score=1.0,  # No distance calculation
                summary=payload.get("summary", ""),
                entities=payload.get("entities", []),
                activities=payload.get("activities", []),
            )
        except Exception as e:
            logger.warning(f"Failed to parse note match: {e}")
            return None


if __name__ == "__main__":
    import fire

    def search(
        query: str,
        time_filter: str | None = None,
        max_days: int = DEFAULT_MAX_DAYS,
        db_path: str | None = None,
    ):
        """
        Perform hierarchical search.

        Args:
            query: Search query
            time_filter: Optional time filter (e.g., "today", "last week")
            max_days: Maximum days to return
            db_path: Path to database
        """
        from src.retrieval.time import parse_time_filter

        searcher = HierarchicalSearcher(db_path=db_path)

        tf = parse_time_filter(time_filter) if time_filter else None
        result = searcher.search(query, time_filter=tf, max_days=max_days)

        return result.to_dict()

    def day(day_str: str, db_path: str | None = None):
        """
        Get context for a specific day.

        Args:
            day_str: Date in YYYY-MM-DD format
            db_path: Path to database
        """
        target_day = datetime.strptime(day_str, "%Y-%m-%d").date()
        searcher = HierarchicalSearcher(db_path=db_path)
        result = searcher.get_day_context(target_day)

        if result:
            return result.to_dict()
        return {"error": f"No notes found for {day_str}"}

    fire.Fire({"search": search, "day": day})
