"""
Multi-provider LLM abstraction layer.

Supported providers (controlled by settings.llm_provider):
  "openai"     — OpenAI ChatOpenAI (default, unchanged behaviour)
  "gemini"     — Google Gemini via langchain-google-genai (gemini-1.5-flash)
  "local_lora" — Local LoRA adapter (Llama-3.2-3B-Instruct + QLoRA)
                 Requires: pip install -r requirements-lora.txt

Usage:
    from app.llm.provider import get_llm

    llm = get_llm(settings)
    # Synchronous call
    response = llm.invoke([HumanMessage(content="Hello")])
    # Streaming
    async for chunk in llm.astream([HumanMessage(content="Hello")]):
        print(chunk.content)
    # JSON mode (OpenAI) / structured extraction (Gemini)
    result = llm_json(settings).invoke([HumanMessage(content="Return JSON")])

For local_lora:
    from app.llm.provider import get_local_lora_provider

    provider = get_local_lora_provider(settings)
    clauses = await provider.generate("Contract text here...")

Both OpenAI/Gemini providers return LangChain BaseChatModel instances, so all
existing .invoke() / .astream() / .with_structured_output() calls work unchanged.
get_local_lora_provider() returns a LocalLoRAProvider — a separate interface
that wraps a HuggingFace transformers model.
"""

from __future__ import annotations

import asyncio
import logging
from functools import lru_cache
from typing import TYPE_CHECKING, Any, Optional

import structlog

from app.config import Settings

if TYPE_CHECKING:
    from app.finetuning.lora_trainer import LoRATrainer  # noqa: F401

logger = structlog.get_logger()


class RobustLLMGateway:
    """
    Custom LLM Gateway with automatic fallback routing.
    Handles automatic retries from primary to backup models.
    """
    def __init__(self, primary, fallbacks):
        self.primary = primary
        self.fallbacks = fallbacks

    def invoke(self, *args, **kwargs):
        try:
            return self.primary.invoke(*args, **kwargs)
        except Exception as e:
            logger.warning("primary_llm_failed", error=str(e))
            for i, fallback in enumerate(self.fallbacks):
                try:
                    logger.info("attempting_fallback", index=i)
                    return fallback.invoke(*args, **kwargs)
                except Exception as e2:
                    logger.warning("fallback_llm_failed", index=i, error=str(e2))
            raise RuntimeError("All LLM providers failed.")

    async def ainvoke(self, *args, **kwargs):
        try:
            return await self.primary.ainvoke(*args, **kwargs)
        except Exception as e:
            logger.warning("primary_llm_failed", error=str(e))
            for i, fallback in enumerate(self.fallbacks):
                try:
                    logger.info("attempting_fallback", index=i)
                    return await fallback.ainvoke(*args, **kwargs)
                except Exception as e2:
                    logger.warning("fallback_llm_failed", index=i, error=str(e2))
            raise RuntimeError("All LLM providers failed.")

    async def astream(self, *args, **kwargs):
        generator = None
        try:
            generator = self.primary.astream(*args, **kwargs)
            # Try to fetch the first chunk to catch connection errors immediately
            first_chunk = await generator.__anext__()
            yield first_chunk
            async for chunk in generator:
                yield chunk
            return
        except StopAsyncIteration:
            return
        except Exception as e:
            logger.warning("primary_llm_streaming_failed", error=str(e))
            
        for i, fallback in enumerate(self.fallbacks):
            try:
                logger.info("attempting_streaming_fallback", index=i)
                generator = fallback.astream(*args, **kwargs)
                first_chunk = await generator.__anext__()
                yield first_chunk
                async for chunk in generator:
                    yield chunk
                return
            except StopAsyncIteration:
                return
            except Exception as e2:
                logger.warning("fallback_llm_streaming_failed", index=i, error=str(e2))
                
        raise RuntimeError("All LLM providers failed during streaming.")

    def with_structured_output(self, *args, **kwargs):
        primary_structured = self.primary.with_structured_output(*args, **kwargs)
        fallbacks_structured = []
        for f in self.fallbacks:
            try:
                fallbacks_structured.append(f.with_structured_output(*args, **kwargs))
            except Exception:
                pass
        return RobustLLMGateway(primary_structured, fallbacks_structured)

# ---------------------------------------------------------------------------
# LangChain-based providers (OpenAI / Gemini)
# ---------------------------------------------------------------------------


