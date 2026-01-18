"""
Graph Expansion for Trace

Expands search results using typed edges and weights from the
relationship graph. Discovers related entities and notes.

P7-03: Graph expansion
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from src.core.paths import DB_PATH
from src.db.migrations import get_connection
from src.retrieval.time import TimeFilter

logger = logging.getLogger(__name__)

# Edge type weights for different query contexts
EDGE_WEIGHTS = {
    "ABOUT_TOPIC": 1.0,  # Topic relationships are highly relevant
    "CO_OCCURRED_WITH": 0.9,  # Co-occurrence suggests strong relationship
    "STUDIED_WHILE": 0.85,  # Learning context
    "USED_APP": 0.8,  # App usage context
    "VISITED_DOMAIN": 0.75,  # Domain visits
    "DOC_REFERENCE": 0.7,  # Document references
    "LISTENED_TO": 0.6,  # Media consumption
    "WATCHED": 0.6,  # Media consumption
}


@dataclass
class RelatedEntity:
    """An entity related to the search results."""

    entity_id: str
    entity_type: str
    canonical_name: str
    edge_type: str
    weight: float
    source_entity_id: str
    source_entity_name: str
    direction: str  # "from" or "to"

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "canonical_name": self.canonical_name,
            "edge_type": self.edge_type,
            "weight": self.weight,
            "source_entity_id": self.source_entity_id,
            "source_entity_name": self.source_entity_name,
            "direction": self.direction,
        }


@dataclass
class ExpandedNote:
    """A note discovered through graph expansion."""

    note_id: str
    note_type: str
    start_ts: datetime
    end_ts: datetime
    file_path: str
    summary: str
    relevance_score: float  # Combines edge weight and path length
    path: list[str]  # Entity IDs forming the path from original entity

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "note_id": self.note_id,
            "note_type": self.note_type,
            "start_ts": self.start_ts.isoformat(),
            "end_ts": self.end_ts.isoformat(),
            "file_path": self.file_path,
            "summary": self.summary,
            "relevance_score": self.relevance_score,
            "path": self.path,
        }


@dataclass
class GraphExpansionResult:
    """Result of graph expansion."""

    source_entities: list[str]
    related_entities: list[RelatedEntity]
    expanded_notes: list[ExpandedNote]
    hops: int
    time_filter: TimeFilter | None

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "source_entities": self.source_entities,
            "related_entities": [e.to_dict() for e in self.related_entities],
            "expanded_notes": [n.to_dict() for n in self.expanded_notes],
            "hops": self.hops,
            "time_filter": self.time_filter.to_dict() if self.time_filter else None,
        }


@dataclass
class EntityInfo:
    """Information about an entity."""

    entity_id: str
    entity_type: str
    canonical_name: str
    aliases: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "canonical_name": self.canonical_name,
            "aliases": self.aliases,
        }


class GraphExpander:
    """
    Expands search results using the relationship graph.

    Features:
    - N-hop expansion from seed entities
    - Edge type filtering
    - Time-constrained expansion
    - Relevance scoring based on edge weights
    """

    def __init__(self, db_path: Path | str | None = None):
        """
        Initialize the graph expander.

        Args:
            db_path: Path to SQLite database
        """
        self.db_path = Path(db_path) if db_path else DB_PATH

    def expand_from_entities(
        self,
        entity_ids: list[str],
        hops: int = 1,
        time_filter: TimeFilter | None = None,
        edge_types: list[str] | None = None,
        min_weight: float = 0.3,
        max_related: int = 20,
    ) -> GraphExpansionResult:
        """
        Expand from a set of seed entities.

        Args:
            entity_ids: Seed entity IDs to expand from
            hops: Number of expansion hops (default: 1)
            time_filter: Optional time range filter for edges
            edge_types: Optional list of edge types to follow
            min_weight: Minimum edge weight to follow
            max_related: Maximum related entities to return

        Returns:
            GraphExpansionResult with related entities and notes
        """
        conn = get_connection(self.db_path)
        try:
            # Track visited entities
            visited = set(entity_ids)
            current_frontier = list(entity_ids)
            all_related: list[RelatedEntity] = []
            all_expanded_notes: list[ExpandedNote] = []

            # Build entity info lookup for source entities
            source_info = self._get_entities_info(conn, entity_ids)

            for hop in range(hops):
                new_frontier = []

                for entity_id in current_frontier:
                    # Get entity info for the source
                    source_entity = source_info.get(entity_id)
                    if not source_entity:
                        source_entity = self._get_entities_info(conn, [entity_id]).get(entity_id)
                        if source_entity:
                            source_info[entity_id] = source_entity

                    source_name = source_entity.canonical_name if source_entity else entity_id

                    # Find connected entities via edges
                    edges = self._get_edges_for_entity(
                        conn,
                        entity_id,
                        time_filter=time_filter,
                        edge_types=edge_types,
                        min_weight=min_weight,
                    )

                    for edge in edges:
                        # Determine the related entity
                        if edge["from_id"] == entity_id:
                            related_id = edge["to_id"]
                            direction = "to"
                        else:
                            related_id = edge["from_id"]
                            direction = "from"

                        if related_id in visited:
                            continue

                        visited.add(related_id)
                        new_frontier.append(related_id)

                        # Get related entity info
                        related_info = self._get_entity_by_id(conn, related_id)
                        if related_info:
                            # Calculate relevance based on edge weight and hop distance
                            edge_type_weight = EDGE_WEIGHTS.get(edge["edge_type"], 0.5)
                            hop_decay = 1.0 / (hop + 1)  # Decay by hop distance
                            relevance = edge["weight"] * edge_type_weight * hop_decay

                            all_related.append(
                                RelatedEntity(
                                    entity_id=related_id,
                                    entity_type=related_info.entity_type,
                                    canonical_name=related_info.canonical_name,
                                    edge_type=edge["edge_type"],
                                    weight=relevance,
                                    source_entity_id=entity_id,
                                    source_entity_name=source_name,
                                    direction=direction,
                                )
                            )

                current_frontier = new_frontier

            # Sort related entities by weight and limit
            all_related.sort(key=lambda e: e.weight, reverse=True)
            all_related = all_related[:max_related]

            # Find notes linked to related entities
            related_entity_ids = [e.entity_id for e in all_related]
            if related_entity_ids:
                expanded_notes = self._get_notes_for_entities(
                    conn,
                    related_entity_ids,
                    time_filter=time_filter,
                    limit=20,
                )
                all_expanded_notes = expanded_notes

            return GraphExpansionResult(
                source_entities=entity_ids,
                related_entities=all_related,
                expanded_notes=all_expanded_notes,
                hops=hops,
                time_filter=time_filter,
            )

        finally:
            conn.close()

    def expand_from_note(
        self,
        note_id: str,
        hops: int = 1,
        time_filter: TimeFilter | None = None,
        min_strength: float = 0.3,
    ) -> GraphExpansionResult:
        """
        Expand from a note by following its entities.

        Args:
            note_id: Note ID to expand from
            hops: Number of expansion hops
            time_filter: Optional time range filter
            min_strength: Minimum entity association strength

        Returns:
            GraphExpansionResult
        """
        conn = get_connection(self.db_path)
        try:
            # Get entities linked to this note
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT entity_id, strength
                FROM note_entities
                WHERE note_id = ? AND strength >= ?
                ORDER BY strength DESC
                """,
                (note_id, min_strength),
            )

            entity_ids = [row["entity_id"] for row in cursor.fetchall()]

            if not entity_ids:
                return GraphExpansionResult(
                    source_entities=[],
                    related_entities=[],
                    expanded_notes=[],
                    hops=hops,
                    time_filter=time_filter,
                )

        finally:
            conn.close()

        # Expand from these entities
        return self.expand_from_entities(
            entity_ids=entity_ids,
            hops=hops,
            time_filter=time_filter,
        )

    def find_connections(
        self,
        entity_a_name: str,
        entity_b_name: str,
        max_hops: int = 3,
    ) -> list[list[EntityInfo]]:
        """
        Find connection paths between two entities.

        Args:
            entity_a_name: First entity name
            entity_b_name: Second entity name
            max_hops: Maximum path length

        Returns:
            List of paths (each path is a list of EntityInfo)
        """
        conn = get_connection(self.db_path)
        try:
            # Find entity IDs
            entity_a_ids = self._find_entity_ids_by_name(conn, entity_a_name)
            entity_b_ids = self._find_entity_ids_by_name(conn, entity_b_name)

            if not entity_a_ids or not entity_b_ids:
                return []

            # BFS to find paths
            paths = []
            target_ids = set(entity_b_ids)

            for start_id in entity_a_ids:
                found_paths = self._bfs_paths(conn, start_id, target_ids, max_hops)
                paths.extend(found_paths)

            # Convert entity IDs to EntityInfo
            result_paths = []
            for path in paths:
                entity_infos = []
                for entity_id in path:
                    info = self._get_entity_by_id(conn, entity_id)
                    if info:
                        entity_infos.append(info)
                if entity_infos:
                    result_paths.append(entity_infos)

            return result_paths

        finally:
            conn.close()

    def get_entity_context(
        self,
        entity_name: str,
        entity_type: str | None = None,
        time_filter: TimeFilter | None = None,
    ) -> dict:
        """
        Get full context for an entity including relationships.

        Args:
            entity_name: Entity name
            entity_type: Optional entity type
            time_filter: Optional time filter

        Returns:
            Dict with entity info, relationships, and notes
        """
        conn = get_connection(self.db_path)
        try:
            # Find entity
            entity_ids = self._find_entity_ids_by_name(conn, entity_name, entity_type)
            if not entity_ids:
                return {"error": "Entity not found"}

            entity_id = entity_ids[0]
            entity_info = self._get_entity_by_id(conn, entity_id)

            # Get outgoing edges
            outgoing = self._get_edges_for_entity(
                conn, entity_id, time_filter=time_filter, direction="from"
            )

            # Get incoming edges
            incoming = self._get_edges_for_entity(
                conn, entity_id, time_filter=time_filter, direction="to"
            )

            # Get notes mentioning this entity
            notes = self._get_notes_for_entities(
                conn, [entity_id], time_filter=time_filter, limit=10
            )

            # Build relationship summary
            relationships = {
                "outgoing": [],
                "incoming": [],
            }

            for edge in outgoing:
                target_info = self._get_entity_by_id(conn, edge["to_id"])
                if target_info:
                    relationships["outgoing"].append(
                        {
                            "entity": target_info.to_dict(),
                            "edge_type": edge["edge_type"],
                            "weight": edge["weight"],
                        }
                    )

            for edge in incoming:
                source_info = self._get_entity_by_id(conn, edge["from_id"])
                if source_info:
                    relationships["incoming"].append(
                        {
                            "entity": source_info.to_dict(),
                            "edge_type": edge["edge_type"],
                            "weight": edge["weight"],
                        }
                    )

            return {
                "entity": entity_info.to_dict() if entity_info else None,
                "relationships": relationships,
                "notes": [n.to_dict() for n in notes],
            }

        finally:
            conn.close()

    def _get_edges_for_entity(
        self,
        conn,
        entity_id: str,
        time_filter: TimeFilter | None = None,
        edge_types: list[str] | None = None,
        min_weight: float = 0.0,
        direction: str = "both",
    ) -> list[dict]:
        """Get edges connected to an entity."""
        cursor = conn.cursor()
        edges = []

        # Build base query
        conditions = ["weight >= ?"]
        params = [min_weight]

        if edge_types:
            placeholders = ",".join("?" * len(edge_types))
            conditions.append(f"edge_type IN ({placeholders})")
            params.extend(edge_types)

        if time_filter:
            conditions.append(
                "(start_ts IS NULL OR start_ts <= ?) AND (end_ts IS NULL OR end_ts >= ?)"
            )
            params.extend([time_filter.end.isoformat(), time_filter.start.isoformat()])

        where_clause = " AND ".join(conditions)

        if direction in ("from", "both"):
            cursor.execute(
                f"""
                SELECT from_id, to_id, edge_type, weight, start_ts, end_ts
                FROM edges
                WHERE from_id = ? AND {where_clause}
                ORDER BY weight DESC
                """,
                [entity_id] + params,
            )
            edges.extend([dict(row) for row in cursor.fetchall()])

        if direction in ("to", "both"):
            cursor.execute(
                f"""
                SELECT from_id, to_id, edge_type, weight, start_ts, end_ts
                FROM edges
                WHERE to_id = ? AND {where_clause}
                ORDER BY weight DESC
                """,
                [entity_id] + params,
            )
            for row in cursor.fetchall():
                edge_dict = dict(row)
                # Avoid duplicates
                if not any(
                    e["from_id"] == edge_dict["from_id"]
                    and e["to_id"] == edge_dict["to_id"]
                    and e["edge_type"] == edge_dict["edge_type"]
                    for e in edges
                ):
                    edges.append(edge_dict)

        return edges

    def _get_entity_by_id(self, conn, entity_id: str) -> EntityInfo | None:
        """Get entity info by ID."""
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT entity_id, entity_type, canonical_name, aliases
            FROM entities
            WHERE entity_id = ?
            """,
            (entity_id,),
        )
        row = cursor.fetchone()

        if row:
            aliases = json.loads(row["aliases"]) if row["aliases"] else []
            return EntityInfo(
                entity_id=row["entity_id"],
                entity_type=row["entity_type"],
                canonical_name=row["canonical_name"],
                aliases=aliases,
            )
        return None

    def _get_entities_info(self, conn, entity_ids: list[str]) -> dict[str, EntityInfo]:
        """Get info for multiple entities."""
        if not entity_ids:
            return {}

        cursor = conn.cursor()
        placeholders = ",".join("?" * len(entity_ids))
        cursor.execute(
            f"""
            SELECT entity_id, entity_type, canonical_name, aliases
            FROM entities
            WHERE entity_id IN ({placeholders})
            """,
            entity_ids,
        )

        result = {}
        for row in cursor.fetchall():
            aliases = json.loads(row["aliases"]) if row["aliases"] else []
            result[row["entity_id"]] = EntityInfo(
                entity_id=row["entity_id"],
                entity_type=row["entity_type"],
                canonical_name=row["canonical_name"],
                aliases=aliases,
            )
        return result

    def _find_entity_ids_by_name(
        self,
        conn,
        name: str,
        entity_type: str | None = None,
    ) -> list[str]:
        """Find entity IDs matching a name."""
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
                        if alias.lower() == normalized:
                            if row["entity_id"] not in entity_ids:
                                entity_ids.append(row["entity_id"])
                            break
                except json.JSONDecodeError:
                    pass

        return entity_ids

    def _get_notes_for_entities(
        self,
        conn,
        entity_ids: list[str],
        time_filter: TimeFilter | None = None,
        limit: int = 20,
    ) -> list[ExpandedNote]:
        """Get notes linked to entities."""
        if not entity_ids:
            return []

        cursor = conn.cursor()
        placeholders = ",".join("?" * len(entity_ids))
        params = list(entity_ids)

        if time_filter:
            sql = f"""
                SELECT DISTINCT n.note_id, n.note_type, n.start_ts, n.end_ts,
                       n.file_path, n.json_payload, MAX(ne.strength) as max_strength
                FROM notes n
                JOIN note_entities ne ON n.note_id = ne.note_id
                WHERE ne.entity_id IN ({placeholders})
                  AND n.start_ts <= ?
                  AND n.end_ts >= ?
                GROUP BY n.note_id
                ORDER BY max_strength DESC, n.start_ts DESC
                LIMIT ?
            """
            params.extend([time_filter.end.isoformat(), time_filter.start.isoformat(), limit])
        else:
            sql = f"""
                SELECT DISTINCT n.note_id, n.note_type, n.start_ts, n.end_ts,
                       n.file_path, n.json_payload, MAX(ne.strength) as max_strength
                FROM notes n
                JOIN note_entities ne ON n.note_id = ne.note_id
                WHERE ne.entity_id IN ({placeholders})
                GROUP BY n.note_id
                ORDER BY max_strength DESC, n.start_ts DESC
                LIMIT ?
            """
            params.append(limit)

        cursor.execute(sql, params)

        notes = []
        for row in cursor.fetchall():
            try:
                payload = json.loads(row["json_payload"])
                summary = payload.get("summary", "")
            except (json.JSONDecodeError, TypeError):
                summary = ""

            notes.append(
                ExpandedNote(
                    note_id=row["note_id"],
                    note_type=row["note_type"],
                    start_ts=datetime.fromisoformat(row["start_ts"]),
                    end_ts=datetime.fromisoformat(row["end_ts"]),
                    file_path=row["file_path"],
                    summary=summary,
                    relevance_score=row["max_strength"],
                    path=[],
                )
            )

        return notes

    def _bfs_paths(
        self,
        conn,
        start_id: str,
        target_ids: set[str],
        max_hops: int,
    ) -> list[list[str]]:
        """BFS to find paths between entities."""
        from collections import deque

        paths = []
        queue = deque([(start_id, [start_id])])
        visited_at_depth = {start_id: 0}

        while queue:
            current, path = queue.popleft()

            if len(path) > max_hops + 1:
                continue

            if current in target_ids and current != start_id:
                paths.append(path)
                continue

            # Get neighbors
            edges = self._get_edges_for_entity(conn, current)
            for edge in edges:
                neighbor = edge["to_id"] if edge["from_id"] == current else edge["from_id"]

                depth = len(path)
                if neighbor not in visited_at_depth or visited_at_depth[neighbor] >= depth:
                    visited_at_depth[neighbor] = depth
                    queue.append((neighbor, path + [neighbor]))

        return paths


if __name__ == "__main__":
    import fire

    def expand(entity_name: str, hops: int = 1, entity_type: str | None = None):
        """Expand from an entity."""
        expander = GraphExpander()

        # First find the entity
        conn = get_connection(expander.db_path)
        try:
            entity_ids = expander._find_entity_ids_by_name(conn, entity_name, entity_type)
        finally:
            conn.close()

        if not entity_ids:
            return {"error": "Entity not found"}

        result = expander.expand_from_entities(entity_ids, hops=hops)
        return result.to_dict()

    def context(entity_name: str, entity_type: str | None = None):
        """Get full context for an entity."""
        expander = GraphExpander()
        return expander.get_entity_context(entity_name, entity_type)

    def connect(entity_a: str, entity_b: str, max_hops: int = 3):
        """Find connection paths between two entities."""
        expander = GraphExpander()
        paths = expander.find_connections(entity_a, entity_b, max_hops)
        return [[e.to_dict() for e in path] for path in paths]

    fire.Fire(
        {
            "expand": expand,
            "context": context,
            "connect": connect,
        }
    )
