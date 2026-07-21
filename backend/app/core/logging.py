"""
app/core/logging.py
====================
Structured logging configuration using structlog.

Environments:
  development  — human-readable ConsoleRenderer (coloured, timestamped)
  production   — JSON lines for log aggregation tools (Datadog, CloudWatch, etc.)

Usage in any module:
    import structlog
    logger = structlog.get_logger()
    logger.info("ingestion_completed", chunk_count=42, duration_ms=180)
"""

import logging
import logging.config
import sys

import structlog


def configure_structlog(log_level: str = "INFO", log_format: str = "json") -> None:
    """
    Configure structlog with shared processors.

    Args:
        log_level:  Python logging level string (INFO, DEBUG, WARNING, ERROR).
        log_format: "json" for production JSON lines, "console" for dev console output.
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    # Shared processors applied to every log event regardless of renderer
    shared_processors: list = [
        structlog.contextvars.merge_contextvars,          # per-request bound vars (e.g. request_id)
        structlog.stdlib.add_logger_name,                 # adds "logger" key
        structlog.stdlib.add_log_level,                   # adds "level" key
        structlog.stdlib.PositionalArgumentsFormatter(),  # % formatting compat
        structlog.processors.StackInfoRenderer(),
        structlog.processors.TimeStamper(fmt="iso"),      # adds "timestamp" key
    ]

    if log_format == "console":
        renderer = structlog.dev.ConsoleRenderer(
            exception_formatter=structlog.dev.plain_traceback
        )
    else:
        # JSON renderer for production — parse-friendly for Datadog/CloudWatch
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    # Root logger — captures stdlib logging from all libraries
    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(level)

    # Quieten noisy loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    # Langfuse SDK logs 404s at ERROR level when a prompt isn't in the remote
    # registry — these are expected fallbacks, not application errors.
    logging.getLogger("langfuse").setLevel(logging.CRITICAL)