def get_llm(settings: Settings, *, json_mode: bool = False):
    """
    Return a RobustLLMGateway wrapping the configured provider with fallbacks.
    """
    primary_provider = (settings.llm_provider or "openai").lower()
    
    primary = None
    fallbacks = []

    if primary_provider == "gemini":
        primary = _build_gemini(settings, json_mode=json_mode)
        try:
            fallbacks.append(_build_openai(settings, json_mode=json_mode))
        except Exception:
            pass
    elif primary_provider == "local_lora":
        logger.info("get_llm_local_lora_streaming_fallback", message="LLM_PROVIDER=local_lora: streaming/query endpoints use OpenAI fallback.")
        primary = _build_openai(settings, json_mode=json_mode)
        try:
            fallbacks.append(_build_gemini(settings, json_mode=json_mode))
        except Exception:
            pass
    else:
        if primary_provider != "openai":
            logger.warning("unknown_llm_provider", provider=primary_provider, fallback="openai")
        primary = _build_openai(settings, json_mode=json_mode)
        try:
            if settings.gemini_api_key:
                fallbacks.append(_build_gemini(settings, json_mode=json_mode))
        except Exception:
            pass

    return RobustLLMGateway(primary, fallbacks)


def _build_openai(settings: Settings, *, json_mode: bool = False):
    """Build a ChatOpenAI instance."""
    from langchain_openai import ChatOpenAI

    kwargs: dict = dict(
        model=settings.openai_model_analysis,
        temperature=settings.openai_temperature,
        api_key=settings.openai_api_key,
    )
    if json_mode:
        kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}

    logger.debug("llm_provider_selected", provider="openai", model=settings.openai_model_analysis)
    return ChatOpenAI(**kwargs)


def _build_gemini(settings: Settings, *, json_mode: bool = False):
    """Build a ChatGoogleGenerativeAI (Gemini) instance."""
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
    except ImportError as exc:
        raise ImportError(
            "langchain-google-genai is required for LLM_PROVIDER=gemini. "
            "Run: pip install langchain-google-genai"
        ) from exc

    if not settings.gemini_api_key:
        raise ValueError(
            "GEMINI_API_KEY must be set in .env when LLM_PROVIDER=gemini."
        )

    model_name = settings.gemini_model
    kwargs: dict = dict(
        model=model_name,
        google_api_key=settings.gemini_api_key,
        temperature=settings.openai_temperature,
    )

    logger.debug("llm_provider_selected", provider="gemini", model=model_name)
    return ChatGoogleGenerativeAI(**kwargs)


def get_streaming_llm(settings: Settings):
    """
    Return an LLM configured for streaming, using RobustLLMGateway for fallbacks.
    """
    primary_provider = (settings.llm_provider or "openai").lower()
    
    primary = None
    fallbacks = []

    if primary_provider == "gemini":
        primary = _build_gemini(settings, json_mode=False)
        from langchain_openai import ChatOpenAI
        fallbacks.append(ChatOpenAI(
            model=settings.openai_model_vision,
            temperature=settings.openai_temperature,
            api_key=settings.openai_api_key,
            streaming=True,
        ))
    else:
        from langchain_openai import ChatOpenAI
        primary = ChatOpenAI(
            model=settings.openai_model_vision,
            temperature=settings.openai_temperature,
            api_key=settings.openai_api_key,
            streaming=True,
        )
        if settings.gemini_api_key:
            fallbacks.append(_build_gemini(settings, json_mode=False))

    return RobustLLMGateway(primary, fallbacks)


def get_analysis_llm(settings: Settings):
    """
    Return the LLM (or LocalLoRAProvider) for Pass 1 contract clause extraction.

    - LLM_PROVIDER=openai   → ChatOpenAI(gpt-4o-mini) — fast, cheap JSON extraction
    - LLM_PROVIDER=local_lora → LocalLoRAProvider wrapping iakshayrathee/contractiq-lora-llama3
    - LLM_PROVIDER=gemini   → Gemini (falls through to get_llm)

    Pass 2 (merge / risk / summary) always uses ChatOpenAI regardless of provider
    because multi-step reasoning benefits from a larger model.

    Returns:
        ChatOpenAI | LocalLoRAProvider | ChatGoogleGenerativeAI
    """
    provider = (settings.llm_provider or "openai").lower()
    if provider == "local_lora":
        adapter_path = settings.local_lora_adapter_path
        if not adapter_path:
            logger.warning(
                "get_analysis_llm_no_adapter",
                message=(
                    "LLM_PROVIDER=local_lora but LOCAL_LORA_ADAPTER_PATH is empty. "
                    "Falling back to OpenAI for analysis."
                ),
            )
            return _build_openai(settings)
        provider_inst = get_local_lora_provider(settings)
        if provider_inst is None:
            logger.warning(
                "get_analysis_llm_lora_failed",
                message="LocalLoRAProvider failed to load. Falling back to OpenAI.",
            )
            return _build_openai(settings)
        return provider_inst
    return get_llm(settings)


