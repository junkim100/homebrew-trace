"""Insights module for analytics and pattern detection.

P12: Analytics & Insights
- P12-01: Activity dashboard
- P12-02: Weekly digest
- P12-03: Pattern detection
"""

from src.insights.dashboard import (
    get_activity_heatmap,
    get_activity_trend,
    get_app_usage,
    get_dashboard_data,
    get_productivity_summary,
    get_topic_usage,
)
from src.insights.digest import (
    generate_weekly_digest,
    get_digest_history,
    send_weekly_digest_notification,
)
from src.insights.patterns import (
    detect_app_patterns,
    detect_day_of_week_patterns,
    detect_focus_patterns,
    detect_time_of_day_patterns,
    get_all_patterns,
    get_insights_summary,
)

__all__ = [
    # Dashboard
    "get_dashboard_data",
    "get_productivity_summary",
    "get_app_usage",
    "get_topic_usage",
    "get_activity_trend",
    "get_activity_heatmap",
    # Digest
    "generate_weekly_digest",
    "send_weekly_digest_notification",
    "get_digest_history",
    # Patterns
    "get_all_patterns",
    "get_insights_summary",
    "detect_time_of_day_patterns",
    "detect_day_of_week_patterns",
    "detect_app_patterns",
    "detect_focus_patterns",
]
