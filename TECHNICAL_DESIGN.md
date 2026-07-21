# ContractIQ — Technical Design Document

> **Version:** 2.1.0
> **Last Updated:** July 2026
> **Stack:** FastAPI · Next.js 14 · PostgreSQL · Qdrant · OpenAI GPT-4o · LangChain

---

## 📌 Overview

**ContractIQ** is an AI-powered legal contract analysis platform that enables users to upload PDF or DOCX legal contracts and receive comprehensive automated analysis. The platform provides structured clause extraction, risk assessment, plain-English summaries, and an interactive RAG-powered chat interface for querying contract content.

**Key capabilities:**
- **Multi-provider LLM support**: OpenAI GPT-4o, Google Gemini, and fine-tuned LoRA adapters
- **Advanced retrieval**: Hybrid dense+sparse vector search with FlashRank reranking
- **Multimodal analysis**: Text, tables, and image extraction with GPT-4o Vision
- **Evidence-grounded, perspective-aware risk scoring**: deterministic regex/numeric rule layer + LLM layer with verbatim citations, per-finding confidence, and configurable blend weights
- **Versioned prompt registry**: version-tagged prompts with optional Langfuse hot-swap, recorded per analysis
- **Progressive analysis UX**: staged partial rendering (clauses → risk → summary) with a background LLM-as-Judge
- **Quality assurance**: Input/output guardrails and LLM-as-Judge evaluation
- **Full observability**: Structured logging and Langfuse tracing

---

## 🏗️ High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Next.js 14 Frontend                         │
│   (TypeScript · TailwindCSS · TanStack Query · Recharts · lucide)   │
└────────────────────────────┬────────────────────────────────────────┘
                             │ HTTP / SSE (streaming)
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     FastAPI Backend (Python 3.11+)                  │
│                                                                     │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  ┌──────────────────┐  │
│  │   Auth   │  │ Projects │  │ Ingestion │  │ Contract Analysis│  │
│  │  (JWT)   │  │   CRUD   │  │ Pipeline  │  │  (2-Pass LLM)    │  │
│  └──────────┘  └──────────┘  └───────────┘  └──────────────────┘  │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  ┌──────────────────┐  │
│  │  Query   │  │ Dashboard│  │ Fine-tune │  │   Guardrails +   │  │
│  │  (RAG)   │  │ (Stats)  │  │  (LoRA)   │  │   Judge Service  │  │
│  └──────────┘  └──────────┘  └───────────┘  └──────────────────┘  │
└────────┬──────────────────────────────┬───────────────────────────-─┘
         │                              │
         ▼                              ▼
┌─────────────────┐          ┌────────────────────┐
│   PostgreSQL 16  │          │    Qdrant v1.14     │
│  (Users, Projects│          │ (Vector Store:      │
│   Analyses, Chat │          │  Dense + Sparse     │
│   Cache, Models) │          │  Hybrid Search)     │
└─────────────────┘          └────────────────────┘
         │
         ▼
