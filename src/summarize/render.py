"""
Markdown Note Renderer for Trace

Converts validated JSON summaries to Markdown notes with YAML frontmatter.

Output format:
- YAML frontmatter with metadata
- Summary section
- Activities timeline
- Topics and learning
- Media consumption
- Co-activities
- Open loops (if any)

P5-06: Markdown note renderer
"""

import logging
from datetime import datetime
from pathlib import Path

from src.summarize.schemas import HourlySummarySchema

logger = logging.getLogger(__name__)


class MarkdownRenderer:
    """
    Renders hourly summaries to Markdown with YAML frontmatter.

    The output format is designed to be:
    - Human readable without Trace
    - Parseable by the app for metadata
    - Consistent with the PRD requirements
    """

    def __init__(self):
        """Initialize the renderer."""
        pass

    def render(
        self,
        summary: HourlySummarySchema,
        note_id: str,
        hour_start: datetime,
        hour_end: datetime,
        location: str | None = None,
    ) -> str:
        """
        Render a summary to Markdown.

        Args:
            summary: Validated HourlySummarySchema
            note_id: Unique identifier for the note
            hour_start: Start of the hour
            hour_end: End of the hour
            location: Location override (uses summary.location if not provided)

        Returns:
            Complete Markdown document with frontmatter
        """
        lines = []

        # Build frontmatter
        lines.append("---")
        lines.extend(self._build_frontmatter(summary, note_id, hour_start, hour_end, location))
        lines.append("---")
        lines.append("")

        # Title
        date_str = hour_start.strftime("%A, %B %d, %Y")
        time_range = f"{hour_start.strftime('%H:00')} - {hour_end.strftime('%H:00')}"
        lines.append(f"# {date_str} | {time_range}")
        lines.append("")

        # Summary section
        lines.append("## Summary")
        lines.append("")
        lines.append(summary.summary)
        lines.append("")

        # Activities section
        if summary.activities:
            lines.append("## Activities")
            lines.append("")
            for activity in summary.activities:
                time_str = f"{activity.time_start} - {activity.time_end}"
                app_str = f" ({activity.app})" if activity.app else ""
                lines.append(f"- **{time_str}**{app_str}: {activity.description}")
            lines.append("")

        # Topics and Learning section
        if summary.topics:
            lines.append("## Topics & Learning")
            lines.append("")
            for topic in summary.topics:
                confidence_str = (
                    f" ({int(topic.confidence * 100)}%)" if topic.confidence < 1.0 else ""
                )
                context_str = f" - {topic.context}" if topic.context else ""
                lines.append(f"- **{topic.name}**{confidence_str}{context_str}")
            lines.append("")

        # Documents section
        if summary.documents:
            lines.append("## Documents")
            lines.append("")
            for doc in summary.documents:
                doc_type = f" [{doc.type}]" if doc.type and doc.type != "other" else ""
                lines.append(f"- **{doc.name}**{doc_type}")
                if doc.key_content:
                    lines.append(f"  - {doc.key_content}")
            lines.append("")

        # Websites section
        if summary.websites:
            lines.append("## Websites Visited")
            lines.append("")
            for site in summary.websites:
                title_str = f" - {site.page_title}" if site.page_title else ""
                lines.append(f"- **{site.domain}**{title_str}")
                if site.purpose:
                    lines.append(f"  - Purpose: {site.purpose}")
            lines.append("")

        # Media section
        has_media = summary.media.listening or summary.media.watching
        if has_media:
            lines.append("## Media")
            lines.append("")

            if summary.media.listening:
                lines.append("### Listening")
                lines.append("")
                for item in summary.media.listening:
                    duration = ""
                    if item.duration_seconds:
                        minutes = item.duration_seconds // 60
                        duration = f" ({minutes}m)"
                    lines.append(f"- {item.artist} - *{item.track}*{duration}")
                lines.append("")

            if summary.media.watching:
                lines.append("### Watching")
                lines.append("")
                for item in summary.media.watching:
                    source = f" on {item.source}" if item.source else ""
                    duration = ""
                    if item.duration_seconds:
                        minutes = item.duration_seconds // 60
                        duration = f" ({minutes}m)"
                    lines.append(f"- *{item.title}*{source}{duration}")
                lines.append("")

        # Co-activities section
        if summary.co_activities:
            lines.append("## Co-Activities")
            lines.append("")
            for co in summary.co_activities:
                lines.append(f"- {co.primary} while {co.secondary}")
            lines.append("")

        # Open loops section
        if summary.open_loops:
            lines.append("## Open Loops")
            lines.append("")
            for loop in summary.open_loops:
                lines.append(f"- [ ] {loop}")
            lines.append("")

        # Location footer
        loc = location or summary.location
        if loc:
            lines.append("---")
            lines.append(f"*Location: {loc}*")
            lines.append("")

        return "\n".join(lines)

    def _build_frontmatter(
        self,
        summary: HourlySummarySchema,
        note_id: str,
        hour_start: datetime,
        hour_end: datetime,
        location: str | None,
    ) -> list[str]:
        """Build YAML frontmatter lines."""
        lines = []

        lines.append(f"id: {note_id}")
        lines.append("type: hour")
        lines.append(f"start_time: {hour_start.isoformat()}")
        lines.append(f"end_time: {hour_end.isoformat()}")

        # Location
        loc = location or summary.location
        if loc:
            # Escape quotes in location
            loc_escaped = loc.replace('"', '\\"')
            lines.append(f'location: "{loc_escaped}"')
        else:
            lines.append("location: null")

        # Categories
        if summary.categories:
            lines.append("categories:")
            for cat in summary.categories:
                lines.append(f"  - {cat}")
        else:
            lines.append("categories: []")

        # Entities (simplified for frontmatter)
        if summary.entities:
            lines.append("entities:")
            for entity in summary.entities:
                # Escape special characters
                name_escaped = entity.name.replace('"', '\\"')
                lines.append(f'  - name: "{name_escaped}"')
                lines.append(f"    type: {entity.type}")
                lines.append(f"    confidence: {entity.confidence:.2f}")
        else:
            lines.append("entities: []")

        lines.append(f"schema_version: {summary.schema_version}")

        return lines

    def render_to_file(
        self,
        summary: HourlySummarySchema,
        note_id: str,
        hour_start: datetime,
        hour_end: datetime,
        file_path: Path,
        location: str | None = None,
    ) -> bool:
        """
        Render a summary and save to file.

        Args:
            summary: Validated HourlySummarySchema
            note_id: Unique identifier for the note
            hour_start: Start of the hour
            hour_end: End of the hour
            file_path: Path to save the file
            location: Optional location override

        Returns:
            True if saved successfully
        """
        try:
            # Ensure parent directory exists
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Render content
            content = self.render(summary, note_id, hour_start, hour_end, location)

            # Write to file
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

            logger.info(f"Saved note to {file_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to save note to {file_path}: {e}")
            return False


