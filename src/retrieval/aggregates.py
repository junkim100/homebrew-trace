"""
Aggregates Lookup for Trace

Handles "most watched/listened" queries via the pre-computed
aggregates table. Provides fast lookups for time-based rankings.

P7-04: Aggregates lookup
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.core.paths import DB_PATH
from src.db.migrations import get_connection
from src.retrieval.time import TimeFilter

logger = logging.getLogger(__name__)

# Valid key types for aggregates
KEY_TYPES = {
    "category",
    "entity",
    "co_activity",
    "app",
    "domain",
    "topic",
    "media",
    "artist",
    "track",
}

# Period type mappings
PERIOD_TYPES = {"day", "week", "month", "year"}


@dataclass
class AggregateItem:
    """A single aggregate result."""

    key: str
    key_type: str
    value: float  # Duration in minutes or count
    period_type: str
    period_start: datetime
    period_end: datetime
    extra: dict | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "key": self.key,
            "key_type": self.key_type,
            "value": self.value,
            "period_type": self.period_type,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "extra": self.extra,
        }


@dataclass
class AggregatesResult:
    """Result of an aggregates lookup."""

    query_type: str
    key_type: str
    time_filter: TimeFilter | None
    items: list[AggregateItem]
    total_value: float

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "query_type": self.query_type,
            "key_type": self.key_type,
            "time_filter": self.time_filter.to_dict() if self.time_filter else None,
            "items": [i.to_dict() for i in self.items],
            "total_value": self.total_value,
        }


class AggregatesLookup:
    """
    Handles lookups against the aggregates table.

    Supports queries like:
    - "Most watched games in July"
    - "Most listened artists this week"
    - "Most used apps today"
    - "Most time spent on topics last month"
    """

    def __init__(self, db_path: Path | str | None = None):
        """
        Initialize the aggregates lookup.

        Args:
            db_path: Path to SQLite database
        """
        self.db_path = Path(db_path) if db_path else DB_PATH

    def get_top_by_key_type(
        self,
        key_type: str,
        time_filter: TimeFilter | None = None,
        limit: int = 10,
    ) -> AggregatesResult:
        """
        Get top items by key type (e.g., top apps, top topics).

        Args:
            key_type: Type of key to query (app, topic, domain, etc.)
            time_filter: Optional time range filter
            limit: Maximum results

        Returns:
            AggregatesResult with top items
        """
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()

            if time_filter:
                # Query aggregates within the time range
                sql = """
                    SELECT key, key_type, SUM(value_num) as total_value,
                           MIN(period_start_ts) as period_start,
                           MAX(period_end_ts) as period_end,
                           extra_json
                    FROM aggregates
                    WHERE key_type = ?
                      AND period_start_ts <= ?
                      AND period_end_ts >= ?
                    GROUP BY key
                    ORDER BY total_value DESC
                    LIMIT ?
                """
                params = [
                    key_type,
                    time_filter.end.isoformat(),
                    time_filter.start.isoformat(),
                    limit,
                ]
            else:
                # Query all aggregates for the key type
                sql = """
                    SELECT key, key_type, SUM(value_num) as total_value,
                           MIN(period_start_ts) as period_start,
                           MAX(period_end_ts) as period_end,
                           extra_json
                    FROM aggregates
                    WHERE key_type = ?
                    GROUP BY key
                    ORDER BY total_value DESC
                    LIMIT ?
                """
                params = [key_type, limit]

            cursor.execute(sql, params)
            rows = cursor.fetchall()

            items = []
            total_value = 0.0

            for row in rows:
                value = row["total_value"] or 0.0
                total_value += value

                # Parse extra JSON if present
                extra = None
                if row["extra_json"]:
                    import json

                    try:
                        extra = json.loads(row["extra_json"])
                    except Exception:
                        pass

                items.append(
                    AggregateItem(
                        key=row["key"],
                        key_type=row["key_type"],
                        value=value,
                        period_type="custom",  # Aggregated across multiple periods
                        period_start=datetime.fromisoformat(row["period_start"]),
                        period_end=datetime.fromisoformat(row["period_end"]),
                        extra=extra,
                    )
                )

            return AggregatesResult(
                query_type="top",
                key_type=key_type,
                time_filter=time_filter,
                items=items,
                total_value=total_value,
            )

        finally:
            conn.close()

    def get_top_apps(
        self,
        time_filter: TimeFilter | None = None,
        limit: int = 10,
    ) -> AggregatesResult:
        """Get top apps by usage time."""
        return self.get_top_by_key_type("app", time_filter, limit)

    def get_top_topics(
        self,
        time_filter: TimeFilter | None = None,
        limit: int = 10,
    ) -> AggregatesResult:
        """Get top topics by time spent."""
        return self.get_top_by_key_type("topic", time_filter, limit)

    def get_top_domains(
        self,
        time_filter: TimeFilter | None = None,
        limit: int = 10,
    ) -> AggregatesResult:
        """Get top domains by visit time."""
        return self.get_top_by_key_type("domain", time_filter, limit)

    def get_top_media(
        self,
        time_filter: TimeFilter | None = None,
        limit: int = 10,
    ) -> AggregatesResult:
        """Get top media (listening/watching) by time."""
        return self.get_top_by_key_type("media", time_filter, limit)

    def get_top_artists(
        self,
        time_filter: TimeFilter | None = None,
        limit: int = 10,
    ) -> AggregatesResult:
        """Get top artists by listening time."""
        return self.get_top_by_key_type("artist", time_filter, limit)

    def get_top_categories(
        self,
        time_filter: TimeFilter | None = None,
        limit: int = 10,
    ) -> AggregatesResult:
        """Get top activity categories by time."""
        return self.get_top_by_key_type("category", time_filter, limit)

    def get_time_for_key(
        self,
        key: str,
        key_type: str | None = None,
        time_filter: TimeFilter | None = None,
    ) -> AggregatesResult:
        """
        Get total time for a specific key.

        Args:
            key: The key to look up (e.g., "VS Code", "Python")
            key_type: Optional key type filter
            time_filter: Optional time range filter

        Returns:
            AggregatesResult with the total time
        """
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()

            # Build query conditions
            conditions = ["LOWER(key) = LOWER(?)"]
            params: list = [key]

            if key_type:
                conditions.append("key_type = ?")
                params.append(key_type)

            if time_filter:
                conditions.append("period_start_ts <= ?")
                conditions.append("period_end_ts >= ?")
                params.extend([time_filter.end.isoformat(), time_filter.start.isoformat()])

            where_clause = " AND ".join(conditions)

            sql = f"""
                SELECT key, key_type, SUM(value_num) as total_value,
                       MIN(period_start_ts) as period_start,
                       MAX(period_end_ts) as period_end
                FROM aggregates
                WHERE {where_clause}
                GROUP BY key, key_type
            """

            cursor.execute(sql, params)
            rows = cursor.fetchall()

            items = []
            total_value = 0.0

            for row in rows:
                value = row["total_value"] or 0.0
                total_value += value

                items.append(
                    AggregateItem(
                        key=row["key"],
                        key_type=row["key_type"],
                        value=value,
                        period_type="custom",
                        period_start=datetime.fromisoformat(row["period_start"]),
                        period_end=datetime.fromisoformat(row["period_end"]),
                    )
                )

            return AggregatesResult(
                query_type="lookup",
                key_type=key_type or "any",
                time_filter=time_filter,
                items=items,
                total_value=total_value,
            )

        finally:
            conn.close()

    def get_summary_for_period(
        self,
        time_filter: TimeFilter,
    ) -> dict:
        """
        Get a summary of all aggregates for a time period.

        Args:
            time_filter: Time range to summarize

        Returns:
            Dict with summaries by key type
        """
        summary = {}

        for key_type in ["category", "app", "domain", "topic", "media"]:
            result = self.get_top_by_key_type(key_type, time_filter, limit=5)
            summary[key_type] = {
                "top_items": [{"key": item.key, "minutes": item.value} for item in result.items],
                "total_minutes": result.total_value,
            }

        return summary

    def search_aggregates(
        self,
        query: str,
        time_filter: TimeFilter | None = None,
        limit: int = 10,
    ) -> AggregatesResult:
        """
        Search aggregates by key name.

        Args:
            query: Search query for key names
            time_filter: Optional time range filter
            limit: Maximum results

        Returns:
            AggregatesResult with matching items
        """
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()

            # Use LIKE for partial matching
            pattern = f"%{query}%"

            if time_filter:
                sql = """
                    SELECT key, key_type, SUM(value_num) as total_value,
                           MIN(period_start_ts) as period_start,
                           MAX(period_end_ts) as period_end
                    FROM aggregates
                    WHERE LOWER(key) LIKE LOWER(?)
                      AND period_start_ts <= ?
                      AND period_end_ts >= ?
                    GROUP BY key, key_type
                    ORDER BY total_value DESC
                    LIMIT ?
                """
                params = [
                    pattern,
                    time_filter.end.isoformat(),
                    time_filter.start.isoformat(),
                    limit,
                ]
            else:
                sql = """
                    SELECT key, key_type, SUM(value_num) as total_value,
                           MIN(period_start_ts) as period_start,
                           MAX(period_end_ts) as period_end
                    FROM aggregates
                    WHERE LOWER(key) LIKE LOWER(?)
                    GROUP BY key, key_type
                    ORDER BY total_value DESC
                    LIMIT ?
                """
                params = [pattern, limit]

            cursor.execute(sql, params)
            rows = cursor.fetchall()

            items = []
            total_value = 0.0

            for row in rows:
                value = row["total_value"] or 0.0
                total_value += value

                items.append(
                    AggregateItem(
                        key=row["key"],
                        key_type=row["key_type"],
                        value=value,
                        period_type="custom",
                        period_start=datetime.fromisoformat(row["period_start"]),
                        period_end=datetime.fromisoformat(row["period_end"]),
                    )
                )

            return AggregatesResult(
                query_type="search",
                key_type="any",
                time_filter=time_filter,
                items=items,
                total_value=total_value,
            )

        finally:
            conn.close()

    def detect_most_query(self, query: str) -> tuple[str, str] | None:
        """
        Detect if a query is a "most" query and extract the key type.

        Args:
            query: User query

        Returns:
            Tuple of (query_type, key_type) or None if not a "most" query
        """
        import re

        query_lower = query.lower()

        # Patterns for "most" queries
        patterns = [
            # "most watched X"
            (r"\bmost\s+watched\b", "media"),
            (r"\bmost\s+viewed\b", "media"),
            # "most listened X"
            (r"\bmost\s+listened\b", "media"),
            (r"\bmost\s+played\b", "media"),
            # "most used X"
            (r"\bmost\s+used\s+apps?\b", "app"),
            (r"\bmost\s+used\b", "app"),
            # "most visited X"
            (r"\bmost\s+visited\s+(?:sites?|domains?|websites?)\b", "domain"),
            (r"\bmost\s+visited\b", "domain"),
            # "most time on X"
            (r"\bmost\s+time\s+(?:on|with|in)\s+apps?\b", "app"),
            (r"\bmost\s+time\s+(?:on|with)\s+topics?\b", "topic"),
            (r"\bmost\s+time\s+(?:on|at)\s+(?:sites?|domains?|websites?)\b", "domain"),
            (r"\bmost\s+time\b", "category"),
            # "top X"
            (r"\btop\s+apps?\b", "app"),
            (r"\btop\s+(?:sites?|domains?|websites?)\b", "domain"),
            (r"\btop\s+topics?\b", "topic"),
            (r"\btop\s+artists?\b", "artist"),
            (r"\btop\s+songs?\b", "track"),
            (r"\btop\s+tracks?\b", "track"),
            # "favorite X"
            (r"\bfavorite\s+apps?\b", "app"),
            (r"\bfavorite\s+artists?\b", "artist"),
            (r"\bfavorite\s+songs?\b", "track"),
            # "frequently used X"
            (r"\bfrequently\s+used\s+apps?\b", "app"),
            (r"\bfrequently\s+visited\b", "domain"),
        ]

        for pattern, key_type in patterns:
            if re.search(pattern, query_lower):
                return ("most", key_type)

        return None


if __name__ == "__main__":
    import fire

    def top(key_type: str, limit: int = 10, time_filter: str | None = None):
        """
        Get top items by key type.

        Args:
            key_type: Type of key (app, topic, domain, etc.)
            limit: Maximum results
            time_filter: Optional time filter (e.g., "today", "last week")
        """
        from src.retrieval.time import parse_time_filter

        lookup = AggregatesLookup()

        tf = None
        if time_filter:
            tf = parse_time_filter(time_filter)

        result = lookup.get_top_by_key_type(key_type, tf, limit)
        return result.to_dict()

    def search(query: str, limit: int = 10):
        """Search aggregates by key name."""
        lookup = AggregatesLookup()
        result = lookup.search_aggregates(query, limit=limit)
        return result.to_dict()

    def time_for(key: str, key_type: str | None = None, time_filter: str | None = None):
        """Get total time for a specific key."""
        from src.retrieval.time import parse_time_filter

        lookup = AggregatesLookup()

        tf = None
        if time_filter:
            tf = parse_time_filter(time_filter)

        result = lookup.get_time_for_key(key, key_type, tf)
        return result.to_dict()

    def summary(time_filter: str = "today"):
        """Get summary for a time period."""
        from src.retrieval.time import parse_time_filter

        lookup = AggregatesLookup()
        tf = parse_time_filter(time_filter)

        if tf:
            return lookup.get_summary_for_period(tf)
        return {"error": "Could not parse time filter"}

    fire.Fire(
        {
            "top": top,
            "search": search,
            "time_for": time_for,
            "summary": summary,
        }
    )
