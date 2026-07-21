import warnings
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env from project root (shared by docker-compose and local dev)
_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- OpenAI (required) ---
    openai_api_key: str = ""
    openai_model_vision: str = "gpt-4o-mini"
    # Pass 1 chunk extraction model. gpt-4o-mini is fast and cheap for JSON extraction.
    # When LLM_PROVIDER=local_lora this field is only used for Pass 2 (merge/risk/summary).
    openai_model_analysis: str = "gpt-4o-mini"
    openai_model_judge: str = "gpt-4o-mini"  # model for LLM-as-Judge evaluation
    openai_model_embedding: str = "text-embedding-3-small"
    openai_temperature: float = Field(default=0.0, ge=0.0, le=2.0)

    # --- Legacy fine-tuned model fields (absorbed to prevent env var leakage) ---
    # These were for an Azure fine-tune that no longer exists.
    # The real fine-tuned model is iakshayrathee/contractiq-lora-llama3 (LoRA).
    # Set LLM_PROVIDER=local_lora + LOCAL_LORA_ADAPTER_PATH to use it.
    openai_model_finetuned: str = Field(default="", description="Deprecated. Use LLM_PROVIDER=local_lora instead.")
    use_finetuned_model: bool = Field(default=False, description="Deprecated. Use LLM_PROVIDER=local_lora instead.")

    # --- Multi-LLM provider ---
    llm_provider: str = Field(
        default="openai",
        description=(
            "LLM provider. Accepted values: "
            "'openai' | 'gemini' | 'local_lora'. "
            "Set LLM_PROVIDER env var."
        ),
    )
    gemini_api_key: str = Field(default="", description="Google Gemini API key. Set GEMINI_API_KEY env var.")
    gemini_model: str = Field(default="gemini-1.5-flash", description="Gemini model name.")

    # --- Guardrails ---
    guardrails_enabled: bool = Field(default=True, description="Enable input/output guardrails")
    judge_enabled: bool = Field(default=True, description="Enable LLM-as-Judge evaluation")
    judge_quality_threshold: float = Field(default=0.7, ge=0.0, le=1.0, description="Minimum acceptable judge score")
    guardrail_hallucination_threshold: float = Field(default=0.25, ge=0.0, le=1.0)

    # --- Risk scoring weights (Phase 4: configurable, not hard-coded) ---
    # These replace the previously magic-number literals in _compute_risk_report.
    # Rule component weight (deterministic checks).
    risk_rule_weight: float = Field(default=0.4, ge=0.0, le=1.0, description="Weight for rule-based risk score (env: RISK_RULE_WEIGHT)")
    # LLM component weight (evidence-grounded LLM checks).
    risk_llm_weight: float = Field(default=0.6, ge=0.0, le=1.0, description="Weight for LLM risk score (env: RISK_LLM_WEIGHT)")
    # Severity-to-score mapping (ordinal → numeric contribution)
    risk_severity_low: int = Field(default=10, ge=0, le=100, description="Score value for LOW severity risks (env: RISK_SEVERITY_LOW)")
    risk_severity_medium: int = Field(default=35, ge=0, le=100, description="Score value for MEDIUM severity risks (env: RISK_SEVERITY_MEDIUM)")
    risk_severity_high: int = Field(default=65, ge=0, le=100, description="Score value for HIGH severity risks (env: RISK_SEVERITY_HIGH)")
    risk_severity_critical: int = Field(default=90, ge=0, le=100, description="Score value for CRITICAL severity risks (env: RISK_SEVERITY_CRITICAL)")
    # Default perspective for risk analysis
    risk_default_perspective: str = Field(default="neutral", description="Default party perspective: 'neutral' | 'customer' | 'vendor' (env: RISK_DEFAULT_PERSPECTIVE)")

    # --- Open-weight LoRA inference (local_lora provider) ---
    # Requires: pip install -r backend/requirements-lora.txt
    # These settings are only read when LLM_PROVIDER=local_lora.
    # The trained model is at: https://huggingface.co/iakshayrathee/contractiq-lora-llama3
    # Trained via notebooks/contractiq_lora_finetune.ipynb on Llama-3.2-3B-Instruct + QLoRA.
    local_lora_adapter_path: str = Field(
        default="iakshayrathee/contractiq-lora-llama3",
        description=(
            "HuggingFace Hub model ID or local path to the LoRA adapter. "
            "Default: 'iakshayrathee/contractiq-lora-llama3'. "
            "Only used when LLM_PROVIDER=local_lora. Set LOCAL_LORA_ADAPTER_PATH env var."
        ),
    )
    local_lora_max_new_tokens: int = Field(
        default=512,
        gt=0,
        description="Max new tokens to generate per inference call. Set LOCAL_LORA_MAX_NEW_TOKENS env var.",
    )
    local_lora_temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=2.0,
        description="Sampling temperature for local LoRA inference. 0.0 = greedy decoding. Set LOCAL_LORA_TEMPERATURE env var.",
    )

    # --- Unstructured Cloud API (deprecated — kept as optional for backward compat) ---
    unstructured_api_key: str = Field(default="", description="Deprecated: Unstructured Cloud API key. No longer required.")
    unstructured_api_url: str = Field(default="https://api.unstructuredapp.io", description="Deprecated: Unstructured Cloud API base URL.")

    # --- Chunking (custom pipeline) ---
    # Legacy chunk_max_characters kept for backward compat with existing tests
    chunk_max_characters: int = Field(default=3000, gt=0)
    chunk_new_after_n_chars: int = Field(default=2400, gt=0)
    chunk_combine_under_n_chars: int = Field(default=500, gt=0)
    # New pipeline parameters
    # Fix 2: CHUNK_SIZE 512→1024, CHUNK_OVERLAP 64→200.
    # Legal clauses regularly exceed 512 chars; 64-char overlap too narrow.
    # Both values are configurable via CHUNK_SIZE and CHUNK_OVERLAP env vars.
    chunk_size: int = Field(default=1024, gt=0, description="Max characters per chunk (env: CHUNK_SIZE)")
    chunk_overlap: int = Field(default=200, ge=0, description="Character overlap between chunks (env: CHUNK_OVERLAP)")

    # --- Image extraction (multimodal RAG) ---
    # Set EXTRACT_IMAGES=false to disable all image extraction silently.
    extract_images: bool = Field(
        default=True,
        description="Enable GPT-4o vision description of PDF images during ingestion (env: EXTRACT_IMAGES)",
    )
    image_min_width: int = Field(
        default=100,
        gt=0,
        description="Minimum image width in pixels to process (env: IMAGE_MIN_WIDTH)",
    )
    image_min_height: int = Field(
        default=100,
        gt=0,
        description="Minimum image height in pixels to process (env: IMAGE_MIN_HEIGHT)",
    )
    vision_concurrency: int = Field(
        default=3,
        gt=0,
        description="Max parallel GPT-4o vision calls during ingestion (env: VISION_CONCURRENCY)",
    )

    # --- Qdrant ---
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: Optional[str] = Field(default=None)
    qdrant_collection_name: str = "rag_collection"

    # --- PostgreSQL ---
    database_url: str = "postgresql+asyncpg://contractiq:contractiq@localhost:5432/contractiq"

    # --- Retrieval ---
    retrieval_top_k: int = Field(default=5, ge=1, le=50)
    # Cosine similarity threshold for filtering retrieved chunks.
    # In hybrid mode, the system retrieves dense vectors and calculates actual
    # cosine similarities (dot product) to filter out irrelevant results.
    # In semantic-only mode, Qdrant's native scores are used.
    # Set to 0.70 to ensure only highly relevant chunks are returned.
    # Set to 0.0 to disable filtering (return all k results).
    retrieval_score_threshold: float = Field(
        default=0.50, 
        ge=0.0, 
        le=1.0,
        description="Cosine similarity threshold. Chunks below this score are filtered out. "
                    "Lowered from 0.70 → 0.50 so broad queries (summaries, page requests) retrieve "
                    "enough context. FlashRank reranker handles quality selection from the larger pool."
    )
    # Adaptive retrieval pool size — when k is None, fetch this many candidates
    # and filter by relevance score threshold. This enables variable chunk counts
    # per query based on actual relevance rather than a fixed slider value.
    adaptive_retrieval_pool_size: int = Field(
        default=20,
        ge=1,
        le=50,
        description="Candidate pool size for adaptive retrieval (env: ADAPTIVE_RETRIEVAL_POOL_SIZE)"
    )
    search_mode: str = Field(default="hybrid", description="Search mode: 'hybrid' (dense+sparse RRF) or 'semantic' (dense only)")

    # --- Poppler (Windows dev only; not needed in Docker) ---
    poppler_path: Optional[str] = Field(default=None)
    # Note: Poppler is only used if explicitly set via POPPLER_PATH env var.
    # The Docker image installs poppler-utils via apt. Cloud extraction does
    # not require poppler at all.

    # --- Langfuse ---
    langfuse_enabled: bool = Field(default=False)
    langfuse_secret_key: Optional[str] = Field(default=None)
    langfuse_public_key: Optional[str] = Field(default=None)
    langfuse_host: str = "https://cloud.langfuse.com"

    # --- CORS ---
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    cors_allow_credentials: bool = True
    cors_allow_methods: str = "*"
    cors_allow_headers: str = "*"

    # --- JWT Authentication ---
    jwt_secret_key: str = Field(
        default="CHANGE_ME_IN_PRODUCTION_USE_openssl_rand_hex_32",
        description="Secret key for signing JWTs. Set JWT_SECRET_KEY env var.",
    )
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = Field(default=60, gt=0, description="Access token lifetime in minutes")

    # --- Application ---
    app_title: str = "ContractIQ API"
    app_version: str = "2.0.0"
    log_level: str = "INFO"


    @model_validator(mode="after")
    def _validate_provider(self) -> "Settings":
        """Warn about unrecognised LLM_PROVIDER values."""
        provider = (self.llm_provider or "openai").lower()
        accepted = {"openai", "gemini", "local_lora"}
        if provider not in accepted:
            warnings.warn(
                f"Unknown LLM_PROVIDER='{provider}'. "
                f"Accepted values: {sorted(accepted)}. Defaulting to 'openai'.",
                UserWarning,
                stacklevel=2,
            )
        return self

    @model_validator(mode="after")
    def _validate_jwt_secret(self) -> "Settings":
        """Assert jwt_secret_key is configured securely in non-local environments."""
        if self.jwt_secret_key == "CHANGE_ME_IN_PRODUCTION_USE_openssl_rand_hex_32":
            import os
            if "PYTEST_CURRENT_TEST" in os.environ:
                return self
            is_local = (
                "localhost" in self.database_url 
                or "127.0.0.1" in self.database_url 
                or "sqlite" in self.database_url 
                or ":memory:" in self.database_url
            )
            if not is_local:
                raise ValueError(
                    "JWT_SECRET_KEY is set to the default placeholder value. "
                    "You MUST configure a secure JWT_SECRET_KEY in production."
                )
            else:
                warnings.warn(
                    "JWT_SECRET_KEY is using the default placeholder value. "
                    "Please configure a secure key before deploying to production.",
                    UserWarning,
                    stacklevel=2,
                )
        return self


@lru_cache
def get_settings() -> Settings:
    """Returns a cached Settings singleton. Call get_settings.cache_clear() in tests."""
    return Settings()
