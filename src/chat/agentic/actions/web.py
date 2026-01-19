"""
Web Search Action

Provides external web search capability for augmenting answers
with current information or historical context.

Uses Tavily API by default, with fallback to a simple implementation.
"""

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar

from src.chat.agentic.actions.base import Action, ActionRegistry, ExecutionContext
from src.chat.agentic.schemas import StepResult, WebCitation, WebResult

logger = logging.getLogger(__name__)


@ActionRegistry.register
class WebSearch(Action):
    """Search the web for external information."""

    name: ClassVar[str] = "web_search"
    default_timeout: ClassVar[float] = 15.0

    def __init__(
        self,
        db_path: Path | None = None,
        api_key: str | None = None,
    ) -> None:
        super().__init__(db_path, api_key)
        self._tavily_client = None
        self._tavily_available: bool | None = None

    def _check_tavily_available(self) -> bool:
        """Check if Tavily is available."""
        if self._tavily_available is not None:
            return self._tavily_available

        try:
            import os

            from tavily import TavilyClient

            tavily_key = os.environ.get("TAVILY_API_KEY")
            if tavily_key:
                self._tavily_client = TavilyClient(api_key=tavily_key)
                self._tavily_available = True
            else:
                self._tavily_available = False
        except ImportError:
            self._tavily_available = False

        return self._tavily_available

    def execute(
        self,
        params: dict[str, Any],
        context: ExecutionContext,
    ) -> StepResult:
        """
        Search the web for information.

        Params:
            query: Search query string
            max_results: Maximum number of results (default 5)
            search_depth: "basic" or "advanced" (default "basic")
            include_domains: Optional list of domains to include
            exclude_domains: Optional list of domains to exclude
        """
        start_time = time.time()
        step_id = params.get("step_id", "web_search")

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

            max_results = params.get("max_results", 5)
            search_depth = params.get("search_depth", "basic")

            # Try Tavily first
            if self._check_tavily_available():
                results = self._search_tavily(
                    query=query,
                    max_results=max_results,
                    search_depth=search_depth,
                    include_domains=params.get("include_domains"),
                    exclude_domains=params.get("exclude_domains"),
                )
            else:
                # Fallback: Return a message that web search is not configured
                logger.warning("Web search not available: TAVILY_API_KEY not set")
                return StepResult(
                    step_id=step_id,
                    action=self.name,
                    success=True,
                    result={
                        "web_results": [],
                        "web_citations": [],
                        "query": query,
                        "message": "Web search not available. Set TAVILY_API_KEY to enable.",
                    },
                    execution_time_ms=(time.time() - start_time) * 1000,
                )

            # Convert to WebResult and WebCitation objects
            web_results = []
            web_citations = []
            accessed_at = datetime.now()

            for result in results:
                web_result = WebResult(
                    title=result.get("title", ""),
                    url=result.get("url", ""),
                    snippet=result.get("content", "")[:500],
                    relevance_score=result.get("score", 0.0),
                )
                web_results.append(web_result.to_dict())

                web_citation = WebCitation(
                    url=result.get("url", ""),
                    title=result.get("title", ""),
                    accessed_at=accessed_at,
                    snippet=result.get("content", "")[:200],
                )
                web_citations.append(web_citation.to_dict())

            return StepResult(
                step_id=step_id,
                action=self.name,
                success=True,
                result={
                    "web_results": web_results,
                    "web_citations": web_citations,
                    "query": query,
                    "results_count": len(web_results),
                },
                execution_time_ms=(time.time() - start_time) * 1000,
            )

        except Exception as e:
            logger.error(f"Web search failed: {e}")
            return StepResult(
                step_id=step_id,
                action=self.name,
                success=False,
                error=str(e),
                execution_time_ms=(time.time() - start_time) * 1000,
            )

    def _search_tavily(
        self,
        query: str,
        max_results: int = 5,
        search_depth: str = "basic",
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
    ) -> list[dict]:
        """Execute search using Tavily API."""
        if not self._tavily_client:
            return []

        try:
            search_params: dict[str, Any] = {
                "query": query,
                "max_results": max_results,
                "search_depth": search_depth,
            }

            if include_domains:
                search_params["include_domains"] = include_domains
            if exclude_domains:
                search_params["exclude_domains"] = exclude_domains

            response = self._tavily_client.search(**search_params)

            return response.get("results", [])

        except Exception as e:
            logger.error(f"Tavily search failed: {e}")
            return []
