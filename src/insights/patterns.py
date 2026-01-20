"""
Pattern Detection Module

Analyzes user activity to surface productivity patterns and insights.
Examples: "You code best in mornings", "Most productive on Tuesdays"

P12-03: Pattern detection
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from src.core.paths import DB_PATH
from src.db import get_connection

logger = logging.getLogger(__name__)


@dataclass
class Pattern:
    """A detected productivity pattern."""

    pattern_type: str  # time_of_day, day_of_week, app_sequence, focus_session
    description: str
    confidence: float  # 0.0 to 1.0
    data: dict  # Supporting data for the pattern


def detect_time_of_day_patterns(days_back: int = 30) -> list[Pattern]:
    """
    Detect when the user is most productive by time of day.

    Returns patterns like:
    - "You're most productive in the morning (9-12)"
    - "Your focus peaks around 10 AM"
    """
    db_path = DB_PATH
    conn = get_connection(db_path)
    patterns = []

    try:
        cutoff = (datetime.now() - timedelta(days=days_back)).isoformat()

        # Get activity by hour
        cursor = conn.execute(
            """
            SELECT
                CAST(strftime('%H', start_ts) AS INTEGER) as hour,
                COUNT(*) as event_count,
                COUNT(DISTINCT DATE(start_ts)) as active_days
            FROM events
            WHERE start_ts >= ?
              AND event_type = 'app'
            GROUP BY hour
            ORDER BY hour
            """,
            (cutoff,),
        )

        hourly_data = {row[0]: {"events": row[1], "days": row[2]} for row in cursor.fetchall()}

        if not hourly_data:
            return patterns

        # Calculate average events per active day for each hour
        hourly_avg = {}
        for hour, data in hourly_data.items():
            if data["days"] > 0:
                hourly_avg[hour] = data["events"] / data["days"]

        if not hourly_avg:
            return patterns

        # Find peak hours (top 3)
        sorted_hours = sorted(hourly_avg.items(), key=lambda x: x[1], reverse=True)
        peak_hours = [h[0] for h in sorted_hours[:3]]

        # Determine time of day category
        morning_activity = sum(hourly_avg.get(h, 0) for h in range(6, 12))
        afternoon_activity = sum(hourly_avg.get(h, 0) for h in range(12, 18))
        evening_activity = sum(hourly_avg.get(h, 0) for h in range(18, 24))
        night_activity = sum(hourly_avg.get(h, 0) for h in range(0, 6))

        total = morning_activity + afternoon_activity + evening_activity + night_activity
        if total == 0:
            return patterns

        # Morning person pattern
        if morning_activity / total > 0.4:
            patterns.append(
                Pattern(
                    pattern_type="time_of_day",
                    description="You're most productive in the morning (6 AM - 12 PM)",
                    confidence=min(morning_activity / total + 0.2, 1.0),
                    data={
                        "peak_period": "morning",
                        "peak_hours": peak_hours,
                        "morning_share": round(morning_activity / total * 100, 1),
                    },
                )
            )
        elif afternoon_activity / total > 0.4:
            patterns.append(
                Pattern(
                    pattern_type="time_of_day",
                    description="You're most productive in the afternoon (12 PM - 6 PM)",
                    confidence=min(afternoon_activity / total + 0.2, 1.0),
                    data={
                        "peak_period": "afternoon",
                        "peak_hours": peak_hours,
                        "afternoon_share": round(afternoon_activity / total * 100, 1),
                    },
                )
            )
        elif evening_activity / total > 0.4:
            patterns.append(
                Pattern(
                    pattern_type="time_of_day",
                    description="You're a night owl - most productive in the evening (6 PM - 12 AM)",
                    confidence=min(evening_activity / total + 0.2, 1.0),
                    data={
                        "peak_period": "evening",
                        "peak_hours": peak_hours,
                        "evening_share": round(evening_activity / total * 100, 1),
                    },
                )
            )

        # Peak hour pattern
        if peak_hours:
            peak_hour = peak_hours[0]
            hour_str = f"{peak_hour}:00" if peak_hour >= 10 else f"0{peak_hour}:00"
            patterns.append(
                Pattern(
                    pattern_type="peak_hour",
                    description=f"Your activity peaks around {hour_str}",
                    confidence=0.7,
                    data={
                        "peak_hour": peak_hour,
                        "hourly_distribution": hourly_avg,
                    },
                )
            )

    except Exception:
        logger.exception("Failed to detect time of day patterns")

    finally:
        conn.close()

    return patterns


def detect_day_of_week_patterns(days_back: int = 30) -> list[Pattern]:
    """
    Detect which days of the week are most productive.

    Returns patterns like:
    - "Tuesdays are your most productive day"
    - "You tend to work less on Fridays"
    """
    db_path = DB_PATH
    conn = get_connection(db_path)
    patterns = []

    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    try:
        cutoff = (datetime.now() - timedelta(days=days_back)).isoformat()

        # Get activity by day of week
        cursor = conn.execute(
            """
            SELECT
                CAST(strftime('%w', start_ts) AS INTEGER) as dow,
                COUNT(*) as event_count,
                COUNT(DISTINCT DATE(start_ts)) as weeks_active
            FROM events
            WHERE start_ts >= ?
              AND event_type = 'app'
            GROUP BY dow
            ORDER BY dow
            """,
            (cutoff,),
        )

        # SQLite %w: 0=Sunday, 1=Monday, ...
        dow_data = {}
        for row in cursor.fetchall():
            # Convert to Monday=0 format
            dow = (row[0] - 1) % 7
            dow_data[dow] = {"events": row[1], "weeks": row[2]}

        if not dow_data:
            return patterns

        # Calculate average events per week for each day
        dow_avg = {}
        for dow, data in dow_data.items():
            if data["weeks"] > 0:
                dow_avg[dow] = data["events"] / data["weeks"]

        if not dow_avg:
            return patterns

        # Find most and least productive days
        sorted_days = sorted(dow_avg.items(), key=lambda x: x[1], reverse=True)
        most_productive = sorted_days[0]
        least_productive = sorted_days[-1]

        # Most productive day pattern
        if most_productive[1] > least_productive[1] * 1.3:  # At least 30% more
            patterns.append(
                Pattern(
                    pattern_type="day_of_week",
                    description=f"{day_names[most_productive[0]]}s are your most productive day",
                    confidence=0.75,
                    data={
                        "most_productive_day": day_names[most_productive[0]],
                        "activity_level": round(most_productive[1], 1),
                        "daily_distribution": {
                            day_names[d]: round(v, 1) for d, v in dow_avg.items()
                        },
                    },
                )
            )

        # Weekend vs weekday pattern
        weekday_avg = (
            sum(dow_avg.get(d, 0) for d in range(5)) / 5 if any(d < 5 for d in dow_avg) else 0
        )
        weekend_avg = (
            sum(dow_avg.get(d, 0) for d in range(5, 7)) / 2 if any(d >= 5 for d in dow_avg) else 0
        )

        if weekday_avg > 0 and weekend_avg > 0:
            if weekday_avg > weekend_avg * 2:
                patterns.append(
                    Pattern(
                        pattern_type="work_pattern",
                        description="You maintain a strong work-life balance with clear weekday focus",
                        confidence=0.8,
                        data={
                            "weekday_avg": round(weekday_avg, 1),
                            "weekend_avg": round(weekend_avg, 1),
                            "ratio": round(weekday_avg / weekend_avg, 2),
                        },
                    )
                )
            elif weekend_avg > weekday_avg * 0.8:
                patterns.append(
                    Pattern(
                        pattern_type="work_pattern",
                        description="You stay active throughout the week, including weekends",
                        confidence=0.7,
                        data={
                            "weekday_avg": round(weekday_avg, 1),
                            "weekend_avg": round(weekend_avg, 1),
                            "ratio": round(weekday_avg / max(weekend_avg, 0.1), 2),
                        },
                    )
                )

    except Exception:
        logger.exception("Failed to detect day of week patterns")

    finally:
        conn.close()

    return patterns


def detect_app_patterns(days_back: int = 30) -> list[Pattern]:
    """
    Detect patterns in app usage.

    Returns patterns like:
    - "You spend most of your time in VS Code"
    - "After Slack, you often switch to Chrome"
    """
    db_path = DB_PATH
    conn = get_connection(db_path)
    patterns = []

    try:
        cutoff = (datetime.now() - timedelta(days=days_back)).isoformat()

        # Get top apps by time spent
        cursor = conn.execute(
            """
            SELECT
                app_name,
                bundle_id,
                SUM(
                    CAST(
                        (julianday(COALESCE(end_ts, datetime('now'))) - julianday(start_ts))
                        * 24 * 60 AS REAL
                    )
                ) as total_minutes
            FROM events
            WHERE start_ts >= ?
              AND event_type = 'app'
              AND app_name IS NOT NULL
            GROUP BY bundle_id
            ORDER BY total_minutes DESC
            LIMIT 10
            """,
            (cutoff,),
        )

        apps = [(row[0], row[1], row[2]) for row in cursor.fetchall()]

        if not apps:
            return patterns

        total_time = sum(a[2] for a in apps)

        # Top app pattern
        if apps and apps[0][2] / total_time > 0.2:
            top_app = apps[0]
            hours = top_app[2] / 60
            patterns.append(
                Pattern(
                    pattern_type="primary_app",
                    description=f"{top_app[0]} is your most-used app ({hours:.1f} hours in the last {days_back} days)",
                    confidence=0.85,
                    data={
                        "app_name": top_app[0],
                        "bundle_id": top_app[1],
                        "total_hours": round(hours, 1),
                        "share": round(top_app[2] / total_time * 100, 1),
                    },
                )
            )

        # Detect development vs communication balance
        dev_apps = ["VS Code", "Xcode", "IntelliJ", "PyCharm", "Terminal", "iTerm", "Code"]
        comm_apps = ["Slack", "Discord", "Teams", "Zoom", "Messages", "Mail"]

        dev_time = sum(a[2] for a in apps if any(d.lower() in a[0].lower() for d in dev_apps))
        comm_time = sum(a[2] for a in apps if any(c.lower() in a[0].lower() for c in comm_apps))

        if dev_time > 0 and comm_time > 0:
            ratio = dev_time / comm_time
            if ratio > 3:
                patterns.append(
                    Pattern(
                        pattern_type="work_balance",
                        description="You spend significantly more time coding than in meetings/chat",
                        confidence=0.7,
                        data={
                            "dev_hours": round(dev_time / 60, 1),
                            "comm_hours": round(comm_time / 60, 1),
                            "ratio": round(ratio, 2),
                        },
                    )
                )
            elif ratio < 0.5:
                patterns.append(
                    Pattern(
                        pattern_type="work_balance",
                        description="You spend more time in communication tools than coding",
                        confidence=0.7,
                        data={
                            "dev_hours": round(dev_time / 60, 1),
                            "comm_hours": round(comm_time / 60, 1),
                            "ratio": round(ratio, 2),
                        },
                    )
                )

    except Exception:
        logger.exception("Failed to detect app patterns")

    finally:
        conn.close()

    return patterns


def detect_focus_patterns(days_back: int = 30) -> list[Pattern]:
    """
    Detect focus session patterns.

    Returns patterns like:
    - "You have 3-4 deep focus sessions per day"
    - "Your average focus session lasts 45 minutes"
    """
    db_path = DB_PATH
    conn = get_connection(db_path)
    patterns = []

    try:
        cutoff = (datetime.now() - timedelta(days=days_back)).isoformat()

        # Find focus sessions (continuous activity on same app for 30+ minutes)
        cursor = conn.execute(
            """
            SELECT
                app_name,
                bundle_id,
                start_ts,
                end_ts,
                CAST(
                    (julianday(COALESCE(end_ts, datetime('now'))) - julianday(start_ts))
                    * 24 * 60 AS REAL
                ) as duration_minutes
            FROM events
            WHERE start_ts >= ?
              AND event_type = 'app'
              AND app_name IS NOT NULL
            ORDER BY start_ts
            """,
            (cutoff,),
        )

        events = cursor.fetchall()

        if not events:
            return patterns

        # Identify focus sessions (same app for 30+ minutes total in a window)
        focus_sessions = []
        current_app = None
        session_start = None
        session_duration = 0

        for _app_name, bundle_id, start_ts, _end_ts, duration in events:
            if current_app == bundle_id:
                session_duration += duration or 0
            else:
                # Save previous session if it was a focus session
                if current_app and session_duration >= 30:
                    focus_sessions.append(
                        {
                            "app": current_app,
                            "duration": session_duration,
                            "start": session_start,
                        }
                    )
                # Start new session
                current_app = bundle_id
                session_start = start_ts
                session_duration = duration or 0

        # Don't forget the last session
        if current_app and session_duration >= 30:
            focus_sessions.append(
                {
                    "app": current_app,
                    "duration": session_duration,
                    "start": session_start,
                }
            )

        if focus_sessions:
            avg_duration = sum(s["duration"] for s in focus_sessions) / len(focus_sessions)
            sessions_per_day = len(focus_sessions) / days_back

            if sessions_per_day >= 1:
                patterns.append(
                    Pattern(
                        pattern_type="focus_sessions",
                        description=f"You have about {sessions_per_day:.1f} deep focus sessions per day",
                        confidence=0.7,
                        data={
                            "sessions_per_day": round(sessions_per_day, 1),
                            "total_sessions": len(focus_sessions),
                            "avg_duration_minutes": round(avg_duration, 1),
                        },
                    )
                )

            if avg_duration >= 45:
                patterns.append(
                    Pattern(
                        pattern_type="focus_duration",
                        description=f"Your average focus session lasts {avg_duration:.0f} minutes - great for deep work!",
                        confidence=0.75,
                        data={
                            "avg_duration_minutes": round(avg_duration, 1),
                            "total_sessions": len(focus_sessions),
                        },
                    )
                )

    except Exception:
        logger.exception("Failed to detect focus patterns")

    finally:
        conn.close()

    return patterns


def get_all_patterns(days_back: int = 30) -> dict:
    """
    Detect all patterns and return them organized by type.

    Returns:
        Dictionary with success status and patterns by category
    """
    try:
        time_patterns = detect_time_of_day_patterns(days_back)
        day_patterns = detect_day_of_week_patterns(days_back)
        app_patterns = detect_app_patterns(days_back)
        focus_patterns = detect_focus_patterns(days_back)

        all_patterns = time_patterns + day_patterns + app_patterns + focus_patterns

        # Sort by confidence
        all_patterns.sort(key=lambda p: p.confidence, reverse=True)

        return {
            "success": True,
            "patterns": [
                {
                    "patternType": p.pattern_type,
                    "description": p.description,
                    "confidence": round(p.confidence, 2),
                    "data": p.data,
                }
                for p in all_patterns
            ],
            "patternCount": len(all_patterns),
            "daysAnalyzed": days_back,
        }

    except Exception as e:
        logger.exception("Failed to get all patterns")
        return {"success": False, "error": str(e)}


def get_insights_summary(days_back: int = 30) -> dict:
    """
    Get a concise summary of key insights.

    Returns:
        Dictionary with top 3 insights as human-readable strings
    """
    result = get_all_patterns(days_back)

    if not result.get("success"):
        return result

    patterns = result.get("patterns", [])

    # Get top 3 most confident patterns
    top_patterns = patterns[:3]

    return {
        "success": True,
        "insights": [p["description"] for p in top_patterns],
        "totalPatterns": len(patterns),
    }


if __name__ == "__main__":
    import fire

    def all(days_back: int = 30):
        """Get all detected patterns."""
        result = get_all_patterns(days_back)
        if result.get("success"):
            print(f"\nDetected {result['patternCount']} patterns from the last {days_back} days:\n")
            for p in result["patterns"]:
                print(f"  [{p['confidence']:.0%}] {p['description']}")
        else:
            print(f"Error: {result.get('error')}")

    def summary(days_back: int = 30):
        """Get insights summary."""
        result = get_insights_summary(days_back)
        if result.get("success"):
            print("\nTop Insights:\n")
            for i, insight in enumerate(result["insights"], 1):
                print(f"  {i}. {insight}")
        else:
            print(f"Error: {result.get('error')}")

    def time(days_back: int = 30):
        """Get time of day patterns."""
        patterns = detect_time_of_day_patterns(days_back)
        for p in patterns:
            print(f"  [{p.confidence:.0%}] {p.description}")

    def days(days_back: int = 30):
        """Get day of week patterns."""
        patterns = detect_day_of_week_patterns(days_back)
        for p in patterns:
            print(f"  [{p.confidence:.0%}] {p.description}")

    def apps(days_back: int = 30):
        """Get app usage patterns."""
        patterns = detect_app_patterns(days_back)
        for p in patterns:
            print(f"  [{p.confidence:.0%}] {p.description}")

    def focus(days_back: int = 30):
        """Get focus session patterns."""
        patterns = detect_focus_patterns(days_back)
        for p in patterns:
            print(f"  [{p.confidence:.0%}] {p.description}")

    fire.Fire(
        {
            "all": all,
            "summary": summary,
            "time": time,
            "days": days,
            "apps": apps,
            "focus": focus,
        }
    )
