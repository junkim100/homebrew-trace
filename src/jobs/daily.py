"""
Daily Job Scheduler and Executor for Trace

Manages the daily revision job:
- Creates pending jobs for each day
- Executes full daily revision pipeline
- Tracks job status and retries

Uses APScheduler for scheduling.

P6-10: Daily job scheduler
"""

import json
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from openai import OpenAI

from src.core.paths import DB_PATH
from src.db.migrations import get_connection
from src.graph.edges import GraphEdgeBuilder
from src.revise.aggregates import AggregatesComputer
from src.revise.cleanup import ArtifactCleaner
from src.revise.daily_note import DailyNoteGenerator
from src.revise.embeddings import EmbeddingRefresher
from src.revise.integrity import IntegrityChecker
from src.revise.normalize import EntityNormalizer
from src.revise.prompts.daily import DAILY_MODEL, build_daily_messages
from src.revise.revise import HourlyNoteReviser, load_hourly_notes_for_day
from src.revise.schemas import DailyRevisionSchema, validate_with_retry

logger = logging.getLogger(__name__)

# Job configuration
MAX_RETRIES = 3
RETRY_DELAY_MINUTES = 30


@dataclass
class DailyJobStatus:
    """Status of a daily job."""

    job_id: str
    job_type: str
    window_start_ts: datetime
    window_end_ts: datetime
    status: str  # 'pending', 'running', 'success', 'failed'
    attempts: int
    last_error: str | None
    result: dict | None


@dataclass
class DailyRevisionResult:
    """Result of a daily revision job."""

    success: bool
    day: str
    hourly_notes_count: int
    hourly_revisions_count: int
    entities_normalized: int
    edges_created: int
    aggregates_computed: int
    embeddings_refreshed: int
    cleanup_completed: bool
    error: str | None = None


