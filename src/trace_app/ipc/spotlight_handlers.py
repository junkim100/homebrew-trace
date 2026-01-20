"""IPC handlers for Spotlight integration.

Provides handlers for:
- Getting Spotlight indexing status
- Reindexing notes for Spotlight
- Indexing individual notes

P11-01: Spotlight integration
"""

import logging
from typing import Any

from src.core.paths import get_notes_path
from src.platform.spotlight import (
    get_spotlight_status,
    index_note_for_spotlight,
    reindex_all_notes,
    trigger_spotlight_reindex,
)
from src.trace_app.ipc.server import handler

logger = logging.getLogger(__name__)


@handler("spotlight.status")
def handle_spotlight_status(params: dict[str, Any]) -> dict[str, Any]:
    """Get Spotlight indexing status."""
    try:
        notes_dir = get_notes_path()
        status = get_spotlight_status(notes_dir)
        return {
            "success": True,
            **status,
        }
    except Exception as e:
        logger.error(f"Failed to get Spotlight status: {e}")
        return {
            "success": False,
            "error": str(e),
        }


@handler("spotlight.reindex")
def handle_spotlight_reindex(params: dict[str, Any]) -> dict[str, Any]:
    """Reindex all notes for Spotlight."""
    try:
        notes_dir = get_notes_path()
        result = reindex_all_notes(notes_dir)

        # Also trigger mdimport
        trigger_spotlight_reindex(notes_dir)

        return {
            "success": True,
            **result,
        }
    except Exception as e:
        logger.error(f"Failed to reindex for Spotlight: {e}")
        return {
            "success": False,
            "error": str(e),
        }


@handler("spotlight.indexNote")
def handle_index_note(params: dict[str, Any]) -> dict[str, Any]:
    """Index a single note for Spotlight.

    Params:
        notePath: Path to the note file (required)
        title: Optional title for the note
        summary: Optional summary for the note
        entities: Optional list of entities/keywords
    """
    note_path = params.get("notePath")
    if not note_path:
        return {
            "success": False,
            "error": "Missing 'notePath' parameter",
        }

    title = params.get("title")
    summary = params.get("summary")
    entities = params.get("entities", [])

    try:
        success = index_note_for_spotlight(
            note_path=note_path,
            title=title,
            summary=summary,
            entities=entities,
        )

        return {"success": success}
    except Exception as e:
        logger.error(f"Failed to index note for Spotlight: {e}")
        return {
            "success": False,
            "error": str(e),
        }


@handler("spotlight.triggerReindex")
def handle_trigger_reindex(params: dict[str, Any]) -> dict[str, Any]:
    """Trigger Spotlight to reindex the notes directory using mdimport."""
    try:
        notes_dir = get_notes_path()
        success = trigger_spotlight_reindex(notes_dir)
        return {"success": success}
    except Exception as e:
        logger.error(f"Failed to trigger Spotlight reindex: {e}")
        return {
            "success": False,
            "error": str(e),
        }
