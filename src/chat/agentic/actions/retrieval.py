"""
Core Retrieval Actions

Actions that wrap the primary retrieval components:
- VectorSearcher for semantic search
- HierarchicalSearcher for daily-first search
- AggregatesLookup for pre-computed rollups
"""

import logging
import time
from pathlib import Path
from typing import Any, ClassVar

from src.chat.agentic.actions.base import Action, ActionRegistry, ExecutionContext
from src.chat.agentic.schemas import StepResult
from src.core.paths import DB_PATH
from src.retrieval.aggregates import AggregatesLookup
from src.retrieval.hierarchical import HierarchicalSearcher
from src.retrieval.search import VectorSearcher
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
class SemanticSearch(Action):
    """Vector similarity search over notes."""

    name: ClassVar[str] = "semantic_search"
    default_timeout: ClassVar[float] = 8.0

    def __init__(
        self,
        db_path: Path | None = None,
        api_key: str | None = None,
    ) -> None:
        super().__init__(db_path, api_key)
        self._searcher: VectorSearcher | None = None

    def _get_searcher(self) -> VectorSearcher:
        if self._searcher is None:
            self._searcher = VectorSearcher(
                db_path=self.db_path or DB_PATH,
                api_key=self.api_key,
            )
        return self._searcher

    def execute(
        self,
        params: dict[str, Any],
        context: ExecutionContext,
    ) -> StepResult:
        """
        Execute semantic search.

        Params:
            query: Search query string
            time_filter: Optional time filter
            limit: Max results (default 10)
            min_score: Minimum similarity score (default 0.0)
        """
        start_time = time.time()
        step_id = params.get("step_id", "semantic_search")

        try:
            query = params.get("query", "")
            if not query:
                return StepResult(
                    step_id=step_id,
                    action=self.name,
                    success=False,
                    error="Query is required",
                    execution_time_ms=(time.time() - start_time) * 1000,
                )

            time_filter = _parse_time_filter_param(params)
            limit = params.get("limit", 10)
            min_score = params.get("min_score", 0.0)

            searcher = self._get_searcher()
            result = searcher.search(
                query=query,
                time_filter=time_filter,
                limit=limit,
                min_score=min_score,
            )

            notes = [n.to_dict() for n in result.matches]

            return StepResult(
                step_id=step_id,
                action=self.name,
                success=True,
                result={
                    "notes": notes,
                    "total_searched": result.total_notes_searched,
                    "query": query,
                },
                execution_time_ms=(time.time() - start_time) * 1000,
            )

        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            return StepResult(
                step_id=step_id,
                action=self.name,
                success=False,
                error=str(e),
                execution_time_ms=(time.time() - start_time) * 1000,
            )


@ActionRegistry.register
class EntitySearch(Action):
    """Search notes by entity name."""

    name: ClassVar[str] = "entity_search"
    default_timeout: ClassVar[float] = 5.0

    def __init__(
        self,
        db_path: Path | None = None,
        api_key: str | None = None,
    ) -> None:
        super().__init__(db_path, api_key)
        self._searcher: VectorSearcher | None = None

    def _get_searcher(self) -> VectorSearcher:
        if self._searcher is None:
            self._searcher = VectorSearcher(
                db_path=self.db_path or DB_PATH,
                api_key=self.api_key,
            )
        return self._searcher

    def execute(
        self,
        params: dict[str, Any],
        context: ExecutionContext,
    ) -> StepResult:
        """
        Search for notes mentioning an entity.

        Params:
            entity_name: Name of the entity to search for
            entity_type: Optional entity type filter
            time_filter: Optional time filter
            limit: Max results (default 10)
        """
        start_time = time.time()
        step_id = params.get("step_id", "entity_search")

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
            limit = params.get("limit", 10)

            searcher = self._get_searcher()
            notes = searcher.search_by_entity(
                entity_name=entity_name,
                entity_type=entity_type,
                time_filter=time_filter,
                limit=limit,
            )

            notes_data = [n.to_dict() for n in notes]

            return StepResult(
                step_id=step_id,
                action=self.name,
                success=True,
                result={
                    "notes": notes_data,
                    "entity_name": entity_name,
                    "entity_type": entity_type,
                },
                execution_time_ms=(time.time() - start_time) * 1000,
            )

        except Exception as e:
            logger.error(f"Entity search failed: {e}")
            return StepResult(
                step_id=step_id,
                action=self.name,
                success=False,
                error=str(e),
                execution_time_ms=(time.time() - start_time) * 1000,
            )


