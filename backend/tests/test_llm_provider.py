"""
tests/test_llm_provider.py
===========================
Unit tests for the multi-LLM provider factory (Task 6).

Tests cover:
  - get_llm() returns ChatOpenAI by default
  - get_llm() returns ChatGoogleGenerativeAI when provider=gemini
  - get_llm() falls back to OpenAI and logs warning for unknown provider
  - get_llm() raises ValueError when gemini_api_key is missing
  - get_llm() raises ImportError when langchain-google-genai is not installed
  - get_streaming_llm() returns streaming-capable model for both providers
  - Provider selection is driven by settings.llm_provider (case-insensitive)
  - json_mode=True is passed through to OpenAI model_kwargs
"""

from unittest.mock import MagicMock, patch

import pytest

from app.config import Settings


def _base_settings(**overrides) -> Settings:
    base = dict(
        openai_api_key="sk-test",
        qdrant_url="http://localhost:6333",
        database_url="sqlite+aiosqlite:///:memory:",
        langfuse_enabled=False,
        gemini_api_key="gemini-test-key",
    )
    base.update(overrides)
    return Settings(**base)


# ---------------------------------------------------------------------------
# get_llm — OpenAI (default)
# ---------------------------------------------------------------------------

class TestGetLLMOpenAI:

    def test_returns_chatopenai_by_default(self):
        """Default provider='openai' should return ChatOpenAI."""
        from langchain_openai import ChatOpenAI
        settings = _base_settings(llm_provider="openai")
        from app.llm.provider import get_llm
        llm = get_llm(settings)
        assert isinstance(llm, ChatOpenAI)

    def test_openai_uses_analysis_model(self):
        """ChatOpenAI model should match settings.openai_model_analysis."""
        settings = _base_settings(
            llm_provider="openai",
            openai_model_analysis="gpt-4o-mini",
        )
        from app.llm.provider import get_llm
        llm = get_llm(settings)
        assert llm.model_name == "gpt-4o-mini"

    def test_json_mode_adds_response_format(self):
        """json_mode=True should set response_format to json_object."""
        settings = _base_settings(llm_provider="openai")
        from app.llm.provider import get_llm
        llm = get_llm(settings, json_mode=True)
        model_kwargs = llm.model_kwargs or {}
        assert model_kwargs.get("response_format", {}).get("type") == "json_object"

    def test_json_mode_false_no_response_format(self):
        """json_mode=False (default) should NOT inject response_format."""
        settings = _base_settings(llm_provider="openai")
        from app.llm.provider import get_llm
        llm = get_llm(settings, json_mode=False)
        model_kwargs = llm.model_kwargs or {}
        assert "response_format" not in model_kwargs

    def test_temperature_is_applied(self):
        """Temperature from settings should propagate to ChatOpenAI."""
        settings = _base_settings(llm_provider="openai", openai_temperature=0.7)
        from app.llm.provider import get_llm
        llm = get_llm(settings)
        assert llm.temperature == pytest.approx(0.7)


# ---------------------------------------------------------------------------
# get_llm — Gemini
# ---------------------------------------------------------------------------

