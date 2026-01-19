"""
Vector Search for Trace

Searches notes by embedding similarity within time ranges.
Uses sqlite-vec for efficient KNN search.

P7-02: Vector search
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.core.paths import DB_PATH
from src.db.migrations import get_connection
from src.db.vectors import (
    init_vector_table,
    load_sqlite_vec,
    query_similar,
)
from src.retrieval.time import TimeFilter
from src.summarize.embeddings import EmbeddingComputer

logger = logging.getLogger(__name__)


@dataclass
class NoteMatch:
    """A note matched by vector search."""

    note_id: str
    note_type: str
    start_ts: datetime
    end_ts: datetime
    file_path: str
    summary: str
    categories: list[str]
    entities: list[dict]
    distance: float  # Lower is more similar
    score: float  # Normalized similarity score (0-1, higher is better)

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "note_id": self.note_id,
            "note_type": self.note_type,
            "start_ts": self.start_ts.isoformat(),
            "end_ts": self.end_ts.isoformat(),
            "file_path": self.file_path,
            "summary": self.summary,
            "categories": self.categories,
            "entities": self.entities,
            "distance": self.distance,
            "score": self.score,
        }


@dataclass
class SearchResult:
    """Result of a vector search."""

    query: str
    time_filter: TimeFilter | None
    matches: list[NoteMatch]
    total_notes_searched: int
    embedding_computed: bool

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "query": self.query,
            "time_filter": self.time_filter.to_dict() if self.time_filter else None,
            "matches": [m.to_dict() for m in self.matches],
            "total_notes_searched": self.total_notes_searched,
            "embedding_computed": self.embedding_computed,
        }


class VectorSearcher:
    """
    Searches notes by semantic similarity using embeddings.

    Features:
    - Computes query embedding on-the-fly
    - Time-filtered search
    - Combines vector similarity with note metadata
    - Returns ranked results with scores
    """

    def __init__(
        self,
        db_path: Path | str | None = None,
        api_key: str | None = None,
    ):
        """
        Initialize the vector searcher.

        Args:
            db_path: Path to SQLite database
            api_key: OpenAI API key for embedding queries
        """
        self.db_path = Path(db_path) if db_path else DB_PATH
        self._embedding_computer = EmbeddingComputer(api_key=api_key, db_path=self.db_path)

    def search(
        self,
        query: str,
        time_filter: TimeFilter | None = None,
        limit: int = 10,
        min_score: float = 0.0,
    ) -> SearchResult:
        """
        Search for notes matching a query.

        Args:
            query: Natural language query
            time_filter: Optional time range filter
            limit: Maximum results to return
            min_score: Minimum similarity score (0-1)

        Returns:
            SearchResult with ranked matches
        """
        # Compute query embedding
        query_embedding = self._embedding_computer.compute_for_query(query)

        if query_embedding is None:
            logger.error("Failed to compute query embedding")
            return SearchResult(
                query=query,
                time_filter=time_filter,
                matches=[],
                total_notes_searched=0,
                embedding_computed=False,
            )

        conn = get_connection(self.db_path)
        try:
            load_sqlite_vec(conn)
            init_vector_table(conn)

            # Perform vector search
            # Fetch more results than needed to allow for time filtering
            fetch_limit = limit * 5 if time_filter else limit

            similar_results = query_similar(
                conn,
                query_embedding,
                limit=fetch_limit,
                source_type="note",
            )

            if not similar_results:
                return SearchResult(
                    query=query,
                    time_filter=time_filter,
                    matches=[],
                    total_notes_searched=0,
                    embedding_computed=True,
                )

            # Get note details for each result
            matches = []
            note_ids = [r["source_id"] for r in similar_results]

            # Build note lookup
            note_lookup = self._get_notes_by_ids(conn, note_ids)

            # Track notes searched (within time filter)
            total_searched = 0

            for result in similar_results:
                note_id = result["source_id"]
                distance = result["distance"]

                if note_id not in note_lookup:
                    continue

                note = note_lookup[note_id]
                note_start = datetime.fromisoformat(note["start_ts"])
                note_end = datetime.fromisoformat(note["end_ts"])

                # Apply time filter
                if time_filter:
                    if not time_filter.overlaps(note_start, note_end):
                        continue

                total_searched += 1

                # Convert distance to similarity score
                # sqlite-vec uses L2 distance, so we need to convert
                # Lower distance = higher similarity
                # Using a simple conversion: score = 1 / (1 + distance)
                score = 1 / (1 + distance)

                if score < min_score:
                    continue

                # Parse JSON payload
                try:
                    payload = json.loads(note["json_payload"])
                    summary = payload.get("summary", "")
                    categories = payload.get("categories", [])
                    entities = payload.get("entities", [])
                except (json.JSONDecodeError, TypeError):
                    summary = ""
                    categories = []
                    entities = []

                matches.append(
                    NoteMatch(
                        note_id=note_id,
                        note_type=note["note_type"],
                        start_ts=note_start,
                        end_ts=note_end,
                        file_path=note["file_path"],
                        summary=summary,
                        categories=categories,
                        entities=entities,
                        distance=distance,
                        score=score,
                    )
                )

                if len(matches) >= limit:
                    break

            # Sort by score (descending)
            matches.sort(key=lambda m: m.score, reverse=True)

            return SearchResult(
                query=query,
                time_filter=time_filter,
                matches=matches,
                total_notes_searched=total_searched,
                embedding_computed=True,
            )

        finally:
            conn.close()

    def search_by_entity(
        self,
        entity_name: str,
        entity_type: str | None = None,
        time_filter: TimeFilter | None = None,
        limit: int = 10,
        min_strength: float = 0.0,
    ) -> list[NoteMatch]:
        """
        Search for notes containing a specific entity.

        Args:
            entity_name: Entity name to search for
            entity_type: Optional entity type filter
            time_filter: Optional time range filter
            limit: Maximum results
            min_strength: Minimum association strength

        Returns:
            List of matching notes
        """
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()

            # Find entity IDs matching the name (check canonical and aliases)
            entity_ids = self._find_entity_ids(conn, entity_name, entity_type)

            if not entity_ids:
                return []

            # Build query for notes linked to these entities
            placeholders = ",".join("?" * len(entity_ids))
            params = list(entity_ids) + [min_strength]

            if time_filter:
                params.extend([time_filter.end.isoformat(), time_filter.start.isoformat()])
                sql = f"""
                    SELECT DISTINCT n.note_id, n.note_type, n.start_ts, n.end_ts,
                           n.file_path, n.json_payload, ne.strength
                    FROM notes n
                    JOIN note_entities ne ON n.note_id = ne.note_id
                    WHERE ne.entity_id IN ({placeholders})
                      AND ne.strength >= ?
                      AND n.start_ts <= ?
                      AND n.end_ts >= ?
                    ORDER BY ne.strength DESC, n.start_ts DESC
                    LIMIT ?
                """
                params.append(limit)
            else:
                sql = f"""
                    SELECT DISTINCT n.note_id, n.note_type, n.start_ts, n.end_ts,
                           n.file_path, n.json_payload, ne.strength
                    FROM notes n
                    JOIN note_entities ne ON n.note_id = ne.note_id
                    WHERE ne.entity_id IN ({placeholders})
                      AND ne.strength >= ?
                    ORDER BY ne.strength DESC, n.start_ts DESC
                    LIMIT ?
                """
                params.append(limit)

            cursor.execute(sql, params)
            rows = cursor.fetchall()

            matches = []
            for row in rows:
                try:
                    payload = json.loads(row["json_payload"])
                    summary = payload.get("summary", "")
                    categories = payload.get("categories", [])
                    entities = payload.get("entities", [])
                except (json.JSONDecodeError, TypeError):
                    summary = ""
                    categories = []
                    entities = []

                matches.append(
                    NoteMatch(
                        note_id=row["note_id"],
                        note_type=row["note_type"],
                        start_ts=datetime.fromisoformat(row["start_ts"]),
                        end_ts=datetime.fromisoformat(row["end_ts"]),
                        file_path=row["file_path"],
                        summary=summary,
                        categories=categories,
                        entities=entities,
                        distance=0.0,
                        score=row["strength"],
                    )
                )

            return matches

        finally:
            conn.close()

    def search_by_category(
        self,
        category: str,
        time_filter: TimeFilter | None = None,
        limit: int = 10,
    ) -> list[NoteMatch]:
        """
        Search for notes with a specific category.

        Args:
            category: Category to search for (work, learning, entertainment, etc.)
            time_filter: Optional time range filter
            limit: Maximum results

        Returns:
            List of matching notes
        """
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()

            # SQLite doesn't have native JSON array search, so we use LIKE
            category_pattern = f'%"{category}"%'

            if time_filter:
                sql = """
                    SELECT note_id, note_type, start_ts, end_ts, file_path, json_payload
                    FROM notes
                    WHERE json_payload LIKE ?
                      AND start_ts <= ?
                      AND end_ts >= ?
                    ORDER BY start_ts DESC
                    LIMIT ?
                """
                params = [
                    category_pattern,
                    time_filter.end.isoformat(),
                    time_filter.start.isoformat(),
                    limit,
                ]
            else:
                sql = """
                    SELECT note_id, note_type, start_ts, end_ts, file_path, json_payload
                    FROM notes
                    WHERE json_payload LIKE ?
                    ORDER BY start_ts DESC
                    LIMIT ?
                """
                params = [category_pattern, limit]

            cursor.execute(sql, params)
            rows = cursor.fetchall()

            matches = []
            for row in rows:
                try:
                    payload = json.loads(row["json_payload"])
                    categories = payload.get("categories", [])

                    # Double-check the category match
                    if category.lower() not in [c.lower() for c in categories]:
                        continue

                    summary = payload.get("summary", "")
                    entities = payload.get("entities", [])
                except (json.JSONDecodeError, TypeError):
                    continue

                matches.append(
                    NoteMatch(
                        note_id=row["note_id"],
                        note_type=row["note_type"],
                        start_ts=datetime.fromisoformat(row["start_ts"]),
                        end_ts=datetime.fromisoformat(row["end_ts"]),
                        file_path=row["file_path"],
                        summary=summary,
                        categories=categories,
                        entities=entities,
                        distance=0.0,
                        score=1.0,
                    )
                )

            return matches

        finally:
            conn.close()

    def get_notes_in_range(
        self,
        time_filter: TimeFilter,
        note_type: str | None = None,
        limit: int = 100,
    ) -> list[NoteMatch]:
        """
        Get all notes within a time range.

        Args:
            time_filter: Time range filter
            note_type: Optional filter by note type ('hour' or 'day')
            limit: Maximum results

        Returns:
            List of notes in chronological order
        """
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()

            if note_type:
                sql = """
                    SELECT note_id, note_type, start_ts, end_ts, file_path, json_payload
                    FROM notes
                    WHERE note_type = ?
                      AND start_ts <= ?
                      AND end_ts >= ?
                    ORDER BY start_ts ASC
                    LIMIT ?
                """
                params = [
                    note_type,
                    time_filter.end.isoformat(),
                    time_filter.start.isoformat(),
                    limit,
                ]
            else:
                sql = """
                    SELECT note_id, note_type, start_ts, end_ts, file_path, json_payload
                    FROM notes
                    WHERE start_ts <= ?
                      AND end_ts >= ?
                    ORDER BY start_ts ASC
                    LIMIT ?
                """
                params = [
                    time_filter.end.isoformat(),
                    time_filter.start.isoformat(),
                    limit,
                ]

            cursor.execute(sql, params)
            rows = cursor.fetchall()

            matches = []
            for row in rows:
                try:
                    payload = json.loads(row["json_payload"])
                    summary = payload.get("summary", "")
                    categories = payload.get("categories", [])
                    entities = payload.get("entities", [])
                except (json.JSONDecodeError, TypeError):
                    summary = ""
                    categories = []
                    entities = []

                matches.append(
                    NoteMatch(
                        note_id=row["note_id"],
                        note_type=row["note_type"],
                        start_ts=datetime.fromisoformat(row["start_ts"]),
                        end_ts=datetime.fromisoformat(row["end_ts"]),
                        file_path=row["file_path"],
                        summary=summary,
                        categories=categories,
                        entities=entities,
                        distance=0.0,
                        score=1.0,
                    )
                )

            return matches

        finally:
            conn.close()

    def _get_notes_by_ids(self, conn, note_ids: list[str]) -> dict[str, dict]:
        """
        Get note details by IDs.

        Args:
            conn: Database connection
            note_ids: List of note IDs

        Returns:
            Dict mapping note_id to note details
        """
        if not note_ids:
            return {}

        cursor = conn.cursor()
        placeholders = ",".join("?" * len(note_ids))

        cursor.execute(
            f"""
            SELECT note_id, note_type, start_ts, end_ts, file_path, json_payload
            FROM notes
            WHERE note_id IN ({placeholders})
            """,
            note_ids,
        )

        return {row["note_id"]: dict(row) for row in cursor.fetchall()}

    def _find_entity_ids(
        self,
        conn,
        name: str,
        entity_type: str | None = None,
    ) -> list[str]:
        """
        Find entity IDs matching a name.

        Checks canonical names and aliases.

        Args:
            conn: Database connection
            name: Entity name to search for
            entity_type: Optional entity type filter

        Returns:
            List of matching entity IDs
        """
        cursor = conn.cursor()
        normalized = name.lower().strip()

        entity_ids = []

        # Search canonical names
        if entity_type:
            cursor.execute(
                """
                SELECT entity_id
                FROM entities
                WHERE entity_type = ? AND LOWER(canonical_name) = ?
                """,
                (entity_type, normalized),
            )
        else:
            cursor.execute(
                """
                SELECT entity_id
                FROM entities
                WHERE LOWER(canonical_name) = ?
                """,
                (normalized,),
            )

        for row in cursor.fetchall():
            entity_ids.append(row["entity_id"])

        # Also search partial matches in canonical names
        partial_pattern = f"%{normalized}%"
        if entity_type:
            cursor.execute(
                """
                SELECT entity_id
                FROM entities
                WHERE entity_type = ? AND LOWER(canonical_name) LIKE ?
                """,
                (entity_type, partial_pattern),
            )
        else:
            cursor.execute(
                """
                SELECT entity_id
                FROM entities
                WHERE LOWER(canonical_name) LIKE ?
                """,
                (partial_pattern,),
            )

        for row in cursor.fetchall():
            if row["entity_id"] not in entity_ids:
                entity_ids.append(row["entity_id"])

        # Search aliases
        if entity_type:
            cursor.execute(
                """
                SELECT entity_id, aliases
                FROM entities
                WHERE entity_type = ? AND aliases IS NOT NULL
                """,
                (entity_type,),
            )
        else:
            cursor.execute(
                """
                SELECT entity_id, aliases
                FROM entities
                WHERE aliases IS NOT NULL
                """
            )

        for row in cursor.fetchall():
            if row["aliases"]:
                try:
                    aliases = json.loads(row["aliases"])
                    for alias in aliases:
                        if normalized in alias.lower():
                            if row["entity_id"] not in entity_ids:
                                entity_ids.append(row["entity_id"])
                            break
                except json.JSONDecodeError:
                    pass

        return entity_ids


if __name__ == "__main__":
    import fire

    def search(query: str, limit: int = 10, time_filter: str | None = None):
        """
        Search for notes matching a query.

        Args:
            query: Natural language query
            limit: Maximum results
            time_filter: Optional time filter (e.g., "today", "last week")
        """
        from src.retrieval.time import parse_time_filter

        searcher = VectorSearcher()

        tf = None
        if time_filter:
            tf = parse_time_filter(time_filter)

        result = searcher.search(query, time_filter=tf, limit=limit)
        return result.to_dict()

    def by_entity(entity: str, entity_type: str | None = None, limit: int = 10):
        """Search for notes by entity."""
        searcher = VectorSearcher()
        matches = searcher.search_by_entity(entity, entity_type, limit=limit)
        return [m.to_dict() for m in matches]

    def by_category(category: str, limit: int = 10):
        """Search for notes by category."""
        searcher = VectorSearcher()
        matches = searcher.search_by_category(category, limit=limit)
        return [m.to_dict() for m in matches]

    fire.Fire(
        {
            "search": search,
            "by_entity": by_entity,
            "by_category": by_category,
        }
    )