┌─────────────────┐
│  LLM Providers  │
│  · OpenAI GPT-4o│
│  · Google Gemini│
│  · Local LoRA   │
│    (Llama-3.2)  │
└─────────────────┘
```

---

## 🗂️ Project Structure

```
AI Legal Contract Analyze/
├── backend/                      # FastAPI Python application
│   ├── app/
│   │   ├── main.py               # App factory, lifespan, middleware
│   │   ├── config.py             # Pydantic Settings (env-driven)
│   │   │
│   │   ├── auth/                 # JWT authentication
│   │   │   ├── router.py         # Auth endpoints (register, login, refresh, logout)
│   │   │   └── dependencies.py   # Auth dependency injection (get_current_user)
│   │   │
│   │   ├── db/                   # Database layer
│   │   │   ├── models.py         # SQLAlchemy ORM models (UserRow, ProjectRow, AnalysisRow, etc.)
│   │   │   └── database.py       # Async session factory, engine initialization
│   │   │
│   │   ├── ingestion/            # Document ingestion pipeline
│   │   │   ├── parser.py         # PDF (PyMuPDF) and DOCX parsers
│   │   │   └── chunker.py        # RecursiveCharacterTextSplitter, table chunking
│   │   │
│   │   ├── llm/                  # Multi-provider LLM abstraction
│   │   │   └── provider.py       # LLM factory (OpenAI, Gemini, LocalLoRAProvider)
│   │   │
│   │   ├── middleware/           # HTTP middleware
│   │   │   └── request_id.py     # Injects X-Request-ID header for tracing
│   │   │
│   │   ├── routes/               # FastAPI routers (REST endpoints)
│   │   │   ├── health.py         # Health check endpoint
│   │   │   ├── projects.py       # Project CRUD operations
│   │   │   ├── ingestion.py      # Document upload and chunk retrieval
│   │   │   ├── contracts.py      # Contract analysis endpoints
│   │   │   ├── query.py          # RAG chat (SSE streaming)
│   │   │   ├── dashboard.py      # Dashboard statistics
│   │   │   ├── analysis.py       # Cross-project analysis utilities
│   │   │   ├── jobs.py           # Background job status
│   │   │   └── finetuning.py     # Fine-tuning management endpoints
│   │   │
│   │   ├── schemas/              # Pydantic request/response models
│   │   │   ├── auth.py           # Auth request/response schemas
│   │   │   ├── contract.py       # ContractAnalysis, Clause, Evidence, RiskItem, RiskReport, ScoringExplanation, PlainSummary, DashboardStats
│   │   │   ├── judge.py          # LLM-as-Judge evaluation schemas
│   │   │   ├── project.py        # Project CRUD schemas
│   │   │   ├── query.py          # Chat message schemas
│   │   │   └── responses.py      # Standard API responses
│   │   │
│   │   ├── services/             # Business logic layer
│   │   │   ├── ingestion_service.py        # 4-stage ingestion pipeline
│   │   │   ├── vector_store_service.py     # Qdrant operations (hybrid search, CRUD)
│   │   │   ├── contract_analysis_service.py # 2-pass LLM extraction + risk analysis
│   │   │   ├── query_service.py            # RAG query orchestration
│   │   │   ├── project_service.py          # Project management
│   │   │   ├── job_service.py              # Async job tracking
│   │   │   ├── guardrails.py               # Input/output validation
│   │   │   ├── judge_service.py            # LLM-as-Judge quality evaluation
│   │   │   ├── reranker.py                 # FlashRank cross-encoder reranker (ONNX)
│   │   │   ├── prompts/                    # Versioned prompt registry
│   │   │   │   └── registry.py             # Prompt catalogue, ACTIVE_VERSIONS, Langfuse pull
│   │   │   └── risk_rules/                 # Deterministic regex/numeric risk extractors
│   │   │       └── extractors.py           # liability cap, notice period, auto-renewal, gov law, indemnity
│   │   │
│   │   ├── finetuning/           # LoRA training system
│   │   │   ├── cli.py            # Click CLI commands
│   │   │   ├── dataset_builder.py # JSONL dataset generation from analyses
│   │   │   ├── lora_trainer.py   # QLoRA training (Llama-3.2-3B-Instruct)
│   │   │   ├── evaluator.py      # Clause F1, precision, recall metrics
│   │   │   ├── data/
│   │   │   │   └── cuad_processor.py # CUAD dataset processing
│   │   │   └── metrics/
│   │   │       ├── consistency_tester.py   # Multi-run consistency testing
│   │   │       ├── cost_calculator.py      # Token cost estimation
│   │   │       └── hallucination_checker.py # Source overlap validation
│   │   │
│   │   ├── evals/                # Evaluation framework
│   │   │   ├── run_evals.py      # Eval runner
│   │   │   ├── dataset.py        # Test dataset loader
│   │   │   ├── reporter.py       # Results reporting
│   │   │   ├── langfuse_tracking.py # Langfuse integration
│   │   │   ├── cli.py            # CLI interface
│   │   │   └── test_cases/
│   │   │       └── contract_eval_cases.json # Eval test cases
│   │   │
│   │   ├── core/                 # Core utilities
│   │   │   └── logging.py        # Structlog configuration
│   │   │
│   │   └── utils/                # Shared utilities
│   │       ├── ai_utils.py       # AI helper functions
│   │       ├── langfuse_utils.py # Langfuse callback handling
│   │       └── rate_limit.py     # SlowAPI rate limiter setup
│   │
│   ├── alembic/                  # Database migrations
│   │   ├── env.py                # Alembic environment config
│   │   ├── script.py.mako        # Migration template
│   │   └── versions/             # Migration scripts (timestamped)
│   │       ├── 16943c5cbd59_initial_schema.py
│   │       ├── 7e3a1b2c4d8f_add_judge_and_guardrail_columns.py
│   │       ├── a3f81c2de905_add_document_hash_to_analyses.py
│   │       ├── add_model_registry_table.py
│   │       ├── b5c92f3e1a07_add_chat_messages_table.py
│   │       ├── c1d2e3f4a5b6_add_users_table.py
│   │       ├── d4e5f6a7b8c9_add_stage_json_to_analyses.py
│   │       ├── force_user_id.py
│   │       └── scope_project_uniqueness.py
│   │
│   ├── tests/                    # Pytest test suite
│   │   ├── conftest.py           # Test fixtures and configuration
│   │   ├── test_ingestion.py     # Ingestion pipeline tests
│   │   ├── test_analysis.py      # Contract analysis tests
│   │   ├── test_vector_store.py  # Vector store tests
│   │   └── test_auth.py          # Authentication tests
│   │
│   ├── requirements.txt          # Core dependencies
│   ├── requirements-lora.txt     # Optional: LoRA/HuggingFace deps
│   ├── requirements-test.txt     # Test dependencies
│   ├── alembic.ini               # Alembic configuration
│   ├── pyproject.toml            # Python project metadata
│   └── Dockerfile                # Backend container image
│
├── frontend/                     # Next.js 14 application
│   ├── app/                      # App Router pages
│   │   ├── page.tsx              # Landing page
│   │   ├── layout.tsx            # Root layout
│   │   ├── globals.css           # Global styles
│   │   ├── login/
│   │   │   └── page.tsx          # Login page
│   │   ├── register/
│   │   │   └── page.tsx          # Registration page
│   │   ├── dashboard/
│   │   │   ├── page.tsx          # User dashboard
│   │   │   └── layout.tsx        # Dashboard layout
│   │   └── projects/
│   │       └── [name]/
│   │           └── page.tsx      # Project detail page
│   │
│   ├── components/               # Reusable React components
│   │   ├── charts/               # Data visualizations
│   │   │   ├── RiskScoreGauge.tsx        # Risk score visualization
│   │   │   ├── ClauseDistribution.tsx    # Clause type breakdown
│   │   │   └── RiskBreakdown.tsx         # Risk category chart
│   │   │
│   │   ├── chat/                 # RAG chat interface
│   │   │   ├── ChatInterface.tsx         # Main chat component
│   │   │   ├── ChatMessage.tsx           # Individual message
│   │   │   └── ChatInput.tsx             # Message input field
│   │   │
│   │   ├── contract/             # Contract analysis display
│   │   │   ├── ClauseList.tsx            # Clause listing
│   │   │   ├── RiskReport.tsx            # Risk report display
│   │   │   ├── SummaryView.tsx           # Plain-English summary
│   │   │   └── MetadataCard.tsx          # Contract metadata
│   │   │
│   │   ├── layout/               # Layout components
│   │   │   ├── Sidebar.tsx               # Navigation sidebar
│   │   │   ├── Header.tsx                # Page header
│   │   │   └── ProjectNav.tsx            # Project navigation
│   │   │
│   │   ├── project/              # Project management UI
│   │   │   ├── ProjectCard.tsx           # Project list card
│   │   │   ├── CreateProject.tsx         # Project creation modal
│   │   │   ├── UploadDocument.tsx        # Document upload
│   │   │   └── IngestionProgress.tsx     # Real-time ingestion status
│   │   │
│   │   └── ui/                   # Generic UI primitives
│   │       ├── Button.tsx                # Button component
│   │       ├── Modal.tsx                 # Modal dialog
│   │       ├── Card.tsx                  # Card container
│   │       ├── Badge.tsx                 # Badge component
│   │       ├── Spinner.tsx               # Loading spinner
│   │       └── Toast.tsx                 # Toast notifications
│   │
│   ├── lib/                      # Utilities and API client
│   │   ├── api.ts                # API client (fetch wrapper)
│   │   ├── hooks.ts              # Custom React hooks
│   │   ├── types.ts              # TypeScript type definitions
│   │   └── utils.ts              # Helper functions
│   │
│   ├── public/                   # Static assets
│   ├── tailwind.config.ts        # Tailwind CSS configuration
│   ├── tsconfig.json             # TypeScript configuration
│   ├── next.config.js            # Next.js configuration
│   ├── package.json              # NPM dependencies
│   └── Dockerfile                # Frontend container image
│
├── notebooks/
│   └── contractiq_lora_finetune.ipynb   # Llama-3.2 + QLoRA fine-tuning notebook
│
├── .github/
│   └── workflows/
│       ├── ci.yml                # CI/CD pipeline
│       └── eval.yml              # Evaluation pipeline
│
├── docker-compose.yml            # Full-stack orchestration (Qdrant, Postgres, Backend, Frontend)
├── .env                          # Environment variables (gitignored)
├── .env.example                  # Environment template
├── .gitignore                    # Git ignore rules
└── TECHNICAL_DESIGN.md           # This document
```

---

## ⚙️ Backend — Detailed Design

### Application Bootstrap (`main.py`)

The application uses FastAPI's **asynccontextmanager lifespan** pattern. On startup:

1. Structured logging is configured (console in DEBUG, JSON in production)
2. PostgreSQL is initialized via async SQLAlchemy
3. All services are instantiated and attached to `app.state`
4. Qdrant vector store collections are loaded
5. Langfuse observability is initialized

On shutdown, Langfuse is flushed and DB connections are closed.

**Middleware stack:**
- `RequestIDMiddleware` — injects a unique `X-Request-ID` on every request
- `CORSMiddleware` — configurable via `CORS_ORIGINS` env var
- `slowapi` rate limiter — prevents API abuse

---

### Configuration (`config.py`)

All configuration is managed via **Pydantic BaseSettings** — environment variables override defaults automatically. The settings class is cached via `@lru_cache` for singleton access.

| Category | Key Settings |
|---|---|
| **LLM** | `LLM_PROVIDER` (openai / gemini / local_lora), `OPENAI_API_KEY`, `GEMINI_API_KEY` |
| **Models** | `OPENAI_MODEL_VISION` (gpt-4o-mini), `OPENAI_MODEL_ANALYSIS` (gpt-4o-mini), `OPENAI_MODEL_JUDGE` (gpt-4o-mini), `OPENAI_MODEL_EMBEDDING` (text-embedding-3-small), `GEMINI_MODEL` (gemini-1.5-flash) |
| **Chunking** | `CHUNK_SIZE` (1024 chars), `CHUNK_OVERLAP` (200 chars) |
| **Retrieval** | `RETRIEVAL_TOP_K` (5), `RETRIEVAL_SCORE_THRESHOLD` (0.50), `SEARCH_MODE` (hybrid / semantic), `ADAPTIVE_RETRIEVAL_POOL_SIZE` (20) |
| **Image** | `EXTRACT_IMAGES` (true), `VISION_CONCURRENCY` (3), `IMAGE_MIN_WIDTH/HEIGHT` (100px) |
| **Reranking** | FlashRank enabled by default (ms-marco-MiniLM ONNX model, no API key required) |
| **Vector DB** | `QDRANT_URL`, `QDRANT_API_KEY`, `QDRANT_COLLECTION_NAME` |
| **Database** | `DATABASE_URL` (PostgreSQL + asyncpg) |
| **Auth** | `JWT_SECRET_KEY`, `JWT_ALGORITHM` (HS256), `JWT_EXPIRE_MINUTES` (60) |
| **Guardrails** | `GUARDRAILS_ENABLED`, `JUDGE_ENABLED`, `JUDGE_QUALITY_THRESHOLD` (0.7), `GUARDRAIL_HALLUCINATION_THRESHOLD` (0.25) |
| **Risk Scoring** | `RISK_RULE_WEIGHT` (0.4), `RISK_LLM_WEIGHT` (0.6), `RISK_SEVERITY_LOW/MEDIUM/HIGH/CRITICAL` (10/35/65/90), `RISK_DEFAULT_PERSPECTIVE` (neutral) — configurable, no hard-coded magic numbers |
| **Observability** | `LANGFUSE_ENABLED`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_HOST` |
| **LoRA** | `LOCAL_LORA_ADAPTER_PATH` (iakshayrathee/contractiq-lora-llama3), `LOCAL_LORA_MAX_NEW_TOKENS` (512), `LOCAL_LORA_TEMPERATURE` (0.0) |

