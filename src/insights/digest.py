"""
Weekly Digest Generator

Generates weekly summary reports with key insights and statistics.
Can deliver summaries via notifications or display in the UI.

P12-02: Weekly digest
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from src.core.paths import DB_PATH
from src.db import get_connection
from src.platform.notifications import send_notification

logger = logging.getLogger(__name__)


@dataclass
class WeeklyDigest:
    """Weekly activity digest."""

    week_start: datetime
    week_end: datetime
    total_hours: float
    unique_apps: int
    notes_generated: int
    top_apps: list[dict]
    top_topics: list[dict]
    productivity_score: float
    highlights: list[str]
    comparison_to_prev_week: dict


def generate_weekly_digest(week_offset: int = 0) -> dict:
    """
    Generate a weekly digest.

    Args:
        week_offset: 0 for current week, 1 for last week, etc.

    Returns:
        Weekly digest dictionary
    """
    db_path = DB_PATH
    conn = get_connection(db_path)

    try:
        # Calculate week boundaries (Monday to Sunday)
        today = datetime.now()
        # Go back to start of current week (Monday)
        days_since_monday = today.weekday()
        week_start = (today - timedelta(days=days_since_monday + (week_offset * 7))).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        week_end = week_start + timedelta(days=7)

        start_ts = week_start.isoformat()
        end_ts = week_end.isoformat()

        # Calculate previous week for comparison
        prev_week_start = week_start - timedelta(days=7)
        prev_week_end = week_start
        prev_start_ts = prev_week_start.isoformat()
        prev_end_ts = prev_week_end.isoformat()

        # Total active time this week
        cursor = conn.execute(
            """
            SELECT SUM(
                CAST(
                    (julianday(COALESCE(end_ts, datetime('now'))) - julianday(start_ts))
                    * 24 * 60 AS REAL
                )
            )
            FROM events
            WHERE start_ts >= ? AND start_ts < ?
              AND event_type = 'app'
            """,
            (start_ts, end_ts),
        )
        total_minutes = cursor.fetchone()[0] or 0
        total_hours = total_minutes / 60

        # Previous week total for comparison
        cursor = conn.execute(
            """
            SELECT SUM(
                CAST(
                    (julianday(COALESCE(end_ts, datetime('now'))) - julianday(start_ts))
                    * 24 * 60 AS REAL
                )
            )
            FROM events
            WHERE start_ts >= ? AND start_ts < ?
              AND event_type = 'app'
            """,
            (prev_start_ts, prev_end_ts),
        )
        prev_total_minutes = cursor.fetchone()[0] or 0
        prev_total_hours = prev_total_minutes / 60

        # Unique apps
        cursor = conn.execute(
            """
            SELECT COUNT(DISTINCT bundle_id)
            FROM events
            WHERE start_ts >= ? AND start_ts < ?
              AND event_type = 'app'
            """,
            (start_ts, end_ts),
        )
        unique_apps = cursor.fetchone()[0] or 0

        # Previous week unique apps
        cursor = conn.execute(
            """
            SELECT COUNT(DISTINCT bundle_id)
            FROM events
            WHERE start_ts >= ? AND start_ts < ?
              AND event_type = 'app'
            """,
            (prev_start_ts, prev_end_ts),
        )
        prev_unique_apps = cursor.fetchone()[0] or 0

        # Notes generated
        cursor = conn.execute(
            """
            SELECT COUNT(*)
            FROM notes
            WHERE start_ts >= ? AND start_ts < ?
            """,
            (start_ts, end_ts),
        )
        notes_count = cursor.fetchone()[0] or 0

        # Previous week notes
        cursor = conn.execute(
            """
            SELECT COUNT(*)
            FROM notes
            WHERE start_ts >= ? AND start_ts < ?
            """,
            (prev_start_ts, prev_end_ts),
        )
        prev_notes_count = cursor.fetchone()[0] or 0

        # Top 5 apps this week
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
            WHERE start_ts >= ? AND start_ts < ?
              AND event_type = 'app'
              AND app_name IS NOT NULL
            GROUP BY bundle_id
            ORDER BY total_minutes DESC
            LIMIT 5
            """,
            (start_ts, end_ts),
        )
        top_apps = [
            {"appName": row[0], "bundleId": row[1], "minutes": round(row[2] or 0, 1)}
            for row in cursor.fetchall()
        ]

        # Top 5 topics this week
        cursor = conn.execute(
            """
            SELECT
                e.canonical_name,
                e.entity_type,
                COUNT(DISTINCT ne.note_id) as note_count
            FROM entities e
            JOIN note_entities ne ON e.entity_id = ne.entity_id
            JOIN notes n ON ne.note_id = n.note_id
            WHERE n.start_ts >= ? AND n.start_ts < ?
              AND e.entity_type IN ('topic', 'project', 'technology')
            GROUP BY e.entity_id
            ORDER BY note_count DESC
            LIMIT 5
            """,
            (start_ts, end_ts),
        )
        top_topics = [
            {"topic": row[0], "entityType": row[1], "noteCount": row[2]}
            for row in cursor.fetchall()
        ]

        # Calculate productivity score (0-100)
        # Based on consistency (notes/day) and activity (hours/day)
        days_in_period = min(7, (datetime.now() - week_start).days + 1)
        notes_per_day = notes_count / max(days_in_period, 1)
        hours_per_day = total_hours / max(days_in_period, 1)

        # Score based on:
        # - Notes generated (target: 10 per day)
        # - Active hours (target: 8 per day)
        notes_score = min(notes_per_day / 10, 1) * 50
        hours_score = min(hours_per_day / 8, 1) * 50
        productivity_score = round(notes_score + hours_score, 1)

        # Generate highlights
        highlights = []

        if total_hours > prev_total_hours:
            pct_increase = ((total_hours - prev_total_hours) / max(prev_total_hours, 0.1)) * 100
            highlights.append(f"Active time increased by {pct_increase:.0f}% from last week")
        elif total_hours < prev_total_hours and prev_total_hours > 0:
            pct_decrease = ((prev_total_hours - total_hours) / prev_total_hours) * 100
            highlights.append(f"Active time decreased by {pct_decrease:.0f}% from last week")

        if top_apps:
            highlights.append(
                f"Most used app: {top_apps[0]['appName']} ({top_apps[0]['minutes']:.0f} min)"
            )

        if top_topics:
            highlights.append(f"Top focus area: {top_topics[0]['topic']}")

        if notes_count > prev_notes_count:
            highlights.append(
                f"Generated {notes_count - prev_notes_count} more notes than last week"
            )

        # Comparison data
        comparison = {
            "hoursChange": round(total_hours - prev_total_hours, 1),
            "hoursChangePercent": round(
                ((total_hours - prev_total_hours) / max(prev_total_hours, 0.1)) * 100, 1
            ),
            "appsChange": unique_apps - prev_unique_apps,
            "notesChange": notes_count - prev_notes_count,
        }

        return {
            "success": True,
            "weekStart": week_start.isoformat(),
            "weekEnd": week_end.isoformat(),
            "totalHours": round(total_hours, 1),
            "uniqueApps": unique_apps,
            "notesGenerated": notes_count,
            "topApps": top_apps,
            "topTopics": top_topics,
            "productivityScore": productivity_score,
            "highlights": highlights,
            "comparison": comparison,
        }

    except Exception as e:
        logger.exception("Failed to generate weekly digest")
        return {"success": False, "error": str(e)}

    finally:
        conn.close()


