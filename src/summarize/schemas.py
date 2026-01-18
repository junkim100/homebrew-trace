"""
JSON Schema Validation for Trace Summaries

Validates LLM output against versioned schemas.
Supports retry on validation failure.

P5-05: JSON schema validation
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

logger = logging.getLogger(__name__)

# Current schema version
SCHEMA_VERSION = 1


class ActivityItem(BaseModel):
    """A single activity in the hour."""

    time_start: str = Field(..., description="Start time in HH:MM format")
    time_end: str = Field(..., description="End time in HH:MM format")
    description: str = Field(..., description="What the user was doing")
    app: str | None = Field(None, description="Application name")
    category: str = Field(
        "other",
        description="Activity category: work, learning, entertainment, communication, creative, browsing, other",
    )


class TopicItem(BaseModel):
    """A topic or subject encountered."""

    name: str = Field(..., description="Topic name")
    context: str | None = Field(None, description="How/why it was encountered")
    confidence: float = Field(0.5, ge=0.0, le=1.0, description="Confidence score")


class EntityItem(BaseModel):
    """An extracted entity."""

    name: str = Field(..., description="Entity name")
    type: str = Field(
        ...,
        description="Entity type: topic, app, domain, document, artist, track, video, game, person, project",
    )
    confidence: float = Field(0.5, ge=0.0, le=1.0, description="Confidence score")

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        valid_types = {
            "topic",
            "app",
            "domain",
            "document",
            "artist",
            "track",
            "video",
            "game",
            "person",
            "project",
        }
        if v.lower() not in valid_types:
            # Try to map common variations
            v_lower = v.lower()
            if v_lower in ("song", "music"):
                return "track"
            if v_lower in ("website", "site", "url"):
                return "domain"
            if v_lower in ("file", "pdf", "doc"):
                return "document"
            if v_lower in ("application", "program"):
                return "app"
            # Default to topic
            return "topic"
        return v.lower()


class ListeningItem(BaseModel):
    """A listening item (music, podcast)."""

    artist: str = Field(..., description="Artist name")
    track: str = Field(..., description="Track name")
    duration_seconds: int | None = Field(None, description="Duration in seconds")


class WatchingItem(BaseModel):
    """A watching item (video, show)."""

    title: str = Field(..., description="Video/show title")
    source: str | None = Field(None, description="Source platform")
    duration_seconds: int | None = Field(None, description="Duration in seconds")


class MediaSection(BaseModel):
    """Media consumption section."""

    listening: list[ListeningItem] = Field(default_factory=list)
    watching: list[WatchingItem] = Field(default_factory=list)


class DocumentItem(BaseModel):
    """A document that was read or edited."""

    name: str = Field(..., description="Document or file name")
    type: str = Field(
        "other", description="Document type: pdf, code, spreadsheet, presentation, other"
    )
    key_content: str | None = Field(None, description="Brief summary of content")


class WebsiteItem(BaseModel):
    """A website that was visited."""

    domain: str = Field(..., description="Website domain")
    page_title: str | None = Field(None, description="Page title")
    purpose: str | None = Field(None, description="Why the user visited")


class CoActivityItem(BaseModel):
    """A co-activity (overlapping activities)."""

    primary: str = Field(..., description="Main activity")
    secondary: str = Field(..., description="Concurrent activity")
    relationship: str = Field(
        "worked_while",
        description="Relationship type: studied_while, worked_while, browsed_while",
    )


class HourlySummarySchema(BaseModel):
    """
    Complete schema for hourly summary output.

    This is the canonical schema that all LLM outputs must conform to.
    """

    schema_version: int = Field(SCHEMA_VERSION, description="Schema version number")
    summary: str = Field(..., description="2-3 sentence overview of the hour")
    categories: list[str] = Field(default_factory=list, description="Activity categories present")
    activities: list[ActivityItem] = Field(
        default_factory=list, description="Timeline of activities"
    )
    topics: list[TopicItem] = Field(default_factory=list, description="Topics encountered")
    entities: list[EntityItem] = Field(default_factory=list, description="Extracted entities")
    media: MediaSection = Field(default_factory=MediaSection, description="Media consumption")
    documents: list[DocumentItem] = Field(default_factory=list, description="Documents accessed")
    websites: list[WebsiteItem] = Field(default_factory=list, description="Websites visited")
    co_activities: list[CoActivityItem] = Field(
        default_factory=list, description="Overlapping activities"
    )
    open_loops: list[str] = Field(
        default_factory=list, description="Incomplete tasks or follow-ups"
    )
    location: str | None = Field(None, description="Location if known")

    @model_validator(mode="before")
    @classmethod
    def handle_missing_fields(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Handle missing or null fields gracefully."""
        if isinstance(data, dict):
            # Ensure schema_version
            if "schema_version" not in data:
                data["schema_version"] = SCHEMA_VERSION

            # Ensure required string field
            if "summary" not in data or not data["summary"]:
                data["summary"] = "No summary available."

            # Ensure media section exists
            if "media" not in data or data["media"] is None:
                data["media"] = {"listening": [], "watching": []}
            elif isinstance(data["media"], dict):
                if "listening" not in data["media"]:
                    data["media"]["listening"] = []
                if "watching" not in data["media"]:
                    data["media"]["watching"] = []

            # Convert null lists to empty lists
            list_fields = [
                "categories",
                "activities",
                "topics",
                "entities",
                "documents",
                "websites",
                "co_activities",
                "open_loops",
            ]
            for field in list_fields:
                if field not in data or data[field] is None:
                    data[field] = []

        return data


