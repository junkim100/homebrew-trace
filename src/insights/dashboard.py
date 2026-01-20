"""
Dashboard Analytics Provider

Provides data for the Activity Dashboard including:
- Time spent per app/topic
- Activity trends over time
- Heatmaps of activity patterns

P12-01: Activity dashboard
"""

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

from src.core.paths import DB_PATH
from src.db import get_connection

logger = logging.getLogger(__name__)


@dataclass
class AppUsage:
    """App usage statistics."""

    app_name: str
    bundle_id: str
    total_minutes: float
    session_count: int
    percentage: float


@dataclass
class TopicUsage:
    """Topic/entity usage statistics."""

    topic: str
    entity_type: str
    note_count: int
    mention_count: int


@dataclass
class HourlyActivity:
    """Activity count for a specific hour."""

    hour: int
    day_of_week: int  # 0=Monday, 6=Sunday
    activity_count: int
    avg_activity: float


def get_app_usage(days_back: int = 7, limit: int = 10) -> list[dict]:
    """
    Get app usage statistics for the time period.

    Args:
        days_back: Number of days to analyze
        limit: Maximum number of apps to return

    Returns:
        List of app usage dictionaries sorted by time spent
    """
    db_path = DB_PATH
    conn = get_connection(db_path)

    try:
        start_ts = (datetime.now() - timedelta(days=days_back)).isoformat()

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
                ) as total_minutes,
                COUNT(*) as session_count
            FROM events
            WHERE event_type = 'app'
              AND start_ts >= ?
              AND app_name IS NOT NULL
            GROUP BY bundle_id
            ORDER BY total_minutes DESC
            LIMIT ?
            """,
            (start_ts, limit),
        )

        results = []
        total_time = 0.0

        rows = cursor.fetchall()
        for row in rows:
            total_time += row[2] or 0

        for row in rows:
            minutes = row[2] or 0
            results.append(
                {
                    "appName": row[0],
                    "bundleId": row[1],
                    "totalMinutes": round(minutes, 1),
                    "sessionCount": row[3],
                    "percentage": round((minutes / total_time * 100) if total_time > 0 else 0, 1),
                }
            )

        return results

    except Exception:
        logger.exception("Failed to get app usage")
        return []

    finally:
        conn.close()


def get_topic_usage(days_back: int = 7, limit: int = 10) -> list[dict]:
    """
    Get topic/entity usage statistics.

    Args:
        days_back: Number of days to analyze
        limit: Maximum number of topics to return

    Returns:
        List of topic usage dictionaries
    """
    db_path = DB_PATH
    conn = get_connection(db_path)

    try:
        start_ts = (datetime.now() - timedelta(days=days_back)).isoformat()

        cursor = conn.execute(
            """
            SELECT
                e.canonical_name,
                e.entity_type,
                COUNT(DISTINCT ne.note_id) as note_count,
                SUM(ne.strength) as total_strength
            FROM entities e
            JOIN note_entities ne ON e.entity_id = ne.entity_id
            JOIN notes n ON ne.note_id = n.note_id
            WHERE n.start_ts >= ?
              AND e.entity_type IN ('topic', 'project', 'person', 'technology')
            GROUP BY e.entity_id
            ORDER BY note_count DESC, total_strength DESC
            LIMIT ?
            """,
            (start_ts, limit),
        )

        results = []
        for row in cursor.fetchall():
            results.append(
                {
                    "topic": row[0],
                    "entityType": row[1],
                    "noteCount": row[2],
                    "mentionStrength": round(row[3] or 0, 2),
                }
            )

        return results

    except Exception:
        logger.exception("Failed to get topic usage")
        return []

    finally:
        conn.close()


def get_activity_trend(days_back: int = 30) -> list[dict]:
    """
    Get daily activity trend over time.

    Args:
        days_back: Number of days to analyze

    Returns:
        List of daily activity counts
    """
    db_path = DB_PATH
    conn = get_connection(db_path)

    try:
        start_ts = (datetime.now() - timedelta(days=days_back)).isoformat()

        cursor = conn.execute(
            """
            SELECT
                date(start_ts) as day,
                COUNT(*) as event_count,
                COUNT(DISTINCT bundle_id) as unique_apps
            FROM events
            WHERE start_ts >= ?
              AND event_type = 'app'
            GROUP BY date(start_ts)
            ORDER BY day ASC
            """,
            (start_ts,),
        )

        results = []
        for row in cursor.fetchall():
            results.append(
                {
                    "date": row[0],
                    "eventCount": row[1],
                    "uniqueApps": row[2],
                }
            )

        return results

    except Exception:
        logger.exception("Failed to get activity trend")
        return []

    finally:
        conn.close()


def get_activity_heatmap(days_back: int = 30) -> list[dict]:
    """
    Get activity heatmap data (hour of day vs day of week).

    Args:
        days_back: Number of days to analyze

    Returns:
        List of heatmap cells with hour, day_of_week, and activity count
    """
    db_path = DB_PATH
    conn = get_connection(db_path)

    try:
        start_ts = (datetime.now() - timedelta(days=days_back)).isoformat()

        cursor = conn.execute(
            """
            SELECT
                CAST(strftime('%H', start_ts) AS INTEGER) as hour,
                CAST(strftime('%w', start_ts) AS INTEGER) as day_of_week,
                COUNT(*) as activity_count
            FROM events
            WHERE start_ts >= ?
              AND event_type = 'app'
            GROUP BY hour, day_of_week
            ORDER BY day_of_week, hour
            """,
            (start_ts,),
        )

        # Build complete grid (0-23 hours, 0-6 days)
        heatmap_data: dict[tuple[int, int], int] = defaultdict(int)
        for row in cursor.fetchall():
            hour = row[0]
            # Convert SQLite day_of_week (0=Sunday) to (0=Monday)
            dow = (row[1] - 1) % 7
            heatmap_data[(hour, dow)] = row[2]

        results = []
        for hour in range(24):
            for dow in range(7):
                results.append(
                    {
                        "hour": hour,
                        "dayOfWeek": dow,
                        "activityCount": heatmap_data[(hour, dow)],
                    }
                )

        return results

    except Exception:
        logger.exception("Failed to get activity heatmap")
        return []

    finally:
        conn.close()


def get_productivity_summary(days_back: int = 7) -> dict:
    """
    Get overall productivity summary.

    Args:
        days_back: Number of days to analyze

    Returns:
        Summary dictionary with key metrics
    """
    db_path = DB_PATH
    conn = get_connection(db_path)

    try:
        start_ts = (datetime.now() - timedelta(days=days_back)).isoformat()

        # Total active time
        cursor = conn.execute(
            """
            SELECT
                SUM(
                    CAST(
                        (julianday(COALESCE(end_ts, datetime('now'))) - julianday(start_ts))
                        * 24 * 60 AS REAL
                    )
                ) as total_minutes
            FROM events
            WHERE start_ts >= ?
              AND event_type = 'app'
            """,
            (start_ts,),
        )
        row = cursor.fetchone()
        total_minutes = row[0] or 0

        # Unique apps used
        cursor = conn.execute(
            """
            SELECT COUNT(DISTINCT bundle_id)
            FROM events
            WHERE start_ts >= ?
              AND event_type = 'app'
            """,
            (start_ts,),
        )
        unique_apps = cursor.fetchone()[0] or 0

        # Notes generated
        cursor = conn.execute(
            """
            SELECT COUNT(*)
            FROM notes
            WHERE start_ts >= ?
            """,
            (start_ts,),
        )
        notes_count = cursor.fetchone()[0] or 0

        # Entities extracted
        cursor = conn.execute(
            """
            SELECT COUNT(DISTINCT ne.entity_id)
            FROM note_entities ne
            JOIN notes n ON ne.note_id = n.note_id
            WHERE n.start_ts >= ?
            """,
            (start_ts,),
        )
        entities_count = cursor.fetchone()[0] or 0

        # Most productive hour (by activity count)
        cursor = conn.execute(
            """
            SELECT
                CAST(strftime('%H', start_ts) AS INTEGER) as hour,
                COUNT(*) as count
            FROM events
            WHERE start_ts >= ?
              AND event_type = 'app'
            GROUP BY hour
            ORDER BY count DESC
            LIMIT 1
            """,
            (start_ts,),
        )
        row = cursor.fetchone()
        most_productive_hour = row[0] if row else None

        return {
            "success": True,
            "totalMinutes": round(total_minutes, 1),
            "totalHours": round(total_minutes / 60, 1),
            "uniqueApps": unique_apps,
            "notesGenerated": notes_count,
            "entitiesExtracted": entities_count,
            "mostProductiveHour": most_productive_hour,
            "daysAnalyzed": days_back,
        }

    except Exception as e:
        logger.exception("Failed to get productivity summary")
        return {"success": False, "error": str(e)}

    finally:
        conn.close()


def get_dashboard_data(days_back: int = 7) -> dict:
    """
    Get all dashboard data in a single call.

    Args:
        days_back: Number of days to analyze

    Returns:
        Complete dashboard data
    """
    return {
        "success": True,
        "summary": get_productivity_summary(days_back),
        "appUsage": get_app_usage(days_back),
        "topicUsage": get_topic_usage(days_back),
        "activityTrend": get_activity_trend(days_back),
        "activityHeatmap": get_activity_heatmap(days_back),
    }


if __name__ == "__main__":
    import fire

    def summary(days: int = 7):
        """Get productivity summary."""
        result = get_productivity_summary(days)
        print(f"Total hours: {result.get('totalHours', 0)}")
        print(f"Unique apps: {result.get('uniqueApps', 0)}")
        print(f"Notes generated: {result.get('notesGenerated', 0)}")
        print(f"Most productive hour: {result.get('mostProductiveHour', 'N/A')}")

    def apps(days: int = 7, limit: int = 10):
        """Get app usage."""
        results = get_app_usage(days, limit)
        for app in results:
            print(f"  {app['appName']}: {app['totalMinutes']} min ({app['percentage']}%)")

    def topics(days: int = 7, limit: int = 10):
        """Get topic usage."""
        results = get_topic_usage(days, limit)
        for topic in results:
            print(f"  {topic['topic']} ({topic['entityType']}): {topic['noteCount']} notes")

    def heatmap(days: int = 30):
        """Get activity heatmap."""
        results = get_activity_heatmap(days)
        print(f"Heatmap cells: {len(results)}")

    fire.Fire({"summary": summary, "apps": apps, "topics": topics, "heatmap": heatmap})
