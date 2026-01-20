"""
IPC handlers for open loops functionality.

P10-03: Open loop tracking
"""

import logging
from typing import Any

from src.chat.open_loops import get_open_loops, get_open_loops_summary
from src.trace_app.ipc.server import handler

logger = logging.getLogger(__name__)


@handler("openloops.list")
def handle_list_open_loops(params: dict[str, Any]) -> dict[str, Any]:
    """
    List open loops from recent notes.

    Params:
        days_back: int (default 7) - How many days to look back
        limit: int (default 50) - Maximum number of loops

    Returns:
        {success, loops: [...], count}
    """
    days_back = params.get("days_back", 7)
    limit = params.get("limit", 50)

    try:
        loops = get_open_loops(days_back=days_back, limit=limit)

        return {
            "success": True,
            "loops": [
                {
                    "loop_id": loop.loop_id,
                    "description": loop.description,
                    "source_note_id": loop.source_note_id,
                    "source_note_path": loop.source_note_path,
                    "detected_at": loop.detected_at.isoformat(),
                    "context": loop.context,
                    "completed": loop.completed,
                }
                for loop in loops
            ],
            "count": len(loops),
        }

    except Exception as e:
        logger.exception("Failed to list open loops")
        return {
            "success": False,
            "error": str(e),
            "loops": [],
            "count": 0,
        }


@handler("openloops.summary")
def handle_open_loops_summary(params: dict[str, Any]) -> dict[str, Any]:
    """
    Get summary of open loops.

    Returns:
        {success, total_count, today_count, this_week_count, recent_loops}
    """
    try:
        summary = get_open_loops_summary()
        return {
            "success": True,
            **summary,
        }

    except Exception as e:
        logger.exception("Failed to get open loops summary")
        return {
            "success": False,
            "error": str(e),
            "total_count": 0,
            "today_count": 0,
            "this_week_count": 0,
            "days_with_loops": 0,
            "recent_loops": [],
        }
