"""
Hourly Summarizer Orchestrator for Trace

Coordinates the complete hourly summarization pipeline:
1. Gather evidence (events, screenshots, text buffers)
2. Triage and select keyframes
3. Call vision LLM for summarization
4. Validate JSON output
5. Render Markdown note
6. Extract and store entities
7. Compute and store embedding
8. Update database

P5-10: Hourly job executor (main orchestrator)
"""

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from openai import OpenAI

from src.core.paths import DB_PATH, ensure_note_directory, get_note_path
from src.db.migrations import get_connection
from src.summarize.embeddings import EmbeddingComputer
from src.summarize.entities import EntityExtractor
from src.summarize.evidence import EvidenceAggregator, HourlyEvidence
from src.summarize.keyframes import KeyframeSelector, ScreenshotCandidate, SelectedKeyframe
from src.summarize.prompts.hourly import (
    HOURLY_MODEL,
    build_vision_messages,
)
from src.summarize.render import MarkdownRenderer
from src.summarize.schemas import (
    HourlySummarySchema,
    generate_empty_summary,
    validate_with_retry,
)
from src.summarize.triage import FrameTriager, HeuristicTriager

logger = logging.getLogger(__name__)

# Maximum keyframes to include in LLM call (token budget)
MAX_KEYFRAMES_FOR_LLM = 10

# Use heuristic triage by default (set to False to use vision API for triage)
USE_HEURISTIC_TRIAGE = True


@dataclass
class SummarizationResult:
    """Result of hourly summarization."""

    success: bool
    note_id: str | None
    file_path: Path | None
    error: str | None = None

    # Statistics
    events_count: int = 0
    screenshots_count: int = 0
    keyframes_count: int = 0
    entities_count: int = 0
    embedding_computed: bool = False


