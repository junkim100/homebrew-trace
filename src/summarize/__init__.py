"""
Hourly Summarization Module for Trace

This module handles the hourly summarization pipeline:
- Frame triage and importance scoring (P5-01)
- Keyframe selection (P5-02)
- Evidence aggregation (P5-03)
- Hourly summarization prompt (P5-04)
- JSON schema validation (P5-05)
- Markdown note rendering (P5-06)
- Entity extraction and storage (P5-07)
- Embedding computation (P5-08)

Phase 5 of Trace MVP implementation.
"""

from src.summarize.embeddings import EmbeddingComputer
from src.summarize.entities import EntityExtractor
from src.summarize.evidence import EvidenceAggregator, HourlyEvidence
from src.summarize.keyframes import KeyframeSelector, SelectedKeyframe
from src.summarize.render import MarkdownRenderer
from src.summarize.schemas import HourlySummarySchema, validate_hourly_summary
from src.summarize.summarizer import HourlySummarizer
from src.summarize.triage import FrameTriager, TriageResult

__all__ = [
    "FrameTriager",
    "TriageResult",
    "KeyframeSelector",
    "SelectedKeyframe",
    "EvidenceAggregator",
    "HourlyEvidence",
    "HourlySummarySchema",
    "validate_hourly_summary",
    "MarkdownRenderer",
    "EntityExtractor",
    "EmbeddingComputer",
    "HourlySummarizer",
]
