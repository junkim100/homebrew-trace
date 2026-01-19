"""
Graph Traversal Actions

Actions for traversing the entity relationship graph to find
connections, co-occurrences, and entity context.
"""

import logging
import time
from pathlib import Path
from typing import Any, ClassVar

from src.chat.agentic.actions.base import Action, ActionRegistry, ExecutionContext
from src.chat.agentic.schemas import StepResult
from src.core.paths import DB_PATH
from src.retrieval.graph import GraphExpander
from src.retrieval.time import TimeFilter, parse_time_filter

logger = logging.getLogger(__name__)


def _parse_time_filter_param(params: dict[str, Any]) -> TimeFilter | None:
    """Parse time filter from params dict."""
    time_filter = params.get("time_filter")
    if time_filter is None:
        return None

    if isinstance(time_filter, TimeFilter):
        return time_filter

    if isinstance(time_filter, dict):
        if "description" in time_filter:
            return parse_time_filter(time_filter["description"])
        if "start" in time_filter and "end" in time_filter:
            from datetime import datetime

            start = time_filter["start"]
            end = time_filter["end"]
            if isinstance(start, str):
                start = datetime.fromisoformat(start)
            if isinstance(end, str):
                end = datetime.fromisoformat(end)
            return TimeFilter(
                start=start,
                end=end,
                description=time_filter.get("description", "custom range"),
            )

    if isinstance(time_filter, str):
        return parse_time_filter(time_filter)

    return None


@ActionRegistry.register
class GraphExpand(Action):
    """Expand from an entity following graph edges."""

    name: ClassVar[str] = "graph_expand"
    default_timeout: ClassVar[float] = 6.0

    def __init__(
        self,
        db_path: Path | None = None,
        api_key: str | None = None,
    ) -> None:
        super().__init__(db_path, api_key)
        self._expander: GraphExpander | None = None

    def _get_expander(self) -> GraphExpander:
        if self._expander is None:
            self._expander = GraphExpander(db_path=self.db_path or DB_PATH)
        return self._expander

    def execute(
        self,
        params: dict[str, Any],
        context: ExecutionContext,
    ) -> StepResult:
        """
        Expand from an entity to find related entities.

        Params:
            entity_name: Name of the entity to expand from
            entity_type: Optional entity type
            edge_types: Optional list of edge types to follow
            hops: Number of hops (default 1)
            time_filter: Optional time filter
            min_weight: Minimum edge weight (default 0.3)
            max_related: Max related entities (default 20)
        """
        start_time = time.time()
        step_id = params.get("step_id", "graph_expand")

        try:
            entity_name = params.get("entity_name", "")
            if not entity_name:
                return StepResult(
                    step_id=step_id,
                    action=self.name,
                    success=False,
                    error="entity_name is required",
                    execution_time_ms=(time.time() - start_time) * 1000,
                )

            entity_type = params.get("entity_type")
            edge_types = params.get("edge_types")
            hops = params.get("hops", 1)
            time_filter = _parse_time_filter_param(params)
            min_weight = params.get("min_weight", 0.3)
            max_related = params.get("max_related", 20)

            expander = self._get_expander()

            # Get entity context first to find entity IDs
            entity_context = expander.get_entity_context(
                entity_name=entity_name,
                entity_type=entity_type,
                time_filter=time_filter,
            )

            if "error" in entity_context:
                return StepResult(
                    step_id=step_id,
                    action=self.name,
                    success=True,
                    result={
                        "related_entities": [],
                        "expanded_notes": [],
                        "entity_name": entity_name,
                        "message": f"Entity '{entity_name}' not found",
                    },
                    execution_time_ms=(time.time() - start_time) * 1000,
                )

            entity_id = entity_context.get("entity", {}).get("entity_id")
            if not entity_id:
                return StepResult(
                    step_id=step_id,
                    action=self.name,
                    success=True,
                    result={
                        "related_entities": [],
                        "expanded_notes": [],
                        "entity_name": entity_name,
                    },
                    execution_time_ms=(time.time() - start_time) * 1000,
                )

            # Expand from the entity
            expansion = expander.expand_from_entities(
                entity_ids=[entity_id],
                hops=hops,
                time_filter=time_filter,
                edge_types=edge_types,
                min_weight=min_weight,
                max_related=max_related,
            )

            related_entities = [e.to_dict() for e in expansion.related_entities]
            expanded_notes = [n.to_dict() for n in expansion.expanded_notes]

            return StepResult(
                step_id=step_id,
                action=self.name,
                success=True,
                result={
                    "related_entities": related_entities,
                    "expanded_notes": expanded_notes,
                    "entity_name": entity_name,
                    "hops_used": hops,
                },
                execution_time_ms=(time.time() - start_time) * 1000,
            )

        except Exception as e:
            logger.error(f"Graph expand failed: {e}")
            return StepResult(
                step_id=step_id,
                action=self.name,
                success=False,
                error=str(e),
                execution_time_ms=(time.time() - start_time) * 1000,
            )