class HourlySummarizer:
    """
    Orchestrates the complete hourly summarization pipeline.

    This is the main entry point for generating hourly notes from
    captured activity data.
    """

    def __init__(
        self,
        api_key: str | None = None,
        db_path: Path | str | None = None,
        model: str = HOURLY_MODEL,
        use_heuristic_triage: bool = USE_HEURISTIC_TRIAGE,
    ):
        """
        Initialize the hourly summarizer.

        Args:
            api_key: OpenAI API key
            db_path: Path to SQLite database
            model: Model to use for summarization
            use_heuristic_triage: Use heuristic triage instead of vision API
        """
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.model = model
        self.use_heuristic_triage = use_heuristic_triage
        self._api_key = api_key
        self._client: OpenAI | None = None

        # Initialize components
        self.aggregator = EvidenceAggregator(db_path=self.db_path)
        self.keyframe_selector = KeyframeSelector()
        self.renderer = MarkdownRenderer()
        self.entity_extractor = EntityExtractor(db_path=self.db_path)
        self.embedding_computer = EmbeddingComputer(api_key=api_key, db_path=self.db_path)

        if use_heuristic_triage:
            self.triager: FrameTriager | HeuristicTriager = HeuristicTriager()
        else:
            self.triager = FrameTriager(api_key=api_key)

    def _get_client(self) -> OpenAI:
        """Get or create the OpenAI client."""
        if self._client is None:
            self._client = OpenAI(api_key=self._api_key) if self._api_key else OpenAI()
        return self._client

    def summarize_hour(
        self,
        hour_start: datetime,
        force: bool = False,
    ) -> SummarizationResult:
        """
        Generate an hourly summary for a specific hour.

        Args:
            hour_start: Start of the hour to summarize
            force: If True, regenerate even if note exists

        Returns:
            SummarizationResult with status and statistics
        """
        # Normalize to hour boundary
        hour_start = hour_start.replace(minute=0, second=0, microsecond=0)
        hour_end = hour_start + timedelta(hours=1)

        logger.info(f"Starting summarization for {hour_start.isoformat()}")

        # Check for existing note
        if not force:
            existing = self._check_existing_note(hour_start)
            if existing:
                logger.info(f"Note already exists for {hour_start.isoformat()}")
                return SummarizationResult(
                    success=True,
                    note_id=existing,
                    file_path=get_note_path(hour_start),
                    error=None,
                )

        # Step 1: Aggregate evidence
        logger.debug("Aggregating evidence...")
        evidence = self.aggregator.aggregate(hour_start)

        # Check if there's any activity
        if evidence.total_events == 0:
            logger.info(f"No activity for {hour_start.isoformat()}, generating empty note")
            return self._generate_empty_note(hour_start, hour_end)

        # Step 2: Get screenshots and triage
        logger.debug("Selecting keyframes...")
        keyframes = self._select_keyframes(hour_start, hour_end, evidence)

        # Step 3: Call LLM for summarization
        logger.debug("Calling LLM for summarization...")
        summary = self._call_llm(evidence, keyframes)

        if summary is None:
            logger.error("LLM summarization failed")
            return SummarizationResult(
                success=False,
                note_id=None,
                file_path=None,
                error="LLM summarization failed",
                events_count=evidence.total_events,
                screenshots_count=evidence.total_screenshots,
            )

        # Step 4: Generate note ID and paths
        note_id = str(uuid.uuid4())
        file_path = get_note_path(hour_start)
        ensure_note_directory(hour_start)

        # Step 5: Render and save Markdown
        logger.debug("Rendering Markdown note...")
        saved = self.renderer.render_to_file(
            summary=summary,
            note_id=note_id,
            hour_start=hour_start,
            hour_end=hour_end,
            file_path=file_path,
            location=evidence.locations[0] if evidence.locations else None,
        )

        if not saved:
            return SummarizationResult(
                success=False,
                note_id=note_id,
                file_path=file_path,
                error="Failed to save Markdown file",
            )

        # Step 6: Store note in database
        logger.debug("Storing note in database...")
        self._store_note(
            note_id=note_id,
            hour_start=hour_start,
            hour_end=hour_end,
            file_path=file_path,
            summary=summary,
        )

        # Step 7: Extract and store entities
        logger.debug("Extracting entities...")
        links = self.entity_extractor.extract_and_store(summary, note_id)
        entities_count = len(links)

        # Step 8: Compute embedding
        logger.debug("Computing embedding...")
        embedding_result = self.embedding_computer.compute_for_note(
            note_id=note_id,
            summary=summary,
            hour_start=hour_start,
        )

        logger.info(f"Summarization complete for {hour_start.isoformat()}: {note_id}")

        return SummarizationResult(
            success=True,
            note_id=note_id,
            file_path=file_path,
            events_count=evidence.total_events,
            screenshots_count=evidence.total_screenshots,
            keyframes_count=len(keyframes),
            entities_count=entities_count,
            embedding_computed=embedding_result.success,
        )

    def _check_existing_note(self, hour_start: datetime) -> str | None:
        """Check if a note already exists for this hour."""
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT note_id FROM notes
                WHERE note_type = 'hour'
                AND start_ts = ?
                """,
                (hour_start.isoformat(),),
            )
            row = cursor.fetchone()
            return row["note_id"] if row else None
        finally:
            conn.close()

    def _select_keyframes(
        self,
        hour_start: datetime,
        hour_end: datetime,
        evidence: HourlyEvidence,
    ) -> list[SelectedKeyframe]:
        """Select keyframes for the hour."""
        # Get screenshots from database
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT s.screenshot_id, s.ts, s.monitor_id, s.path, s.fingerprint, s.diff_score,
                       e.app_id, e.app_name, e.window_title
                FROM screenshots s
                LEFT JOIN events e ON s.ts >= e.start_ts AND s.ts < e.end_ts
                WHERE s.ts >= ? AND s.ts < ?
                ORDER BY s.ts
                """,
                (hour_start.isoformat(), hour_end.isoformat()),
            )

            candidates = []
            for row in cursor.fetchall():
                try:
                    timestamp = datetime.fromisoformat(row["ts"])
                except (ValueError, TypeError):
                    continue

                # Ensure diff_score is a float
                diff_score_val = row["diff_score"]
                if diff_score_val is None:
                    diff_score_val = 0.0
                elif not isinstance(diff_score_val, (int, float)):
                    try:
                        diff_score_val = float(diff_score_val)
                    except (ValueError, TypeError):
                        diff_score_val = 0.0

                candidate = ScreenshotCandidate(
                    screenshot_id=row["screenshot_id"],
                    screenshot_path=Path(row["path"]),
                    timestamp=timestamp,
                    monitor_id=row["monitor_id"],
                    diff_score=float(diff_score_val),
                    fingerprint=row["fingerprint"] or "",
                    app_id=row["app_id"],
                    app_name=row["app_name"],
                    window_title=row["window_title"],
                )

                # Triage if using heuristic
                if self.use_heuristic_triage and isinstance(self.triager, HeuristicTriager):
                    triage_result = self.triager.triage(
                        screenshot_id=candidate.screenshot_id,
                        screenshot_path=candidate.screenshot_path,
                        timestamp=timestamp,
                        app_id=row["app_id"],
                        window_title=row["window_title"],
                        diff_score=float(diff_score_val) if diff_score_val else 0.5,
                    )
                    candidate.triage_result = triage_result

                candidates.append(candidate)

        finally:
            conn.close()

        # Select keyframes
        keyframes = self.keyframe_selector.select(candidates)

        # Limit for LLM call
        return keyframes[:MAX_KEYFRAMES_FOR_LLM]

    def _call_llm(
        self,
        evidence: HourlyEvidence,
        keyframes: list[SelectedKeyframe],
    ) -> HourlySummarySchema | None:
        """Call the LLM for summarization."""
        try:
            # Build messages
            messages = build_vision_messages(evidence, keyframes, self.aggregator)

            client = self._get_client()
            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_completion_tokens=4096,
                response_format={"type": "json_object"},
            )

            response_text = response.choices[0].message.content or "{}"

            # Validate response
            result = validate_with_retry(response_text)

            if not result.valid:
                logger.error(f"LLM response validation failed: {result.error}")
                # Try one more time with stricter prompt
                return None

            return result.data

        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return None

    def _generate_empty_note(
        self,
        hour_start: datetime,
        hour_end: datetime,
    ) -> SummarizationResult:
        """Generate an empty note for hours with no activity."""
        note_id = str(uuid.uuid4())
        file_path = get_note_path(hour_start)
        ensure_note_directory(hour_start)

        summary = generate_empty_summary(hour_start, hour_end, "No activity detected")

        # Render and save
        saved = self.renderer.render_to_file(
            summary=summary,
            note_id=note_id,
            hour_start=hour_start,
            hour_end=hour_end,
            file_path=file_path,
        )

        if not saved:
            return SummarizationResult(
                success=False,
                note_id=note_id,
                file_path=file_path,
                error="Failed to save empty note",
            )

        # Store in database
        self._store_note(
            note_id=note_id,
            hour_start=hour_start,
            hour_end=hour_end,
            file_path=file_path,
            summary=summary,
        )

        return SummarizationResult(
            success=True,
            note_id=note_id,
            file_path=file_path,
            events_count=0,
            screenshots_count=0,
        )

    def _store_note(
        self,
        note_id: str,
        hour_start: datetime,
        hour_end: datetime,
        file_path: Path,
        summary: HourlySummarySchema,
    ) -> None:
        """Store note metadata in the database."""
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()

            # Serialize summary to JSON
            json_payload = json.dumps(summary.model_dump())

            cursor.execute(
                """
                INSERT OR REPLACE INTO notes
                (note_id, note_type, start_ts, end_ts, file_path, json_payload, created_ts, updated_ts)
                VALUES (?, 'hour', ?, ?, ?, ?, ?, ?)
                """,
                (
                    note_id,
                    hour_start.isoformat(),
                    hour_end.isoformat(),
                    str(file_path),
                    json_payload,
                    datetime.now().isoformat(),
                    datetime.now().isoformat(),
                ),
            )
            conn.commit()
        finally:
            conn.close()


