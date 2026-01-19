"""
Analysis Actions

Actions for analyzing retrieved data:
- Pattern extraction from notes
- Period comparison
- Temporal sequence analysis
- Result merging
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar

from src.chat.agentic.actions.base import Action, ActionRegistry, ExecutionContext
from src.chat.agentic.schemas import (
    ComparisonResult,
    PatternResult,
    StepResult,
    TemporalSequenceItem,
)
from src.core.paths import DB_PATH
from src.retrieval.aggregates import AggregatesLookup
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
class ExtractPatterns(Action):
    """Extract behavioral patterns from notes using LLM."""

    name: ClassVar[str] = "extract_patterns"
    default_timeout: ClassVar[float] = 8.0

    def __init__(
        self,
        db_path: Path | None = None,
        api_key: str | None = None,
    ) -> None:
        super().__init__(db_path, api_key)
        self._client = None

    def _get_client(self):
        """Get OpenAI client."""
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(api_key=self.api_key) if self.api_key else OpenAI()
        return self._client

    def execute(
        self,
        params: dict[str, Any],
        context: ExecutionContext,
    ) -> StepResult:
        """
        Extract patterns from notes.

        Params:
            pattern_type: Type of pattern to look for (post_activity, correlation, habit)
            focus_activity: Optional activity to focus on
            notes_ref: Optional step ID to get notes from (otherwise uses context)
        """
        start_time = time.time()
        step_id = params.get("step_id", "extract_patterns")

        try:
            pattern_type = params.get("pattern_type", "general")
            focus_activity = params.get("focus_activity")

            # Get notes from context or referenced step
            notes_ref = params.get("notes_ref")
            if notes_ref:
                ref_result = context.get_result(notes_ref)
                if ref_result and ref_result.result:
                    notes = ref_result.result.get("notes", [])
                else:
                    notes = []
            else:
                notes = context.get_all_notes()

            if not notes:
                return StepResult(
                    step_id=step_id,
                    action=self.name,
                    success=True,
                    result=PatternResult(
                        patterns=["Insufficient data to extract patterns"],
                        evidence_note_ids=[],
                        confidence=0.0,
                    ).to_dict(),
                    execution_time_ms=(time.time() - start_time) * 1000,
                )

            # Build prompt for pattern extraction
            notes_summary = self._summarize_notes_for_prompt(notes[:20])

            prompt = self._build_pattern_prompt(
                pattern_type=pattern_type,
                focus_activity=focus_activity,
                notes_summary=notes_summary,
            )

            client = self._get_client()
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an analyst extracting behavioral patterns from activity data. Output JSON.",
                    },
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                max_tokens=500,
                temperature=0.3,
            )

            response_text = response.choices[0].message.content or "{}"
            result_data = json.loads(response_text)

            patterns = result_data.get("patterns", [])
            confidence = result_data.get("confidence", 0.5)

            return StepResult(
                step_id=step_id,
                action=self.name,
                success=True,
                result=PatternResult(
                    patterns=patterns,
                    evidence_note_ids=[n.get("note_id", "") for n in notes[:10]],
                    confidence=confidence,
                ).to_dict(),
                execution_time_ms=(time.time() - start_time) * 1000,
            )

        except Exception as e:
            logger.error(f"Extract patterns failed: {e}")
            return StepResult(
                step_id=step_id,
                action=self.name,
                success=False,
                error=str(e),
                execution_time_ms=(time.time() - start_time) * 1000,
            )

    def _summarize_notes_for_prompt(self, notes: list[dict]) -> str:
        """Create a summarized view of notes for the prompt."""
        lines = []
        for note in notes:
            timestamp = note.get("start_ts", "")
            summary = note.get("summary", "")[:200]
            categories = note.get("categories", [])
            cat_str = ", ".join(categories[:3]) if categories else "uncategorized"
            lines.append(f"- [{timestamp}] ({cat_str}) {summary}")
        return "\n".join(lines)

    def _build_pattern_prompt(
        self,
        pattern_type: str,
        focus_activity: str | None,
        notes_summary: str,
    ) -> str:
        """Build the pattern extraction prompt."""
        focus_str = f" related to '{focus_activity}'" if focus_activity else ""

        return f"""Analyze the following activity notes and extract behavioral patterns{focus_str}.