@ActionRegistry.register
class FindConnections(Action):
    """Find paths between two entities in the graph."""

    name: ClassVar[str] = "find_connections"
    default_timeout: ClassVar[float] = 8.0

    def __init__(
        self,
        db_path: Path | None = None,
        api_key: str | None = None,
    ) -> None:
        super().__init__(db_path, api_key)
        self._expander: GraphExpander | None = None

    def _get_expander(self) -> GraphExpander:
        if self._expander is None:
            self._expander = GraphExpander(db_path=self.db_path or DB_PATH)
        return self._expander

    def execute(
        self,
        params: dict[str, Any],
        context: ExecutionContext,
    ) -> StepResult:
        """
        Find connection paths between two entities.

        Params:
            entity_a: First entity name
            entity_b: Second entity name
            max_hops: Maximum path length (default 3)
        """
        start_time = time.time()
        step_id = params.get("step_id", "find_connections")

        try:
            entity_a = params.get("entity_a", "")
            entity_b = params.get("entity_b", "")

            if not entity_a or not entity_b:
                return StepResult(
                    step_id=step_id,
                    action=self.name,
                    success=False,
                    error="Both entity_a and entity_b are required",
                    execution_time_ms=(time.time() - start_time) * 1000,
                )

            max_hops = params.get("max_hops", 3)

            expander = self._get_expander()
            paths = expander.find_connections(
                entity_a_name=entity_a,
                entity_b_name=entity_b,
                max_hops=max_hops,
            )

            # Convert paths to serializable format
            paths_data = []
            for path in paths:
                path_entities = [
                    {
                        "entity_id": e.entity_id,
                        "entity_type": e.entity_type,
                        "canonical_name": e.canonical_name,
                    }
                    for e in path
                ]
                paths_data.append(path_entities)

            return StepResult(
                step_id=step_id,
                action=self.name,
                success=True,
                result={
                    "paths": paths_data,
                    "entity_a": entity_a,
                    "entity_b": entity_b,
                    "paths_found": len(paths_data),
                },
                execution_time_ms=(time.time() - start_time) * 1000,
            )

        except Exception as e:
            logger.error(f"Find connections failed: {e}")
            return StepResult(
                step_id=step_id,
                action=self.name,
                success=False,
                error=str(e),
                execution_time_ms=(time.time() - start_time) * 1000,
            )


