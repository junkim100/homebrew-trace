"""IPC handlers for chat and retrieval functionality.

This module registers IPC handlers for the chat API, allowing the Electron
frontend to send queries and receive answers with citations.
"""

import logging
from typing import Any

from src.chat.api import ChatAPI, ChatRequest
from src.core.paths import NOTES_DIR
from src.trace_app.ipc.server import handler

logger = logging.getLogger(__name__)

# Singleton chat API instance
_chat_api: ChatAPI | None = None


def get_chat_api() -> ChatAPI:
    """Get or create the chat API instance."""
    global _chat_api
    if _chat_api is None:
        _chat_api = ChatAPI()
    return _chat_api


@handler("chat.query")
def handle_chat_query(params: dict[str, Any]) -> dict[str, Any]:
    """Handle a chat query from the frontend.

    Params:
        query: The user's question
        time_filter: Optional time filter hint (e.g., "today", "last week")
        include_graph_expansion: Whether to expand results using graph (default: True)
        include_aggregates: Whether to include aggregates (default: True)
        max_results: Maximum number of results to return (default: 10)

    Returns:
        ChatResponse as dict with answer, citations, notes, etc.
    """
    query = params.get("query")
    if not query:
        raise ValueError("query parameter is required")

    request = ChatRequest(
        query=query,
        time_filter_hint=params.get("time_filter"),
        include_graph_expansion=params.get("include_graph_expansion", True),
        include_aggregates=params.get("include_aggregates", True),
        max_results=params.get("max_results", 10),
    )

    api = get_chat_api()
    response = api.chat(request)
    return response.to_dict()


@handler("notes.read")
def handle_read_note(params: dict[str, Any]) -> dict[str, Any]:
    """Read the contents of a note file.

    Params:
        note_id: The note ID (format: YYYYMMDD-HH or YYYYMMDD for daily notes)

    Returns:
        {"content": str, "path": str} or {"error": str}
    """
    import re

    note_id = params.get("note_id")
    if not note_id:
        raise ValueError("note_id parameter is required")

    # Validate note_id format to prevent path traversal attacks
    # Must match YYYYMMDD-HH (hourly) or YYYYMMDD (daily)
    if not re.match(r"^\d{8}(-\d{2})?$", note_id):
        raise ValueError(f"Invalid note_id format: {note_id}")

    # Parse note_id to find the file
    # Format: YYYYMMDD-HH for hourly, YYYYMMDD for daily
    try:
        if "-" in note_id:
            # Hourly note: YYYYMMDD-HH
            date_part, hour = note_id.split("-")
            year = date_part[:4]
            month = date_part[4:6]
            day = date_part[6:8]
            # Validate hour is 00-23
            if not (0 <= int(hour) <= 23):
                raise ValueError(f"Invalid hour in note_id: {hour}")
            filename = f"hour-{note_id}.md"
        else:
            # Daily note: YYYYMMDD
            year = note_id[:4]
            month = note_id[4:6]
            day = note_id[6:8]
            filename = f"day-{note_id}.md"

        # Validate date components are reasonable
        if not (1 <= int(month) <= 12) or not (1 <= int(day) <= 31):
            raise ValueError(f"Invalid date in note_id: {note_id}")

        note_path = NOTES_DIR / year / month / day / filename

        # Validate that the resolved path stays within NOTES_DIR
        resolved_path = note_path.resolve()
        notes_dir_resolved = NOTES_DIR.resolve()
        if not resolved_path.is_relative_to(notes_dir_resolved):
            raise ValueError("Invalid note_id: path traversal detected")

        if not note_path.exists():
            raise FileNotFoundError(f"Note not found: {note_id}")

        content = note_path.read_text(encoding="utf-8")
        return {"content": content, "path": str(note_path)}

    except (ValueError, IndexError) as e:
        raise ValueError(f"Invalid note_id format: {note_id}") from e


@handler("notes.list")
def handle_list_notes(params: dict[str, Any]) -> dict[str, Any]:
    """List available notes, optionally filtered by date range.

    Params:
        start_date: Optional start date (YYYYMMDD format)
        end_date: Optional end date (YYYYMMDD format)
        limit: Maximum number of notes to return (default: 50)

    Returns:
        {"notes": [{"note_id": str, "timestamp": str, "type": str, "path": str}, ...]}
    """

    limit = params.get("limit", 50)
    start_date = params.get("start_date")
    end_date = params.get("end_date")

    notes = []

    # Walk the notes directory structure
    if not NOTES_DIR.exists():
        return {"notes": []}

    for year_dir in sorted(NOTES_DIR.iterdir(), reverse=True):
        if not year_dir.is_dir() or not year_dir.name.isdigit():
            continue

        for month_dir in sorted(year_dir.iterdir(), reverse=True):
            if not month_dir.is_dir() or not month_dir.name.isdigit():
                continue

            for day_dir in sorted(month_dir.iterdir(), reverse=True):
                if not day_dir.is_dir() or not day_dir.name.isdigit():
                    continue

                date_str = f"{year_dir.name}{month_dir.name}{day_dir.name}"

                # Apply date filters
                if start_date and date_str < start_date:
                    continue
                if end_date and date_str > end_date:
                    continue

                for note_file in sorted(day_dir.glob("*.md"), reverse=True):
                    name = note_file.stem
                    if name.startswith("hour-"):
                        note_id = name[5:]  # Remove "hour-" prefix
                        note_type = "hourly"
                    elif name.startswith("day-"):
                        note_id = name[4:]  # Remove "day-" prefix
                        note_type = "daily"
                    else:
                        continue

                    notes.append(
                        {
                            "note_id": note_id,
                            "type": note_type,
                            "path": str(note_file),
                            "date": date_str,
                        }
                    )

                    if len(notes) >= limit:
                        return {"notes": notes}

    return {"notes": notes}


def reset_chat_api():
    """Reset the chat API instance (called when API key changes)."""
    global _chat_api
    _chat_api = None
