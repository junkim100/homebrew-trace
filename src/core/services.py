"""
Service Manager for Trace

Centralized management of all background services:
- Capture Daemon: Screenshot and activity capture
- Hourly Scheduler: Hourly note summarization
- Daily Scheduler: Daily revision and cleanup

Features:
- Auto-start all services on app launch
- Health monitoring and automatic restart
- Backfill detection for missing notes
- macOS notifications for errors
"""

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

from src.capture.daemon import CaptureDaemon
from src.core.paths import DB_PATH
from src.jobs.backfill import BackfillDetector, BackfillResult
from src.jobs.daily import DailyJobScheduler
from src.jobs.hourly import HourlyJobScheduler
from src.platform.notifications import (
    send_critical_notification,
    send_error_notification,
    send_service_notification,
)
from src.platform.sleep_wake import SleepWakeDetector

logger = logging.getLogger(__name__)


class ServiceState(str, Enum):
    """State of a service."""

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    FAILED = "failed"
    RESTARTING = "restarting"


@dataclass
class ServiceStatus:
    """Status information for a service."""

    name: str
    state: ServiceState
    start_time: datetime | None = None
    restart_count: int = 0
    last_error: str | None = None
    details: dict = field(default_factory=dict)


class ServiceManager:
    """
    Manages lifecycle of all background services.

    Provides centralized control for starting, stopping, and monitoring
    all Trace background services.
    """

    # Maximum restart attempts before giving up
    MAX_RESTART_ATTEMPTS = 3

    # Health check interval in seconds
    HEALTH_CHECK_INTERVAL = 60

    # Backfill check interval (only check every N health checks)
    BACKFILL_CHECK_INTERVAL = 60  # Check every 60 health checks (~1 hour)

    def __init__(
        self,
        db_path: Path | str | None = None,
        api_key: str | None = None,
    ):
        """
        Initialize the service manager.

        Args:
            db_path: Path to SQLite database
            api_key: OpenAI API key for summarization
        """
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")

        # Service instances
        self._capture_daemon: CaptureDaemon | None = None
        self._hourly_scheduler: HourlyJobScheduler | None = None
        self._daily_scheduler: DailyJobScheduler | None = None
        self._backfill_detector: BackfillDetector | None = None
        self._sleep_wake_detector: SleepWakeDetector | None = None

        # Service status tracking
        self._services: dict[str, ServiceStatus] = {
            "capture": ServiceStatus(name="capture", state=ServiceState.STOPPED),
            "hourly": ServiceStatus(name="hourly", state=ServiceState.STOPPED),
            "daily": ServiceStatus(name="daily", state=ServiceState.STOPPED),
        }

        # Health monitoring
        self._health_thread: threading.Thread | None = None
        self._health_check_count = 0
        self._running = False
        self._lock = threading.Lock()

    def start_all(self, notify: bool = True) -> dict[str, bool]:
        """
        Start all services.

        Args:
            notify: Whether to send notifications for failures

        Returns:
            Dictionary mapping service names to success status
        """
        logger.info("Starting all services...")
        results = {}

        # Check for API key
        if not self.api_key:
            logger.warning("OPENAI_API_KEY not set - hourly/daily summarization will fail")
            if notify:
                send_critical_notification(
                    "API Key Missing",
                    "Set OPENAI_API_KEY for note generation",
                )

        # Start services
        results["capture"] = self._start_capture()
        results["hourly"] = self._start_hourly()
        results["daily"] = self._start_daily()

        # Start health monitor
        self._start_health_monitor()

        # Start sleep/wake detector for immediate catch-up on wake
        self._start_sleep_wake_detector()

        # Run initial backfill check (in background)
        self._schedule_backfill_check()

        # Notify about failures
        failed = [k for k, v in results.items() if not v]
        if failed and notify:
            send_error_notification(
                f"Failed to start: {', '.join(failed)}",
                "Check logs for details",
            )

        logger.info(f"Service startup complete: {results}")
        return results

    def stop_all(self) -> None:
        """Stop all services gracefully."""
        logger.info("Stopping all services...")

        self._running = False

        # Stop health monitor
        if self._health_thread and self._health_thread.is_alive():
            self._health_thread.join(timeout=5)

        # Stop sleep/wake detector
        self._stop_sleep_wake_detector()

        # Stop services in reverse order
        self._stop_daily()
        self._stop_hourly()
        self._stop_capture()

        logger.info("All services stopped")

    def get_health_status(self) -> dict:
        """
        Get health status of all services.

        Returns:
            Dictionary with service statuses and overall health
        """
        with self._lock:
            statuses = {}
            all_healthy = True

            for name, status in self._services.items():
                is_running = self._check_service_running(name)

                statuses[name] = {
                    "state": status.state.value,
                    "running": is_running,
                    "start_time": status.start_time.isoformat() if status.start_time else None,
                    "restart_count": status.restart_count,
                    "last_error": status.last_error,
                }

                if not is_running and status.state != ServiceState.STOPPED:
                    all_healthy = False

            return {
                "healthy": all_healthy,
                "services": statuses,
                "health_checks": self._health_check_count,
            }

    def restart_service(self, service_name: str) -> bool:
        """
        Restart a specific service.

        Args:
            service_name: Name of service to restart

        Returns:
            True if restart successful
        """
        logger.info(f"Restarting service: {service_name}")

        with self._lock:
            if service_name not in self._services:
                logger.error(f"Unknown service: {service_name}")
                return False

            status = self._services[service_name]
            status.state = ServiceState.RESTARTING

        # Stop then start
        if service_name == "capture":
            self._stop_capture()
            return self._start_capture()
        elif service_name == "hourly":
            self._stop_hourly()
            return self._start_hourly()
        elif service_name == "daily":
            self._stop_daily()
            return self._start_daily()

        return False

    def trigger_backfill(self, notify: bool = True) -> BackfillResult:
        """
        Manually trigger backfill check and execution.

        Args:
            notify: Whether to send notifications

        Returns:
            BackfillResult with statistics
        """
        if self._backfill_detector is None:
            self._backfill_detector = BackfillDetector(
                db_path=self.db_path,
                api_key=self.api_key,
            )

        return self._backfill_detector.check_and_backfill(notify=notify)

    # --- Private methods ---

    def _start_capture(self) -> bool:
        """Start the capture daemon."""
        try:
            with self._lock:
                self._services["capture"].state = ServiceState.STARTING

            self._capture_daemon = CaptureDaemon(
                db_path=self.db_path,
                capture_interval=1.0,
            )
            self._capture_daemon.start(blocking=False)

            with self._lock:
                self._services["capture"].state = ServiceState.RUNNING
                self._services["capture"].start_time = datetime.now()
                self._services["capture"].last_error = None

            logger.info("Capture daemon started")
            return True

        except Exception as e:
            logger.error(f"Failed to start capture daemon: {e}")
            with self._lock:
                self._services["capture"].state = ServiceState.FAILED
                self._services["capture"].last_error = str(e)
            return False

    def _stop_capture(self) -> None:
        """Stop the capture daemon."""
        if self._capture_daemon:
            try:
                self._capture_daemon.stop()
                logger.info("Capture daemon stopped")
            except Exception as e:
                logger.error(f"Error stopping capture daemon: {e}")

            self._capture_daemon = None

        with self._lock:
            self._services["capture"].state = ServiceState.STOPPED

    def _start_hourly(self) -> bool:
        """Start the hourly scheduler."""
        try:
            with self._lock:
                self._services["hourly"].state = ServiceState.STARTING

            self._hourly_scheduler = HourlyJobScheduler(
                db_path=self.db_path,
                api_key=self.api_key,
            )
            self._hourly_scheduler.start()

            with self._lock:
                self._services["hourly"].state = ServiceState.RUNNING
                self._services["hourly"].start_time = datetime.now()
                self._services["hourly"].last_error = None

            logger.info("Hourly scheduler started")
            return True

        except Exception as e:
            logger.error(f"Failed to start hourly scheduler: {e}")
            with self._lock:
                self._services["hourly"].state = ServiceState.FAILED
                self._services["hourly"].last_error = str(e)
            return False

    def _stop_hourly(self) -> None:
        """Stop the hourly scheduler."""
        if self._hourly_scheduler:
            try:
                self._hourly_scheduler.stop()
                logger.info("Hourly scheduler stopped")
            except Exception as e:
                logger.error(f"Error stopping hourly scheduler: {e}")

            self._hourly_scheduler = None

        with self._lock:
            self._services["hourly"].state = ServiceState.STOPPED

    def _start_daily(self) -> bool:
        """Start the daily scheduler."""
        try:
            with self._lock:
                self._services["daily"].state = ServiceState.STARTING

            self._daily_scheduler = DailyJobScheduler(
                db_path=self.db_path,
                api_key=self.api_key,
            )
            self._daily_scheduler.start()

            with self._lock:
                self._services["daily"].state = ServiceState.RUNNING
                self._services["daily"].start_time = datetime.now()
                self._services["daily"].last_error = None

            logger.info("Daily scheduler started")
            return True

        except Exception as e:
            logger.error(f"Failed to start daily scheduler: {e}")
            with self._lock:
                self._services["daily"].state = ServiceState.FAILED
                self._services["daily"].last_error = str(e)
            return False

    def _stop_daily(self) -> None:
        """Stop the daily scheduler."""
        if self._daily_scheduler:
            try:
                self._daily_scheduler.stop()
                logger.info("Daily scheduler stopped")
            except Exception as e:
                logger.error(f"Error stopping daily scheduler: {e}")

            self._daily_scheduler = None

        with self._lock:
            self._services["daily"].state = ServiceState.STOPPED

    def _start_health_monitor(self) -> None:
        """Start the health monitoring thread."""
        self._running = True
        self._health_thread = threading.Thread(
            target=self._health_check_loop,
            daemon=True,
            name="health-monitor",
        )
        self._health_thread.start()
        logger.info("Health monitor started")

    def _health_check_loop(self) -> None:
        """Background health check loop."""
        while self._running:
            try:
                self._perform_health_check()
                self._health_check_count += 1

                # Periodic backfill check
                if self._health_check_count % self.BACKFILL_CHECK_INTERVAL == 0:
                    self._schedule_backfill_check()

            except Exception as e:
                logger.error(f"Health check error: {e}")

            time.sleep(self.HEALTH_CHECK_INTERVAL)

    def _perform_health_check(self) -> None:
        """Check health of all services and restart if needed."""
        for name in self._services:
            with self._lock:
                status = self._services[name]

                # Skip if intentionally stopped
                if status.state == ServiceState.STOPPED:
                    continue

                # Check if service is running
                if not self._check_service_running(name):
                    logger.warning(f"Service {name} is not running (state: {status.state})")

                    # Attempt restart if under limit
                    if status.restart_count < self.MAX_RESTART_ATTEMPTS:
                        status.restart_count += 1
                        logger.info(
                            f"Restarting {name} (attempt {status.restart_count}/{self.MAX_RESTART_ATTEMPTS})"
                        )

                        # Release lock for restart
                        self._lock.release()
                        try:
                            success = self.restart_service(name)
                            if success:
                                send_service_notification(
                                    name, "restarted", f"Attempt {status.restart_count}"
                                )
                            else:
                                send_error_notification(
                                    f"Failed to restart {name}",
                                    f"Attempt {status.restart_count}",
                                )
                        finally:
                            self._lock.acquire()
                    else:
                        # Max retries exceeded
                        if status.state != ServiceState.FAILED:
                            status.state = ServiceState.FAILED
                            send_critical_notification(
                                f"{name.title()} Service Failed",
                                f"Max restart attempts ({self.MAX_RESTART_ATTEMPTS}) exceeded",
                            )

    def _check_service_running(self, name: str) -> bool:
        """Check if a specific service is actually running."""
        if name == "capture":
            return self._capture_daemon is not None and self._capture_daemon._running
        elif name == "hourly":
            return self._hourly_scheduler is not None and self._hourly_scheduler.is_running()
        elif name == "daily":
            return self._daily_scheduler is not None and self._daily_scheduler.is_running()
        return False

    def _schedule_backfill_check(self) -> None:
        """Schedule a backfill check in a background thread."""
        if not self.api_key:
            logger.debug("Skipping backfill check - no API key")
            return

        thread = threading.Thread(
            target=self._run_backfill_check,
            daemon=True,
            name="backfill-check",
        )
        thread.start()

    def _start_sleep_wake_detector(self) -> None:
        """Start the sleep/wake detector for immediate catch-up on wake."""
        try:
            self._sleep_wake_detector = SleepWakeDetector()

            # Register wake callback to trigger immediate backfill
            self._sleep_wake_detector.add_wake_callback(self._on_system_wake)

            # Register sleep callback for logging
            self._sleep_wake_detector.add_sleep_callback(self._on_system_sleep)

            if self._sleep_wake_detector.start():
                logger.info("Sleep/wake detector started")
            else:
                logger.warning("Failed to start sleep/wake detector")
        except Exception as e:
            logger.error(f"Error starting sleep/wake detector: {e}")

    def _stop_sleep_wake_detector(self) -> None:
        """Stop the sleep/wake detector."""
        if self._sleep_wake_detector:
            self._sleep_wake_detector.stop()
            self._sleep_wake_detector = None
            logger.info("Sleep/wake detector stopped")

    def _on_system_sleep(self, sleep_time: datetime) -> None:
        """Handle system sleep event."""
        logger.info(f"System going to sleep at {sleep_time}")
        # Could pause capture daemon here if needed

    def _on_system_wake(self, wake_time: datetime, sleep_duration: float) -> None:
        """
        Handle system wake event.

        Triggers immediate backfill check to catch up on any missed
        summarization windows while the system was sleeping.

        Args:
            wake_time: When the system woke up
            sleep_duration: How long the system was asleep (seconds)
        """
        logger.info(f"System woke at {wake_time} after sleeping {sleep_duration:.1f}s")

        # Only trigger backfill if we slept for more than 5 minutes
        # (short sleeps probably didn't miss any hourly windows)
        if sleep_duration > 300:  # 5 minutes
            logger.info("Triggering immediate backfill check after wake")
            send_service_notification(
                "System Wake",
                f"Checking for missed notes after {sleep_duration / 60:.0f}min sleep",
            )
            self._schedule_backfill_check()
        else:
            logger.debug(f"Short sleep ({sleep_duration:.0f}s), skipping backfill")

    def _run_backfill_check(self) -> None:
        """Run backfill check in background."""
        try:
            if self._backfill_detector is None:
                self._backfill_detector = BackfillDetector(
                    db_path=self.db_path,
                    api_key=self.api_key,
                )

            missing = self._backfill_detector.find_missing_hours()
            if missing:
                logger.info(f"Found {len(missing)} hours needing backfill")
                self._backfill_detector.trigger_backfill(missing, notify=True)

        except Exception as e:
            logger.error(f"Backfill check failed: {e}")


if __name__ == "__main__":
    import fire

    def start(db_path: str | None = None):
        """Start all services."""
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

        manager = ServiceManager(db_path=db_path)
        results = manager.start_all()

        print(f"Service startup: {results}")
        print("Press Ctrl+C to stop...")

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            manager.stop_all()

        return results

    def status(db_path: str | None = None):
        """Check service status (without starting)."""
        manager = ServiceManager(db_path=db_path)
        return manager.get_health_status()

    fire.Fire({"start": start, "status": status})
