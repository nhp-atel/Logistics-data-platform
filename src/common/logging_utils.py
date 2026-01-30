"""
Structured logging utilities with JSON formatting for cloud environments.
"""

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging in cloud environments."""

    def __init__(self, service_name: str = "logistics-platform"):
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record as JSON."""
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "severity": record.levelname,
            "message": record.getMessage(),
            "service": self.service_name,
            "logger": record.name,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Add extra fields
        if hasattr(record, "extra_fields"):
            log_entry.update(record.extra_fields)

        # Add trace context if present
        if hasattr(record, "trace_id"):
            log_entry["logging.googleapis.com/trace"] = record.trace_id
        if hasattr(record, "span_id"):
            log_entry["logging.googleapis.com/spanId"] = record.span_id

        return json.dumps(log_entry, default=str)


class StructuredLogger(logging.Logger):
    """Logger that supports structured logging with extra fields."""

    def _log_with_context(
        self,
        level: int,
        msg: str,
        *args,
        trace_id: str | None = None,
        span_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Log a message with optional context."""
        extra = kwargs.pop("extra", {})

        # Add trace context
        if trace_id:
            extra["trace_id"] = trace_id
        if span_id:
            extra["span_id"] = span_id

        # Add any additional keyword arguments as extra fields
        extra_fields = {k: v for k, v in kwargs.items() if k not in ("exc_info", "stack_info", "stacklevel")}
        if extra_fields:
            extra["extra_fields"] = extra_fields

        # Filter kwargs to only include valid logging kwargs
        log_kwargs = {k: v for k, v in kwargs.items() if k in ("exc_info", "stack_info", "stacklevel")}
        log_kwargs["extra"] = extra

        super()._log(level, msg, args, **log_kwargs)

    def info(self, msg: str, *args, **kwargs) -> None:
        """Log an info message."""
        self._log_with_context(logging.INFO, msg, *args, **kwargs)

    def warning(self, msg: str, *args, **kwargs) -> None:
        """Log a warning message."""
        self._log_with_context(logging.WARNING, msg, *args, **kwargs)

    def error(self, msg: str, *args, **kwargs) -> None:
        """Log an error message."""
        self._log_with_context(logging.ERROR, msg, *args, **kwargs)

    def debug(self, msg: str, *args, **kwargs) -> None:
        """Log a debug message."""
        self._log_with_context(logging.DEBUG, msg, *args, **kwargs)

    def critical(self, msg: str, *args, **kwargs) -> None:
        """Log a critical message."""
        self._log_with_context(logging.CRITICAL, msg, *args, **kwargs)


def setup_logging(
    service_name: str = "logistics-platform",
    log_level: str = "INFO",
    use_json: bool = True,
) -> None:
    """
    Set up logging configuration.

    Args:
        service_name: Name of the service for log entries
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        use_json: Whether to use JSON formatting (True for cloud, False for local dev)
    """
    # Set the custom logger class
    logging.setLoggerClass(StructuredLogger)

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, log_level.upper()))

    # Set formatter
    if use_json:
        formatter = JSONFormatter(service_name=service_name)
    else:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    # Suppress noisy loggers
    logging.getLogger("google").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("apache_beam").setLevel(logging.WARNING)


def get_logger(name: str) -> StructuredLogger:
    """
    Get a structured logger instance.

    Args:
        name: Logger name (typically __name__)

    Returns:
        StructuredLogger instance
    """
    return logging.getLogger(name)  # type: ignore
