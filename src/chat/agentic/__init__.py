"""
Agentic Query Pipeline for Trace Chat

This module provides an advanced query processing pipeline that can handle
complex, multi-step queries by decomposing them into execution plans.

Key components:
- QueryClassifier: Detects if a query needs agentic handling
- QueryPlanner: LLM-based query decomposition into executable steps
- PlanExecutor: Executes plans with parallel steps and dependency tracking
- Actions: Atomic operations (search, graph traversal, analysis, web search)
"""

from src.chat.agentic.classifier import QueryClassifier
from src.chat.agentic.executor import ExecutionContext, ExecutionResult, PlanExecutor
from src.chat.agentic.planner import QueryPlanner
from src.chat.agentic.schemas import (
    PlanStep,
    QueryPlan,
    StepResult,
)

__all__ = [
    "QueryClassifier",
    "QueryPlanner",
    "PlanExecutor",
    "ExecutionContext",
    "ExecutionResult",
    "QueryPlan",
    "PlanStep",
    "StepResult",
]
