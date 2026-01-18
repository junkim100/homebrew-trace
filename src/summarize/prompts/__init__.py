"""
Prompts for Trace Summarization

Contains structured prompts for:
- Hourly summarization (P5-04)
- Daily revision (future)
"""

from src.summarize.prompts.hourly import (
    HOURLY_SCHEMA_DESCRIPTION,
    HOURLY_SYSTEM_PROMPT,
    build_hourly_user_prompt,
)

__all__ = [
    "HOURLY_SYSTEM_PROMPT",
    "HOURLY_SCHEMA_DESCRIPTION",
    "build_hourly_user_prompt",
]