class DailyJobExecutor:
    """
    Executes daily revision jobs.

    The daily revision pipeline:
    1. Load all hourly notes for the day
    2. Call LLM for daily revision
    3. Apply entity normalizations
    4. Revise hourly notes
    5. Generate daily summary note
    6. Build graph edges
    7. Refresh embeddings
    8. Compute aggregates
    9. Run integrity checkpoint
    10. Delete raw artifacts (if integrity passes)
    """

    def __init__(
        self,
        db_path: Path | str | None = None,
        api_key: str | None = None,
    ):
        """
        Initialize the job executor.

        Args:
            db_path: Path to SQLite database
            api_key: OpenAI API key
        """
        self.db_path = Path(db_path) if db_path else DB_PATH
        self._api_key = api_key
        self._client: OpenAI | None = None

        # Initialize components
        self.normalizer = EntityNormalizer(db_path=self.db_path)
        self.reviser = HourlyNoteReviser(db_path=self.db_path)
        self.daily_note_generator = DailyNoteGenerator(db_path=self.db_path)
        self.edge_builder = GraphEdgeBuilder(db_path=self.db_path)
        self.embedding_refresher = EmbeddingRefresher(db_path=self.db_path, api_key=api_key)
        self.aggregates_computer = AggregatesComputer(db_path=self.db_path)
        self.integrity_checker = IntegrityChecker(db_path=self.db_path)
        self.cleaner = ArtifactCleaner(db_path=self.db_path)

    def _get_client(self) -> OpenAI:
        """Get or create the OpenAI client (lazy initialization)."""
        if self._client is None:
            self._client = OpenAI(api_key=self._api_key) if self._api_key else OpenAI()
        return self._client

    def create_pending_job(self, day: datetime) -> str:
        """
        Create a pending job for a day.

        Args:
            day: The day to create job for

        Returns:
            Job ID
        """
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day.replace(hour=23, minute=59, second=59, microsecond=999999)

        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()

            # Check for existing job
            cursor.execute(
                """
                SELECT job_id, status FROM jobs
                WHERE job_type = 'daily'
                AND window_start_ts = ?
                """,
                (day_start.isoformat(),),
            )
            row = cursor.fetchone()

            if row:
                # Job exists
                if row["status"] in ("success", "running"):
                    logger.debug(
                        f"Job already exists for {day_start.strftime('%Y-%m-%d')}: {row['status']}"
                    )
                    return row["job_id"]
                # Reset failed job for retry
                job_id = row["job_id"]
                cursor.execute(
                    """
                    UPDATE jobs
                    SET status = 'pending', updated_ts = ?
                    WHERE job_id = ?
                    """,
                    (datetime.now().isoformat(), job_id),
                )
            else:
                # Create new job
                job_id = str(uuid.uuid4())
                cursor.execute(
                    """
                    INSERT INTO jobs
                    (job_id, job_type, window_start_ts, window_end_ts, status, attempts, created_ts, updated_ts)
                    VALUES (?, 'daily', ?, ?, 'pending', 0, ?, ?)
                    """,
                    (
                        job_id,
                        day_start.isoformat(),
                        day_end.isoformat(),
                        datetime.now().isoformat(),
                        datetime.now().isoformat(),
                    ),
                )

            conn.commit()
            logger.info(f"Created pending daily job {job_id} for {day_start.strftime('%Y-%m-%d')}")
            return job_id

        finally:
            conn.close()

    def execute_job(self, job_id: str) -> DailyRevisionResult:
        """
        Execute a specific daily job.

        Args:
            job_id: ID of the job to execute

        Returns:
            DailyRevisionResult
        """
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()

            # Get job details
            cursor.execute(
                """
                SELECT job_id, window_start_ts, status, attempts
                FROM jobs
                WHERE job_id = ?
                """,
                (job_id,),
            )
            row = cursor.fetchone()

            if row is None:
                logger.error(f"Job not found: {job_id}")
                return DailyRevisionResult(
                    success=False,
                    day="unknown",
                    hourly_notes_count=0,
                    hourly_revisions_count=0,
                    entities_normalized=0,
                    edges_created=0,
                    aggregates_computed=0,
                    embeddings_refreshed=0,
                    cleanup_completed=False,
                    error="Job not found",
                )

            if row["status"] == "running":
                logger.warning(f"Job {job_id} is already running")
                return DailyRevisionResult(
                    success=False,
                    day=row["window_start_ts"][:10],
                    hourly_notes_count=0,
                    hourly_revisions_count=0,
                    entities_normalized=0,
                    edges_created=0,
                    aggregates_computed=0,
                    embeddings_refreshed=0,
                    cleanup_completed=False,
                    error="Job already running",
                )

            # Update status to running
            attempts = row["attempts"] + 1
            cursor.execute(
                """
                UPDATE jobs
                SET status = 'running', attempts = ?, updated_ts = ?
                WHERE job_id = ?
                """,
                (attempts, datetime.now().isoformat(), job_id),
            )
            conn.commit()

            day = datetime.fromisoformat(row["window_start_ts"])

        finally:
            conn.close()

        # Execute daily revision pipeline
        try:
            logger.info(
                f"Executing daily job {job_id} for {day.strftime('%Y-%m-%d')} (attempt {attempts})"
            )
            result = self._execute_pipeline(day)

            # Update job status
            self._update_job_status(
                job_id=job_id,
                success=result.success,
                error=result.error,
                result={
                    "day": result.day,
                    "hourly_notes_count": result.hourly_notes_count,
                    "hourly_revisions_count": result.hourly_revisions_count,
                    "entities_normalized": result.entities_normalized,
                    "edges_created": result.edges_created,
                    "aggregates_computed": result.aggregates_computed,
                    "embeddings_refreshed": result.embeddings_refreshed,
                    "cleanup_completed": result.cleanup_completed,
                },
            )

            return result

        except Exception as e:
            logger.error(f"Daily job {job_id} failed with exception: {e}")
            self._update_job_status(
                job_id=job_id,
                success=False,
                error=str(e),
            )
            return DailyRevisionResult(
                success=False,
                day=day.strftime("%Y-%m-%d"),
                hourly_notes_count=0,
                hourly_revisions_count=0,
                entities_normalized=0,
                edges_created=0,
                aggregates_computed=0,
                embeddings_refreshed=0,
                cleanup_completed=False,
                error=str(e),
            )

    def _execute_pipeline(self, day: datetime) -> DailyRevisionResult:
        """
        Execute the full daily revision pipeline.

        Args:
            day: The day to process

        Returns:
            DailyRevisionResult
        """
        day_str = day.strftime("%Y-%m-%d")

        # Step 1: Load hourly notes
        logger.info(f"Step 1: Loading hourly notes for {day_str}")
        hourly_notes = load_hourly_notes_for_day(day, self.db_path)

        if not hourly_notes:
            logger.info(f"No hourly notes found for {day_str}")
            return DailyRevisionResult(
                success=True,
                day=day_str,
                hourly_notes_count=0,
                hourly_revisions_count=0,
                entities_normalized=0,
                edges_created=0,
                aggregates_computed=0,
                embeddings_refreshed=0,
                cleanup_completed=False,
            )

        # Step 2: Call LLM for daily revision
        logger.info(f"Step 2: Calling LLM for daily revision ({len(hourly_notes)} notes)")
        revision = self._call_llm_for_revision(day, hourly_notes)

        if revision is None:
            return DailyRevisionResult(
                success=False,
                day=day_str,
                hourly_notes_count=len(hourly_notes),
                hourly_revisions_count=0,
                entities_normalized=0,
                edges_created=0,
                aggregates_computed=0,
                embeddings_refreshed=0,
                cleanup_completed=False,
                error="LLM call failed",
            )

        # Step 3: Apply entity normalizations
        logger.info(f"Step 3: Applying {len(revision.entity_normalizations)} entity normalizations")
        norm_result = self.normalizer.apply_normalizations(revision.entity_normalizations)

        # Step 4: Revise hourly notes
        logger.info(f"Step 4: Revising {len(revision.hourly_revisions)} hourly notes")
        revise_result = self.reviser.revise_hourly_notes(day, revision)

        # Step 5: Generate daily summary note
        logger.info("Step 5: Generating daily summary note")
        self.daily_note_generator.generate(day, revision)

        # Step 6: Build graph edges
        logger.info(f"Step 6: Building {len(revision.graph_edges)} graph edges")
        note_ids = [n["note_id"] for n in hourly_notes]
        edge_result = self.edge_builder.build_edges_from_revision(
            revision.graph_edges, day, note_ids
        )

        # Step 7: Refresh embeddings
        logger.info("Step 7: Refreshing embeddings for revised notes")
        embed_result = self.embedding_refresher.refresh_embeddings_for_day(day, force=True)

        # Step 8: Compute aggregates
        logger.info("Step 8: Computing daily aggregates")
        agg_result = self.aggregates_computer.compute_daily_aggregates(day, revision)

        # Step 9: Run integrity checkpoint
        logger.info("Step 9: Running integrity checkpoint")
        integrity_result = self.integrity_checker.check_integrity(day)

        # Step 10: Delete raw artifacts (only if integrity passes)
        cleanup_completed = False
        if integrity_result.passed:
            logger.info("Step 10: Cleaning up raw artifacts")
            cleanup_result = self.cleaner.cleanup_day(day)
            cleanup_completed = cleanup_result.success
        else:
            logger.warning(
                f"Skipping cleanup - integrity check failed with {integrity_result.error_count} errors"
            )

        return DailyRevisionResult(
            success=True,
            day=day_str,
            hourly_notes_count=len(hourly_notes),
            hourly_revisions_count=revise_result.revised_count,
            entities_normalized=norm_result.total_entities_merged,
            edges_created=edge_result.created_count + edge_result.updated_count,
            aggregates_computed=agg_result.total_aggregates,
            embeddings_refreshed=embed_result.refreshed_count,
            cleanup_completed=cleanup_completed,
        )

    def _call_llm_for_revision(
        self,
        day: datetime,
        hourly_notes: list[dict],
    ) -> DailyRevisionSchema | None:
        """
        Call the LLM to generate daily revision.

        Args:
            day: The day being revised
            hourly_notes: List of hourly note data

        Returns:
            DailyRevisionSchema or None on failure
        """
        try:
            messages = build_daily_messages(day.date(), hourly_notes)
            client = self._get_client()

            response = client.chat.completions.create(
                model=DAILY_MODEL,
                messages=messages,
                max_completion_tokens=8000,
            )

            content = response.choices[0].message.content

            # Validate and parse response
            result = validate_with_retry(content)

            if not result.valid:
                logger.error(f"Failed to validate LLM response: {result.error}")
                return None

            return result.data

        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return None

    def _update_job_status(
        self,
        job_id: str,
        success: bool,
        error: str | None = None,
        result: dict | None = None,
    ) -> None:
        """Update job status in database."""
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            status = "success" if success else "failed"
            result_json = json.dumps(result) if result else None

            cursor.execute(
                """
                UPDATE jobs
                SET status = ?, last_error = ?, result_json = ?, updated_ts = ?
                WHERE job_id = ?
                """,
                (status, error, result_json, datetime.now().isoformat(), job_id),
            )
            conn.commit()
        finally:
            conn.close()

    def execute_pending_jobs(self) -> list[DailyRevisionResult]:
        """Execute all pending daily jobs."""
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT job_id FROM jobs
                WHERE job_type = 'daily'
                AND status = 'pending'
                AND attempts < ?
                ORDER BY window_start_ts
                """,
                (MAX_RETRIES,),
            )
            job_ids = [row["job_id"] for row in cursor.fetchall()]
        finally:
            conn.close()

        results = []
        for job_id in job_ids:
            result = self.execute_job(job_id)
            results.append(result)

        return results

    def get_job_status(self, job_id: str) -> DailyJobStatus | None:
        """Get status of a job."""
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT job_id, job_type, window_start_ts, window_end_ts,
                       status, attempts, last_error, result_json
                FROM jobs
                WHERE job_id = ?
                """,
                (job_id,),
            )
            row = cursor.fetchone()

            if row is None:
                return None

            return DailyJobStatus(
                job_id=row["job_id"],
                job_type=row["job_type"],
                window_start_ts=datetime.fromisoformat(row["window_start_ts"]),
                window_end_ts=datetime.fromisoformat(row["window_end_ts"]),
                status=row["status"],
                attempts=row["attempts"],
                last_error=row["last_error"],
                result=json.loads(row["result_json"]) if row["result_json"] else None,
            )
        finally:
            conn.close()

    def get_recent_jobs(self, limit: int = 7) -> list[DailyJobStatus]:
        """Get recent daily jobs."""
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT job_id, job_type, window_start_ts, window_end_ts,
                       status, attempts, last_error, result_json
                FROM jobs
                WHERE job_type = 'daily'
                ORDER BY window_start_ts DESC
                LIMIT ?
                """,
                (limit,),
            )

            jobs = []
            for row in cursor.fetchall():
                jobs.append(
                    DailyJobStatus(
                        job_id=row["job_id"],
                        job_type=row["job_type"],
                        window_start_ts=datetime.fromisoformat(row["window_start_ts"]),
                        window_end_ts=datetime.fromisoformat(row["window_end_ts"]),
                        status=row["status"],
                        attempts=row["attempts"],
                        last_error=row["last_error"],
                        result=json.loads(row["result_json"]) if row["result_json"] else None,
                    )
                )

            return jobs
        finally:
            conn.close()


class DailyJobScheduler:
    """
    Schedules and runs daily revision jobs.

    Uses APScheduler to run jobs once per day (at 3 AM by default).
    """

    def __init__(
        self,
        db_path: Path | str | None = None,
        api_key: str | None = None,
        on_job_complete: Callable[[DailyRevisionResult], None] | None = None,
        run_hour: int = 3,
    ):
        """
        Initialize the scheduler.

        Args:
            db_path: Path to SQLite database
            api_key: OpenAI API key
            on_job_complete: Callback when a job completes
            run_hour: Hour of day to run (0-23, default: 3 AM)
        """
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.api_key = api_key
        self.on_job_complete = on_job_complete
        self.run_hour = run_hour

        self.executor = DailyJobExecutor(db_path=self.db_path, api_key=api_key)
        self.scheduler = BackgroundScheduler()
        self._running = False

    def start(self) -> None:
        """Start the scheduler."""
        if self._running:
            logger.warning("Scheduler is already running")
            return

        # Add daily job at configured hour
        self.scheduler.add_job(
            self._daily_job,
            trigger=CronTrigger(hour=self.run_hour, minute=0),
            id="daily_revision",
            name="Daily Revision",
            replace_existing=True,
        )

        self.scheduler.start()
        self._running = True
        logger.info(f"Daily job scheduler started (runs at {self.run_hour:02d}:00)")

        # Execute any pending jobs immediately
        self._execute_pending()

    def stop(self) -> None:
        """Stop the scheduler."""
        if not self._running:
            return

        self.scheduler.shutdown(wait=True)
        self._running = False
        logger.info("Daily job scheduler stopped")

    def _daily_job(self) -> None:
        """Job that runs once per day."""
        # Create job for yesterday (today's data is still being captured)
        yesterday = (datetime.now() - timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        logger.info(f"Daily job triggered for {yesterday.strftime('%Y-%m-%d')}")

        job_id = self.executor.create_pending_job(yesterday)
        result = self.executor.execute_job(job_id)

        if self.on_job_complete:
            self.on_job_complete(result)

    def _execute_pending(self) -> None:
        """Execute any pending jobs on startup."""
        results = self.executor.execute_pending_jobs()

        for result in results:
            if self.on_job_complete:
                self.on_job_complete(result)

    def trigger_now(self, day: datetime | None = None) -> DailyRevisionResult:
        """
        Trigger daily revision immediately.

        Args:
            day: Day to process (defaults to yesterday)

        Returns:
            DailyRevisionResult
        """
        if day is None:
            day = (datetime.now() - timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
        else:
            day = day.replace(hour=0, minute=0, second=0, microsecond=0)

        job_id = self.executor.create_pending_job(day)
        return self.executor.execute_job(job_id)

    def is_running(self) -> bool:
        """Check if scheduler is running."""
        return self._running

    def get_next_run_time(self) -> datetime | None:
        """Get the next scheduled run time."""
        if not self._running:
            return None

        job = self.scheduler.get_job("daily_revision")
        if job and job.next_run_time:
            return job.next_run_time
        return None


if __name__ == "__main__":
    import time

    import fire

    def run(hours: int = 24, db_path: str | None = None):
        """
        Run the daily scheduler for a specified duration.

        Args:
            hours: Number of hours to run
            db_path: Path to database
        """

        def on_complete(result: DailyRevisionResult):
            print(f"Job complete: success={result.success}, day={result.day}")

        scheduler = DailyJobScheduler(db_path=db_path, on_job_complete=on_complete)
        scheduler.start()

        print(f"Scheduler started. Running for {hours} hour(s)...")
        print(f"Next run: {scheduler.get_next_run_time()}")

        try:
            end_time = datetime.now() + timedelta(hours=hours)
            while datetime.now() < end_time:
                time.sleep(60)
        except KeyboardInterrupt:
            print("\nStopping scheduler...")
        finally:
            scheduler.stop()

    def trigger(day: str | None = None, db_path: str | None = None):
        """
        Trigger daily revision immediately.

        Args:
            day: Date in YYYY-MM-DD format (defaults to yesterday)
            db_path: Path to database
        """
        target_day = datetime.strptime(day, "%Y-%m-%d") if day else None

        scheduler = DailyJobScheduler(db_path=db_path)
        result = scheduler.trigger_now(target_day)

        return {
            "success": result.success,
            "day": result.day,
            "hourly_notes": result.hourly_notes_count,
            "revisions": result.hourly_revisions_count,
            "entities_normalized": result.entities_normalized,
            "edges_created": result.edges_created,
            "aggregates": result.aggregates_computed,
            "embeddings": result.embeddings_refreshed,
            "cleanup": result.cleanup_completed,
            "error": result.error,
        }

    def status(db_path: str | None = None, limit: int = 7):
        """
        Show recent daily job status.

        Args:
            db_path: Path to database
            limit: Number of jobs to show
        """
        executor = DailyJobExecutor(db_path=db_path)
        jobs = executor.get_recent_jobs(limit)

        result = []
        for job in jobs:
            result.append(
                {
                    "job_id": job.job_id[:8],
                    "day": job.window_start_ts.strftime("%Y-%m-%d"),
                    "status": job.status,
                    "attempts": job.attempts,
                    "error": job.last_error[:50] if job.last_error else None,
                }
            )

        return result

    def pending(db_path: str | None = None):
        """Execute all pending daily jobs."""
        executor = DailyJobExecutor(db_path=db_path)
        results = executor.execute_pending_jobs()

        return {
            "executed": len(results),
            "successful": sum(1 for r in results if r.success),
        }

    fire.Fire(
        {
            "run": run,
            "trigger": trigger,
            "status": status,
            "pending": pending,
        }
    )
