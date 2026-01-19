"""
macOS Sleep/Wake Detection for Trace

Monitors system sleep and wake events using NSWorkspace notifications.
This allows immediate catch-up processing when the computer wakes from sleep
instead of waiting for the hourly backfill check.

Uses PyObjC to listen to:
- NSWorkspaceWillSleepNotification: System is about to sleep
- NSWorkspaceDidWakeNotification: System just woke up
- NSWorkspaceScreensDidSleepNotification: Display went to sleep
- NSWorkspaceScreensDidWakeNotification: Display woke up
"""

import logging
import sys
import threading
import time
from collections.abc import Callable
from datetime import datetime

logger = logging.getLogger(__name__)

# Type alias for wake callbacks
WakeCallback = Callable[[datetime, float], None]


class SleepWakeDetector:
    """
    Detects macOS sleep and wake events.

    Provides callbacks when the system sleeps or wakes, enabling
    immediate catch-up processing for missed summarization windows.
    """

    def __init__(self):
        """Initialize the sleep/wake detector."""
        self._running = False
        self._thread: threading.Thread | None = None
        self._sleep_time: datetime | None = None
        self._wake_callbacks: list[WakeCallback] = []
        self._sleep_callbacks: list[Callable[[datetime], None]] = []
        self._observer = None
        self._lock = threading.Lock()

    def add_wake_callback(self, callback: WakeCallback) -> None:
        """
        Add a callback to be called when system wakes.

        Args:
            callback: Function taking (wake_time, sleep_duration_seconds)
        """
        with self._lock:
            self._wake_callbacks.append(callback)

    def add_sleep_callback(self, callback: Callable[[datetime], None]) -> None:
        """
        Add a callback to be called when system sleeps.

        Args:
            callback: Function taking (sleep_time)
        """
        with self._lock:
            self._sleep_callbacks.append(callback)

    def start(self) -> bool:
        """
        Start monitoring sleep/wake events.

        Returns:
            True if started successfully, False otherwise
        """
        if sys.platform != "darwin":
            logger.warning("Sleep/wake detection only supported on macOS")
            return False

        if self._running:
            logger.debug("Sleep/wake detector already running")
            return True

        try:
            self._running = True
            self._thread = threading.Thread(
                target=self._run_event_loop,
                name="SleepWakeDetector",
                daemon=True,
            )
            self._thread.start()
            logger.info("Sleep/wake detector started")
            return True
        except Exception as e:
            logger.error(f"Failed to start sleep/wake detector: {e}")
            self._running = False
            return False

    def stop(self) -> None:
        """Stop monitoring sleep/wake events."""
        self._running = False
        if self._thread and self._thread.is_alive():
            # The thread will exit on next iteration
            self._thread.join(timeout=2.0)
        self._thread = None
        logger.info("Sleep/wake detector stopped")

    def _run_event_loop(self) -> None:
        """Run the event loop that listens for sleep/wake notifications."""
        try:
            # Import PyObjC components
            import objc
            from AppKit import NSWorkspace
            from Foundation import NSDate, NSObject, NSRunLoop

            # Create observer class using proper ObjC initialization
            class SleepWakeObserver(NSObject):
                detector = objc.ivar("detector")

                def initWithDetector_(self, detector):
                    self = objc.super(SleepWakeObserver, self).init()
                    if self is None:
                        return None
                    self.detector = detector
                    return self

                def handleSleepNotification_(self, notification):
                    """Called when system is about to sleep."""
                    if self.detector:
                        self.detector._on_sleep()

                def handleWakeNotification_(self, notification):
                    """Called when system wakes from sleep."""
                    if self.detector:
                        self.detector._on_wake()

                def handleScreenSleepNotification_(self, notification):
                    """Called when display goes to sleep."""
                    logger.debug("Display went to sleep")

                def handleScreenWakeNotification_(self, notification):
                    """Called when display wakes up."""
                    logger.debug("Display woke up")

            # Get the shared workspace and notification center
            workspace = NSWorkspace.sharedWorkspace()
            notification_center = workspace.notificationCenter()

            # Create observer
            self._observer = SleepWakeObserver.alloc().initWithDetector_(self)

            # Register for notifications
            notification_center.addObserver_selector_name_object_(
                self._observer,
                "handleSleepNotification:",
                "NSWorkspaceWillSleepNotification",
                None,
            )
            notification_center.addObserver_selector_name_object_(
                self._observer,
                "handleWakeNotification:",
                "NSWorkspaceDidWakeNotification",
                None,
            )
            notification_center.addObserver_selector_name_object_(
                self._observer,
                "handleScreenSleepNotification:",
                "NSWorkspaceScreensDidSleepNotification",
                None,
            )
            notification_center.addObserver_selector_name_object_(
                self._observer,
                "handleScreenWakeNotification:",
                "NSWorkspaceScreensDidWakeNotification",
                None,
            )

            logger.debug("Registered for sleep/wake notifications")

            # Run the event loop
            run_loop = NSRunLoop.currentRunLoop()
            while self._running:
                # Process events for a short interval
                run_loop.runMode_beforeDate_(
                    "NSDefaultRunLoopMode",
                    NSDate.dateWithTimeIntervalSinceNow_(1.0),
                )

            # Cleanup
            notification_center.removeObserver_(self._observer)
            self._observer = None

        except ImportError as e:
            logger.warning(f"PyObjC not available for sleep/wake detection: {e}")
            # Fall back to polling-based detection
            self._run_polling_fallback()
        except Exception as e:
            logger.error(f"Error in sleep/wake event loop: {e}")

    def _run_polling_fallback(self) -> None:
        """
        Fallback polling-based sleep detection.

        Detects sleep by monitoring for gaps in time between checks.
        If time jumps forward significantly, we likely just woke from sleep.
        """
        logger.info("Using polling-based sleep detection (PyObjC not available)")
        last_check = datetime.now()
        check_interval = 5.0  # Check every 5 seconds
        sleep_threshold = 30.0  # Consider it sleep if >30 seconds gap

        while self._running:
            time.sleep(check_interval)
            now = datetime.now()
            elapsed = (now - last_check).total_seconds()

            if elapsed > sleep_threshold:
                # Significant time gap detected - likely woke from sleep
                logger.info(f"Detected wake from sleep (gap: {elapsed:.1f}s)")
                self._sleep_time = last_check
                self._on_wake()

            last_check = now

    def _on_sleep(self) -> None:
        """Handle system sleep event."""
        self._sleep_time = datetime.now()
        logger.info(f"System going to sleep at {self._sleep_time}")

        with self._lock:
            for callback in self._sleep_callbacks:
                try:
                    callback(self._sleep_time)
                except Exception as e:
                    logger.error(f"Error in sleep callback: {e}")

    def _on_wake(self) -> None:
        """Handle system wake event."""
        wake_time = datetime.now()
        sleep_duration = 0.0

        if self._sleep_time:
            sleep_duration = (wake_time - self._sleep_time).total_seconds()
            logger.info(f"System woke at {wake_time} (slept for {sleep_duration:.1f}s)")
        else:
            logger.info(f"System woke at {wake_time} (sleep time unknown)")

        with self._lock:
            for callback in self._wake_callbacks:
                try:
                    callback(wake_time, sleep_duration)
                except Exception as e:
                    logger.error(f"Error in wake callback: {e}")

        self._sleep_time = None

    @property
    def is_running(self) -> bool:
        """Check if the detector is running."""
        return self._running

    @property
    def last_sleep_time(self) -> datetime | None:
        """Get the time of the last sleep event."""
        return self._sleep_time


