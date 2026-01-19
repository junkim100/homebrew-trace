"""
Plan Executor for Agentic Pipeline

Executes query plans by running steps in order, respecting dependencies,
and merging results. Supports parallel execution of independent steps.
"""

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.chat.agentic.actions.base import ActionRegistry, ExecutionContext
from src.chat.agentic.schemas import PlanStep, QueryPlan, StepResult

logger = logging.getLogger(__name__)

# Maximum total execution time for a plan
MAX_PLAN_TIMEOUT = 30.0

# Maximum workers for parallel execution
MAX_WORKERS = 4


@dataclass
class ExecutionResult:
    """Result of executing a complete plan."""

    plan_id: str
    query: str
    success: bool
    steps_completed: int
    steps_failed: int
    total_execution_time_ms: float
    merged_notes: list[dict[str, Any]] = field(default_factory=list)
    merged_entities: list[dict[str, Any]] = field(default_factory=list)
    aggregates: list[dict[str, Any]] = field(default_factory=list)
    web_results: list[dict[str, Any]] = field(default_factory=list)
    patterns: list[str] = field(default_factory=list)
    comparison: dict[str, Any] | None = None
    fallback_used: bool = False
    fallback_reason: str | None = None
    step_results: dict[str, StepResult] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "plan_id": self.plan_id,
            "query": self.query,
            "success": self.success,
            "steps_completed": self.steps_completed,
            "steps_failed": self.steps_failed,
            "total_execution_time_ms": self.total_execution_time_ms,
            "merged_notes": self.merged_notes,
            "merged_entities": self.merged_entities,
            "aggregates": self.aggregates,
            "web_results": self.web_results,
            "patterns": self.patterns,
            "comparison": self.comparison,
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason,
        }