---

### Database Models (`db/models.py`)

Using **SQLAlchemy 2.0 async ORM** with Alembic for migrations.

```
users
├── id (UUID, PK)
├── email (unique, indexed)
├── hashed_password
└── created_at

projects
├── id (UUID, PK)
├── name (unique per user)
├── description
├── collection_name (unique Qdrant collection)
├── user_id → users.id (nullable for backward compat)
└── created_at

analyses
├── id (UUID, PK)
├── project_id → projects.id
├── status (pending | running | completed | failed)
├── analysis_json, risk_json, summary_json
├── overall_risk_score (0–100)
├── document_hash (SHA-256, for caching)
├── judge_json, guardrail_warnings_json
├── quality_score (0.0–1.0, from LLM-as-Judge)
├── flagged_for_review
├── stage_json (nullable — live pipeline progress: {"stage","processed","total"})
└── created_at / completed_at

chat_messages
├── id (UUID, PK)
├── project_id → projects.id
├── role (user | assistant)
├── content
├── sources_json
└── created_at

query_cache
├── cache_key (SHA-256 of project+question, indexed)
├── project_id → projects.id
├── question / answer
├── chunks_retrieved
└── sources_json

model_registry
├── id, model_id (unique)
├── base_model, job_id
├── training metrics (loss, tokens, duration)
├── eval metrics (clause_f1, precision, recall)
└── status (pending | running | validating_files | ready | failed | active)
```

---

### Authentication (`auth/`)

**JWT dual-token strategy:**

| Token | Type | Lifetime | Storage |
|---|---|---|---|
| Access Token | Short-lived JWT (HS256) | 60 minutes | React memory / Authorization header |
| Refresh Token | Long-lived JWT (HS256) | 7 days | `httpOnly`, `SameSite=Strict` cookie |

**Endpoints:**
- `POST /auth/register` — create account (bcrypt password hashing)
- `POST /auth/login` — returns access token in body + refresh cookie
- `POST /auth/refresh` — issues new access token from refresh cookie
- `POST /auth/logout` — clears refresh cookie

**Password security:** `passlib[bcrypt]` with pinned `bcrypt<4.0.0` for compatibility.

---

### Ingestion Pipeline (`ingestion/`, `services/ingestion_service.py`)

The ingestion pipeline processes uploaded PDF and DOCX files through four stages:

```
Upload (PDF / DOCX)
       │
       ▼
Stage 1: Parsing
  ├── PDF  → PyMuPDF (page-level text + image + table extraction)
  └── DOCX → python-docx (paragraph + table extraction)
       │
       ▼
Stage 1b: Image Description (PDF only, optional)
  └── GPT-4o Vision → text descriptions of informational images
      (concurrency-limited via asyncio.Semaphore, default 3)
      (decorative/logo images skipped with "SKIP" response)
       │
       ▼
Stage 1c: Table Extraction (all document types)
  └── Extract table chunks with HTML storage + markdown embedding
      (one chunk per table, preserves structure)
       │
       ▼
Stage 2: Chunking
  └── RecursiveCharacterTextSplitter for text chunks
      chunk_size=1024, chunk_overlap=200
  └── Merge text + table + image chunks with contiguous indexing
       │
       ▼
Stage 3: Document Preparation
  └── Build LangChain Document objects with metadata
      (page_number, chunk_type: text | table | image_description)
  └── Contextual embedding: prepend metadata prefix for better retrieval
      Format: "[Document: X | Page: Y | Clause: Z | Section: W]\n<content>"
       │
       ▼
Stage 4: Embedding + Storage (VectorStoreService)
  ├── Dense vectors  → OpenAI text-embedding-3-small (1536 dim)
  ├── Sparse vectors → FastEmbed BM25 (Qdrant/bm25)
  └── Metadata storage → Top-level payload fields for efficient filtering
```

**Key design decisions:**
- **Custom PyMuPDF pipeline**: Replaced Unstructured Cloud API (zero external API dependency, lower cost, faster)
- **Unified vector schema**: Image and table chunks use the same dense+sparse vector fields as text chunks — no schema modifications required
- **Dual content storage**: Table chunks store HTML in metadata for rendering, markdown text in page_content for embedding
- **Contextual embedding**: Metadata prefix prepended to content before embedding improves page/clause/section-specific retrieval accuracy
- **Top-level metadata fields**: Stored directly in Qdrant payload enable efficient filtering without JSON parsing overhead
- **Concurrency control**: Application-level `asyncio.Lock` prevents race conditions during parallel ingestion jobs
- **Vision rate limiting**: `asyncio.Semaphore` caps concurrent GPT-4o vision calls to prevent rate-limit errors and control costs

---

### Vector Store Service (`services/vector_store_service.py`)

**Qdrant** is used as the vector database with one collection per project.

**Hybrid search (default):** Combines dense (OpenAI embeddings) and sparse (BM25) vectors using **Reciprocal Rank Fusion (RRF)**, followed by optional **FlashRank reranking**.

```
Query
  ├── Dense vector  → OpenAI text-embedding-3-small (1536 dim)
  └── Sparse vector → FastEmbed BM25 encoder (Qdrant/bm25)
         │
         ▼
  Qdrant Prefetch (50 dense + 50 sparse candidates)
         │
         ▼
  Fusion.RRF (reciprocal rank fusion merges ranked lists)
         │
         ▼
  Top-K results (default K=5, configurable)
         │
         ▼
  Score normalization:
    - Hybrid mode: rank-based scores (1.0 - rank/total)
    - Semantic mode: native cosine similarity
         │
         ▼
  FlashRank reranking (optional semantic reranker)
    - Model: ms-marco-MiniLM (ONNX, local inference)
    - Reranks top-K results for improved relevance
    - No API key required, <100ms latency
         │
         ▼
  Optional page filtering (metadata-based)
         │
         ▼
  Threshold filter (semantic mode only, default 0.50)
         │
         ▼
  Final results returned to client
```

**Scoring strategy:**
- **Hybrid mode (RRF)**: Uses normalized rank-based scores (1.0 = top result, ~0 = last result). FlashRank can optionally rerank the RRF results for improved semantic relevance. No threshold filtering — all K results returned.
- **Semantic mode**: Uses Qdrant's native cosine similarity scores. Applies `RETRIEVAL_SCORE_THRESHOLD` (default 0.50) to filter low-quality matches. FlashRank reranking available.