Pattern type to focus on: {pattern_type}

Activity Notes:
{notes_summary}

Identify 2-5 meaningful patterns. Output JSON:
{{
  "patterns": ["Pattern 1 description", "Pattern 2 description", ...],
  "confidence": 0.0-1.0  // How confident are you in these patterns
}}

Focus on:
- Recurring behaviors
- Time-based correlations
- Activity sequences
- Habit formations"""


@ActionRegistry.register
class ComparePeriods(Action):
    """Compare activity data between two time periods."""

    name: ClassVar[str] = "compare_periods"
    default_timeout: ClassVar[float] = 10.0

    def __init__(
        self,
        db_path: Path | None = None,
        api_key: str | None = None,
    ) -> None:
        super().__init__(db_path, api_key)
        self._aggregates: AggregatesLookup | None = None
        self._client = None

    def _get_aggregates(self) -> AggregatesLookup:
        if self._aggregates is None:
            self._aggregates = AggregatesLookup(db_path=self.db_path or DB_PATH)
        return self._aggregates

    def _get_client(self):
        """Get OpenAI client."""
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(api_key=self.api_key) if self.api_key else OpenAI()
        return self._client

    def execute(
        self,
        params: dict[str, Any],
        context: ExecutionContext,
    ) -> StepResult:
        """
        Compare two time periods.

        Params:
            period_a: First time period (string or TimeFilter)
            period_b: Second time period (string or TimeFilter)
            focus: What to focus on (apps, topics, habits, etc.)
        """
        start_time = time.time()
        step_id = params.get("step_id", "compare_periods")

        try:
            period_a_param = params.get("period_a")
            period_b_param = params.get("period_b")

            if not period_a_param or not period_b_param:
                return StepResult(
                    step_id=step_id,
                    action=self.name,
                    success=False,
                    error="Both period_a and period_b are required",
                    execution_time_ms=(time.time() - start_time) * 1000,
                )

            # Parse time filters
            period_a = _parse_time_filter_param({"time_filter": period_a_param})
            period_b = _parse_time_filter_param({"time_filter": period_b_param})

            if not period_a or not period_b:
                return StepResult(
                    step_id=step_id,
                    action=self.name,
                    success=False,
                    error="Could not parse time periods",
                    execution_time_ms=(time.time() - start_time) * 1000,
                )

            focus = params.get("focus", "general")

            # Get aggregates for both periods
            aggregates = self._get_aggregates()

            period_a_data = {}
            period_b_data = {}

            for key_type in ["app", "topic", "category", "domain"]:
                a_result = aggregates.get_top_by_key_type(key_type, period_a, limit=5)
                b_result = aggregates.get_top_by_key_type(key_type, period_b, limit=5)

                period_a_data[key_type] = [
                    {"key": item.key, "minutes": item.value} for item in a_result.items
                ]
                period_b_data[key_type] = [
                    {"key": item.key, "minutes": item.value} for item in b_result.items
                ]

            # Use LLM to analyze differences
            differences, commonalities = self._analyze_comparison(
                period_a.description,
                period_b.description,
                period_a_data,
                period_b_data,
                focus,
            )

            result = ComparisonResult(
                period_a_description=period_a.description,
                period_b_description=period_b.description,
                period_a_data=period_a_data,
                period_b_data=period_b_data,
                differences=differences,
                commonalities=commonalities,
            )

            return StepResult(
                step_id=step_id,
                action=self.name,
                success=True,
                result=result.to_dict(),
                execution_time_ms=(time.time() - start_time) * 1000,
            )

        except Exception as e:
            logger.error(f"Compare periods failed: {e}")
            return StepResult(
                step_id=step_id,
                action=self.name,
                success=False,
                error=str(e),
                execution_time_ms=(time.time() - start_time) * 1000,
            )

    def _analyze_comparison(
        self,
        period_a_desc: str,
        period_b_desc: str,
        period_a_data: dict,
        period_b_data: dict,
        focus: str,
    ) -> tuple[list[str], list[str]]:
        """Use LLM to analyze the comparison data."""
        try:
            client = self._get_client()

            prompt = f"""Compare these two time periods and identify key differences and commonalities.