def parse_frontmatter(markdown_content: str) -> tuple[dict, str]:
    """
    Parse YAML frontmatter from Markdown content.

    Args:
        markdown_content: Complete Markdown file content

    Returns:
        Tuple of (frontmatter dict, body content)
    """
    import yaml

    if not markdown_content.startswith("---"):
        return {}, markdown_content

    # Find the closing ---
    lines = markdown_content.split("\n")
    end_idx = None
    for i, line in enumerate(lines[1:], 1):
        if line.strip() == "---":
            end_idx = i
            break

    if end_idx is None:
        return {}, markdown_content

    # Parse frontmatter
    frontmatter_text = "\n".join(lines[1:end_idx])
    try:
        frontmatter = yaml.safe_load(frontmatter_text) or {}
    except yaml.YAMLError:
        frontmatter = {}

    # Get body
    body = "\n".join(lines[end_idx + 1 :])

    return frontmatter, body


if __name__ == "__main__":
    import json
    import uuid

    import fire

    from src.summarize.schemas import HourlySummarySchema

    def demo():
        """Generate a demo Markdown note."""
        # Create sample summary
        summary = HourlySummarySchema(
            schema_version=1,
            summary="The user spent the hour coding a Python project in VS Code, reviewing pull requests on GitHub, and listening to lo-fi beats on Spotify.",
            categories=["work", "browsing", "entertainment"],
            activities=[
                {
                    "time_start": "14:00",
                    "time_end": "14:25",
                    "description": "Writing Python code for the Trace project",
                    "app": "VS Code",
                    "category": "work",
                },
                {
                    "time_start": "14:25",
                    "time_end": "14:45",
                    "description": "Reviewing pull requests and code changes",
                    "app": "Safari",
                    "category": "work",
                },
                {
                    "time_start": "14:45",
                    "time_end": "15:00",
                    "description": "Reading documentation about async Python",
                    "app": "Safari",
                    "category": "learning",
                },
            ],
            topics=[
                {
                    "name": "Python async/await",
                    "context": "Learning about asyncio patterns",
                    "confidence": 0.85,
                },
                {
                    "name": "Database migrations",
                    "context": "Working on schema updates",
                    "confidence": 0.9,
                },
            ],
            entities=[
                {"name": "VS Code", "type": "app", "confidence": 0.95},
                {"name": "GitHub", "type": "domain", "confidence": 0.9},
                {"name": "Python", "type": "topic", "confidence": 0.95},
                {"name": "Trace", "type": "project", "confidence": 0.9},
            ],
            media={
                "listening": [
                    {"artist": "Lofi Girl", "track": "Chill Study Beats", "duration_seconds": 1800}
                ],
                "watching": [],
            },
            documents=[
                {
                    "name": "asyncio_guide.pdf",
                    "type": "pdf",
                    "key_content": "Python asyncio patterns and best practices",
                }
            ],
            websites=[
                {"domain": "github.com", "page_title": "Pull Requests", "purpose": "Code review"},
                {"domain": "docs.python.org", "page_title": "asyncio", "purpose": "Documentation"},
            ],
            co_activities=[
                {
                    "primary": "Coding Python",
                    "secondary": "Listening to lo-fi beats",
                    "relationship": "worked_while",
                }
            ],
            open_loops=[
                "Need to finish the schema migration tests",
                "Review the edge case handling",
            ],
            location="San Francisco, CA",
        )

        # Render
        renderer = MarkdownRenderer()
        hour_start = datetime(2025, 1, 15, 14, 0, 0)
        hour_end = datetime(2025, 1, 15, 15, 0, 0)
        note_id = str(uuid.uuid4())

        markdown = renderer.render(summary, note_id, hour_start, hour_end)
        print(markdown)

    def render_json(json_file: str, output_file: str | None = None):
        """Render a JSON summary file to Markdown."""
        with open(json_file) as f:
            data = json.load(f)

        summary = HourlySummarySchema.model_validate(data)

        renderer = MarkdownRenderer()
        hour_start = datetime.now().replace(minute=0, second=0, microsecond=0)
        hour_end = hour_start.replace(hour=hour_start.hour + 1)
        note_id = str(uuid.uuid4())

        markdown = renderer.render(summary, note_id, hour_start, hour_end)

        if output_file:
            with open(output_file, "w") as f:
                f.write(markdown)
            print(f"Saved to {output_file}")
        else:
            print(markdown)

    fire.Fire({"demo": demo, "render": render_json})
