"""
Graph Visualization Data Provider

Provides graph data in a format suitable for visualization.
Returns nodes (entities) and edges for rendering in a graph UI.

P10-04: Graph visualization
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from src.core.paths import get_db_path
from src.db.connection import get_connection

logger = logging.getLogger(__name__)


@dataclass
class GraphNode:
    """A node in the visualization graph."""

    id: str
    label: str
    type: str
    note_count: int = 0
    edge_count: int = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "type": self.type,
            "noteCount": self.note_count,
            "edgeCount": self.edge_count,
        }


@dataclass
class GraphEdge:
    """An edge in the visualization graph."""

    source: str
    target: str
    type: str
    weight: float

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "target": self.target,
            "type": self.type,
            "weight": self.weight,
        }


def get_graph_data(
    days_back: int = 30,
    entity_types: list[str] | None = None,
    min_edge_weight: float = 0.3,
    limit: int = 100,
) -> dict:
    """
    Get graph data for visualization.

    Args:
        days_back: How many days of data to include
        entity_types: Filter by entity types (topic, app, domain, etc.)
        min_edge_weight: Minimum edge weight to include
        limit: Maximum number of nodes

    Returns:
        Dict with nodes and edges arrays
    """
    db_path = get_db_path()
    conn = get_connection(db_path)

    try:
        start_ts = (datetime.now() - timedelta(days=days_back)).isoformat()

        # Get entities with most connections
        type_filter = ""

        if entity_types:
            placeholders = ",".join("?" * len(entity_types))
            type_filter = f"AND e.entity_type IN ({placeholders})"

        cursor = conn.execute(
            f"""
            SELECT
                e.entity_id,
                e.entity_type,
                e.canonical_name,
                COUNT(DISTINCT ne.note_id) as note_count,
                (
                    SELECT COUNT(*) FROM edges ed
                    WHERE (ed.from_id = e.entity_id OR ed.to_id = e.entity_id)
                    AND ed.weight >= ?
                ) as edge_count
            FROM entities e
            LEFT JOIN note_entities ne ON e.entity_id = ne.entity_id
            LEFT JOIN notes n ON ne.note_id = n.note_id AND n.start_ts >= ?
            {type_filter.replace("?", "?") if type_filter else ""}
            GROUP BY e.entity_id
            HAVING note_count > 0 OR edge_count > 0
            ORDER BY edge_count DESC, note_count DESC
            LIMIT ?
            """,
            [min_edge_weight, start_ts] + (entity_types or []) + [limit],
        )

        nodes: list[GraphNode] = []
        node_ids: set[str] = set()

        for row in cursor.fetchall():
            node = GraphNode(
                id=row[0],
                label=row[2],
                type=row[1],
                note_count=row[3] or 0,
                edge_count=row[4] or 0,
            )
            nodes.append(node)
            node_ids.add(node.id)

        # Get edges between the selected nodes
        edges: list[GraphEdge] = []

        if node_ids:
            placeholders = ",".join("?" * len(node_ids))
            cursor = conn.execute(
                f"""
                SELECT from_id, to_id, edge_type, weight
                FROM edges
                WHERE from_id IN ({placeholders})
                  AND to_id IN ({placeholders})
                  AND weight >= ?
                ORDER BY weight DESC
                """,
                list(node_ids) + list(node_ids) + [min_edge_weight],
            )

            for row in cursor.fetchall():
                edge = GraphEdge(
                    source=row[0],
                    target=row[1],
                    type=row[2],
                    weight=row[3],
                )
                edges.append(edge)

        return {
            "success": True,
            "nodes": [n.to_dict() for n in nodes],
            "edges": [e.to_dict() for e in edges],
            "nodeCount": len(nodes),
            "edgeCount": len(edges),
        }

    except Exception as e:
        logger.exception("Failed to get graph data")
        return {
            "success": False,
            "error": str(e),
            "nodes": [],
            "edges": [],
            "nodeCount": 0,
            "edgeCount": 0,
        }

    finally:
        conn.close()


def get_entity_types() -> list[dict]:
    """
    Get all distinct entity types with counts.

    Returns:
        List of {type, count} dicts
    """
    db_path = get_db_path()
    conn = get_connection(db_path)

    try:
        cursor = conn.execute(
            """
            SELECT entity_type, COUNT(*) as count
            FROM entities
            GROUP BY entity_type
            ORDER BY count DESC
            """
        )

        return [{"type": row[0], "count": row[1]} for row in cursor.fetchall()]

    finally:
        conn.close()


def get_entity_details(entity_id: str) -> dict:
    """
    Get detailed information about an entity.

    Args:
        entity_id: The entity ID

    Returns:
        Dict with entity details, related entities, and notes
    """
    db_path = get_db_path()
    conn = get_connection(db_path)

    try:
        # Get entity info
        cursor = conn.execute(
            """
            SELECT entity_id, entity_type, canonical_name, aliases
            FROM entities
            WHERE entity_id = ?
            """,
            (entity_id,),
        )
        row = cursor.fetchone()

        if not row:
            return {"success": False, "error": "Entity not found"}

        aliases = json.loads(row[3]) if row[3] else []

        entity = {
            "id": row[0],
            "type": row[1],
            "name": row[2],
            "aliases": aliases,
        }

        # Get connected entities via edges
        cursor = conn.execute(
            """
            SELECT
                CASE WHEN ed.from_id = ? THEN ed.to_id ELSE ed.from_id END as related_id,
                CASE WHEN ed.from_id = ? THEN 'outgoing' ELSE 'incoming' END as direction,
                ed.edge_type,
                ed.weight,
                e.canonical_name,
                e.entity_type
            FROM edges ed
            JOIN entities e ON e.entity_id =
                CASE WHEN ed.from_id = ? THEN ed.to_id ELSE ed.from_id END
            WHERE ed.from_id = ? OR ed.to_id = ?
            ORDER BY ed.weight DESC
            LIMIT 20
            """,
            (entity_id, entity_id, entity_id, entity_id, entity_id),
        )

        related = []
        for row in cursor.fetchall():
            related.append(
                {
                    "id": row[0],
                    "direction": row[1],
                    "edgeType": row[2],
                    "weight": row[3],
                    "name": row[4],
                    "type": row[5],
                }
            )

        # Get notes mentioning this entity
        cursor = conn.execute(
            """
            SELECT n.note_id, n.file_path, n.start_ts, n.json_payload, ne.strength
            FROM note_entities ne
            JOIN notes n ON ne.note_id = n.note_id
            WHERE ne.entity_id = ?
            ORDER BY ne.strength DESC, n.start_ts DESC
            LIMIT 10
            """,
            (entity_id,),
        )

        notes = []
        for row in cursor.fetchall():
            try:
                payload = json.loads(row[3])
                summary = payload.get("summary", "")
            except (json.JSONDecodeError, TypeError):
                summary = ""

            notes.append(
                {
                    "noteId": row[0],
                    "path": row[1],
                    "timestamp": row[2],
                    "summary": summary,
                    "strength": row[4],
                }
            )

        return {
            "success": True,
            "entity": entity,
            "related": related,
            "notes": notes,
        }

    except Exception as e:
        logger.exception("Failed to get entity details")
        return {"success": False, "error": str(e)}

    finally:
        conn.close()


if __name__ == "__main__":
    import fire

    def graph(days: int = 30, limit: int = 50, min_weight: float = 0.3):
        """Get graph data for visualization."""
        result = get_graph_data(days_back=days, limit=limit, min_edge_weight=min_weight)
        print(f"Nodes: {result['nodeCount']}, Edges: {result['edgeCount']}")
        for node in result["nodes"][:10]:
            print(f"  {node['type']}: {node['label']} ({node['edgeCount']} edges)")

    def types():
        """List entity types."""
        for t in get_entity_types():
            print(f"  {t['type']}: {t['count']}")

    def details(entity_id: str):
        """Get entity details."""
        return get_entity_details(entity_id)

    fire.Fire({"graph": graph, "types": types, "details": details})