Period A ({period_a_desc}):
{json.dumps(period_a_data, indent=2)}

Period B ({period_b_desc}):
{json.dumps(period_b_data, indent=2)}

Focus area: {focus}

Output JSON:
{{
  "differences": ["Difference 1", "Difference 2", ...],
  "commonalities": ["Commonality 1", "Commonality 2", ...]
}}

Be specific and mention actual data values where relevant."""

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You analyze activity data comparisons. Output JSON.",
                    },
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                max_tokens=500,
                temperature=0.3,
            )

            response_text = response.choices[0].message.content or "{}"
            result_data = json.loads(response_text)

            return (
                result_data.get("differences", []),
                result_data.get("commonalities", []),
            )

        except Exception as e:
            logger.warning(f"LLM comparison analysis failed: {e}")
            # Fallback to basic comparison
            return self._basic_comparison(period_a_data, period_b_data)

    def _basic_comparison(
        self,
        period_a_data: dict,
        period_b_data: dict,
    ) -> tuple[list[str], list[str]]:
        """Basic comparison without LLM."""
        differences = []
        commonalities = []

        for key_type in period_a_data:
            a_keys = {item["key"] for item in period_a_data.get(key_type, [])}
            b_keys = {item["key"] for item in period_b_data.get(key_type, [])}

            only_a = a_keys - b_keys
            only_b = b_keys - a_keys
            common = a_keys & b_keys

            if only_a:
                differences.append(f"{key_type}: {', '.join(list(only_a)[:3])} only in period A")
            if only_b:
                differences.append(f"{key_type}: {', '.join(list(only_b)[:3])} only in period B")
            if common:
                commonalities.append(f"{key_type}: {', '.join(list(common)[:3])} in both periods")

        return differences, commonalities


@ActionRegistry.register
class TemporalSequence(Action):
    """Analyze temporal sequences of activities."""

    name: ClassVar[str] = "temporal_sequence"
    default_timeout: ClassVar[float] = 6.0

    def execute(
        self,
        params: dict[str, Any],
        context: ExecutionContext,
    ) -> StepResult:
        """
        Analyze activities before/after a given activity.

        Params:
            activity_filter: Activity or category to focus on
            sequence_type: "before" or "after"
            notes_ref: Optional step ID to get notes from
        """
        start_time = time.time()
        step_id = params.get("step_id", "temporal_sequence")

        try:
            activity_filter = params.get("activity_filter", "")
            sequence_type = params.get("sequence_type", "after")

            # Get notes from context
            notes_ref = params.get("notes_ref")
            if notes_ref:
                ref_result = context.get_result(notes_ref)
                if ref_result and ref_result.result:
                    notes = ref_result.result.get("notes", [])
                else:
                    notes = []
            else:
                notes = context.get_all_notes()

            if not notes:
                return StepResult(
                    step_id=step_id,
                    action=self.name,
                    success=True,
                    result={
                        "sequence_items": [],
                        "activity_filter": activity_filter,
                        "sequence_type": sequence_type,
                    },
                    execution_time_ms=(time.time() - start_time) * 1000,
                )

            # Sort notes by timestamp
            sorted_notes = sorted(
                notes,
                key=lambda n: n.get("start_ts", ""),
            )

            # Find notes matching the activity filter
            matching_indices = []
            for i, note in enumerate(sorted_notes):
                categories = note.get("categories", [])
                summary = note.get("summary", "").lower()
                if activity_filter.lower() in summary or activity_filter.lower() in [
                    c.lower() for c in categories
                ]:
                    matching_indices.append(i)

            # Get before/after notes
            sequence_items: list[dict] = []
            for idx in matching_indices:
                if sequence_type == "after" and idx + 1 < len(sorted_notes):
                    next_note = sorted_notes[idx + 1]
                    sequence_items.append(
                        TemporalSequenceItem(
                            timestamp=datetime.fromisoformat(next_note.get("start_ts", "")),
                            activity=next_note.get("summary", "")[:100],
                            category=", ".join(next_note.get("categories", [])[:2]),
                            note_id=next_note.get("note_id", ""),
                        ).to_dict()
                    )
                elif sequence_type == "before" and idx > 0:
                    prev_note = sorted_notes[idx - 1]
                    sequence_items.append(
                        TemporalSequenceItem(
                            timestamp=datetime.fromisoformat(prev_note.get("start_ts", "")),
                            activity=prev_note.get("summary", "")[:100],
                            category=", ".join(prev_note.get("categories", [])[:2]),
                            note_id=prev_note.get("note_id", ""),
                        ).to_dict()
                    )

            return StepResult(
                step_id=step_id,
                action=self.name,
                success=True,
                result={
                    "sequence_items": sequence_items,
                    "activity_filter": activity_filter,
                    "sequence_type": sequence_type,
                    "matches_found": len(matching_indices),
                },
                execution_time_ms=(time.time() - start_time) * 1000,
            )

        except Exception as e:
            logger.error(f"Temporal sequence failed: {e}")
            return StepResult(
                step_id=step_id,
                action=self.name,
                success=False,
                error=str(e),
                execution_time_ms=(time.time() - start_time) * 1000,
            )


@ActionRegistry.register
class MergeResults(Action):
    """Merge results from multiple steps."""

    name: ClassVar[str] = "merge_results"
    default_timeout: ClassVar[float] = 2.0

    def execute(
        self,
        params: dict[str, Any],
        context: ExecutionContext,
    ) -> StepResult:
        """
        Merge and deduplicate results from multiple steps.

        Params:
            result_refs: List of step IDs to merge results from
        """
        start_time = time.time()
        step_id = params.get("step_id", "merge_results")

        try:
            result_refs = params.get("result_refs", [])

            merged_notes: list[dict] = []
            merged_entities: list[dict] = []
            merged_aggregates: list[dict] = []
            seen_note_ids: set[str] = set()
            seen_entity_ids: set[str] = set()

            for ref in result_refs:
                ref_result = context.get_result(ref)
                if not ref_result or not ref_result.result:
                    continue

                data = ref_result.result
                if isinstance(data, dict):
                    # Merge notes
                    for note in data.get("notes", []):
                        note_id = note.get("note_id")
                        if note_id and note_id not in seen_note_ids:
                            seen_note_ids.add(note_id)
                            merged_notes.append(note)

                    # Merge entities
                    for entity in data.get("related_entities", []) + data.get("entities", []):
                        entity_id = entity.get("entity_id")
                        if entity_id and entity_id not in seen_entity_ids:
                            seen_entity_ids.add(entity_id)
                            merged_entities.append(entity)

                    # Merge aggregates
                    merged_aggregates.extend(data.get("aggregates", []))

            # Also include context-level accumulated data
            for note in context.get_all_notes():
                note_id = note.get("note_id")
                if note_id and note_id not in seen_note_ids:
                    seen_note_ids.add(note_id)
                    merged_notes.append(note)

            # Sort notes by timestamp (most recent first)
            merged_notes.sort(key=lambda n: n.get("start_ts", ""), reverse=True)

            return StepResult(
                step_id=step_id,
                action=self.name,
                success=True,
                result={
                    "notes": merged_notes,
                    "entities": merged_entities,
                    "aggregates": merged_aggregates,
                    "total_notes": len(merged_notes),
                    "total_entities": len(merged_entities),
                },
                execution_time_ms=(time.time() - start_time) * 1000,
            )

        except Exception as e:
            logger.error(f"Merge results failed: {e}")
            return StepResult(
                step_id=step_id,
                action=self.name,
                success=False,
                error=str(e),
                execution_time_ms=(time.time() - start_time) * 1000,
            )