class PlanExecutor:
    """
    Executes query plans with parallel step execution.

    Manages dependencies between steps, handles timeouts,
    and provides graceful degradation on failures.
    """

    def __init__(
        self,
        db_path: Path | None = None,
        api_key: str | None = None,
    ) -> None:
        """
        Initialize the plan executor.

        Args:
            db_path: Path to SQLite database
            api_key: OpenAI API key for actions that need LLM
        """
        self.db_path = db_path
        self.api_key = api_key

    def execute(self, plan: QueryPlan) -> ExecutionResult:
        """
        Execute a query plan.

        Args:
            plan: QueryPlan to execute

        Returns:
            ExecutionResult with merged results
        """
        start_time = time.time()

        context = ExecutionContext(
            db_path=self.db_path,
            api_key=self.api_key,
        )

        steps_completed = 0
        steps_failed = 0

        try:
            # Get execution phases (groups of steps that can run in parallel)
            phases = plan.get_execution_order()

            for phase in phases:
                # Check total timeout
                elapsed = time.time() - start_time
                if elapsed > MAX_PLAN_TIMEOUT:
                    logger.warning(f"Plan timeout reached after {elapsed:.1f}s")
                    break

                # Execute steps in this phase
                phase_results = self._execute_phase(phase, plan.steps, context)

                for step_id, result in phase_results.items():
                    context.add_result(step_id, result)
                    if result.success:
                        steps_completed += 1
                    else:
                        steps_failed += 1
                        # Check if this was a required step
                        step = next((s for s in plan.steps if s.step_id == step_id), None)
                        if step and step.required and not result.success:
                            logger.warning(f"Required step {step_id} failed: {result.error}")

            # Build final result
            return self._build_execution_result(
                plan=plan,
                context=context,
                start_time=start_time,
                steps_completed=steps_completed,
                steps_failed=steps_failed,
            )

        except Exception as e:
            logger.error(f"Plan execution failed: {e}")
            return ExecutionResult(
                plan_id=plan.plan_id,
                query=plan.query,
                success=False,
                steps_completed=steps_completed,
                steps_failed=steps_failed + 1,
                total_execution_time_ms=(time.time() - start_time) * 1000,
                fallback_used=True,
                fallback_reason=str(e),
            )

    def _execute_phase(
        self,
        phase_step_ids: list[str],
        all_steps: list[PlanStep],
        context: ExecutionContext,
    ) -> dict[str, StepResult]:
        """
        Execute a phase of steps (potentially in parallel).

        Args:
            phase_step_ids: Step IDs to execute in this phase
            all_steps: All steps in the plan
            context: Execution context

        Returns:
            Dict mapping step_id to StepResult
        """
        results: dict[str, StepResult] = {}

        # Get step objects
        steps = [s for s in all_steps if s.step_id in phase_step_ids]

        if len(steps) == 1:
            # Single step - execute directly
            step = steps[0]
            results[step.step_id] = self._execute_step(step, context)
        else:
            # Multiple steps - execute in parallel
            with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(steps))) as executor:
                future_to_step = {
                    executor.submit(self._execute_step, step, context): step for step in steps
                }

                for future in as_completed(future_to_step):
                    step = future_to_step[future]
                    try:
                        result = future.result(timeout=step.timeout_seconds)
                        results[step.step_id] = result
                    except TimeoutError:
                        results[step.step_id] = StepResult(
                            step_id=step.step_id,
                            action=step.action,
                            success=False,
                            error="Execution timeout",
                            execution_time_ms=step.timeout_seconds * 1000,
                        )
                    except Exception as e:
                        results[step.step_id] = StepResult(
                            step_id=step.step_id,
                            action=step.action,
                            success=False,
                            error=str(e),
                            execution_time_ms=0,
                        )

        return results

    def _execute_step(
        self,
        step: PlanStep,
        context: ExecutionContext,
    ) -> StepResult:
        """
        Execute a single step.

        Args:
            step: Step to execute
            context: Execution context

        Returns:
            StepResult
        """
        start_time = time.time()

        try:
            # Get the action
            action = ActionRegistry.create(
                name=step.action,
                db_path=self.db_path,
                api_key=self.api_key,
            )

            if action is None:
                return StepResult(
                    step_id=step.step_id,
                    action=step.action,
                    success=False,
                    error=f"Unknown action: {step.action}",
                    execution_time_ms=(time.time() - start_time) * 1000,
                )

            # Add step_id to params for tracking
            params = {**step.params, "step_id": step.step_id}

            # Execute the action
            result = action.execute(params, context)

            logger.debug(
                f"Step {step.step_id} ({step.action}) completed in {result.execution_time_ms:.1f}ms"
            )

            return result

        except Exception as e:
            logger.error(f"Step {step.step_id} failed: {e}")
            return StepResult(
                step_id=step.step_id,
                action=step.action,
                success=False,
                error=str(e),
                execution_time_ms=(time.time() - start_time) * 1000,
            )

    def _build_execution_result(
        self,
        plan: QueryPlan,
        context: ExecutionContext,
        start_time: float,
        steps_completed: int,
        steps_failed: int,
    ) -> ExecutionResult:
        """
        Build the final execution result from context.

        Args:
            plan: The executed plan
            context: Execution context with all results
            start_time: Plan start time
            steps_completed: Number of successful steps
            steps_failed: Number of failed steps

        Returns:
            ExecutionResult
        """
        total_time = (time.time() - start_time) * 1000

        # Extract accumulated data from context
        notes = context.get_all_notes()
        entities = context.get_all_entities()
        aggregates = context.get_all_aggregates()
        web_results = context.get_all_web_results()

        # Extract patterns and comparison from step results
        patterns: list[str] = []
        comparison: dict[str, Any] | None = None

        for result in context.get_all_results().values():
            if result.success and result.result:
                data = result.result
                if isinstance(data, dict):
                    if "patterns" in data:
                        patterns.extend(data["patterns"])
                    if "period_a_description" in data:  # Comparison result
                        comparison = data

        success = steps_completed > 0 or len(notes) > 0

        return ExecutionResult(
            plan_id=plan.plan_id,
            query=plan.query,
            success=success,
            steps_completed=steps_completed,
            steps_failed=steps_failed,
            total_execution_time_ms=total_time,
            merged_notes=notes,
            merged_entities=entities,
            aggregates=aggregates,
            web_results=web_results,
            patterns=patterns,
            comparison=comparison,
            fallback_used=False,
            step_results=context.get_all_results(),
        )

    async def execute_async(self, plan: QueryPlan) -> ExecutionResult:
        """
        Execute a plan asynchronously.

        Args:
            plan: QueryPlan to execute

        Returns:
            ExecutionResult
        """
        # For now, run synchronous executor in thread pool
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.execute, plan)
