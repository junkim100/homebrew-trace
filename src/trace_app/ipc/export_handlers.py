"""IPC handlers for export/backup functionality.

Provides handlers for:
- Getting export summary
- Exporting to JSON, Markdown, or archive formats

P10-02: Export/backup functionality
"""

import logging
from pathlib import Path
from typing import Any

from src.core.export import TraceExporter, export_trace_data
from src.trace_app.ipc.server import handler

logger = logging.getLogger(__name__)


@handler("export.summary")
def handle_export_summary(params: dict[str, Any]) -> dict[str, Any]:
    """Get summary of exportable data.

    Returns counts of notes, entities, edges, and estimated size.
    """
    try:
        exporter = TraceExporter()
        summary = exporter.get_export_summary()

        return {
            "success": True,
            **summary,
        }
    except Exception as e:
        logger.error(f"Failed to get export summary: {e}")
        return {
            "success": False,
            "error": str(e),
        }


@handler("export.json")
def handle_export_json(params: dict[str, Any]) -> dict[str, Any]:
    """Export data to JSON format.

    Params:
        output_path: Path to output JSON file (required)
    """
    output_path = params.get("output_path")
    if not output_path:
        return {
            "success": False,
            "error": "Missing 'output_path' parameter",
        }

    try:
        result = export_trace_data(output_path, format="json")
        return result
    except Exception as e:
        logger.error(f"Failed to export JSON: {e}")
        return {
            "success": False,
            "error": str(e),
        }


@handler("export.markdown")
def handle_export_markdown(params: dict[str, Any]) -> dict[str, Any]:
    """Export notes to Markdown directory.

    Params:
        output_path: Path to output directory (required)
    """
    output_path = params.get("output_path")
    if not output_path:
        return {
            "success": False,
            "error": "Missing 'output_path' parameter",
        }

    try:
        result = export_trace_data(output_path, format="markdown")
        return result
    except Exception as e:
        logger.error(f"Failed to export Markdown: {e}")
        return {
            "success": False,
            "error": str(e),
        }


@handler("export.archive")
def handle_export_archive(params: dict[str, Any]) -> dict[str, Any]:
    """Export everything to a ZIP archive.

    Params:
        output_path: Path to output ZIP file (required)
    """
    output_path = params.get("output_path")
    if not output_path:
        return {
            "success": False,
            "error": "Missing 'output_path' parameter",
        }

    try:
        # Ensure .zip extension
        path = Path(output_path)
        if not path.suffix == ".zip":
            output_path = str(path.with_suffix(".zip"))

        result = export_trace_data(output_path, format="archive")
        return result
    except Exception as e:
        logger.error(f"Failed to export archive: {e}")
        return {
            "success": False,
            "error": str(e),
        }
