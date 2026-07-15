"""
Langfuse observability helpers.

Provides a thin wrapper around Langfuse's CallbackHandler so that the rest
of the codebase can import a single helper without caring whether Langfuse
is enabled or not.
"""

import logging
from typing import Optional

from app.config import Settings

logger = logging.getLogger(__name__)

_langfuse_instance = None


def init_langfuse(settings: Settings) -> None:
    """Initialise the global Langfuse client if enabled."""
    global _langfuse_instance
    if not settings.langfuse_enabled:
        logger.info("Langfuse observability disabled.")
        return

    try:
        from langfuse import Langfuse

        _langfuse_instance = Langfuse(
            secret_key=settings.langfuse_secret_key,
            public_key=settings.langfuse_public_key,
            host=settings.langfuse_host,
        )
        logger.info("Langfuse observability enabled → %s", settings.langfuse_host)
    except Exception as exc:
        logger.warning("Failed to initialise Langfuse: %s. Continuing without tracing.", exc)


def get_langfuse_callback(
    *,
    trace_name: str = "llm-call",
    metadata: dict | None = None,
) -> Optional[object]:
    """
    Return a LangChain-compatible Langfuse callback handler, or None if
    Langfuse is disabled/unavailable.

    Usage:
        cb = get_langfuse_callback(trace_name="query")
        response = llm.invoke(messages, config={"callbacks": [cb]} if cb else {})
    """
    if _langfuse_instance is None:
        return None

    try:
        from langfuse.callback import CallbackHandler

        return CallbackHandler(
            trace_name=trace_name,
            metadata=metadata or {},
        )
    except Exception as exc:
        logger.debug("Could not create Langfuse callback: %s", exc)
        return None


def flush_langfuse() -> None:
    """Flush pending Langfuse events (call during shutdown)."""
    if _langfuse_instance is not None:
        try:
            _langfuse_instance.flush()
        except Exception:
            pass
