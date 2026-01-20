"""
IPC handlers for graph visualization.

P10-04: Graph visualization
"""

import logging
from typing import Any

from src.retrieval.graph_viz import get_entity_details, get_entity_types, get_graph_data
from src.trace_app.ipc.server import handler

logger = logging.getLogger(__name__)


@handler("graph.data")
def handle_graph_data(params: dict[str, Any]) -> dict[str, Any]:
    """
    Get graph data for visualization.

    Params:
        days_back: int (default 30) - How many days of data to include
        entity_types: list[str] (optional) - Filter by entity types
        min_edge_weight: float (default 0.3) - Minimum edge weight
        limit: int (default 100) - Maximum number of nodes

    Returns:
        {success, nodes: [...], edges: [...], nodeCount, edgeCount}
    """
    days_back = params.get("days_back", 30)
    entity_types = params.get("entity_types")
    min_edge_weight = params.get("min_edge_weight", 0.3)
    limit = params.get("limit", 100)

    return get_graph_data(
        days_back=days_back,
        entity_types=entity_types,
        min_edge_weight=min_edge_weight,
        limit=limit,
    )


@handler("graph.entity_types")
def handle_entity_types(params: dict[str, Any]) -> dict[str, Any]:
    """
    Get all entity types with counts.

    Returns:
        {success, types: [{type, count}, ...]}
    """
    try:
        types = get_entity_types()
        return {"success": True, "types": types}
    except Exception as e:
        logger.exception("Failed to get entity types")
        return {"success": False, "error": str(e), "types": []}


@handler("graph.entity_details")
def handle_entity_details(params: dict[str, Any]) -> dict[str, Any]:
    """
    Get detailed information about an entity.

    Params:
        entity_id: str - The entity ID

    Returns:
        {success, entity, related, notes}
    """
    entity_id = params.get("entity_id")
    if not entity_id:
        return {"success": False, "error": "entity_id is required"}

    return get_entity_details(entity_id)