# ---------------------------------------------------------------------------
# Local LoRA provider (separate from LangChain providers)
# ---------------------------------------------------------------------------


class LocalLoRAProvider:
    """
    Async wrapper around a HuggingFace transformers + PEFT LoRA adapter.

    Exposes an interface similar to LangChain providers but does NOT
    inherit from BaseChatModel — a HF transformers model cannot implement
    that ABC without a heavyweight shim that handles BaseMessage types,
    _generate, streaming callbacks, etc.

    Usage:
        provider = get_local_lora_provider(settings)
        clauses_json = await provider.generate("Contract text...")
        clauses_list = await provider.extract_clauses("Contract text...")

    Inference is wrapped in asyncio.run_in_executor so it does not block
    the FastAPI event loop.
    """

    def __init__(self, trainer: "LoRATrainer") -> None:
        self._trainer = trainer

    async def generate(self, text: str) -> str:
        """
        Run inference and return the raw JSON string from the model.

        Args:
            text: Contract text to extract clauses from.

        Returns:
            Raw model output (JSON string). Use extract_clauses() for
            parsed results.
        """
        clauses = await self._trainer.run_inference(text)
        import json as _json
        return _json.dumps(clauses)

    async def extract_clauses(self, text: str) -> list[dict]:
        """
        Run inference and return parsed clause dicts.

        Args:
            text: Contract text to extract clauses from.

        Returns:
            List of clause dicts (clause_type, title, text,
            section_reference, obligations).
        """
        return await self._trainer.run_inference(text)

    async def astream(self, text: str):
        """
        Simulate streaming by yielding the full result as a single chunk.

        Transformers generation is not natively streaming in the same way
        as OpenAI's token-level SSE. For true streaming, implement
        TextIteratorStreamer from transformers.
        """
        result = await self.generate(text)
        yield result


def get_local_lora_provider(settings: Settings) -> Optional[LocalLoRAProvider]:
    """
    Build and return a LocalLoRAProvider for LLM_PROVIDER=local_lora.

    Loads the LoRA adapter specified by LOCAL_LORA_ADAPTER_PATH.
    If the adapter fails to load (missing path, missing deps, OOM),
    logs a warning and returns None — callers should fall back to
    get_llm(settings) with LLM_PROVIDER=openai.

    Requires: pip install -r requirements-lora.txt

    Args:
        settings: Application settings.

    Returns:
        LocalLoRAProvider instance, or None if adapter could not be loaded.
    """
    adapter_path = settings.local_lora_adapter_path
    if not adapter_path:
        logger.warning(
            "local_lora_no_adapter_path",
            message=(
                "LOCAL_LORA_ADAPTER_PATH is not set. "
                "Cannot load local LoRA provider. Returning None — "
                "caller should fall back to a cloud provider."
            ),
        )
        return None

    try:
        from app.finetuning.lora_trainer import LoRATrainer
    except ImportError as exc:
        logger.error(
            "local_lora_import_error",
            error=str(exc),
            message="lora_trainer module could not be imported.",
        )
        return None

    try:
        trainer = LoRATrainer()
        trainer.load_adapter(adapter_path)
        logger.info("local_lora_provider_ready", adapter_path=adapter_path)
        return LocalLoRAProvider(trainer)
    except Exception as exc:
        logger.warning(
            "local_lora_load_failed",
            adapter_path=adapter_path,
            error=str(exc),
            fallback="openai",
            message=(
                "Failed to load LoRA adapter. "
                "Check that requirements-lora.txt is installed and "
                "LOCAL_LORA_ADAPTER_PATH points to a valid adapter."
            ),
        )
        return None
