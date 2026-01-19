"""
Logging infrastructure for Trace.

P9-05: Logging infrastructure
Provides structured logging to file and console.
"""

import json
import logging
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from src.core.paths import DATA_ROOT

# Default log directory
LOG_DIR = DATA_ROOT / "logs"

# Log format for console (human-readable)
CONSOLE_FORMAT = "%(asctime)s [%(levelname)8s] %(name)s: %(message)s"
CONSOLE_DATE_FORMAT = "%H:%M:%S"

# Log format for file (structured, more detail)
FILE_FORMAT = "%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s"
FILE_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Default log levels
DEFAULT_CONSOLE_LEVEL = logging.INFO
DEFAULT_FILE_LEVEL = logging.DEBUG

# Log rotation settings
MAX_LOG_SIZE_MB = 10
MAX_LOG_FILES = 5


class StructuredLogFormatter(logging.Formatter):
    """
    Formatter that outputs structured JSON logs.

    Useful for log aggregation and analysis tools.
    """

    def __init__(self, include_extra: bool = True):
        """
        Initialize the formatter.

        Args:
            include_extra: Include extra fields in the log record
        """
        super().__init__()
        self.include_extra = include_extra

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as JSON."""
        log_data = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields
        if self.include_extra:
            # Get extra fields from record
            extra_fields = {}
            for key, value in record.__dict__.items():
                if key not in {
                    "name",
                    "msg",
                    "args",
                    "created",
                    "filename",
                    "funcName",
                    "levelname",
                    "levelno",
                    "lineno",
                    "module",
                    "msecs",
                    "pathname",
                    "process",
                    "processName",
                    "relativeCreated",
                    "stack_info",
                    "exc_info",
                    "exc_text",
                    "thread",
                    "threadName",
                    "message",
                    "taskName",
                }:
                    try:
                        # Ensure the value is JSON serializable
                        json.dumps(value)
                        extra_fields[key] = value
                    except (TypeError, ValueError):
                        extra_fields[key] = str(value)

            if extra_fields:
                log_data["extra"] = extra_fields

        return json.dumps(log_data)


class ColoredConsoleFormatter(logging.Formatter):
    """
    Formatter that adds colors to console output.
    """

    # ANSI color codes
    COLORS = {
        logging.DEBUG: "\033[36m",  # Cyan
        logging.INFO: "\033[32m",  # Green
        logging.WARNING: "\033[33m",  # Yellow
        logging.ERROR: "\033[31m",  # Red
        logging.CRITICAL: "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def __init__(self, fmt: str | None = None, datefmt: str | None = None, use_colors: bool = True):
        """
        Initialize the formatter.

        Args:
            fmt: Log format string
            datefmt: Date format string
            use_colors: Whether to use colors
        """
        super().__init__(fmt=fmt, datefmt=datefmt)
        self.use_colors = use_colors and sys.stderr.isatty()

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record with optional colors."""
        if self.use_colors:
            original_levelname = record.levelname
            color = self.COLORS.get(record.levelno, "")
            record.levelname = f"{color}{record.levelname}{self.RESET}"
            try:
                return super().format(record)
            finally:
                record.levelname = original_levelname
        return super().format(record)


def setup_logging(
    console_level: int | str = DEFAULT_CONSOLE_LEVEL,
    file_level: int | str = DEFAULT_FILE_LEVEL,
    log_dir: Path | str | None = None,
    log_file: str = "trace.log",
    structured_file: str | None = "trace.jsonl",
    use_colors: bool = True,
    capture_warnings: bool = True,
) -> logging.Logger:
    """
    Set up logging for the Trace application.

    Configures:
    - Console handler with human-readable format
    - Rotating file handler with detailed format
    - Optional JSON log file for structured logging

    Args:
        console_level: Log level for console output
        file_level: Log level for file output
        log_dir: Directory for log files
        log_file: Name of the main log file
        structured_file: Name of the JSON log file (None to disable)
        use_colors: Use colored output in console
        capture_warnings: Capture Python warnings to log

    Returns:
        Root logger instance
    """
    # Convert string levels to int
    if isinstance(console_level, str):
        console_level = getattr(logging, console_level.upper())
    if isinstance(file_level, str):
        file_level = getattr(logging, file_level.upper())

    # Set up log directory
    if log_dir is None:
        log_dir = LOG_DIR
    else:
        log_dir = Path(log_dir)

    log_dir.mkdir(parents=True, exist_ok=True)

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Capture all, handlers filter

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Console handler
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(console_level)
    console_formatter = ColoredConsoleFormatter(
        fmt=CONSOLE_FORMAT,
        datefmt=CONSOLE_DATE_FORMAT,
        use_colors=use_colors,
    )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # File handler (rotating)
    file_path = log_dir / log_file
    file_handler = RotatingFileHandler(
        file_path,
        maxBytes=MAX_LOG_SIZE_MB * 1024 * 1024,
        backupCount=MAX_LOG_FILES,
        encoding="utf-8",
    )
    file_handler.setLevel(file_level)
    file_formatter = logging.Formatter(
        fmt=FILE_FORMAT,
        datefmt=FILE_DATE_FORMAT,
    )
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    # Structured JSON log file
    if structured_file:
        structured_path = log_dir / structured_file
        structured_handler = RotatingFileHandler(
            structured_path,
            maxBytes=MAX_LOG_SIZE_MB * 1024 * 1024,
            backupCount=MAX_LOG_FILES,
            encoding="utf-8",
        )
        structured_handler.setLevel(file_level)
        structured_formatter = StructuredLogFormatter()
        structured_handler.setFormatter(structured_formatter)
        root_logger.addHandler(structured_handler)

    # Capture warnings
    if capture_warnings:
        logging.captureWarnings(True)

    # Log startup
    root_logger.info(
        f"Logging initialized (console: {logging.getLevelName(console_level)}, file: {logging.getLevelName(file_level)})"
    )

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger for a specific module.

    Args:
        name: Logger name (usually __name__)

    Returns:
        Logger instance
    """
    return logging.getLogger(name)


class LogContext:
    """
    Context manager for adding context to log messages.

    Usage:
        with LogContext(operation="capture", hour="2025-01-15T10:00"):
            logger.info("Processing...")  # Will include extra fields
    """

    def __init__(self, **context: Any):
        """
        Initialize the log context.

        Args:
            **context: Key-value pairs to add to log records
        """
        self.context = context
        self._old_factory: logging.LogRecordFactory | None = None

    def __enter__(self):
        """Enter the context."""
        context = self.context

        old_factory = logging.getLogRecordFactory()
        self._old_factory = old_factory

        def record_factory(*args, **kwargs):
            record = old_factory(*args, **kwargs)
            for key, value in context.items():
                setattr(record, key, value)
            return record

        logging.setLogRecordFactory(record_factory)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit the context."""
        if self._old_factory:
            logging.setLogRecordFactory(self._old_factory)


