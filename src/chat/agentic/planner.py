"""
Query Planner for Agentic Pipeline

Uses an LLM to decompose complex queries into executable plans.
The planner analyzes user queries and generates step-by-step
execution plans that can be run by the PlanExecutor.
"""

import json
import logging
import uuid
from typing import Any

from openai import OpenAI
from pydantic import ValidationError

from src.chat.agentic.prompts.planner import PlannerPromptBuilder
from src.chat.agentic.schemas import PlanStep, QueryPlan

logger = logging.getLogger(__name__)

# Model for planning (use a capable but cost-effective model)
PLANNER_MODEL = "gpt-4o-mini"


class QueryPlanner:
    """
    LLM-based query planner for complex queries.

    Takes a user query and generates an execution plan consisting
    of multiple steps that can be run in parallel or sequentially.
    """

    def __init__(self, api_key: str | None = None) -> None:
        """
        Initialize the query planner.

        Args:
            api_key: OpenAI API key (uses env var if not provided)
        """
        self._api_key = api_key
        self._client: OpenAI | None = None
        self._prompt_builder = PlannerPromptBuilder()

    def _get_client(self) -> OpenAI:
        """Get or create the OpenAI client."""
        if self._client is None:
            self._client = OpenAI(api_key=self._api_key) if self._api_key else OpenAI()
        return self._client

    def plan(
        self,
        query: str,
        time_context: str | None = None,
        available_data_summary: dict[str, Any] | None = None,
    ) -> QueryPlan:
        """
        Generate an execution plan for a query.

        Args:
            query: The user's query string
            time_context: Optional description of time context
            available_data_summary: Optional summary of available data

        Returns:
            QueryPlan with executable steps

        Raises:
            ValueError: If planning fails after retries
        """
        messages = self._prompt_builder.build_messages(
            query=query,
            time_context=time_context,
            available_data_summary=available_data_summary,
        )

        # Try to generate and validate plan
        last_error = None
        for attempt in range(3):
            try:
                plan_json = self._call_planner_llm(messages)
                plan = self._parse_and_validate_plan(plan_json, query)
                logger.info(
                    f"Generated plan with {len(plan.steps)} steps for query: {query[:50]}..."
                )
                return plan
            except (json.JSONDecodeError, ValidationError, KeyError) as e:
                last_error = e
                logger.warning(f"Plan generation attempt {attempt + 1} failed: {e}")
                # Add error context for retry
                messages.append(
                    {
                        "role": "assistant",
                        "content": plan_json if "plan_json" in dir() else "{}",
                    }
                )
                messages.append(
                    {
                        "role": "user",
                        "content": f"The previous response had an error: {e}. Please fix and output valid JSON.",
                    }
                )

        # If all retries failed, create a fallback plan
        logger.error(f"Planning failed after retries: {last_error}")
        return self._create_fallback_plan(query)

    def _call_planner_llm(self, messages: list[dict[str, str]]) -> str:
        """
        Call the LLM to generate a plan.

        Args:
            messages: Chat messages for the API

        Returns:
            Raw JSON response string
        """
        client = self._get_client()

        response = client.chat.completions.create(
            model=PLANNER_MODEL,
            messages=messages,  # type: ignore
            response_format={"type": "json_object"},
            max_tokens=2000,
            temperature=0.2,  # Low temperature for consistent planning
        )

        return response.choices[0].message.content or "{}"

    def _parse_and_validate_plan(self, plan_json: str, query: str) -> QueryPlan:
        """
        Parse and validate the plan JSON.

        Args:
            plan_json: Raw JSON string from LLM
            query: Original query (for plan metadata)

        Returns:
            Validated QueryPlan

        Raises:
            json.JSONDecodeError: If JSON is invalid
            ValidationError: If plan doesn't match schema
        """
        data = json.loads(plan_json)

        # Add query if not present
        if "query" not in data:
            data["query"] = query

        # Generate plan_id if not present
        if "plan_id" not in data:
            data["plan_id"] = f"plan-{uuid.uuid4().hex[:8]}"

        # Ensure steps have step_ids
        for i, step in enumerate(data.get("steps", [])):
            if "step_id" not in step:
                step["step_id"] = f"s{i + 1}"

        # Validate with Pydantic
        plan = QueryPlan(**data)

        # Validate execution order (check for cycles)
        plan.get_execution_order()

        return plan

    def _create_fallback_plan(self, query: str) -> QueryPlan:
        """
        Create a fallback plan when LLM planning fails.

        Falls back to simple hierarchical search.

        Args:
            query: Original query

        Returns:
            Simple fallback QueryPlan
        """
        logger.info("Using fallback plan for query")

        return QueryPlan(
            plan_id=f"fallback-{uuid.uuid4().hex[:8]}",
            query=query,
            query_type="simple",
            reasoning="Fallback plan due to planning failure - using hierarchical search",
            steps=[
                PlanStep(
                    step_id="s1",
                    action="hierarchical_search",
                    params={"query": query, "max_days": 5},
                    depends_on=[],
                    required=True,
                    timeout_seconds=10.0,
                    description="Fallback hierarchical search",
                )
            ],
            estimated_time_seconds=10.0,
            requires_web_search=False,
        )

    def plan_for_type(
        self,
        query: str,
        query_type: str,
        time_filter_description: str | None = None,
    ) -> QueryPlan:
        """
        Generate a plan using predefined templates for known query types.

        This is faster than LLM planning for common patterns.

        Args:
            query: User query
            query_type: Detected query type
            time_filter_description: Optional time filter

        Returns:
            QueryPlan for the query type
        """
        plan_id = f"template-{uuid.uuid4().hex[:8]}"
        time_params = (
            {"time_filter": {"description": time_filter_description}}
            if time_filter_description
            else {}
        )

        if query_type == "relationship":
            return self._plan_relationship_query(query, plan_id, time_params)
        elif query_type == "memory_recall":
            return self._plan_memory_recall_query(query, plan_id, time_params)
        elif query_type == "comparison":
            return self._plan_comparison_query(query, plan_id)
        elif query_type == "correlation":
            return self._plan_correlation_query(query, plan_id, time_params)
        elif query_type == "web_augmented":
            return self._plan_web_augmented_query(query, plan_id, time_params)
        else:
            # Default to LLM planning
            return self.plan(query, time_filter_description)

    def _plan_relationship_query(
        self,
        query: str,
        plan_id: str,
        time_params: dict,
    ) -> QueryPlan:
        """Create a plan for relationship queries."""
        # Extract potential entity from query (simplified)
        # In production, would use NER or more sophisticated extraction
        return QueryPlan(
            plan_id=plan_id,
            query=query,
            query_type="relationship",
            reasoning="Relationship query - searching for co-occurring entities",
            steps=[
                PlanStep(
                    step_id="s1",
                    action="semantic_search",
                    params={"query": query, "limit": 10, **time_params},
                    depends_on=[],
                    required=True,
                    timeout_seconds=8.0,
                    description="Initial semantic search for relevant notes",
                ),
                PlanStep(
                    step_id="s2",
                    action="hierarchical_search",
                    params={"query": query, "max_days": 5, **time_params},
                    depends_on=[],
                    required=False,
                    timeout_seconds=10.0,
                    description="Hierarchical search for broader context",
                ),
                PlanStep(
                    step_id="s3",
                    action="merge_results",
                    params={"result_refs": ["s1", "s2"]},
                    depends_on=["s1", "s2"],
                    required=True,
                    timeout_seconds=2.0,
                    description="Merge search results",
                ),
            ],
            estimated_time_seconds=12.0,
            requires_web_search=False,
        )

    def _plan_memory_recall_query(
        self,
        query: str,
        plan_id: str,
        time_params: dict,
    ) -> QueryPlan:
        """Create a plan for memory recall queries."""
        return QueryPlan(
            plan_id=plan_id,
            query=query,
            query_type="memory_recall",
            reasoning="Memory recall - broad semantic search to find matching memories",
            steps=[
                PlanStep(
                    step_id="s1",
                    action="semantic_search",
                    params={"query": query, "limit": 15, **time_params},
                    depends_on=[],
                    required=True,
                    timeout_seconds=8.0,
                    description="Semantic search for memory fragments",
                ),
                PlanStep(
                    step_id="s2",
                    action="hierarchical_search",
                    params={"query": query, "max_days": 7, **time_params},
                    depends_on=[],
                    required=False,
                    timeout_seconds=10.0,
                    description="Hierarchical search for day context",
                ),
                PlanStep(
                    step_id="s3",
                    action="merge_results",
                    params={"result_refs": ["s1", "s2"]},
                    depends_on=["s1", "s2"],
                    required=True,
                    timeout_seconds=2.0,
                    description="Merge and deduplicate results",
                ),
            ],
            estimated_time_seconds=12.0,
            requires_web_search=False,
        )

    def _plan_comparison_query(
        self,
        query: str,
        plan_id: str,
    ) -> QueryPlan:
        """Create a plan for comparison queries."""
        # Would need to parse periods from query in production
        return QueryPlan(
            plan_id=plan_id,
            query=query,
            query_type="comparison",
            reasoning="Comparison query - gathering data from two periods",
            steps=[
                PlanStep(
                    step_id="s1",
                    action="semantic_search",
                    params={"query": query, "limit": 20},
                    depends_on=[],
                    required=True,
                    timeout_seconds=8.0,
                    description="Search for notes related to the comparison",
                ),
                PlanStep(
                    step_id="s2",
                    action="aggregates_query",
                    params={"key_type": "app", "limit": 10},
                    depends_on=[],
                    required=False,
                    timeout_seconds=3.0,
                    description="Get app usage aggregates",
                ),
                PlanStep(
                    step_id="s3",
                    action="aggregates_query",
                    params={"key_type": "category", "limit": 10},
                    depends_on=[],
                    required=False,
                    timeout_seconds=3.0,
                    description="Get category aggregates",
                ),
                PlanStep(
                    step_id="s4",
                    action="merge_results",
                    params={"result_refs": ["s1", "s2", "s3"]},
                    depends_on=["s1", "s2", "s3"],
                    required=True,
                    timeout_seconds=2.0,
                    description="Merge all comparison data",
                ),
            ],
            estimated_time_seconds=12.0,
            requires_web_search=False,
        )

    def _plan_correlation_query(
        self,
        query: str,
        plan_id: str,
        time_params: dict,
    ) -> QueryPlan:
        """Create a plan for correlation/pattern queries."""
        return QueryPlan(
            plan_id=plan_id,
            query=query,
            query_type="correlation",
            reasoning="Correlation query - finding patterns in activities",
            steps=[
                PlanStep(
                    step_id="s1",
                    action="semantic_search",
                    params={"query": query, "limit": 20, **time_params},
                    depends_on=[],
                    required=True,
                    timeout_seconds=8.0,
                    description="Search for relevant activity notes",
                ),
                PlanStep(
                    step_id="s2",
                    action="extract_patterns",
                    params={"pattern_type": "correlation", "notes_ref": "s1"},
                    depends_on=["s1"],
                    required=False,
                    timeout_seconds=8.0,
                    description="Extract behavioral patterns",
                ),
            ],
            estimated_time_seconds=16.0,
            requires_web_search=False,
        )

    def _plan_web_augmented_query(
        self,
        query: str,
        plan_id: str,
        time_params: dict,
    ) -> QueryPlan:
        """Create a plan for web-augmented queries."""
        return QueryPlan(
            plan_id=plan_id,
            query=query,
            query_type="web_augmented",
            reasoning="Web-augmented query - combining local notes with external search",
            steps=[
                PlanStep(
                    step_id="s1",
                    action="semantic_search",
                    params={"query": query, "limit": 10, **time_params},
                    depends_on=[],
                    required=True,
                    timeout_seconds=8.0,
                    description="Search local notes for context",
                ),
                PlanStep(
                    step_id="s2",
                    action="web_search",
                    params={"query": query, "max_results": 5},
                    depends_on=[],
                    required=False,
                    timeout_seconds=15.0,
                    description="Search web for external context",
                ),
                PlanStep(
                    step_id="s3",
                    action="merge_results",
                    params={"result_refs": ["s1", "s2"]},
                    depends_on=["s1", "s2"],
                    required=True,
                    timeout_seconds=2.0,
                    description="Merge local and web results",
                ),
            ],
            estimated_time_seconds=18.0,
            requires_web_search=True,
        )
