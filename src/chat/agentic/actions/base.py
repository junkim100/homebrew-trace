"""
Base Action Interface and Registry

Defines the abstract base class for all actions and provides
a registry for action lookup during plan execution.
"""

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, ClassVar

from src.chat.agentic.schemas import StepResult

logger = logging.getLogger(__name__)


class ExecutionContext:
    """
    Shared context for plan execution.

    Stores results from completed steps and provides access to
    shared resources like database connections.
    """

    def __init__(
        self,
        db_path: Path | None = None,
        api_key: str | None = None,
    ) -> None:
        """
        Initialize execution context.

        Args:
            db_path: Path to SQLite database
            api_key: OpenAI API key for LLM calls
        """
        self.db_path = db_path
        self.api_key = api_key
        self._results: dict[str, StepResult] = {}
        self._notes: list[dict[str, Any]] = []
        self._entities: list[dict[str, Any]] = []
        self._aggregates: list[dict[str, Any]] = []
        self._web_results: list[dict[str, Any]] = []

    def add_result(self, step_id: str, result: StepResult) -> None:
        """Store a step result."""
        self._results[step_id] = result

        # Extract and accumulate notes, entities, aggregates
        if result.success and result.result:
            data = result.result
            if isinstance(data, dict):
                if "notes" in data:
                    self._notes.extend(data["notes"])
                if "entities" in data:
                    self._entities.extend(data["entities"])
                if "related_entities" in data:
                    self._entities.extend(data["related_entities"])
                if "aggregates" in data:
                    self._aggregates.extend(data["aggregates"])
                if "web_results" in data:
                    self._web_results.extend(data["web_results"])

    def get_result(self, step_id: str) -> StepResult | None:
        """Get a step result by ID."""
        return self._results.get(step_id)

    def get_all_results(self) -> dict[str, StepResult]:
        """Get all step results."""
        return self._results.copy()

    def get_all_notes(self) -> list[dict[str, Any]]:
        """Get all accumulated notes (deduplicated by note_id)."""
        seen: set[str] = set()
        unique_notes: list[dict[str, Any]] = []
        for note in self._notes:
            note_id = note.get("note_id")
            if note_id and note_id not in seen:
                seen.add(note_id)
                unique_notes.append(note)
        return unique_notes

    def get_all_entities(self) -> list[dict[str, Any]]:
        """Get all accumulated entities (deduplicated by entity_id)."""
        seen: set[str] = set()
        unique_entities: list[dict[str, Any]] = []
        for entity in self._entities:
            entity_id = entity.get("entity_id")
            if entity_id and entity_id not in seen:
                seen.add(entity_id)
                unique_entities.append(entity)
        return unique_entities

    def get_all_aggregates(self) -> list[dict[str, Any]]:
        """Get all accumulated aggregates."""
        return self._aggregates.copy()

    def get_all_web_results(self) -> list[dict[str, Any]]:
        """Get all web search results."""
        return self._web_results.copy()


class Action(ABC):
    """
    Abstract base class for all executable actions.

    Actions are atomic operations that can be composed into
    query execution plans. Each action wraps existing retrieval
    or analysis components.
    """

    # Action name used in plans
    name: ClassVar[str] = ""

    # Default timeout in seconds
    default_timeout: ClassVar[float] = 10.0

    def __init__(
        self,
        db_path: Path | None = None,
        api_key: str | None = None,
    ) -> None:
        """
        Initialize the action.

        Args:
            db_path: Path to SQLite database
            api_key: OpenAI API key for LLM calls
        """
        self.db_path = db_path
        self.api_key = api_key

    @abstractmethod
    def execute(
        self,
        params: dict[str, Any],
        context: ExecutionContext,
    ) -> StepResult:
        """
        Execute the action with given parameters.

        Args:
            params: Action-specific parameters
            context: Shared execution context with previous results

        Returns:
            StepResult with success status and result data
        """
        pass

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        """
        Validate action parameters.

        Args:
            params: Parameters to validate

        Returns:
            List of validation error messages (empty if valid)
        """
        return []


class ActionRegistry:
    """
    Registry of available actions for plan execution.

    Provides action lookup by name and manages action instantiation.
    """

    _actions: ClassVar[dict[str, type[Action]]] = {}

    @classmethod
    def register(cls, action_class: type[Action]) -> type[Action]:
        """
        Register an action class.

        Args:
            action_class: Action class to register

        Returns:
            The registered action class (for use as decorator)
        """
        if not action_class.name:
            raise ValueError(f"Action class {action_class.__name__} has no name")
        cls._actions[action_class.name] = action_class
        logger.debug(f"Registered action: {action_class.name}")
        return action_class

    @classmethod
    def get(cls, name: str) -> type[Action] | None:
        """
        Get an action class by name.

        Args:
            name: Action name

        Returns:
            Action class or None if not found
        """
        return cls._actions.get(name)

    @classmethod
    def create(
        cls,
        name: str,
        db_path: Path | None = None,
        api_key: str | None = None,
    ) -> Action | None:
        """
        Create an action instance by name.

        Args:
            name: Action name
            db_path: Path to SQLite database
            api_key: OpenAI API key

        Returns:
            Action instance or None if not found
        """
        action_class = cls.get(name)
        if action_class:
            return action_class(db_path=db_path, api_key=api_key)
        return None

    @classmethod
    def list_actions(cls) -> list[str]:
        """Get list of registered action names."""
        return list(cls._actions.keys())