def log_exception(
    logger: logging.Logger,
    message: str,
    exc: Exception,
    level: int = logging.ERROR,
    **extra: Any,
) -> None:
    """
    Log an exception with context.

    Args:
        logger: Logger to use
        message: Log message
        exc: Exception to log
        level: Log level
        **extra: Extra fields to include
    """
    logger.log(
        level,
        f"{message}: {type(exc).__name__}: {exc}",
        exc_info=True,
        extra=extra,
    )


def log_timing(
    logger: logging.Logger,
    operation: str,
    duration_seconds: float,
    level: int = logging.DEBUG,
    **extra: Any,
) -> None:
    """
    Log timing information.

    Args:
        logger: Logger to use
        operation: Name of the operation
        duration_seconds: Duration in seconds
        level: Log level
        **extra: Extra fields to include
    """
    if duration_seconds < 1:
        duration_str = f"{duration_seconds * 1000:.1f}ms"
    else:
        duration_str = f"{duration_seconds:.2f}s"

    logger.log(
        level,
        f"{operation} completed in {duration_str}",
        extra={"operation": operation, "duration_seconds": duration_seconds, **extra},
    )


class OperationTimer:
    """
    Context manager for timing operations and logging the result.

    Usage:
        with OperationTimer(logger, "summarize_hour"):
            # do work
    """

    def __init__(
        self,
        logger: logging.Logger,
        operation: str,
        level: int = logging.DEBUG,
        **extra: Any,
    ):
        """
        Initialize the timer.

        Args:
            logger: Logger to use
            operation: Name of the operation
            level: Log level
            **extra: Extra fields to include
        """
        self.logger = logger
        self.operation = operation
        self.level = level
        self.extra = extra
        self.start_time: float | None = None

    def __enter__(self):
        """Enter the context."""
        import time

        self.start_time = time.time()
        self.logger.log(
            self.level,
            f"Starting {self.operation}",
            extra={"operation": self.operation, **self.extra},
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit the context."""
        import time

        if self.start_time is not None:
            duration = time.time() - self.start_time
            if exc_type is None:
                log_timing(self.logger, self.operation, duration, self.level, **self.extra)
            else:
                self.logger.log(
                    logging.ERROR,
                    f"{self.operation} failed after {duration:.2f}s",
                    exc_info=True,
                    extra={"operation": self.operation, "duration_seconds": duration, **self.extra},
                )


# Module-level logger for this file
logger = get_logger(__name__)


if __name__ == "__main__":
    import tempfile

    import fire

    def test_logging(level: str = "DEBUG", use_colors: bool = True):
        """Test logging setup."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            setup_logging(
                console_level=level,
                file_level="DEBUG",
                log_dir=tmp_dir,
                use_colors=use_colors,
            )

            test_logger = get_logger("test")

            test_logger.debug("Debug message")
            test_logger.info("Info message")
            test_logger.warning("Warning message")
            test_logger.error("Error message")

            # Test context
            with LogContext(operation="test_op", user_id="123"):
                test_logger.info("Message with context")

            # Test timing
            with OperationTimer(test_logger, "test_operation"):
                import time

                time.sleep(0.1)

            # Test exception logging
            try:
                raise ValueError("Test error")
            except ValueError as e:
                log_exception(test_logger, "Caught exception", e)

            # Show log files
            log_path = Path(tmp_dir)
            for f in log_path.iterdir():
                print(f"Log file: {f}")
                print(f.read_text()[:500])
                print("---")

    def show_formats():
        """Show available log formats."""
        print("Console format:", CONSOLE_FORMAT)
        print("File format:", FILE_FORMAT)
        print()
        print("Example structured log:")
        record = logging.LogRecord(
            name="test.module",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        formatter = StructuredLogFormatter()
        print(formatter.format(record))

    fire.Fire(
        {
            "test": test_logging,
            "formats": show_formats,
        }
    )
