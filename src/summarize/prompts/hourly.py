"""
Hourly Summarization Prompt for Trace

Structured prompt for gpt-5-mini to generate hourly notes.
Outputs strict JSON conforming to a versioned schema.

P5-04: Hourly summarization prompt
"""

from datetime import datetime

from src.summarize.evidence import EvidenceAggregator, HourlyEvidence
from src.summarize.keyframes import SelectedKeyframe

# Schema version for output validation
SCHEMA_VERSION = 1

# Model for hourly summarization
HOURLY_MODEL = "gpt-5-mini-2025-08-07"

HOURLY_SCHEMA_DESCRIPTION = """
{
  "schema_version": 1,
  "summary": "2-3 sentence overview of the hour's activities",
  "categories": ["list", "of", "activity", "categories"],
  "activities": [
    {
      "time_start": "HH:MM",
      "time_end": "HH:MM",
      "description": "What the user was doing",
      "app": "Application name",
      "category": "work|learning|entertainment|communication|creative|browsing|other"
    }
  ],
  "topics": [
    {
      "name": "Topic or subject",
      "context": "How/why it was encountered",
      "confidence": 0.0-1.0
    }
  ],
  "entities": [
    {
      "name": "Entity name",
      "type": "topic|app|domain|document|artist|track|video|game|person|project",
      "confidence": 0.0-1.0
    }
  ],
  "media": {
    "listening": [{"artist": "...", "track": "...", "duration_seconds": 123}],
    "watching": [{"title": "...", "source": "...", "duration_seconds": 123}]
  },
  "documents": [
    {
      "name": "Document or file name",
      "type": "pdf|code|spreadsheet|presentation|other",
      "key_content": "Brief summary of what was read/edited"
    }
  ],
  "websites": [
    {
      "domain": "example.com",
      "page_title": "Page title if known",
      "purpose": "Why the user visited"
    }
  ],
  "co_activities": [
    {
      "primary": "Main activity",
      "secondary": "Concurrent activity",
      "relationship": "studied_while|worked_while|browsed_while"
    }
  ],
  "open_loops": ["Things mentioned but not completed"],
  "location": "Location if known, null otherwise"
}
"""

HOURLY_SYSTEM_PROMPT = f"""You are a personal activity summarizer for Trace, a second-brain application.

Your task is to analyze the user's digital activity for one hour and generate a structured summary.

## Output Requirements

You MUST respond with valid JSON conforming to this schema:
{HOURLY_SCHEMA_DESCRIPTION}

## Guidelines

1. **Summary**: Write a concise 2-3 sentence overview capturing the main activities and context.

2. **Categories**: List activity categories present (e.g., "work", "learning", "entertainment", "communication", "creative", "browsing").

3. **Activities**: Create a timeline of distinct activities with clear time boundaries. Merge very short activities into broader segments when appropriate.

4. **Topics**: Extract topics, subjects, or concepts the user was engaging with. Include learning topics, project names, research subjects.

5. **Entities**: Extract named entities with their types:
   - topic: Abstract subjects or concepts
   - app: Applications used significantly
   - domain: Web domains visited meaningfully
   - document: Specific files or documents
   - artist: Musicians or content creators
   - track: Specific songs or audio content
   - video: Specific videos or shows
   - game: Games played
   - person: People mentioned or communicated with
   - project: Projects or work items

6. **Media**: Capture any media consumption (music, videos, podcasts).

7. **Documents**: Note documents that were read or edited, with brief content summaries.

8. **Websites**: Record significant website visits with purpose.

9. **Co-activities**: Identify overlapping activities (e.g., "studied machine learning while listening to Spotify").

10. **Open Loops**: Note any incomplete tasks or items that might need follow-up.

## Constraints

- Do NOT include full document or website contents
- Keep all descriptions concise
- Confidence scores should reflect certainty (0.0-1.0)
- Use exact timestamps from the evidence when available
- Location should be geographic if known, null otherwise

## Schema Version

The current schema version is {SCHEMA_VERSION}. Include this in your response.
"""


