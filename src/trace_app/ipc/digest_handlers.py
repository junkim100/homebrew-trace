"""IPC handlers for Weekly Digest.

Provides handlers for:
- Generating weekly digests
- Sending digest notifications
- Getting digest history

P12-02: Weekly digest
"""

import logging
from typing import Any

from src.insights.digest import (
    generate_weekly_digest,
    get_digest_history,
    send_weekly_digest_notification,
)
from src.trace_app.ipc.server import handler

logger = logging.getLogger(__name__)


@handler("digest.current")
def handle_current_digest(params: dict[str, Any]) -> dict[str, Any]:
    """Get digest for current week."""
    try:
        return generate_weekly_digest(0)
    except Exception as e:
        logger.error(f"Failed to generate current week digest: {e}")
        return {"success": False, "error": str(e)}


@handler("digest.week")
def handle_week_digest(params: dict[str, Any]) -> dict[str, Any]:
    """Get digest for a specific week offset.

    Params:
        week_offset: 0 for current, 1 for last week, etc.
    """
    try:
        week_offset = params.get("week_offset", 1)
        return generate_weekly_digest(week_offset)
    except Exception as e:
        logger.error(f"Failed to generate week digest: {e}")
        return {"success": False, "error": str(e)}


@handler("digest.notify")
def handle_send_notification(params: dict[str, Any]) -> dict[str, Any]:
    """Send weekly digest notification.

    Params:
        week_offset: Week to generate digest for (default: 1)
    """
    try:
        week_offset = params.get("week_offset", 1)
        return send_weekly_digest_notification(week_offset)
    except Exception as e:
        logger.error(f"Failed to send digest notification: {e}")
        return {"success": False, "error": str(e)}


@handler("digest.history")
def handle_digest_history(params: dict[str, Any]) -> dict[str, Any]:
    """Get digest history for multiple weeks.

    Params:
        weeks: Number of weeks to include (default: 4)
    """
    try:
        weeks = params.get("weeks", 4)
        digests = get_digest_history(weeks)
        return {"success": True, "digests": digests}
    except Exception as e:
        logger.error(f"Failed to get digest history: {e}")
        return {"success": False, "error": str(e)}
