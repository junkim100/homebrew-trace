"""
Export/Backup Functionality for Trace

Exports all notes and graph data to portable formats:
- JSON archive with metadata, entities, and graph edges
- Markdown archive with all notes
- Combined archive (ZIP) with both

P10-02: Export/backup functionality
"""

import json
import logging
import shutil
import sqlite3
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.core.paths import NOTES_DIR
from src.db.migrations import get_connection

logger = logging.getLogger(__name__)


@dataclass
class ExportStats:
    """Statistics from an export operation."""

    notes_count: int
    entities_count: int
    edges_count: int
    export_path: str
    export_size_bytes: int
    export_time_seconds: float


class TraceExporter:
    """
    Exports Trace data to portable formats.

    Supports:
    - JSON metadata export (entities, edges, note metadata)
    - Markdown notes export (full note files)
    - Combined ZIP archive
    """

    def __init__(self, db_path: Path | str | None = None, notes_dir: Path | None = None):
        """
        Initialize the exporter.

        Args:
            db_path: Path to SQLite database
            notes_dir: Path to notes directory
        """
        self.db_path = Path(db_path) if db_path else None
        self.notes_dir = notes_dir or NOTES_DIR

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection."""
        return get_connection(self.db_path)

    def export_json(self, output_path: Path | str) -> ExportStats:
        """
        Export metadata to JSON format.

        Exports:
        - Notes metadata (id, type, timestamps, file path)
        - Entities (id, type, canonical name, aliases)
        - Graph edges (from, to, type, weight)
        - Aggregates

        Args:
            output_path: Path to output JSON file

        Returns:
            ExportStats with export details
        """
        start_time = datetime.now()
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        conn = self._get_connection()
        try:
            # Export notes metadata
            cursor = conn.execute(
                """
                SELECT note_id, note_type, start_ts, end_ts, file_path, created_ts
                FROM notes
                ORDER BY start_ts
                """
            )
            notes = [
                {
                    "note_id": row[0],
                    "note_type": row[1],
                    "start_ts": row[2],
                    "end_ts": row[3],
                    "file_path": row[4],
                    "created_ts": row[5],
                }
                for row in cursor.fetchall()
            ]

            # Export entities
            cursor = conn.execute(
                """
                SELECT entity_id, entity_type, canonical_name, aliases, created_ts
                FROM entities
                ORDER BY canonical_name
                """
            )
            entities = [
                {
                    "entity_id": row[0],
                    "entity_type": row[1],
                    "canonical_name": row[2],
                    "aliases": json.loads(row[3]) if row[3] else [],
                    "created_ts": row[4],
                }
                for row in cursor.fetchall()
            ]

            # Export note-entity associations
            cursor = conn.execute(
                """
                SELECT note_id, entity_id, strength, context
                FROM note_entities
                """
            )
            note_entities = [
                {
                    "note_id": row[0],
                    "entity_id": row[1],
                    "strength": row[2],
                    "context": row[3],
                }
                for row in cursor.fetchall()
            ]

            # Export edges
            cursor = conn.execute(
                """
                SELECT from_id, to_id, edge_type, weight, start_ts, end_ts, evidence_note_ids
                FROM edges
                ORDER BY weight DESC
                """
            )
            edges = [
                {
                    "from_id": row[0],
                    "to_id": row[1],
                    "edge_type": row[2],
                    "weight": row[3],
                    "start_ts": row[4],
                    "end_ts": row[5],
                    "evidence_note_ids": json.loads(row[6]) if row[6] else [],
                }
                for row in cursor.fetchall()
            ]

            # Export aggregates
            cursor = conn.execute(
                """
                SELECT period_type, period_start_ts, period_end_ts, key_type, key, value_num
                FROM aggregates
                ORDER BY period_start_ts, key_type
                """
            )
            aggregates = [
                {
                    "period_type": row[0],
                    "period_start_ts": row[1],
                    "period_end_ts": row[2],
                    "key_type": row[3],
                    "key": row[4],
                    "value": row[5],
                }
                for row in cursor.fetchall()
            ]

            # Build export structure
            export_data = {
                "export_version": "1.0",
                "exported_at": datetime.now().isoformat(),
                "source": "Trace",
                "counts": {
                    "notes": len(notes),
                    "entities": len(entities),
                    "edges": len(edges),
                    "aggregates": len(aggregates),
                },
                "notes": notes,
                "entities": entities,
                "note_entities": note_entities,
                "edges": edges,
                "aggregates": aggregates,
            }

            # Write JSON file
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)

            export_time = (datetime.now() - start_time).total_seconds()

            return ExportStats(
                notes_count=len(notes),
                entities_count=len(entities),
                edges_count=len(edges),
                export_path=str(output_path),
                export_size_bytes=output_path.stat().st_size,
                export_time_seconds=export_time,
            )

        finally:
            conn.close()

    def export_markdown(self, output_dir: Path | str) -> ExportStats:
        """
        Export all Markdown notes to a directory.

        Preserves the directory structure (YYYY/MM/DD/).

        Args:
            output_dir: Directory to export notes to

        Returns:
            ExportStats with export details
        """
        start_time = datetime.now()
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        notes_count = 0
        total_size = 0

        # Copy all markdown files preserving directory structure
        if self.notes_dir.exists():
            for md_file in self.notes_dir.rglob("*.md"):
                # Get relative path
                rel_path = md_file.relative_to(self.notes_dir)
                dest_path = output_dir / rel_path

                # Create destination directory
                dest_path.parent.mkdir(parents=True, exist_ok=True)

                # Copy file
                shutil.copy2(md_file, dest_path)
                notes_count += 1
                total_size += dest_path.stat().st_size

        export_time = (datetime.now() - start_time).total_seconds()

        return ExportStats(
            notes_count=notes_count,
            entities_count=0,
            edges_count=0,
            export_path=str(output_dir),
            export_size_bytes=total_size,
            export_time_seconds=export_time,
        )

    def export_archive(self, output_path: Path | str) -> ExportStats:
        """
        Export everything to a ZIP archive.

        Contains:
        - metadata.json (entities, edges, note metadata)
        - notes/ directory with all Markdown files

        Args:
            output_path: Path to output ZIP file

        Returns:
            ExportStats with export details
        """
        import tempfile

        start_time = datetime.now()
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Ensure .zip extension
        if not output_path.suffix == ".zip":
            output_path = output_path.with_suffix(".zip")

        notes_count = 0
        entities_count = 0
        edges_count = 0

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Export JSON metadata
            json_stats = self.export_json(temp_path / "metadata.json")
            entities_count = json_stats.entities_count
            edges_count = json_stats.edges_count

            # Export Markdown notes
            md_stats = self.export_markdown(temp_path / "notes")
            notes_count = md_stats.notes_count

            # Create ZIP archive
            with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                # Add metadata.json
                zipf.write(temp_path / "metadata.json", "metadata.json")

                # Add all notes
                notes_dir = temp_path / "notes"
                if notes_dir.exists():
                    for md_file in notes_dir.rglob("*.md"):
                        arcname = "notes" / md_file.relative_to(notes_dir)
                        zipf.write(md_file, arcname)

        export_time = (datetime.now() - start_time).total_seconds()

        return ExportStats(
            notes_count=notes_count,
            entities_count=entities_count,
            edges_count=edges_count,
            export_path=str(output_path),
            export_size_bytes=output_path.stat().st_size,
            export_time_seconds=export_time,
        )

    def get_export_summary(self) -> dict:
        """
        Get a summary of data that would be exported.

        Returns:
            Dictionary with counts of exportable data
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM notes")
            notes_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM entities")
            entities_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM edges")
            edges_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM aggregates")
            aggregates_count = cursor.fetchone()[0]

            # Count markdown files
            md_count = sum(1 for _ in self.notes_dir.rglob("*.md")) if self.notes_dir.exists() else 0

            # Estimate size
            md_size = (
                sum(f.stat().st_size for f in self.notes_dir.rglob("*.md"))
                if self.notes_dir.exists()
                else 0
            )

            return {
                "notes_in_db": notes_count,
                "markdown_files": md_count,
                "entities": entities_count,
                "edges": edges_count,
                "aggregates": aggregates_count,
                "estimated_markdown_size_bytes": md_size,
            }

        finally:
            conn.close()