def build_hourly_user_prompt(
    evidence: HourlyEvidence,
    keyframes: list[SelectedKeyframe] | None = None,
    aggregator: EvidenceAggregator | None = None,
) -> str:
    """
    Build the user prompt for hourly summarization.

    Args:
        evidence: Aggregated evidence for the hour
        keyframes: Selected keyframes with descriptions
        aggregator: Optional aggregator for building timeline text

    Returns:
        Formatted user prompt string
    """
    lines = []

    # Header
    lines.append(
        f"# Hour: {evidence.hour_start.strftime('%Y-%m-%d %H:00')} - {evidence.hour_end.strftime('%H:00')}"
    )
    lines.append("")

    # Build timeline
    if aggregator:
        lines.append(aggregator.build_timeline_text(evidence))
    else:
        # Fallback: simple timeline
        lines.append("## Activity Timeline")
        lines.append("")
        for event in evidence.events:
            time_str = event.start_ts.strftime("%H:%M:%S")
            duration_min = event.duration_seconds // 60
            app = event.app_name or "Unknown"
            line = f"- [{time_str}] ({duration_min}m) {app}"
            if event.window_title:
                line += f" - {event.window_title[:50]}"
            lines.append(line)

    lines.append("")

    # Keyframe descriptions
    if keyframes:
        lines.append("## Keyframe Observations")
        lines.append("")
        for kf in keyframes:
            time_str = kf.timestamp.strftime("%H:%M:%S")
            desc = ""
            if kf.triage_result and kf.triage_result.description:
                desc = kf.triage_result.description
            elif kf.window_title:
                desc = f"{kf.app_name or 'App'}: {kf.window_title}"
            else:
                desc = kf.selection_reason

            lines.append(f"- [{time_str}] {desc}")
        lines.append("")

    # Text evidence
    if evidence.text_snippets:
        lines.append("## Extracted Text (Document/OCR)")
        lines.append("")
        for snippet in evidence.text_snippets:
            time_str = snippet.timestamp.strftime("%H:%M:%S")
            source = snippet.source_type
            lines.append(f"### [{time_str}] Source: {source}")
            if snippet.ref:
                lines.append(f"Reference: {snippet.ref}")
            lines.append("```")
            # Truncate long text for the prompt
            text = snippet.text
            if len(text) > 1000:
                text = text[:1000] + "... [truncated]"
            lines.append(text)
            lines.append("```")
            lines.append("")

    # Now playing
    if evidence.now_playing_spans:
        lines.append("## Media Playing During This Hour")
        lines.append("")
        for span in evidence.now_playing_spans:
            duration = int((span.end_ts - span.start_ts).total_seconds())
            lines.append(f"- {span.artist} - {span.track} ({duration}s via {span.app})")
        lines.append("")

    # Location
    if evidence.locations:
        lines.append(f"## Location: {', '.join(evidence.locations)}")
        lines.append("")

    # Statistics
    lines.append("## Evidence Statistics")
    lines.append(f"- Total events: {evidence.total_events}")
    lines.append(f"- Total screenshots: {evidence.total_screenshots}")
    lines.append(f"- Text buffers: {evidence.total_text_buffers}")
    lines.append(f"- Selected keyframes: {len(keyframes) if keyframes else 0}")
    lines.append("")

    # Instructions
    lines.append("---")
    lines.append(
        "Based on this evidence, generate a structured JSON summary following the schema provided in the system prompt."
    )

    return "\n".join(lines)


def build_vision_messages(
    evidence: HourlyEvidence,
    keyframes: list[SelectedKeyframe],
    aggregator: EvidenceAggregator | None = None,
) -> list[dict]:
    """
    Build messages with vision content for the LLM.

    Args:
        evidence: Aggregated evidence for the hour
        keyframes: Selected keyframes (must include screenshot paths)
        aggregator: Optional aggregator for building timeline text

    Returns:
        List of message dicts for the OpenAI API
    """
    import base64

    messages = [{"role": "system", "content": HOURLY_SYSTEM_PROMPT}]

    # Build user content with images
    user_content = []

    # Add text prompt first
    text_prompt = build_hourly_user_prompt(evidence, keyframes, aggregator)
    user_content.append({"type": "text", "text": text_prompt})

    # Add keyframe images
    for kf in keyframes:
        if kf.screenshot_path and kf.screenshot_path.exists():
            try:
                with open(kf.screenshot_path, "rb") as f:
                    image_data = base64.b64encode(f.read()).decode("utf-8")

                time_str = kf.timestamp.strftime("%H:%M:%S")
                user_content.append(
                    {
                        "type": "text",
                        "text": f"[Screenshot at {time_str}]",
                    }
                )
                user_content.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_data}",
                            "detail": "low",  # Use low for cost efficiency
                        },
                    }
                )
            except Exception:
                continue

    messages.append({"role": "user", "content": user_content})

    return messages


if __name__ == "__main__":
    import fire

    def show_schema():
        """Show the JSON schema for hourly summaries."""
        print(HOURLY_SCHEMA_DESCRIPTION)

    def show_system_prompt():
        """Show the system prompt."""
        print(HOURLY_SYSTEM_PROMPT)

    def demo_user_prompt():
        """Show a demo user prompt."""
        from datetime import timedelta

        # Create mock evidence
        hour_start = datetime.now().replace(minute=0, second=0, microsecond=0)
        evidence = HourlyEvidence(
            hour_start=hour_start,
            hour_end=hour_start + timedelta(hours=1),
            total_events=5,
            total_screenshots=120,
            total_text_buffers=3,
        )

        print(build_hourly_user_prompt(evidence))

    fire.Fire(
        {
            "schema": show_schema,
            "system": show_system_prompt,
            "demo": demo_user_prompt,
        }
    )
