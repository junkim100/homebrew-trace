"""IPC handlers for Activity Dashboard.

Provides handlers for:
- Getting dashboard summary
- Getting app usage statistics
- Getting topic usage statistics
- Getting activity trends and heatmaps

P12-01: Activity dashboard
"""

import logging
from typing import Any

from src.insights.dashboard import (
    get_activity_heatmap,
    get_activity_trend,
    get_app_usage,
    get_dashboard_data,
    get_productivity_summary,
    get_topic_usage,
)
from src.trace_app.ipc.server import handler

logger = logging.getLogger(__name__)


@handler("dashboard.data")
def handle_dashboard_data(params: dict[str, Any]) -> dict[str, Any]:
    """Get all dashboard data in a single call."""
    try:
        days_back = params.get("days_back", 7)
        return get_dashboard_data(days_back)
    except Exception as e:
        logger.error(f"Failed to get dashboard data: {e}")
        return {"success": False, "error": str(e)}


@handler("dashboard.summary")
def handle_dashboard_summary(params: dict[str, Any]) -> dict[str, Any]:
    """Get productivity summary."""
    try:
        days_back = params.get("days_back", 7)
        return get_productivity_summary(days_back)
    except Exception as e:
        logger.error(f"Failed to get dashboard summary: {e}")
        return {"success": False, "error": str(e)}


@handler("dashboard.appUsage")
def handle_app_usage(params: dict[str, Any]) -> dict[str, Any]:
    """Get app usage statistics."""
    try:
        days_back = params.get("days_back", 7)
        limit = params.get("limit", 10)
        apps = get_app_usage(days_back, limit)
        return {"success": True, "apps": apps}
    except Exception as e:
        logger.error(f"Failed to get app usage: {e}")
        return {"success": False, "error": str(e)}


@handler("dashboard.topicUsage")
def handle_topic_usage(params: dict[str, Any]) -> dict[str, Any]:
    """Get topic/entity usage statistics."""
    try:
        days_back = params.get("days_back", 7)
        limit = params.get("limit", 10)
        topics = get_topic_usage(days_back, limit)
        return {"success": True, "topics": topics}
    except Exception as e:
        logger.error(f"Failed to get topic usage: {e}")
        return {"success": False, "error": str(e)}


@handler("dashboard.activityTrend")
def handle_activity_trend(params: dict[str, Any]) -> dict[str, Any]:
    """Get daily activity trend."""
    try:
        days_back = params.get("days_back", 30)
        trend = get_activity_trend(days_back)
        return {"success": True, "trend": trend}
    except Exception as e:
        logger.error(f"Failed to get activity trend: {e}")
        return {"success": False, "error": str(e)}


@handler("dashboard.heatmap")
def handle_activity_heatmap(params: dict[str, Any]) -> dict[str, Any]:
    """Get activity heatmap data."""
    try:
        days_back = params.get("days_back", 30)
        heatmap = get_activity_heatmap(days_back)
        return {"success": True, "heatmap": heatmap}
    except Exception as e:
        logger.error(f"Failed to get activity heatmap: {e}")
        return {"success": False, "error": str(e)}
