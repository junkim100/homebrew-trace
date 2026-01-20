"""
Open Loops Tracker

Queries and manages incomplete tasks/follow-ups from notes.
Surfaces "open loops" - things the user started but may not have finished.

P10-03: Open loop tracking
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from src.core.paths import get_db_path
from src.db.connection import get_connection

logger = logging.getLogger(__name__)


@dataclass
class OpenLoop:
    """An open loop extracted from notes."""

    loop_id: str
    description: str
    source_note_id: str
    source_note_path: str
    detected_at: datetime
    context: str | None = None
    completed: bool = False
    completed_at: datetime | None = None


def get_open_loops(
    days_back: int = 7,
    include_completed: bool = False,
    limit: int = 50,
) -> list[OpenLoop]:
    """
    Get open loops from recent notes.

    Args:
        days_back: How many days back to look
        include_completed: Whether to include completed loops
        limit: Maximum number of loops to return

    Returns:
        List of OpenLoop objects sorted by recency
    """
    db_path = get_db_path()
    conn = get_connection(db_path)

    try:
        # Calculate time range
        end_ts = datetime.now().isoformat()
        start_ts = (datetime.now() - timedelta(days=days_back)).isoformat()

        # Query notes with open_loops in their JSON payload
        cursor = conn.execute(
            """
            SELECT note_id, file_path, json_payload, start_ts
            FROM notes
            WHERE note_type = 'hour'
              AND start_ts >= ?
              AND start_ts <= ?
            ORDER BY start_ts DESC
            """,
            (start_ts, end_ts),
        )

        loops: list[OpenLoop] = []

        for row in cursor.fetchall():
            note_id = row[0]
            file_path = row[1]
            json_payload = row[2]
            note_ts = row[3]

            try:
                payload = json.loads(json_payload)
                open_loops = payload.get("open_loops", [])

                for idx, loop_text in enumerate(open_loops):
                    if not loop_text or not isinstance(loop_text, str):
                        continue

                    loop = OpenLoop(
                        loop_id=f"{note_id}:{idx}",
                        description=loop_text.strip(),
                        source_note_id=note_id,
                        source_note_path=file_path,
                        detected_at=datetime.fromisoformat(note_ts),
                        context=payload.get("summary"),
                        completed=False,
                    )
                    loops.append(loop)

            except json.JSONDecodeError:
                logger.warning(f"Failed to parse JSON for note {note_id}")
                continue

        # Sort by recency and limit
        loops.sort(key=lambda x: x.detected_at, reverse=True)

        # Deduplicate similar loops (same description from different hours)
        seen_descriptions: set[str] = set()
        unique_loops: list[OpenLoop] = []

        for loop in loops:
            # Normalize description for comparison
            normalized = loop.description.lower().strip()
            if normalized not in seen_descriptions:
                seen_descriptions.add(normalized)
                unique_loops.append(loop)

        return unique_loops[:limit]

    finally:
        conn.close()


def get_open_loops_summary() -> dict:
    """
    Get a summary of open loops.

    Returns:
        Dict with counts and recent loops
    """
    loops = get_open_loops(days_back=30, limit=100)

    # Group by day
    by_day: dict[str, list[OpenLoop]] = {}
    for loop in loops:
        day_key = loop.detected_at.strftime("%Y-%m-%d")
        if day_key not in by_day:
            by_day[day_key] = []
        by_day[day_key].append(loop)

    return {
        "total_count": len(loops),
        "today_count": len(by_day.get(datetime.now().strftime("%Y-%m-%d"), [])),
        "this_week_count": len(
            [loop for loop in loops if (datetime.now() - loop.detected_at).days < 7]
        ),
        "days_with_loops": len(by_day),
        "recent_loops": [
            {
                "loop_id": loop.loop_id,
                "description": loop.description,
                "source_note_id": loop.source_note_id,
                "detected_at": loop.detected_at.isoformat(),
                "context": loop.context,
            }
            for loop in loops[:10]
        ],
    }


if __name__ == "__main__":
    import fire

    def list_loops(days: int = 7, limit: int = 20):
        """List open loops from recent notes."""
        loops = get_open_loops(days_back=days, limit=limit)

        if not loops:
            print("No open loops found.")
            return

        print(f"\nFound {len(loops)} open loops:\n")

        for loop in loops:
            print(f"  [{loop.detected_at.strftime('%Y-%m-%d %H:%M')}]")
            print(f"    {loop.description}")
            print(f"    Source: {loop.source_note_path}")
            print()

    def summary():
        """Show open loops summary."""
        s = get_open_loops_summary()
        print("\nOpen Loops Summary:")
        print(f"  Total: {s['total_count']}")
        print(f"  Today: {s['today_count']}")
        print(f"  This week: {s['this_week_count']}")
        print(f"  Days with loops: {s['days_with_loops']}")
        print("\nRecent:")
        for loop in s["recent_loops"][:5]:
            print(f"  - {loop['description']}")

    fire.Fire({"list": list_loops, "summary": summary})