**Performance characteristics:**
- **Initial retrieval**: 50 dense + 50 sparse candidates fetched, fused to top-K (typical: 5-20 results)
- **Reranking latency**: FlashRank adds ~50-100ms for K=5, ~200-300ms for K=20 (local ONNX inference)
- **Quality improvement**: FlashRank typically improves MRR@5 by 10-15% over RRF alone

**Page filtering:** When `page_filter` parameter is provided, Qdrant filters results to specific page numbers using top-level metadata fields. This enables precise page-scoped queries like "what's on page 5?"

**Adaptive retrieval mode:** When `k=None`, fetches up to `ADAPTIVE_RETRIEVAL_POOL_SIZE` (20) candidates and filters by score threshold — returns variable chunk counts based on relevance.

**Collection schema per project:**

```json
{
  "vectors": {
    "dense": { "size": 1536, "distance": "Cosine" },
    "sparse": { "type": "sparse" }
  },
  "payload_schema": {
    "page_content": "text",
    "original_content": "text (JSON)",
    "source_file": "keyword",
    "page_number": "integer (indexed)",
    "chunk_index": "integer",
    "clause_type": "keyword",
    "section_reference": "keyword"
  }
}
```

**Metadata storage improvements:**
- Top-level payload fields (`page_number`, `clause_type`, `section_reference`) enable efficient filtering without JSON parsing
- Contextual embedding prepends metadata prefix to improve retrieval for page/clause/section queries
- Original `page_content` preserved for display, embedded text includes context

---

### Reranking Strategy

The system uses a **two-stage retrieval + reranking architecture** for optimal relevance:

**Stage 1: Initial Retrieval (Qdrant)**
- **Hybrid mode**: RRF fusion of 50 dense + 50 sparse candidates → top-K results
- **Semantic mode**: Dense vector search → top-K results filtered by threshold

**Stage 2: Semantic Reranking (FlashRank)**
- **Model**: `ms-marco-MiniLM-L-6-v2` cross-encoder (ONNX format, 90MB)
- **Inference**: Local CPU/GPU inference via FlashRank library
- **Latency**: ~50-100ms for K=5, ~200-300ms for K=20
- **Quality**: Improves MRR@5 by 10-15% over retrieval-only baseline

**Why reranking matters:**
- Initial retrieval optimizes for recall (finding all relevant chunks)
- Reranker optimizes for precision (ranking most relevant chunks first)
- Cross-encoder models see full query-document interaction (vs. bi-encoder embeddings)
- Local inference means zero API cost and no external dependency

**Configuration:**
- Reranking is automatically enabled when FlashRank is installed
- Falls back gracefully to retrieval-only if FlashRank unavailable
- No configuration required — works out of the box

---

### Contract Analysis Service (`services/contract_analysis_service.py`)

The core analysis engine uses a **two-pass LLM pipeline**:

#### Pass 1 — Per-chunk parallel extraction

Each chunk is processed concurrently (max 5 parallel calls via `asyncio.Semaphore`) using a structured JSON prompt. Extracts:

- **Clauses** — type, title, verbatim text, section reference, obligations
- **Metadata fragments** — parties, effective date, expiration date, governing law
- **Key dates** — any explicitly mentioned dates

**20 supported clause types:**
`confidentiality`, `termination`, `indemnification`, `liability`, `non_compete`, `non_solicitation`, `intellectual_property`, `payment`, `governing_law`, `dispute_resolution`, `force_majeure`, `data_privacy`, `warranty`, `insurance`, `assignment`, `amendment`, `entire_agreement`, `severability`, `auto_renewal`, `other`

#### Pass 2 — Merge + meta-analysis

A single LLM call merges all fragments into a unified `ContractAnalysis` object. Deduplicates clauses, resolves conflicting metadata, and produces contract-level output.

**Additional outputs generated:**
- **Risk Report** — evidence-grounded, perspective-aware risk scoring (0–100), categorized by `RiskSeverity` (low / medium / high / critical) and `RiskCategory`
- **Plain-English Summary** — non-legal language summary with adaptive depth (`brief` / `standard` / `detailed`)
- **Document hash caching** — SHA-256 of document content; identical documents skip re-analysis

**Provider routing for analysis:**
- `LLM_PROVIDER=openai` → `gpt-4o-mini` for Pass 1, `gpt-4o-mini` for Pass 2
- `LLM_PROVIDER=gemini` → Gemini Flash for all passes
- `LLM_PROVIDER=local_lora` → LoRA adapter for Pass 1, OpenAI for Pass 2

#### Evidence-grounded, perspective-aware risk scoring

Risk scoring is a **hybrid of a deterministic rule layer and an evidence-grounded LLM layer**,
run concurrently and merged:

- **Rule layer** (`services/risk_rules/extractors.py`): pure regex + numeric-parsing functions
  (no LLM, no DB) — `extract_liability_cap`, `extract_notice_period`, `extract_auto_renewal_terms`,
  `extract_governing_law`, `extract_indemnity_asymmetry`. These replace brittle substring keyword
  checks so rules fire on genuine language (e.g. "shall not exceed $1,000,000", "sixty (60) days
  written notice", fee-based caps).
- **LLM layer**: retrieves verbatim source passages (`_retrieve_risk_evidence`) and prompts the
  LLM (perspective-aware: `neutral` / `customer` / `vendor`) to return risks that **each carry a
  verbatim `evidence` quote and a `confidence` score**. Risks without a supporting quote are excluded.
- **Verification pass** (`_verify_risk_evidence`, Phase 5): high/critical risks whose evidence cannot
  be fuzzy-matched back to the source are dropped or downgraded.
- **Configurable blend**: `score = RISK_RULE_WEIGHT·rule_score + RISK_LLM_WEIGHT·llm_score`
  (LLM component is distribution-based: `max·0.6 + avg·0.4`), with severity→points from
  `RISK_SEVERITY_*`. The `ScoringExplanation` persists the raw `feature_vector`
  (cap presence, min notice days, one-sided indemnity, missing-clause counts, severity counts),
  the `weights_used`, and the `perspective` — so the UI can fully explain the score.

#### Versioned prompt registry

All pipeline prompts live in `services/prompts/registry.py` with explicit version tags
(`chunk_extraction_v1`, `merge_v1`, `risk_analysis_v2`, `summary_v2`, `evidence_verification_v1`,
`risk_regeneration_v1`, `summary_regeneration_v1`). `ACTIVE_VERSIONS` selects the live version per
stage; each analysis records the version set it used. When `LANGFUSE_ENABLED=true`, `get_prompt()`
first attempts a Langfuse pull (hot-swap without deploy) and falls back to the local catalogue.

#### Progressive rendering + background judge

`run_analysis_pipeline_from_row` persists partial results and a `stage_json` progress signal as each
stage completes (`extracting_clauses` → `assessing_risk` → `writing_summary` → `reviewing_quality`),
so the polling frontend renders clauses before risk and risk before summary. The row is marked
`completed` as soon as the summary is ready; the **LLM-as-Judge (plus one bounded judge-informed
regeneration) then runs as a fire-and-forget background task** that writes `quality_score` /
`flagged_for_review` afterward — removing the judge from the user-visible critical path.

#### Stale-analysis correctness

Analyses are keyed to a project + a content hash (there is no per-document FK). `get_analysis` is
**hash-aware**: it recomputes the current corpus hash and returns `None` (→ `status="none"`) when it
diverges from the stored `document_hash` or the corpus is empty. Document delete and successful
re-ingestion both call `invalidate_analyses(project_id)`. When the last document is removed, chat
history is cleared; otherwise it is preserved.

---

### LLM Provider Abstraction (`llm/provider.py`)

A thin abstraction layer routes to the correct LLM backend based on `LLM_PROVIDER` env var.

| Function | Returns | Purpose |
|---|---|---|
| `get_llm(settings)` | `BaseChatModel` | General purpose LLM (query/chat) |
| `get_streaming_llm(settings)` | `BaseChatModel` | Streaming-enabled LLM for SSE endpoints |
| `get_analysis_llm(settings)` | `BaseChatModel \| LocalLoRAProvider` | Pass 1 clause extraction |
| `get_local_lora_provider(settings)` | `LocalLoRAProvider \| None` | Load HF LoRA adapter |

**`LocalLoRAProvider`** wraps a HuggingFace `transformers` model with an async interface. Inference is offloaded via `asyncio.run_in_executor` to avoid blocking the event loop.

---

### Guardrails (`services/guardrails.py`)

**Input Guardrails (pre-processing):**
- Size limit: max 10,000,000 characters
- Prompt injection detection via regex patterns (e.g., "ignore previous instructions", template injection, Llama `[INST]` injection)
- Repetitive/abusive content detection

**Output Guardrails (post-processing):**
- **Hallucination detection** — checks source overlap between generated answers and retrieved chunks (threshold: 0.25)
- **Unsafe legal statement detection** — flags definitive legal advice ("you are legally required to", "this is legally binding")
- **Confidence scoring** — based on source overlap ratio

---

### LLM-as-Judge (`services/judge_service.py`)

After each analysis completes (as a **background task, off the user-visible critical path**), a
separate `gpt-4o-mini` instance evaluates the output quality across 5 dimensions:

| Dimension | Score Range | Measures |
|---|---|---|
| Clause Extraction Recall | 0.0 – 1.0 | All significant clauses found? |
| Clause Extraction Precision | 0.0 – 1.0 | Extracted texts are accurate? |
| Risk Assessment Accuracy | 0.0 – 1.0 | Risks are genuine and calibrated? |
| Summary Faithfulness | 0.0 – 1.0 | Summary accurately represents contract? |
| Summary Completeness | 0.0 – 1.0 | All significant aspects covered? |

**Flagging:** If overall `quality_score < JUDGE_QUALITY_THRESHOLD` (0.7), `flagged_for_review=True` is set on the analysis row, and one bounded judge-informed regeneration of the risk/summary output is attempted.

---

### Query / RAG Service (`services/query_service.py`)

**Chat flow (streaming SSE):**

```
User Question
      │
      ▼
Input Guardrail Check
      │
      ▼
Query Cache Lookup (SHA-256 key: project_id + normalized_question)
      │ (cache miss)
      ▼
Hybrid Vector Retrieval (VectorStoreService)
      │
      ▼
Context Assembly (retrieved chunks + chat history)
      │
      ▼
LLM Streaming Response (SSE to frontend)
      │
      ▼
Output Guardrail Check
      │
      ▼
Cache Write + Chat Message Persistence
```

---

### Fine-tuning System (`finetuning/`)

Supports training and evaluating a custom **QLoRA adapter** on top of **Llama-3.2-3B-Instruct**.

| Module | Purpose |
|---|---|
| `dataset_builder.py` | Build JSONL training datasets from existing analyses |
| `lora_trainer.py` | `LoRATrainer` class — loads base model, applies QLoRA, runs training and inference |
| `evaluator.py` | Compute clause F1, precision, recall against ground truth |
| `cli.py` | Click CLI for train/eval/export commands |

**Trained model:** `iakshayrathee/contractiq-lora-llama3` (HuggingFace Hub)

**Training notebook:** `notebooks/contractiq_lora_finetune.ipynb` (Colab-compatible, uses `unsloth` + `trl`)

**Model registry:** Tracks trained model metadata, performance metrics, and lifecycle status in the `model_registry` PostgreSQL table.

---

### API Routes Summary

| Router | Prefix | Tag | Key Endpoints |
|---|---|---|---|
| `auth/router.py` | `/auth` | Auth | register, login, refresh, logout |
| `routes/projects.py` | `/projects` | Projects | CRUD for projects |
| `routes/ingestion.py` | `/projects/{name}` | Ingestion | upload document, list chunks |
| `routes/contracts.py` | `/projects/{name}` | Contracts | trigger analysis, get analysis/risk/summary |
| `routes/query.py` | `/projects/{name}` | Query | RAG chat (streaming SSE) |
| `routes/dashboard.py` | `/dashboard` | Dashboard | aggregated stats + `?range=` filter (7d/30d/90d/all), period-over-period trends, activity timeline, quality/flagged counts, risk-category & contract-type breakdowns |
| `routes/analysis.py` | `/analysis` | Analysis | cross-project analysis |
| `routes/jobs.py` | `/jobs` | Jobs | background job status |
| `routes/finetuning.py` | `/finetuning` | Fine-tuning | train, evaluate, list models |
| `routes/health.py` | `/health` | Health | liveness probe |

---

## 🖥️ Frontend — Detailed Design

### Technology Stack

| Layer | Technology |
|---|---|
| Framework | Next.js 14 (App Router) |
| Language | TypeScript |
| Styling | TailwindCSS 3 |
| Data Fetching | TanStack Query v5 |
| Charts | Recharts v3 |
| Icons | lucide-react |
| Markdown | react-markdown + remark-gfm |

### Pages (App Router)

| Route | Component | Purpose |
|---|---|---|
| `/` | `app/page.tsx` | Landing page — product overview |
| `/login` | `app/login/` | User login form |
| `/register` | `app/register/` | User registration form |
| `/dashboard` | `app/dashboard/` | Project list + activity stats |
| `/projects/[name]` | `app/projects/` | Project detail, analysis, chat |

### Component Directories

| Directory | Contents |
|---|---|
| `components/charts/` | Risk score charts, clause distribution visualizations |
| `components/chat/` | RAG chat UI with SSE streaming |
| `components/contract/` | Clause list, risk report, summary display |
| `components/layout/` | Sidebar, header, navigation |
| `components/project/` | Project cards, creation modal |
| `components/projects/` | Projects list view |
| `components/ui/` | Generic primitives (buttons, modals, loaders) |

### Data Flow

```
TanStack Query
    ├── useQuery     → GET requests (projects, analyses, chunks)
    └── useMutation  → POST/DELETE (create project, trigger analysis)

SSE Streaming (Chat)
    └── fetch() with ReadableStream → token-by-token message rendering
```

---

## 🚀 Performance Characteristics & Optimization

### Ingestion Pipeline Performance

| Operation | Typical Latency | Notes |
|---|---|---|
| PDF parsing (text) | ~1-2s per page | PyMuPDF, single-threaded |
| PDF parsing (image-heavy) | ~3-5s per page | Includes image extraction |
| DOCX parsing | ~0.5-1s per page | python-docx, faster than PDF |
| Vision API call | ~2-3s per image | OpenAI API latency + inference |
| Vision API cost | ~$0.001-0.003 per image | gpt-4o-mini pricing |
| Chunking | ~0.1s per 100 pages | Local text splitting |
| Embedding (dense) | ~0.5-1s per 100 chunks | OpenAI API batch processing |
| Embedding (sparse) | ~0.05s per 100 chunks | Local FastEmbed inference |
| Qdrant upsert | ~0.1-0.3s per 100 points | Network + indexing time |

**Example: 10-page contract with 2 images**
- Parsing: 2s
- Vision: 6s (2 images × 3s, concurrent)
- Chunking: 0.1s
- Embedding: 0.5s (assume 25 chunks)
- Storage: 0.1s
- **Total**: ~8-10 seconds

**Example: 50-page contract with 10 images**
- Parsing: 10s
- Vision: 30s (10 images, batched by semaphore limit)
- Chunking: 0.2s
- Embedding: 2s (assume 120 chunks)
- Storage: 0.5s
- **Total**: ~40-50 seconds

### Query Performance

| Operation | Typical Latency | Notes |
|---|---|---|
| Query embedding | ~50-100ms | OpenAI API |
| Hybrid search (RRF) | ~50-150ms | Qdrant prefetch + fusion |
| Semantic search | ~30-80ms | Dense vector only |
| FlashRank reranking (K=5) | ~50-100ms | Local ONNX CPU inference |
| FlashRank reranking (K=20) | ~200-300ms | Linear with K |
| LLM streaming (first token) | ~500-800ms | OpenAI GPT-4o-mini |
| LLM streaming (throughput) | ~50-80 tokens/s | Varies by load |

**Example: RAG query with K=5**
- Embed query: 80ms
- Hybrid search: 100ms
- Reranking: 70ms
- LLM first token: 600ms
- **Time to first token**: ~850ms

### Analysis Performance

| Operation | Typical Latency | Notes |
|---|---|---|
| Pass 1 (per chunk) | ~1-2s | Parallel, 5 concurrent LLM calls |
| Pass 1 (20 chunks) | ~8-12s | Batched via semaphore |
| Pass 2 (merge) | ~3-5s | Single LLM call |
| Risk analysis | ~2-3s | Rule-based + LLM |
| Plain summary | ~3-4s | LLM generation |
| LLM-as-Judge | ~2-3s | Quality evaluation |
| **Total (20-chunk contract)** | ~20-30s | End-to-end analysis |

### Database Query Performance

| Query | Typical Latency | Notes |
|---|---|---|
| Project list (user) | ~5-15ms | Indexed by user_id |
| Analysis fetch | ~8-20ms | JSON deserialization overhead |
| Chat history (100 messages) | ~15-30ms | Paginated, indexed |
| Document hash lookup | ~3-8ms | Indexed cache_key |

### Optimization Strategies

**Ingestion:**
- ✅ Vision concurrency capped at 3 (prevents rate limits)
- ✅ Embeddings batched (500 docs per Qdrant upsert)
- ✅ Sparse encoding preloaded (zero cold-start)
- ✅ Application lock prevents concurrent ingestion (data consistency)

**Retrieval:**
- ✅ Hybrid RRF with 50+50 candidates (good recall)
- ✅ FlashRank reranking (10-15% MRR improvement)
- ✅ Threshold filtering only in semantic mode
- ✅ Top-level metadata fields (efficient page filtering)
- ⚠️ Consider: Increase prefetch limits for complex queries

**Analysis:**
- ✅ Pass 1 parallelism (5 concurrent LLM calls)
- ✅ Document hash caching (skip duplicate analyses)
- ✅ Retry logic with exponential backoff (transient errors)
- ⚠️ Consider: Increase concurrency for very large contracts

**Database:**
- ✅ Connection pooling (async SQLAlchemy)
- ✅ Indexes on user_id, project_id, cache_key
- ⚠️ Consider: Read replicas for dashboard queries
- ⚠️ Consider: Partitioning chat_messages by project_id

### Scalability Considerations

| Component | Current Limit | Scaling Strategy |
|---|---|---|
| Qdrant | Single instance | Qdrant Cloud cluster or self-hosted cluster |
| PostgreSQL | Single instance | Read replicas + connection pooling |
| FastAPI | Single process | Horizontal scaling (load balancer + multiple pods) |
| OpenAI API | Rate limited | Backoff + retry, consider Azure OpenAI for higher limits |
| Vision API | 3 concurrent | Increase VISION_CONCURRENCY, monitor costs |

---

## 🐳 Infrastructure & Deployment

### Docker Compose Services

| Service | Image | Port | Purpose |
|---|---|---|---|
| `qdrant` | `qdrant/qdrant:v1.14.0` | 6333, 6334 | Vector database |
| `postgres` | `postgres:16-alpine` | 5432 | Relational database |
| `backend` | custom (./backend/Dockerfile) | 8000 | FastAPI API server |
| `frontend` | custom (./frontend/Dockerfile) | 3000 | Next.js web app |

### Cloud Deployment

- **Backend:** Render.com (configured via `backend/render.yaml`)
- **Frontend:** Vercel (configured via `vercel.json`)
- **Vector DB:** Qdrant Cloud
- **Database:** Managed PostgreSQL (Render / Railway)

### Environment Variables (`.env`)

Key variables required at runtime:

```bash
# LLM
OPENAI_API_KEY=sk-...
LLM_PROVIDER=openai              # openai | gemini | local_lora
GEMINI_API_KEY=                  # only for LLM_PROVIDER=gemini

# Databases
DATABASE_URL=postgresql+asyncpg://contractiq:contractiq@localhost:5432/contractiq
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=                  # only for Qdrant Cloud

# Auth
JWT_SECRET_KEY=<generate with: openssl rand -hex 32>

# Observability (optional)
LANGFUSE_ENABLED=false
LANGFUSE_SECRET_KEY=
LANGFUSE_PUBLIC_KEY=

# LoRA (optional — only for LLM_PROVIDER=local_lora)
LOCAL_LORA_ADAPTER_PATH=iakshayrathee/contractiq-lora-llama3
```

---

## 🔐 Security Design

| Concern | Approach |
|---|---|
| Authentication | JWT HS256 — short-lived access token + httpOnly refresh cookie |
| Password storage | bcrypt hashing via passlib |
| Input validation | Pydantic schemas + custom input guardrails |
| Prompt injection | Regex-based detection on all ingested content |
| Rate limiting | `slowapi` on critical endpoints |
| CORS | Configurable origin whitelist via `CORS_ORIGINS` env var |
| JWT in production | Enforces non-default `JWT_SECRET_KEY` when database is remote |
| User isolation | All project/analysis queries are scoped to `user_id` |

---

## 🔍 Troubleshooting & Common Issues

### Ingestion Failures

**Issue: "Vision API rate limit exceeded"**
- **Cause**: Too many concurrent vision API calls
- **Solution**: Reduce `VISION_CONCURRENCY` env var (default: 3)
- **Prevention**: Monitor OpenAI API usage dashboard

**Issue: "Sparse encoding failed"**
- **Cause**: FastEmbed BM25 model not downloaded
- **Solution**: Restart service — model downloads automatically on first use
- **Prevention**: Docker image includes pre-downloaded models

**Issue: "Concurrent ingestion conflict"**
- **Cause**: Multiple simultaneous uploads to same project
- **Solution**: Application lock prevents this — check logs for deadlock
- **Prevention**: Design ensures only one ingestion per collection at a time

### Retrieval Issues

**Issue: "All chunks scored below threshold"**
- **Symptoms**: Zero results returned, log shows threshold filter
- **Solution**: Lower `RETRIEVAL_SCORE_THRESHOLD` (default: 0.50)
- **Prevention**: Use hybrid mode (default) — no threshold filtering

**Issue: "Slow query performance (>2s)"**
- **Cause**: Large K value or FlashRank overhead
- **Solution**: Reduce K or disable reranking
- **Debugging**: Check logs for "FlashRank reranking" latency

**Issue: "Page filter returns no results"**
- **Cause**: Page numbers not stored in top-level metadata
- **Solution**: Re-ingest document — older ingests may lack metadata fields
- **Prevention**: Alembic migrations handle schema updates

### Analysis Failures

**Issue: "Pass 1 extraction timeout"**
- **Cause**: LLM rate limits or transient API errors
- **Solution**: Retry automatically via exponential backoff (3 attempts)
- **Prevention**: Monitor OpenAI API status

**Issue: "Low quality score (flagged for review)"**
- **Cause**: LLM-as-Judge quality threshold not met (default: 0.7)
- **Solution**: Review flagged analyses manually, adjust `JUDGE_QUALITY_THRESHOLD`
- **Investigation**: Check `judge_json` field in analyses table

**Issue: "LoRA inference OOM"**
- **Cause**: Insufficient GPU/CPU memory for PEFT model
- **Solution**: Switch to `LLM_PROVIDER=openai` or increase memory
- **Prevention**: Local concurrency semaphore (1) prevents parallel LoRA calls

### Authentication Issues

**Issue: "JWT signature verification failed"**
- **Cause**: `JWT_SECRET_KEY` changed between login and request
- **Solution**: Keep secret key stable, or force users to re-login
- **Prevention**: Use environment variable, never hardcode

**Issue: "Refresh token expired"**
- **Cause**: 7-day refresh token lifetime exceeded
- **Solution**: User must re-login
- **Prevention**: Implement "remember me" for longer sessions

### Database Issues

**Issue: "Connection pool exhausted"**
- **Cause**: Too many concurrent requests
- **Solution**: Increase pool size in `DATABASE_URL` query params
- **Example**: `?pool_size=20&max_overflow=10`

**Issue: "Alembic migration conflict"**
- **Cause**: Multiple backend instances running migrations
- **Solution**: Run migrations manually once before deploy
- **Command**: `alembic upgrade head`

### Debugging Tips

**Enable debug logging:**
```bash
export LOG_LEVEL=DEBUG
```

**Check Langfuse traces:**
- Enable: `LANGFUSE_ENABLED=true`
- View: https://cloud.langfuse.com

**Inspect Qdrant collection:**
```python
from qdrant_client import QdrantClient
client = QdrantClient(url="http://localhost:6333")
info = client.get_collection("collection_name")
print(info)
```

**Check PostgreSQL query performance:**
```sql
-- Enable query logging
ALTER DATABASE contractiq SET log_statement = 'all';
ALTER DATABASE contractiq SET log_min_duration_statement = 100;  -- log slow queries (>100ms)
```

---

## 📊 Observability

| Tool | Purpose |
|---|---|
| **structlog** | Structured JSON logging (console in dev, JSON in production) |
| **Langfuse** | LLM call tracing, token usage, latency tracking (opt-in) |
| **Request IDs** | Every request gets a unique `X-Request-ID` for log correlation |
| **LLM-as-Judge** | Automated quality scoring stored in the `analyses` table |

---

## 🧪 Testing

- **Test framework:** pytest + pytest-asyncio
- **Location:** `backend/tests/`
- **Config:** `backend/pyproject.toml`
- **Dependencies:** `backend/requirements-test.txt`

Test coverage targets:
- Service layer (ingestion, analysis, query)
- Auth endpoints (register, login, refresh, logout)
- Guardrails (input validation, hallucination detection)
- Evaluator (clause F1 metrics)

---

## 🔄 Key Data Flows

### Contract Upload & Analysis Flow

```
User uploads PDF/DOCX
         │
         ▼
POST /projects/{name}/ingest
         │
         ▼
IngestionService
  ├── Parse (PyMuPDF / python-docx)
  ├── Extract images + GPT-4o vision descriptions
  ├── Extract tables (HTML + markdown)
  ├── Chunk (1024 chars, 200 overlap)
  ├── Merge multimodal chunks
  ├── Add contextual metadata prefix
  └── Embed + store → Qdrant (dense + sparse vectors, top-level metadata)
         │
         ▼
POST /projects/{name}/analyze
         │
         ▼
ContractAnalysisService
  ├── Validate input (guardrails)
  ├── Check document hash cache
  ├── Pass 1: parallel chunk clause extraction (GPT-4o-mini or LoRA)
  ├── Pass 2: merge + risk + summary (GPT-4o-mini)
  ├── LLM-as-Judge evaluation
  └── Persist to analyses table (PostgreSQL)
         │
         ▼
GET /projects/{name}/analysis
GET /projects/{name}/risk
GET /projects/{name}/summary
         │
         ▼
Frontend renders structured results
```

### RAG Chat Flow

```
User sends message
         │
         ▼
POST /projects/{name}/query (SSE)
         │
         ▼
QueryService
  ├── Input guardrail check
  ├── Cache lookup (SHA-256 key)
  ├── Hybrid vector retrieval (Qdrant RRF) or semantic search
  ├── Optional page filtering (metadata-based)
  ├── Context assembly + history
  ├── Stream LLM response (SSE chunks)
  ├── Output guardrail check
  └── Cache write + persist ChatMessageRow
         │
         ▼
Frontend renders streamed tokens with source citations
```

---

## 📦 Dependency Summary

### Backend Core

| Package | Version | Purpose |
|---|---|---|
| `fastapi` | 0.115.14 | Web framework |
| `uvicorn` | 0.35.0 | ASGI server |
| `pydantic` | 2.11.7 | Data validation |
| `pydantic-settings` | 2.10.1 | Settings management |
| `python-dotenv` | 1.1.1 | Environment variable loading |
| `langchain` | 0.3.27 | LLM orchestration |
| `langchain-core` | 0.3.75 | LangChain core abstractions |
| `langchain-openai` | 0.3.32 | OpenAI integration |
| `langchain-google-genai` | ≥1.0.0 | Gemini integration |
| `langchain-qdrant` | 0.2.0 | Qdrant vector store |
| `langgraph` | ≥0.2.0 | LangGraph framework |
| `openai` | 1.106.1 | OpenAI API client |
| `qdrant-client` | ≥1.9.0 | Vector DB client |
| `fastembed` | ≥0.3.0 | BM25 sparse encoder |
| `flashrank` | ≥0.2.9 | Local cross-encoder reranker (ONNX) |
| `sqlalchemy[asyncio]` | 2.0.41 | Async ORM |
| `asyncpg` | 0.31.0 | PostgreSQL async driver |
| `alembic` | 1.16.1 | DB migrations |
| `pymupdf` | ≥1.24.0 | PDF parsing |
| `python-docx` | ≥1.1.2 | DOCX parsing |
| `pillow` | 11.3.0 | Image processing |
| `python-jose[cryptography]` | ≥3.3.0 | JWT |
| `passlib[bcrypt]` | ≥1.7.4 | Password hashing |
| `bcrypt` | ≥3.1.7,<4.0.0 | Bcrypt implementation (pinned for passlib compat) |
| `python-multipart` | 0.0.20 | File upload support |
| `email-validator` | ≥2.1.0 | Email validation |
| `langfuse` | 2.60.4 | LLM observability |
| `slowapi` | 0.1.9 | Rate limiting |
| `structlog` | ≥24.0.0 | Structured logging |
| `tiktoken` | 0.8.0 | Token counting |
| `click` | 8.1.0 | CLI framework |
| `datasets` | 3.0.0 | Dataset management |
| `scikit-learn` | 1.5.0 | ML utilities |

### Frontend Core

| Package | Version | Purpose |
|---|---|---|
| `next` | ^14.2.0 | React framework |
| `react` | ^18.3.0 | UI library |
| `react-dom` | ^18.3.0 | React DOM renderer |
| `@tanstack/react-query` | ^5.51.0 | Server state management |
| `recharts` | ^3.8.1 | Data visualization |
| `lucide-react` | ^1.7.0 | Icons |
| `react-markdown` | ^10.1.0 | Markdown rendering |
| `remark-gfm` | ^4.0.1 | GitHub Flavored Markdown support |
| `clsx` | ^2.1.1 | Conditional class names |
| `tailwindcss` | ^3.4.0 | Utility CSS framework |
| `typescript` | ^5.4.0 | TypeScript compiler |

---

## 🚀 Local Development Setup

### Prerequisites

- Docker + Docker Compose
- Python 3.11+ (for local backend dev)
- Node.js 20+ (for local frontend dev)
- OpenAI API key

### Quick Start (Docker)

```bash
# 1. Copy environment file
cp .env.example .env
# Edit .env — set OPENAI_API_KEY and JWT_SECRET_KEY

# 2. Start all services
docker-compose up --build

# Frontend → http://localhost:3000
# Backend  → http://localhost:8000
# API Docs → http://localhost:8000/docs
```

### Local Backend Dev

```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt

# Run database migrations
alembic upgrade head

# Start server
uvicorn app.main:app --reload --port 8000
```

### Local Frontend Dev

```bash
cd frontend
npm install
npm run dev
# → http://localhost:3000
```

### Using Local LoRA Provider

```bash
pip install -r backend/requirements-lora.txt
# Set in .env:
# LLM_PROVIDER=local_lora
# LOCAL_LORA_ADAPTER_PATH=iakshayrathee/contractiq-lora-llama3
```

---

## 📝 Design Decisions & Trade-offs

| Decision | Rationale |
|---|---|
| **Two-pass analysis** | Pass 1 parallelism handles large contracts efficiently; Pass 2 ensures global consistency across chunks |
| **Hybrid vector search (dense + sparse)** | BM25 + semantic embeddings improves recall for legal terminology that may not embed well. RRF fusion combines strengths of both approaches. |
| **FlashRank reranking** | Local ONNX cross-encoder adds semantic reranking without API dependency. Improves MRR@5 by 10-15% with <100ms latency overhead. |
| **Per-project Qdrant collections** | Strict user-level isolation; simple deletion on project removal |
| **Document hash caching** | SHA-256 content hash avoids expensive LLM calls for duplicate documents |
| **httpOnly refresh cookie** | Refresh token never accessible to JavaScript — mitigates XSS token theft |
| **Custom PyMuPDF pipeline** | Removes Unstructured Cloud dependency, eliminates external API costs and latency |
| **Chunk size 1024 / overlap 200** | Legal clauses regularly exceed 512 chars; 200-char overlap preserves context across clause boundaries |
| **LLM-as-Judge** | Automated quality gate without human review bottleneck; flags low-quality analyses for human review |
| **LoRA adapter over full fine-tune** | Lower compute cost; HuggingFace Hub distribution; QLoRA enables consumer GPU inference |
| **Contextual embedding** | Metadata prefix improves retrieval accuracy for page/clause/section-specific queries without schema changes |
| **Top-level metadata fields** | Enables efficient Qdrant filtering without JSON parsing overhead |
| **Rank-based scoring for RRF** | Normalized 0-1 scores provide UI-friendly confidence values; all K results returned without threshold filtering |
| **Table chunk separation** | HTML preserved for rendering; markdown text optimized for embedding; maintains table structure |
| **Vision concurrency semaphore** | Prevents OpenAI rate-limit 429 errors; controls cost by limiting parallel vision API calls |
| **Local concurrency for LoRA** | Serialized PEFT model inference prevents GPU OOM and CPU thrashing on consumer hardware |
| **Threshold lowered to 0.50** | Enables broader initial retrieval for summary/page queries; FlashRank reranker handles quality selection from larger candidate pool |

---

*Document generated from codebase analysis of ContractIQ v2.1.0*


---

## 📚 Summary & Future Roadmap

### Current State (v2.1.0)

ContractIQ v2.1.0 represents a mature, production-ready AI legal contract analysis platform with:

✅ **Core capabilities:**
- PDF/DOCX ingestion with multimodal support (text, tables, images)
- Two-pass LLM contract analysis with 20 clause types
- Hybrid retrieval (RRF) + semantic reranking (FlashRank)
- Real-time RAG chat with SSE streaming
- JWT authentication with dual-token strategy
- Input/output guardrails + LLM-as-Judge quality evaluation

✅ **Production features:**
- Document hash caching (skip duplicate analyses)
- Structured JSON logging + Langfuse observability
- Rate limiting and concurrency controls
- Alembic database migrations
- Docker Compose orchestration
- CI/CD pipelines (GitHub Actions)

✅ **Advanced features:**
- Multi-LLM provider support (OpenAI, Gemini, LoRA)
- Fine-tuning pipeline (QLoRA on Llama-3.2-3B)
- Contextual embedding for improved retrieval
- Top-level metadata fields for efficient filtering
- Model registry and evaluation framework
- Evidence-grounded, perspective-aware risk scoring with configurable weights and a persisted feature vector
- Versioned prompt registry with optional Langfuse hot-swap
- Progressive/staged analysis rendering with a background LLM-as-Judge
- Hash-aware stale-analysis invalidation and multi-document shared-corpus support
- Dashboard time-range filtering with real period-over-period trends and activity timeline
- Extended eval metrics: severity-calibration MAE, risk-band accuracy, citation-validity rate

### Performance Benchmarks

| Metric | Typical Value | Notes |
|---|---|---|
| **Ingestion (10-page PDF)** | 8-10 seconds | With 2 images, vision enabled |
| **Ingestion (50-page PDF)** | 40-50 seconds | With 10 images |
| **Analysis (20-chunk contract)** | 20-30 seconds | End-to-end, all outputs |
| **RAG query time-to-first-token** | ~850ms | K=5, hybrid + reranking |
| **Database query latency** | 5-30ms | Indexed queries |
| **Qdrant search latency** | 30-150ms | Depends on mode |
| **FlashRank overhead** | 50-300ms | Depends on K |

### Known Limitations

| Limitation | Impact | Workaround |
|---|---|---|
| **Single-instance Qdrant** | Limited throughput | Use Qdrant Cloud cluster |
| **OpenAI rate limits** | Ingestion throttling | Increase VISION_CONCURRENCY carefully |
| **No document versioning** | Cannot track changes | Manual versioning via project names |
| **No clause comparison** | Cannot diff contracts | Use separate analyses |
| **English-only** | Cannot analyze non-English contracts | Future: multilingual models |
| **No redlining** | Cannot track edits | Manual tracking required |

### Future Enhancements (Roadmap)

**Phase 1: Usability (Q1 2025)**
- [ ] Bulk document upload (multiple PDFs per project)
- [ ] Exportable reports (PDF/DOCX generation)
- [ ] Clause comparison across contracts
- [ ] Custom clause type definitions (user-configurable)
- [ ] Contract templates library

**Phase 2: Advanced Analysis (Q2 2025)**
- [ ] Clause-level risk scoring (not just contract-level)
- [ ] Change detection (redlining support)
- [ ] Multi-contract analysis (compare 2+ contracts)
- [ ] Obligation tracking with deadlines
- [ ] Financial term extraction (amounts, payment schedules)

**Phase 3: Enterprise Features (Q3 2025)**
- [ ] Team collaboration (shared projects, comments)
- [ ] Role-based access control (RBAC)
- [ ] Audit logs (compliance tracking)
- [ ] Custom risk profiles (industry-specific)
- [ ] SSO integration (SAML, OAuth)

**Phase 4: AI Improvements (Q4 2025)**
- [ ] Multilingual support (Spanish, French, German)
- [ ] Domain-specific LoRA adapters (NDA, SaaS, employment)
- [ ] Active learning (user corrections improve model)
- [ ] Clause recommendation engine
- [ ] Auto-drafting capabilities (generate clauses)

### Contributing

Contributions are welcome! Key areas for contribution:

- **Parser improvements**: Support for scanned PDFs (OCR), better table extraction
- **Prompt engineering**: Improve clause extraction prompts for edge cases
- **Evaluation datasets**: Expand contract_eval_cases.json with more test cases
- **Frontend polish**: Improve UI/UX, add data visualizations
- **Documentation**: Expand API docs, add tutorials

### License & Acknowledgments

**License:** MIT (see LICENSE file)

**Key dependencies:**
- FastAPI, LangChain, Qdrant — core framework
- PyMuPDF, python-docx — document parsing
- OpenAI, HuggingFace — LLM providers
- FlashRank — local semantic reranking
- Next.js, TailwindCSS — frontend framework

**Acknowledgments:**
- CUAD dataset (Columbia University) for fine-tuning data
- Qdrant team for hybrid search implementation guidance
- LangChain community for RAG best practices

---

*Document version 2.1.0 — Last updated July 2026*  
*For questions or support, see the project README or open a GitHub issue.*