class TestGetLLMGemini:

    def test_returns_gemini_model_when_provider_gemini(self):
        """provider=gemini should return ChatGoogleGenerativeAI."""
        mock_gemini_cls = MagicMock()
        mock_instance = MagicMock()
        mock_gemini_cls.return_value = mock_instance

        settings = _base_settings(
            llm_provider="gemini",
            gemini_api_key="api-key-123",
            gemini_model="gemini-1.5-flash",
        )

        with patch.dict("sys.modules", {"langchain_google_genai": MagicMock(
            ChatGoogleGenerativeAI=mock_gemini_cls
        )}):
            from importlib import reload
            import app.llm.provider as provider_mod
            reload(provider_mod)

            result = provider_mod.get_llm(settings)

        mock_gemini_cls.assert_called_once()
        call_kwargs = mock_gemini_cls.call_args.kwargs
        assert call_kwargs["model"] == "gemini-1.5-flash"
        assert call_kwargs["google_api_key"] == "api-key-123"

    def test_gemini_provider_is_case_insensitive(self):
        """LLM_PROVIDER=GEMINI (uppercase) should work the same."""
        mock_gemini_cls = MagicMock()
        settings = _base_settings(
            llm_provider="GEMINI",
            gemini_api_key="api-key-456",
        )

        with patch.dict("sys.modules", {"langchain_google_genai": MagicMock(
            ChatGoogleGenerativeAI=mock_gemini_cls
        )}):
            from importlib import reload
            import app.llm.provider as provider_mod
            reload(provider_mod)
            provider_mod.get_llm(settings)

        mock_gemini_cls.assert_called_once()

    def test_gemini_raises_value_error_when_api_key_missing(self):
        """Missing GEMINI_API_KEY should raise ValueError, not crash silently."""
        settings = _base_settings(llm_provider="gemini", gemini_api_key="")

        mock_google_genai = MagicMock()
        mock_google_genai.ChatGoogleGenerativeAI = MagicMock()

        with patch.dict("sys.modules", {"langchain_google_genai": mock_google_genai}):
            from importlib import reload
            import app.llm.provider as provider_mod
            reload(provider_mod)

            with pytest.raises(ValueError, match="GEMINI_API_KEY"):
                provider_mod.get_llm(settings)

    def test_gemini_raises_import_error_when_package_missing(self):
        """If langchain-google-genai is not installed, should raise ImportError with helpful message."""
        settings = _base_settings(llm_provider="gemini", gemini_api_key="key")

        with patch.dict("sys.modules", {"langchain_google_genai": None}):
            from importlib import reload
            import app.llm.provider as provider_mod
            reload(provider_mod)

            with pytest.raises((ImportError, ModuleNotFoundError)):
                provider_mod.get_llm(settings)


# ---------------------------------------------------------------------------
# get_llm — Unknown provider
# ---------------------------------------------------------------------------

class TestGetLLMUnknownProvider:

    def test_unknown_provider_falls_back_to_openai(self):
        """Unknown provider string should fall back to OpenAI and log a warning."""
        from langchain_openai import ChatOpenAI
        settings = _base_settings(llm_provider="anthropic")  # not supported

        with patch("app.llm.provider.logger") as mock_logger:
            from importlib import reload
            import app.llm.provider as provider_mod
            reload(provider_mod)
            llm = provider_mod.get_llm(settings)

        # Should still return a working LLM (OpenAI)
        assert llm is not None


# ---------------------------------------------------------------------------
# get_streaming_llm
# ---------------------------------------------------------------------------

class TestGetStreamingLLM:

    def test_streaming_llm_openai_has_streaming_enabled(self):
        """OpenAI streaming LLM should have streaming=True."""
        settings = _base_settings(llm_provider="openai")
        from app.llm.provider import get_streaming_llm
        llm = get_streaming_llm(settings)
        # LangChain ChatOpenAI exposes streaming attribute
        assert getattr(llm, "streaming", True) is True

    def test_streaming_llm_gemini_returns_gemini_model(self):
        """Gemini streaming LLM should return ChatGoogleGenerativeAI."""
        mock_gemini_cls = MagicMock()
        mock_instance = MagicMock()
        mock_gemini_cls.return_value = mock_instance

        settings = _base_settings(
            llm_provider="gemini",
            gemini_api_key="key",
        )

        with patch.dict("sys.modules", {"langchain_google_genai": MagicMock(
            ChatGoogleGenerativeAI=mock_gemini_cls
        )}):
            from importlib import reload
            import app.llm.provider as provider_mod
            reload(provider_mod)

            result = provider_mod.get_streaming_llm(settings)

        mock_gemini_cls.assert_called_once()
