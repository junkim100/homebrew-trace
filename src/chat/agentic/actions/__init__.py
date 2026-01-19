"""
Agentic Actions Module

Provides atomic operations that can be composed into query execution plans.
Each action wraps existing retrieval components with a standardized interface.
"""

from src.chat.agentic.actions.analysis import (
    ComparePeriods,
    ExtractPatterns,
    MergeResults,
    TemporalSequence,
)
from src.chat.agentic.actions.base import Action, ActionRegistry
from src.chat.agentic.actions.graph import (
    FindConnections,
    GetCoOccurrences,
    GetEntityContext,
    GraphExpand,
)
from src.chat.agentic.actions.retrieval import (
    AggregatesQuery,
    EntitySearch,
    HierarchicalSearch,
    SemanticSearch,
    TimeRangeNotes,
)
from src.chat.agentic.actions.web import WebSearch

__all__ = [
    # Base
    "Action",
    "ActionRegistry",
    # Retrieval
    "SemanticSearch",
    "EntitySearch",
    "HierarchicalSearch",
    "TimeRangeNotes",
    "AggregatesQuery",
    # Graph
    "GraphExpand",
    "FindConnections",
    "GetCoOccurrences",
    "GetEntityContext",
    # Analysis
    "ExtractPatterns",
    "ComparePeriods",
    "TemporalSequence",
    "MergeResults",
    # Web
    "WebSearch",
]