def export_trace_data(
    output_path: str,
    format: str = "archive",
    db_path: str | None = None,
) -> dict:
    """
    Export Trace data to the specified format.

    Args:
        output_path: Path to output file or directory
        format: Export format ('json', 'markdown', 'archive')
        db_path: Optional database path

    Returns:
        Dictionary with export stats
    """
    exporter = TraceExporter(db_path=db_path)

    if format == "json":
        stats = exporter.export_json(output_path)
    elif format == "markdown":
        stats = exporter.export_markdown(output_path)
    elif format == "archive":
        stats = exporter.export_archive(output_path)
    else:
        raise ValueError(f"Unknown format: {format}")

    return {
        "success": True,
        "format": format,
        "notes_count": stats.notes_count,
        "entities_count": stats.entities_count,
        "edges_count": stats.edges_count,
        "export_path": stats.export_path,
        "export_size_bytes": stats.export_size_bytes,
        "export_time_seconds": stats.export_time_seconds,
    }


if __name__ == "__main__":
    import fire

    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    def summary():
        """Show summary of exportable data."""
        exporter = TraceExporter()
        return exporter.get_export_summary()

    def export_json(output: str):
        """Export to JSON format."""
        return export_trace_data(output, format="json")

    def export_markdown(output: str):
        """Export to Markdown directory."""
        return export_trace_data(output, format="markdown")

    def export_archive(output: str):
        """Export to ZIP archive."""
        return export_trace_data(output, format="archive")

    fire.Fire(
        {
            "summary": summary,
            "json": export_json,
            "markdown": export_markdown,
            "archive": export_archive,
        }
    )