# Singleton instance for easy access
_detector: SleepWakeDetector | None = None


def get_sleep_wake_detector() -> SleepWakeDetector:
    """Get or create the singleton sleep/wake detector."""
    global _detector
    if _detector is None:
        _detector = SleepWakeDetector()
    return _detector


def on_wake(callback: WakeCallback) -> None:
    """
    Register a callback for system wake events.

    Args:
        callback: Function taking (wake_time, sleep_duration_seconds)
    """
    get_sleep_wake_detector().add_wake_callback(callback)


def on_sleep(callback: Callable[[datetime], None]) -> None:
    """
    Register a callback for system sleep events.

    Args:
        callback: Function taking (sleep_time)
    """
    get_sleep_wake_detector().add_sleep_callback(callback)


if __name__ == "__main__":
    import fire

    def test_detector(duration: int = 60):
        """
        Test the sleep/wake detector.

        Args:
            duration: How long to run the test in seconds
        """
        logging.basicConfig(level=logging.DEBUG)

        detector = SleepWakeDetector()

        def on_sleep_callback(sleep_time):
            print(f"SLEEP: {sleep_time}")

        def on_wake_callback(wake_time, duration):
            print(f"WAKE: {wake_time} (slept {duration:.1f}s)")

        detector.add_sleep_callback(on_sleep_callback)
        detector.add_wake_callback(on_wake_callback)

        print(f"Starting sleep/wake detector for {duration} seconds...")
        print("Put your computer to sleep to test!")
        detector.start()

        try:
            time.sleep(duration)
        except KeyboardInterrupt:
            pass

        detector.stop()
        print("Test complete.")

    fire.Fire({"test": test_detector})