def send_weekly_digest_notification(week_offset: int = 1) -> dict:
    """
    Generate and send a weekly digest notification.

    Args:
        week_offset: Week to generate digest for (default: 1 = last week)

    Returns:
        Result dictionary
    """
    digest = generate_weekly_digest(week_offset)

    if not digest.get("success"):
        return digest

    # Build notification message
    title = "Trace Weekly Digest"

    lines = [
        f"Total active time: {digest['totalHours']:.1f} hours",
        f"Apps used: {digest['uniqueApps']}",
        f"Notes generated: {digest['notesGenerated']}",
    ]

    if digest["topApps"]:
        lines.append(f"Top app: {digest['topApps'][0]['appName']}")

    message = " | ".join(lines)

    # Send notification
    success = send_notification(
        title=title,
        message=message,
        subtitle=f"Week of {digest['weekStart'][:10]}",
        sound=False,
    )

    return {
        "success": success,
        "digest": digest,
        "notificationSent": success,
    }


def get_digest_history(weeks: int = 4) -> list[dict]:
    """
    Get digest history for the last N weeks.

    Args:
        weeks: Number of weeks to include

    Returns:
        List of weekly digests
    """
    digests = []
    for week_offset in range(1, weeks + 1):
        digest = generate_weekly_digest(week_offset)
        if digest.get("success"):
            digests.append(digest)
    return digests


if __name__ == "__main__":
    import fire

    def current():
        """Generate digest for current week."""
        digest = generate_weekly_digest(0)
        print("\nCurrent Week Digest")
        print(f"  Total hours: {digest.get('totalHours', 0):.1f}")
        print(f"  Apps used: {digest.get('uniqueApps', 0)}")
        print(f"  Notes: {digest.get('notesGenerated', 0)}")
        print(f"  Productivity: {digest.get('productivityScore', 0):.1f}/100")
        print("\nHighlights:")
        for h in digest.get("highlights", []):
            print(f"  - {h}")

    def last():
        """Generate digest for last week."""
        digest = generate_weekly_digest(1)
        print("\nLast Week Digest")
        print(f"  Total hours: {digest.get('totalHours', 0):.1f}")
        print(f"  Apps used: {digest.get('uniqueApps', 0)}")
        print(f"  Notes: {digest.get('notesGenerated', 0)}")
        print(f"  Productivity: {digest.get('productivityScore', 0):.1f}/100")

    def notify():
        """Send weekly digest notification."""
        result = send_weekly_digest_notification()
        print(f"Notification sent: {result.get('notificationSent', False)}")

    def history(weeks: int = 4):
        """Get digest history."""
        digests = get_digest_history(weeks)
        for d in digests:
            print(
                f"Week of {d['weekStart'][:10]}: {d['totalHours']:.1f}h, {d['notesGenerated']} notes"
            )

    fire.Fire({"current": current, "last": last, "notify": notify, "history": history})
