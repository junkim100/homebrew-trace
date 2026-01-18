"""
Hourly Job Scheduler and Executor for Trace

Manages the hourly summarization job:
- Creates pending jobs for each hour
- Executes summarization
- Tracks job status and retries

Uses APScheduler for scheduling.

P5-09: Hourly job scheduler
P5-10: Hourly job executor
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

from src.core.paths import DB_PATH
from src.db.migrations import get_connection
from src.summarize.summarizer import HourlySummarizer, SummarizationResult

logger = logging.getLogger(__name__)

# Job configuration
MAX_RETRIES = 3
RETRY_DELAY_MINUTES = 5


@dataclass
class JobStatus:
    """Status of a job."""

    job_id: str
    job_type: str
    window_start_ts: datetime
    window_end_ts: datetime
    status: str  # 'pending', 'running', 'success', 'failed'
    attempts: int
    last_error: str | None
    result: dict | None


class HourlyJobExecutor:
    """
    Executes hourly summarization jobs.

    Handles:
    - Job creation for new hours
    - Job execution with retry logic
    - Status tracking in database
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
        self.api_key = api_key
        self.summarizer = HourlySummarizer(api_key=api_key, db_path=self.db_path)

    def create_pending_job(self, hour_start: datetime) -> str:
        """
        Create a pending job for an hour.

        Args:
            hour_start: Start of the hour

        Returns:
            Job ID
        """
        hour_start = hour_start.replace(minute=0, second=0, microsecond=0)
        hour_end = hour_start + timedelta(hours=1)

        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()

            # Check for existing job
            cursor.execute(
                """
                SELECT job_id, status FROM jobs
                WHERE job_type = 'hourly'
                AND window_start_ts = ?
                """,
                (hour_start.isoformat(),),
            )
            row = cursor.fetchone()

            if row:
                # Job exists
                if row["status"] in ("success", "running"):
                    logger.debug(
                        f"Job already exists for {hour_start.isoformat()}: {row['status']}"
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
                    VALUES (?, 'hourly', ?, ?, 'pending', 0, ?, ?)
                    """,
                    (
                        job_id,
                        hour_start.isoformat(),
                        hour_end.isoformat(),
                        datetime.now().isoformat(),
                        datetime.now().isoformat(),
                    ),
                )

            conn.commit()
            logger.info(f"Created pending job {job_id} for {hour_start.isoformat()}")
            return job_id

        finally:
            conn.close()

    def execute_job(self, job_id: str) -> SummarizationResult:
        """
        Execute a specific job.

        Args:
            job_id: ID of the job to execute

        Returns:
            SummarizationResult from summarization
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
                return SummarizationResult(
                    success=False,
                    note_id=None,
                    file_path=None,
                    error="Job not found",
                )

            if row["status"] == "running":
                logger.warning(f"Job {job_id} is already running")
                return SummarizationResult(
                    success=False,
                    note_id=None,
                    file_path=None,
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

            hour_start = datetime.fromisoformat(row["window_start_ts"])

        finally:
            conn.close()

        # Execute summarization
        try:
            logger.info(f"Executing job {job_id} for {hour_start.isoformat()} (attempt {attempts})")
            result = self.summarizer.summarize_hour(hour_start)

            # Update job status
            self._update_job_status(
                job_id=job_id,
                success=result.success,
                error=result.error,
                result={
                    "note_id": result.note_id,
                    "file_path": str(result.file_path) if result.file_path else None,
                    "events_count": result.events_count,
                    "screenshots_count": result.screenshots_count,
                    "keyframes_count": result.keyframes_count,
                    "entities_count": result.entities_count,
                    "embedding_computed": result.embedding_computed,
                },
            )

            return result

        except Exception as e:
            logger.error(f"Job {job_id} failed with exception: {e}")
            self._update_job_status(
                job_id=job_id,
                success=False,
                error=str(e),
            )
            return SummarizationResult(
                success=False,
                note_id=None,
                file_path=None,
                error=str(e),
            )

    def execute_pending_jobs(self) -> list[SummarizationResult]:
        """
        Execute all pending jobs.

        Returns:
            List of results
        """
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT job_id FROM jobs
                WHERE job_type = 'hourly'
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

    def get_job_status(self, job_id: str) -> JobStatus | None:
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

            return JobStatus(
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

    def get_recent_jobs(self, limit: int = 24) -> list[JobStatus]:
        """Get recent jobs."""
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT job_id, job_type, window_start_ts, window_end_ts,
                       status, attempts, last_error, result_json
                FROM jobs
                WHERE job_type = 'hourly'
                ORDER BY window_start_ts DESC
                LIMIT ?
                """,
                (limit,),
            )

            jobs = []
            for row in cursor.fetchall():
                jobs.append(
                    JobStatus(
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


class HourlyJobScheduler:
    """
    Schedules and runs hourly summarization jobs.

    Uses APScheduler to run jobs at the start of each hour.
    """

    def __init__(
        self,
        db_path: Path | str | None = None,
        api_key: str | None = None,
        on_job_complete: Callable[[SummarizationResult], None] | None = None,
    ):
        """
        Initialize the scheduler.

        Args:
            db_path: Path to SQLite database
            api_key: OpenAI API key
            on_job_complete: Callback when a job completes
        """
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.api_key = api_key
        self.on_job_complete = on_job_complete

        self.executor = HourlyJobExecutor(db_path=self.db_path, api_key=api_key)
        self.scheduler = BackgroundScheduler()
        self._running = False

    def start(self) -> None:
        """Start the scheduler."""
        if self._running:
            logger.warning("Scheduler is already running")
            return

        # Add hourly job at minute 5 of each hour (giving time for capture to complete)
        self.scheduler.add_job(
            self._hourly_job,
            trigger=CronTrigger(minute=5),
            id="hourly_summarization",
            name="Hourly Summarization",
            replace_existing=True,
        )

        self.scheduler.start()
        self._running = True
        logger.info("Hourly job scheduler started")

        # Execute any pending jobs immediately
        self._execute_pending()

    def stop(self) -> None:
        """Stop the scheduler."""
        if not self._running:
            return

        self.scheduler.shutdown(wait=True)
        self._running = False
        logger.info("Hourly job scheduler stopped")

    def _hourly_job(self) -> None:
        """Job that runs every hour."""
        # Create job for the previous hour
        previous_hour = (datetime.now() - timedelta(hours=1)).replace(
            minute=0, second=0, microsecond=0
        )

        logger.info(f"Hourly job triggered for {previous_hour.isoformat()}")

        job_id = self.executor.create_pending_job(previous_hour)
        result = self.executor.execute_job(job_id)

        if self.on_job_complete:
            self.on_job_complete(result)

    def _execute_pending(self) -> None:
        """Execute any pending jobs on startup."""
        results = self.executor.execute_pending_jobs()

        for result in results:
            if self.on_job_complete:
                self.on_job_complete(result)

    def trigger_now(self, hour_start: datetime | None = None) -> SummarizationResult:
        """
        Trigger summarization immediately.

        Args:
            hour_start: Hour to summarize (defaults to previous hour)

        Returns:
            Summarization result
        """
        if hour_start is None:
            hour_start = (datetime.now() - timedelta(hours=1)).replace(
                minute=0, second=0, microsecond=0
            )
        else:
            hour_start = hour_start.replace(minute=0, second=0, microsecond=0)

        job_id = self.executor.create_pending_job(hour_start)
        return self.executor.execute_job(job_id)

    def is_running(self) -> bool:
        """Check if scheduler is running."""
        return self._running

    def get_next_run_time(self) -> datetime | None:
        """Get the next scheduled run time."""
        if not self._running:
            return None

        job = self.scheduler.get_job("hourly_summarization")
        if job and job.next_run_time:
            return job.next_run_time
        return None


if __name__ == "__main__":
    import time

    import fire

    def run(hours: int = 1, db_path: str | None = None):
        """
        Run the hourly scheduler for a specified duration.

        Args:
            hours: Number of hours to run
            db_path: Path to database
        """

        def on_complete(result: SummarizationResult):
            print(f"Job complete: success={result.success}, note_id={result.note_id}")

        scheduler = HourlyJobScheduler(db_path=db_path, on_job_complete=on_complete)
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

    def trigger(hour: str | None = None, db_path: str | None = None):
        """
        Trigger summarization immediately.

        Args:
            hour: Hour to summarize in ISO format
            db_path: Path to database
        """
        hour_start = datetime.fromisoformat(hour) if hour else None

        scheduler = HourlyJobScheduler(db_path=db_path)
        result = scheduler.trigger_now(hour_start)

        return {
            "success": result.success,
            "note_id": result.note_id,
            "file_path": str(result.file_path) if result.file_path else None,
            "error": result.error,
        }

    def status(db_path: str | None = None, limit: int = 24):
        """
        Show recent job status.

        Args:
            db_path: Path to database
            limit: Number of jobs to show
        """
        executor = HourlyJobExecutor(db_path=db_path)
        jobs = executor.get_recent_jobs(limit)

        result = []
        for job in jobs:
            result.append(
                {
                    "job_id": job.job_id[:8],
                    "hour": job.window_start_ts.strftime("%Y-%m-%d %H:00"),
                    "status": job.status,
                    "attempts": job.attempts,
                    "error": job.last_error[:50] if job.last_error else None,
                }
            )

        return result

    def pending(db_path: str | None = None):
        """Execute all pending jobs."""
        executor = HourlyJobExecutor(db_path=db_path)
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