@dataclass
class ValidationResult:
    """Result of schema validation."""

    valid: bool
    data: HourlySummarySchema | None = None
    error: str | None = None
    raw_json: dict | None = None


def validate_hourly_summary(
    json_str: str | dict,
    strict: bool = False,
) -> ValidationResult:
    """
    Validate an hourly summary against the schema.

    Args:
        json_str: JSON string or dict to validate
        strict: If True, fail on any non-conforming data

    Returns:
        ValidationResult with parsed data or error
    """
    # Parse JSON if string
    if isinstance(json_str, str):
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            return ValidationResult(
                valid=False,
                error=f"Invalid JSON: {e}",
                raw_json=None,
            )
    else:
        data = json_str

    # Validate against schema
    try:
        if strict:
            # Strict mode: no extra fields, no missing required fields
            validated = HourlySummarySchema.model_validate(data)
        else:
            # Lenient mode: allow missing fields, use defaults
            validated = HourlySummarySchema.model_validate(data)

        return ValidationResult(
            valid=True,
            data=validated,
            error=None,
            raw_json=data,
        )

    except Exception as e:
        return ValidationResult(
            valid=False,
            error=str(e),
            raw_json=data,
        )


def fix_common_issues(json_str: str) -> str:
    """
    Attempt to fix common JSON issues from LLM output.

    Args:
        json_str: Potentially malformed JSON string

    Returns:
        Fixed JSON string
    """
    # Remove markdown code blocks
    if "```json" in json_str:
        json_str = json_str.split("```json")[-1]
    if "```" in json_str:
        json_str = json_str.split("```")[0]

    # Strip whitespace
    json_str = json_str.strip()

    # Try to find JSON object boundaries
    if not json_str.startswith("{"):
        start_idx = json_str.find("{")
        if start_idx != -1:
            json_str = json_str[start_idx:]

    if not json_str.endswith("}"):
        end_idx = json_str.rfind("}")
        if end_idx != -1:
            json_str = json_str[: end_idx + 1]

    return json_str


def validate_with_retry(
    json_str: str,
    max_attempts: int = 2,
) -> ValidationResult:
    """
    Validate JSON with automatic fix attempts.

    Args:
        json_str: JSON string to validate
        max_attempts: Maximum validation attempts

    Returns:
        ValidationResult from best attempt
    """
    attempt = 0
    last_result = None

    while attempt < max_attempts:
        attempt += 1

        # Fix common issues
        if attempt > 1:
            json_str = fix_common_issues(json_str)

        result = validate_hourly_summary(json_str)

        if result.valid:
            return result

        last_result = result
        logger.debug(f"Validation attempt {attempt} failed: {result.error}")

    return last_result or ValidationResult(valid=False, error="Validation failed")


def generate_empty_summary(
    hour_start: datetime,
    hour_end: datetime,
    reason: str = "No activity detected",
) -> HourlySummarySchema:
    """
    Generate an empty/minimal summary when no activity is detected.

    Args:
        hour_start: Start of the hour
        hour_end: End of the hour
        reason: Reason for empty summary

    Returns:
        Minimal valid HourlySummarySchema
    """
    return HourlySummarySchema(
        schema_version=SCHEMA_VERSION,
        summary=f"{reason} for {hour_start.strftime('%Y-%m-%d %H:00')} - {hour_end.strftime('%H:00')}.",
        categories=[],
        activities=[],
        topics=[],
        entities=[],
        media=MediaSection(listening=[], watching=[]),
        documents=[],
        websites=[],
        co_activities=[],
        open_loops=[],
        location=None,
    )


if __name__ == "__main__":
    import fire

    def validate(json_file: str | None = None, json_str: str | None = None):
        """
        Validate a JSON file or string against the hourly summary schema.

        Args:
            json_file: Path to JSON file
            json_str: JSON string to validate
        """
        if json_file:
            with open(json_file) as f:
                content = f.read()
        elif json_str:
            content = json_str
        else:
            # Demo with sample data
            content = json.dumps(
                {
                    "summary": "The user spent the hour coding in VS Code and browsing GitHub.",
                    "categories": ["work", "browsing"],
                    "activities": [
                        {
                            "time_start": "14:00",
                            "time_end": "14:30",
                            "description": "Writing Python code",
                            "app": "VS Code",
                            "category": "work",
                        }
                    ],
                    "topics": [{"name": "Python", "confidence": 0.9}],
                    "entities": [
                        {"name": "VS Code", "type": "app", "confidence": 0.95},
                        {"name": "GitHub", "type": "domain", "confidence": 0.8},
                    ],
                    "media": {"listening": [], "watching": []},
                    "documents": [],
                    "websites": [{"domain": "github.com", "purpose": "Code review"}],
                    "co_activities": [],
                    "open_loops": [],
                    "location": None,
                }
            )

        result = validate_with_retry(content)

        return {
            "valid": result.valid,
            "error": result.error,
            "schema_version": result.data.schema_version if result.data else None,
            "summary": result.data.summary if result.data else None,
            "entity_count": len(result.data.entities) if result.data else 0,
        }

    def schema():
        """Show the Pydantic schema as JSON Schema."""
        print(json.dumps(HourlySummarySchema.model_json_schema(), indent=2))

    fire.Fire({"validate": validate, "schema": schema})
