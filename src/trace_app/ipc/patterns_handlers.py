"""IPC handlers for Pattern Detection.

Provides handlers for:
- Getting all detected patterns
- Getting insights summary
- Getting specific pattern types

P12-03: Pattern detection
"""

import logging
from typing import Any

from src.insights.patterns import (
    detect_app_patterns,
    detect_day_of_week_patterns,
    detect_focus_patterns,
    detect_time_of_day_patterns,
    get_all_patterns,
    get_insights_summary,
)
from src.trace_app.ipc.server import handler

logger = logging.getLogger(__name__)


@handler("patterns.all")
def handle_all_patterns(params: dict[str, Any]) -> dict[str, Any]:
    """Get all detected patterns."""
    try:
        days_back = params.get("days_back", 30)
        return get_all_patterns(days_back)
    except Exception as e:
        logger.error(f"Failed to get all patterns: {e}")
        return {"success": False, "error": str(e)}


@handler("patterns.summary")
def handle_insights_summary(params: dict[str, Any]) -> dict[str, Any]:
    """Get insights summary (top 3 patterns).

    Params:
        days_back: Number of days to analyze (default: 30)
    """
    try:
        days_back = params.get("days_back", 30)
        return get_insights_summary(days_back)
    except Exception as e:
        logger.error(f"Failed to get insights summary: {e}")
        return {"success": False, "error": str(e)}


@handler("patterns.timeOfDay")
def handle_time_of_day_patterns(params: dict[str, Any]) -> dict[str, Any]:
    """Get time of day patterns.

    Params:
        days_back: Number of days to analyze (default: 30)
    """
    try:
        days_back = params.get("days_back", 30)
        patterns = detect_time_of_day_patterns(days_back)
        return {
            "success": True,
            "patterns": [
                {
                    "patternType": p.pattern_type,
                    "description": p.description,
                    "confidence": round(p.confidence, 2),
                    "data": p.data,
                }
                for p in patterns
            ],
        }
    except Exception as e:
        logger.error(f"Failed to get time of day patterns: {e}")
        return {"success": False, "error": str(e)}


@handler("patterns.dayOfWeek")
def handle_day_of_week_patterns(params: dict[str, Any]) -> dict[str, Any]:
    """Get day of week patterns.

    Params:
        days_back: Number of days to analyze (default: 30)
    """
    try:
        days_back = params.get("days_back", 30)
        patterns = detect_day_of_week_patterns(days_back)
        return {
            "success": True,
            "patterns": [
                {
                    "patternType": p.pattern_type,
                    "description": p.description,
                    "confidence": round(p.confidence, 2),
                    "data": p.data,
                }
                for p in patterns
            ],
        }
    except Exception as e:
        logger.error(f"Failed to get day of week patterns: {e}")
        return {"success": False, "error": str(e)}


@handler("patterns.apps")
def handle_app_patterns(params: dict[str, Any]) -> dict[str, Any]:
    """Get app usage patterns.

    Params:
        days_back: Number of days to analyze (default: 30)
    """
    try:
        days_back = params.get("days_back", 30)
        patterns = detect_app_patterns(days_back)
        return {
            "success": True,
            "patterns": [
                {
                    "patternType": p.pattern_type,
                    "description": p.description,
                    "confidence": round(p.confidence, 2),
                    "data": p.data,
                }
                for p in patterns
            ],
        }
    except Exception as e:
        logger.error(f"Failed to get app patterns: {e}")
        return {"success": False, "error": str(e)}


@handler("patterns.focus")
def handle_focus_patterns(params: dict[str, Any]) -> dict[str, Any]:
    """Get focus session patterns.

    Params:
        days_back: Number of days to analyze (default: 30)
    """
    try:
        days_back = params.get("days_back", 30)
        patterns = detect_focus_patterns(days_back)
        return {
            "success": True,
            "patterns": [
                {
                    "patternType": p.pattern_type,
                    "description": p.description,
                    "confidence": round(p.confidence, 2),
                    "data": p.data,
                }
                for p in patterns
            ],
        }
    except Exception as e:
        logger.error(f"Failed to get focus patterns: {e}")
        return {"success": False, "error": str(e)}