if __name__ == "__main__":
    import fire

    def summarize(
        hour: str | None = None,
        force: bool = False,
        db_path: str | None = None,
    ):
        """
        Summarize an hour.

        Args:
            hour: Hour in ISO format (e.g., '2025-01-15T14:00:00'), defaults to previous hour
            force: Force regeneration even if note exists
            db_path: Path to database
        """
        if hour:
            hour_start = datetime.fromisoformat(hour)
        else:
            now = datetime.now()
            hour_start = (now - timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)

        summarizer = HourlySummarizer(db_path=db_path)
        result = summarizer.summarize_hour(hour_start, force=force)

        return {
            "success": result.success,
            "note_id": result.note_id,
            "file_path": str(result.file_path) if result.file_path else None,
            "error": result.error,
            "events_count": result.events_count,
            "screenshots_count": result.screenshots_count,
            "keyframes_count": result.keyframes_count,
            "entities_count": result.entities_count,
            "embedding_computed": result.embedding_computed,
        }

    def batch(
        start_hour: str,
        end_hour: str,
        force: bool = False,
        db_path: str | None = None,
    ):
        """
        Summarize multiple hours.

        Args:
            start_hour: Start hour in ISO format
            end_hour: End hour in ISO format
            force: Force regeneration
            db_path: Path to database
        """
        start = datetime.fromisoformat(start_hour).replace(minute=0, second=0, microsecond=0)
        end = datetime.fromisoformat(end_hour).replace(minute=0, second=0, microsecond=0)

        summarizer = HourlySummarizer(db_path=db_path)
        results = []

        current = start
        while current < end:
            result = summarizer.summarize_hour(current, force=force)
            results.append(
                {
                    "hour": current.isoformat(),
                    "success": result.success,
                    "note_id": result.note_id,
                }
            )
            current += timedelta(hours=1)

        return {
            "total": len(results),
            "successful": sum(1 for r in results if r["success"]),
            "results": results,
        }

    fire.Fire({"summarize": summarize, "batch": batch})