@ActionRegistry.register
class GetCoOccurrences(Action):
    """Find entities that co-occurred with a given entity."""

    name: ClassVar[str] = "get_co_occurrences"
    default_timeout: ClassVar[float] = 5.0

    def __init__(
        self,
        db_path: Path | None = None,
        api_key: str | None = None,
    ) -> None:
        super().__init__(db_path, api_key)
        self._expander: GraphExpander | None = None

    def _get_expander(self) -> GraphExpander:
        if self._expander is None:
            self._expander = GraphExpander(db_path=self.db_path or DB_PATH)
        return self._expander

    def execute(
        self,
        params: dict[str, Any],
        context: ExecutionContext,
    ) -> StepResult:
        """
        Find entities that co-occurred with the given entity.

        Params:
            entity_name: Name of the entity
            edge_type: Optional specific edge type (default: CO_OCCURRED_WITH)
            time_filter: Optional time filter
            limit: Max results (default 10)
        """
        start_time = time.time()
        step_id = params.get("step_id", "get_co_occurrences")

        try:
            entity_name = params.get("entity_name", "")
            if not entity_name:
                return StepResult(
                    step_id=step_id,
                    action=self.name,
                    success=False,
                    error="entity_name is required",
                    execution_time_ms=(time.time() - start_time) * 1000,
                )

            edge_type = params.get("edge_type", "CO_OCCURRED_WITH")
            time_filter = _parse_time_filter_param(params)
            limit = params.get("limit", 10)

            expander = self._get_expander()

            # Get entity context
            entity_context = expander.get_entity_context(
                entity_name=entity_name,
                time_filter=time_filter,
            )

            if "error" in entity_context:
                return StepResult(
                    step_id=step_id,
                    action=self.name,
                    success=True,
                    result={
                        "co_occurrences": [],
                        "entity_name": entity_name,
                        "message": f"Entity '{entity_name}' not found",
                    },
                    execution_time_ms=(time.time() - start_time) * 1000,
                )

            entity_id = entity_context.get("entity", {}).get("entity_id")
            if not entity_id:
                return StepResult(
                    step_id=step_id,
                    action=self.name,
                    success=True,
                    result={
                        "co_occurrences": [],
                        "entity_name": entity_name,
                    },
                    execution_time_ms=(time.time() - start_time) * 1000,
                )

            # Expand with specific edge type
            expansion = expander.expand_from_entities(
                entity_ids=[entity_id],
                hops=1,
                time_filter=time_filter,
                edge_types=[edge_type] if edge_type else None,
                max_related=limit,
            )

            co_occurrences = [e.to_dict() for e in expansion.related_entities]

            return StepResult(
                step_id=step_id,
                action=self.name,
                success=True,
                result={
                    "co_occurrences": co_occurrences,
                    "entity_name": entity_name,
                    "edge_type": edge_type,
                },
                execution_time_ms=(time.time() - start_time) * 1000,
            )

        except Exception as e:
            logger.error(f"Get co-occurrences failed: {e}")
            return StepResult(
                step_id=step_id,
                action=self.name,
                success=False,
                error=str(e),
                execution_time_ms=(time.time() - start_time) * 1000,
            )


@ActionRegistry.register
class GetEntityContext(Action):
    """Get full context for an entity including relationships."""

    name: ClassVar[str] = "get_entity_context"
    default_timeout: ClassVar[float] = 5.0

    def __init__(
        self,
        db_path: Path | None = None,
        api_key: str | None = None,
    ) -> None:
        super().__init__(db_path, api_key)
        self._expander: GraphExpander | None = None

    def _get_expander(self) -> GraphExpander:
        if self._expander is None:
            self._expander = GraphExpander(db_path=self.db_path or DB_PATH)
        return self._expander

    def execute(
        self,
        params: dict[str, Any],
        context: ExecutionContext,
    ) -> StepResult:
        """
        Get complete context for an entity.

        Params:
            entity_name: Name of the entity
            entity_type: Optional entity type
            time_filter: Optional time filter
            include_edges: Whether to include relationship data (default True)
        """
        start_time = time.time()
        step_id = params.get("step_id", "get_entity_context")

        try:
            entity_name = params.get("entity_name", "")
            if not entity_name:
                return StepResult(
                    step_id=step_id,
                    action=self.name,
                    success=False,
                    error="entity_name is required",
                    execution_time_ms=(time.time() - start_time) * 1000,
                )

            entity_type = params.get("entity_type")
            time_filter = _parse_time_filter_param(params)

            expander = self._get_expander()
            entity_context = expander.get_entity_context(
                entity_name=entity_name,
                entity_type=entity_type,
                time_filter=time_filter,
            )

            return StepResult(
                step_id=step_id,
                action=self.name,
                success=True,
                result=entity_context,
                execution_time_ms=(time.time() - start_time) * 1000,
            )

        except Exception as e:
            logger.error(f"Get entity context failed: {e}")
            return StepResult(
                step_id=step_id,
                action=self.name,
                success=False,
                error=str(e),
                execution_time_ms=(time.time() - start_time) * 1000,
            )