@ActionRegistry.register
class HierarchicalSearch(Action):
    """Two-stage hierarchical search (daily first, then hourly)."""

    name: ClassVar[str] = "hierarchical_search"
    default_timeout: ClassVar[float] = 10.0

    def __init__(
        self,
        db_path: Path | None = None,
        api_key: str | None = None,
    ) -> None:
        super().__init__(db_path, api_key)
        self._searcher: HierarchicalSearcher | None = None

    def _get_searcher(self) -> HierarchicalSearcher:
        if self._searcher is None:
            self._searcher = HierarchicalSearcher(
                db_path=self.db_path or DB_PATH,
                api_key=self.api_key,
            )
        return self._searcher

    def execute(
        self,
        params: dict[str, Any],
        context: ExecutionContext,
    ) -> StepResult:
        """
        Execute hierarchical search.

        Params:
            query: Search query string
            time_filter: Optional time filter
            max_days: Max days to return (default 5)
            max_hours_per_day: Max hours per day (default 3)
            include_hourly_drilldown: Whether to drill into hourly notes (default True)
        """
        start_time = time.time()
        step_id = params.get("step_id", "hierarchical_search")

        try:
            query = params.get("query", "")
            if not query:
                return StepResult(
                    step_id=step_id,
                    action=self.name,
                    success=False,
                    error="Query is required",
                    execution_time_ms=(time.time() - start_time) * 1000,
                )

            time_filter = _parse_time_filter_param(params)
            max_days = params.get("max_days", 5)
            max_hours_per_day = params.get("max_hours_per_day", 3)
            include_hourly = params.get("include_hourly_drilldown", True)

            searcher = self._get_searcher()
            result = searcher.search(
                query=query,
                time_filter=time_filter,
                max_days=max_days,
                max_hours_per_day=max_hours_per_day,
                include_hourly_drilldown=include_hourly,
            )

            # Get notes optimized for LLM context
            notes = result.get_context_for_llm(max_notes=10)
            notes_data = [n.to_dict() for n in notes]

            return StepResult(
                step_id=step_id,
                action=self.name,
                success=True,
                result={
                    "notes": notes_data,
                    "days_matched": len(result.day_matches),
                    "query": query,
                },
                execution_time_ms=(time.time() - start_time) * 1000,
            )

        except Exception as e:
            logger.error(f"Hierarchical search failed: {e}")
            return StepResult(
                step_id=step_id,
                action=self.name,
                success=False,
                error=str(e),
                execution_time_ms=(time.time() - start_time) * 1000,
            )


@ActionRegistry.register
class TimeRangeNotes(Action):
    """Get all notes in a time range."""

    name: ClassVar[str] = "time_range_notes"
    default_timeout: ClassVar[float] = 5.0

    def __init__(
        self,
        db_path: Path | None = None,
        api_key: str | None = None,
    ) -> None:
        super().__init__(db_path, api_key)
        self._searcher: VectorSearcher | None = None

    def _get_searcher(self) -> VectorSearcher:
        if self._searcher is None:
            self._searcher = VectorSearcher(
                db_path=self.db_path or DB_PATH,
                api_key=self.api_key,
            )
        return self._searcher

    def execute(
        self,
        params: dict[str, Any],
        context: ExecutionContext,
    ) -> StepResult:
        """
        Get notes within a time range.

        Params:
            time_filter: Time filter (required)
            note_type: Optional filter for 'hour' or 'day' notes
            limit: Max results (default 100)
        """
        start_time = time.time()
        step_id = params.get("step_id", "time_range_notes")

        try:
            time_filter = _parse_time_filter_param(params)
            if not time_filter:
                return StepResult(
                    step_id=step_id,
                    action=self.name,
                    success=False,
                    error="time_filter is required",
                    execution_time_ms=(time.time() - start_time) * 1000,
                )

            note_type = params.get("note_type")
            limit = params.get("limit", 100)

            searcher = self._get_searcher()
            notes = searcher.get_notes_in_range(
                time_filter=time_filter,
                note_type=note_type,
                limit=limit,
            )

            notes_data = [n.to_dict() for n in notes]

            return StepResult(
                step_id=step_id,
                action=self.name,
                success=True,
                result={
                    "notes": notes_data,
                    "time_filter": time_filter.description,
                },
                execution_time_ms=(time.time() - start_time) * 1000,
            )

        except Exception as e:
            logger.error(f"Time range notes failed: {e}")
            return StepResult(
                step_id=step_id,
                action=self.name,
                success=False,
                error=str(e),
                execution_time_ms=(time.time() - start_time) * 1000,
            )


@ActionRegistry.register
class AggregatesQuery(Action):
    """Query pre-computed aggregates (time rollups)."""

    name: ClassVar[str] = "aggregates_query"
    default_timeout: ClassVar[float] = 3.0

    def __init__(
        self,
        db_path: Path | None = None,
        api_key: str | None = None,
    ) -> None:
        super().__init__(db_path, api_key)
        self._aggregates: AggregatesLookup | None = None

    def _get_aggregates(self) -> AggregatesLookup:
        if self._aggregates is None:
            self._aggregates = AggregatesLookup(
                db_path=self.db_path or DB_PATH,
            )
        return self._aggregates

    def execute(
        self,
        params: dict[str, Any],
        context: ExecutionContext,
    ) -> StepResult:
        """
        Query aggregates by key type.

        Params:
            key_type: Type of aggregate (app, domain, topic, artist, track, category)
            time_filter: Optional time filter
            limit: Max results (default 10)
        """
        start_time = time.time()
        step_id = params.get("step_id", "aggregates_query")

        try:
            key_type = params.get("key_type", "app")
            time_filter = _parse_time_filter_param(params)
            limit = params.get("limit", 10)

            aggregates = self._get_aggregates()
            result = aggregates.get_top_by_key_type(
                key_type=key_type,
                time_filter=time_filter,
                limit=limit,
            )

            aggregates_data = [item.to_dict() for item in result.items]

            return StepResult(
                step_id=step_id,
                action=self.name,
                success=True,
                result={
                    "aggregates": aggregates_data,
                    "key_type": key_type,
                    "total_minutes": sum(item.value for item in result.items),
                },
                execution_time_ms=(time.time() - start_time) * 1000,
            )

        except Exception as e:
            logger.error(f"Aggregates query failed: {e}")
            return StepResult(
                step_id=step_id,
                action=self.name,
                success=False,
                error=str(e),
                execution_time_ms=(time.time() - start_time) * 1000,
            )
