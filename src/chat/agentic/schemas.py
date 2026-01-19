"""
Pydantic Schemas for Agentic Query Pipeline

Defines the data structures for query plans, execution steps, and results.
These schemas ensure type safety and validation for the planning and execution process.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class TimeFilterParam(BaseModel):
    """Time filter parameters for plan steps."""

    start: datetime | str | None = None
    end: datetime | str | None = None
    description: str | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "start": self.start.isoformat() if isinstance(self.start, datetime) else self.start,
            "end": self.end.isoformat() if isinstance(self.end, datetime) else self.end,
            "description": self.description,
        }


# Valid action types for plan steps
ActionType = Literal[
    "semantic_search",
    "entity_search",
    "graph_expand",
    "aggregates_query",
    "hierarchical_search",
    "time_range_notes",
    "find_connections",
    "get_co_occurrences",
    "get_entity_context",
    "compare_periods",
    "extract_patterns",
    "merge_results",
    "filter_by_edge_type",
    "temporal_sequence",
    "web_search",
]

# Valid query types that can trigger agentic processing
QueryType = Literal[
    "relationship",
    "memory_recall",
    "comparison",
    "correlation",
    "web_augmented",
    "multi_entity",
    "simple",
]


class PlanStep(BaseModel):
    """A single step in the execution plan."""

    step_id: str = Field(..., description="Unique step identifier")
    action: ActionType = Field(..., description="Action to execute")
    params: dict[str, Any] = Field(default_factory=dict, description="Action parameters")
    depends_on: list[str] = Field(default_factory=list, description="Step IDs this depends on")
    required: bool = Field(True, description="Whether failure should halt execution")
    timeout_seconds: float = Field(10.0, ge=1.0, le=30.0)
    description: str = Field(..., description="Human-readable step description")

    @field_validator("step_id", mode="before")
    @classmethod
    def generate_step_id(cls, v: str | None) -> str:
        """Generate step ID if not provided."""
        if not v:
            return f"s{uuid.uuid4().hex[:8]}"
        return v


class QueryPlan(BaseModel):
    """Complete execution plan for a complex query."""

    plan_id: str = Field(default_factory=lambda: f"plan-{uuid.uuid4().hex[:8]}")
    query: str = Field(..., description="Original user query")
    query_type: QueryType = Field(..., description="Detected query category")
    reasoning: str = Field(..., description="Why this plan was chosen")
    steps: list[PlanStep] = Field(..., min_length=1, max_length=10)
    estimated_time_seconds: float = Field(10.0, ge=0, le=30)
    requires_web_search: bool = Field(False)

    @field_validator("steps")
    @classmethod
    def validate_dependencies(cls, steps: list[PlanStep]) -> list[PlanStep]:
        """Ensure all dependencies reference valid step IDs."""
        step_ids = {s.step_id for s in steps}
        for step in steps:
            for dep in step.depends_on:
                if dep not in step_ids:
                    raise ValueError(f"Step {step.step_id} depends on unknown step {dep}")
        return steps

    def get_execution_order(self) -> list[list[str]]:
        """
        Get steps grouped by execution phase (parallel groups).

        Returns:
            List of step ID groups that can be executed in parallel.
        """
        remaining = {s.step_id: set(s.depends_on) for s in self.steps}
        completed: set[str] = set()
        phases: list[list[str]] = []

        while remaining:
            # Find steps with all dependencies met
            ready = [step_id for step_id, deps in remaining.items() if deps.issubset(completed)]

            if not ready:
                # Circular dependency detected
                raise ValueError(f"Circular dependency detected in steps: {remaining}")

            phases.append(ready)
            for step_id in ready:
                del remaining[step_id]
                completed.add(step_id)

        return phases

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "plan_id": self.plan_id,
            "query": self.query,
            "query_type": self.query_type,
            "reasoning": self.reasoning,
            "steps": [
                {
                    "step_id": s.step_id,
                    "action": s.action,
                    "params": s.params,
                    "depends_on": s.depends_on,
                    "required": s.required,
                    "timeout_seconds": s.timeout_seconds,
                    "description": s.description,
                }
                for s in self.steps
            ],
            "estimated_time_seconds": self.estimated_time_seconds,
            "requires_web_search": self.requires_web_search,
        }


@dataclass
class StepResult:
    """Result of executing a single plan step."""

    step_id: str
    action: str
    success: bool
    result: Any = None
    error: str | None = None
    execution_time_ms: float = 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "step_id": self.step_id,
            "action": self.action,
            "success": self.success,
            "result": self.result,
            "error": self.error,
            "execution_time_ms": self.execution_time_ms,
        }


@dataclass
class WebResult:
    """Result from a web search."""

    title: str
    url: str
    snippet: str
    relevance_score: float = 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "relevance_score": self.relevance_score,
        }


@dataclass
class WebCitation:
    """Citation for external web content."""

    url: str
    title: str
    accessed_at: datetime
    snippet: str

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "url": self.url,
            "title": self.title,
            "accessed_at": self.accessed_at.isoformat(),
            "snippet": self.snippet,
        }


@dataclass
class ComparisonResult:
    """Result of period comparison analysis."""

    period_a_description: str
    period_b_description: str
    period_a_data: dict[str, Any] = field(default_factory=dict)
    period_b_data: dict[str, Any] = field(default_factory=dict)
    differences: list[str] = field(default_factory=list)
    commonalities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "period_a_description": self.period_a_description,
            "period_b_description": self.period_b_description,
            "period_a_data": self.period_a_data,
            "period_b_data": self.period_b_data,
            "differences": self.differences,
            "commonalities": self.commonalities,
        }


@dataclass
class PatternResult:
    """Result of pattern extraction analysis."""

    patterns: list[str] = field(default_factory=list)
    evidence_note_ids: list[str] = field(default_factory=list)
    confidence: float = 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "patterns": self.patterns,
            "evidence_note_ids": self.evidence_note_ids,
            "confidence": self.confidence,
        }


@dataclass
class TemporalSequenceItem:
    """An item in a temporal sequence analysis."""

    timestamp: datetime
    activity: str
    category: str
    note_id: str

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "activity": self.activity,
            "category": self.category,
            "note_id": self.note_id,
        }


class ClassificationResult(BaseModel):
    """Result of query complexity classification."""

    is_complex: bool = Field(..., description="Whether query needs agentic handling")
    query_type: QueryType = Field(..., description="Detected query type")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Classification confidence")
    signals: list[str] = Field(default_factory=list, description="Detected complexity signals")
    reasoning: str = Field("", description="Why this classification was made")

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "is_complex": self.is_complex,
            "query_type": self.query_type,
            "confidence": self.confidence,
            "signals": self.signals,
            "reasoning": self.reasoning,
        }
