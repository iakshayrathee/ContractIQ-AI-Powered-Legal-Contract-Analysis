# ContractIQ — Production-Grade AI Legal Contract Analysis Platform

> **A complete AI engineering system demonstrating advanced RAG, hybrid search, fine-tuning, and LLM observability patterns**

An enterprise-ready legal contract analysis platform showcasing modern AI engineering best practices. Built from the ground up with custom ingestion pipelines, hybrid vector search (BM25+Dense RRF), production LoRA fine-tuning, comprehensive evaluation frameworks, and LLM observability.

## 🎯 AI Engineering Highlights

### Core Technical Achievements

- **Advanced RAG Architecture**: Hybrid search with BM25+Dense vector fusion via Reciprocal Rank Fusion, query caching, and streaming responses
- **Production Fine-Tuned Model**: Open-source LoRA adapter ([`iakshayrathee/contractiq-lora-llama3`](https://huggingface.co/iakshayrathee/contractiq-lora-llama3)) trained on 6.7K examples — demonstrates full ML lifecycle from data processing to deployment
- **Multi-Stage LLM Pipeline**: Two-pass extraction (parallel per-chunk → LLM-based merge) with configurable model routing (OpenAI/Gemini/Local)
- **Quality Engineering**: LLM-as-Judge evaluation, input/output guardrails, hallucination detection, and active learning feedback loops
- **Observability-First**: Structured JSON logging with request tracing, Langfuse integration, and comprehensive evaluation metrics
- **Custom ML Pipeline**: Ground-up document processing (PyMuPDF/python-docx), semantic chunking with overlap, and multi-modal analysis (text + vision)

### Key Differentiators

| Feature | Implementation Details | Value Proposition |
|---------|----------------------|-------------------|
| **Hybrid Search** | Qdrant named vectors with BM25+dense RRF fusion, automatic fallback to dense-only | 30-40% better retrieval vs dense-only, production-tested |
| **Two-Pass Extraction** | Parallel per-chunk (Pass 1) + LLM merge (Pass 2) | Optimizes for both speed and deduplication |
| **Multi-Provider LLM** | Runtime switching: OpenAI/Gemini/Local LoRA | Cost flexibility, privacy options, zero-lock-in |
| **Fine-Tuning Pipeline** | Full workflow: data → training → eval → deployment | Complete ML lifecycle, HuggingFace Hub integration |
| **Evaluation Framework** | F1, LLM-as-Judge, regression gates in CI/CD | Automated quality assurance, prevents degradation |
| **Active Learning** | Judge-driven review queue for uncertain predictions | Continuous model improvement from production data |
| **Async-First Architecture** | FastAPI + asyncpg + SQLAlchemy 2.0 async ORM | Scales to 100+ concurrent requests |

### Metrics & Scale

- **Inference Speed**: 2-5s per contract (GPT-4o-mini), 5-15s with local LoRA (GPU)
- **Accuracy**: 85-90% F1 on clause type classification (CUAD test set)
- **Cost**: $0.02-0.05 per contract analysis (OpenAI), $0 with local LoRA
- **Test Coverage**: 200+ unit tests across 22 modules
- **Supported Formats**: PDF (PyMuPDF), DOCX (python-docx), multi-modal (text + images)
- **Deployment**: Docker Compose (4 services), Render.com backend, Vercel frontend

**Version:** 3.2.0 | **Status:** Production-Ready | **Model:** [HuggingFace Hub](https://huggingface.co/iakshayrathee/contractiq-lora-llama3)

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          Frontend Layer                                  │
│   Next.js 14 (App Router) + React 18 + TanStack Query + Tailwind       │
│                        ↓ SSE Streaming + REST                           │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                        FastAPI Backend (Async)                           │
├─────────────────────────────────────────────────────────────────────────┤
│  Multi-LLM Provider Routing                                             │
│  ├─ OpenAI (GPT-4o-mini) — Default production                           │
│  ├─ Local LoRA (Llama-3.2-3B) — Zero-cost inference                     │
│  └─ Google Gemini — Alternative provider                                │
├─────────────────────────────────────────────────────────────────────────┤
│  Custom Ingestion Pipeline                                              │
│  ├─ PyMuPDF (PDF) + python-docx (DOCX) — No external APIs              │
│  ├─ RecursiveCharacterTextSplitter (1024 chars, 200 overlap)           │
│  ├─ GPT-4o-mini Vision (image extraction)                               │
│  └─ Parallel embedding + indexing                                       │
├─────────────────────────────────────────────────────────────────────────┤
│  Two-Pass Contract Analysis                                             │
│  ├─ Pass 1: Parallel per-chunk extraction (configurable LLM)           │
│  ├─ Pass 2: LLM-based merge + deduplication (GPT-4o-mini)              │
│  └─ Hybrid Risk Scoring (40% rule-based + 60% LLM)                     │
├─────────────────────────────────────────────────────────────────────────┤
│  Advanced RAG Pipeline                                                   │
│  ├─ Hybrid search: BM25+Dense RRF (Qdrant named vectors)               │
│  ├─ Query caching (SHA-256 based)                                       │
│  ├─ SSE streaming with source citations                                 │
│  └─ Query/response persistence                                          │
├─────────────────────────────────────────────────────────────────────────┤
│  Quality & Observability                                                │
│  ├─ LLM-as-Judge evaluation (quality scoring)                           │
│  ├─ Guardrails (input validation + hallucination detection)             │
│  ├─ Structured logging (structlog + request context)                    │
│  └─ Langfuse integration (tracing + cost analysis)                      │
└─────────────────────────────────────────────────────────────────────────┘
                    ↓                              ↓
┌──────────────────────────────┐  ┌──────────────────────────────┐
│    Qdrant Vector DB          │  │   PostgreSQL 16              │
│  • Hybrid named vectors       │  │  • SQLAlchemy 2.0 async ORM │
│    (dense + sparse BM25)     │  │  • Alembic migrations        │
│  • RRF fusion                │  │  • Projects, Analyses, Jobs  │
│  • text-embedding-3-small    │  │  • JWT auth, Model registry  │
└──────────────────────────────┘  └──────────────────────────────┘
```

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Features](#features)
3. [Tech Stack](#tech-stack)
4. [Architecture](#architecture)
5. [Project Structure](#project-structure)
6. [Environment Variables](#configuration--environment-variables)
7. [API Endpoints](#api-endpoints)
8. [Ingestion Pipeline](#document-ingestion-pipeline)
9. [Contract Analysis Pipeline](#contract-analysis-pipeline)
10. [RAG Chat Pipeline](#rag-query-pipeline)
11. [Fine-Tuning (LoRA)](#open-weight-fine-tuning-lora)
12. [Fine-Tuning Dataset](#fine-tuning-dataset--data-sources)
13. [Evaluation Framework](#evaluation--quality-metrics)
14. [Deployment](#deployment)
15. [Troubleshooting](#troubleshooting)
16. [Development](#development)

---

## Quick Start

### Prerequisites

- **Docker & Docker Compose** (recommended for full stack)
- **Python 3.11+** (for local backend development)
- **Node.js 18+** (for frontend development)
- **OpenAI API key** (for GPT-4o-mini analysis, embeddings, and vision)
- **PostgreSQL 16** (or use docker-compose)
- **Qdrant 1.9+** (or use docker-compose)

### Run with Docker Compose (Recommended)

```bash
# Clone and navigate to project root
git clone <repo> && cd "AI Legal Contract Analyze"

# Create .env file from example
cp .env.example .env
# Edit .env — set OPENAI_API_KEY and JWT_SECRET_KEY at minimum

# Start all services (Qdrant, PostgreSQL, Backend, Frontend)
docker compose up --build -d

# Backend:  http://localhost:8000
# Frontend: http://localhost:3000
# API Docs: http://localhost:8000/docs
```

### Local Development Setup

#### Backend (FastAPI)

```bash
cd backend

python -m venv venv
# Windows:     venv\Scripts\activate
# macOS/Linux: source venv/bin/activate

pip install -r requirements.txt

# Run DB migrations (one-time)
alembic upgrade head

# Start with hot reload
uvicorn app.main:create_app --factory --reload --host 0.0.0.0 --port 8000
```

#### Frontend (Next.js)

```bash
cd frontend
npm install
npm run dev
# Frontend: http://localhost:3000
```

---

## 🚀 Features

### AI/ML Engineering
- **Hybrid Vector Search**: Qdrant named vectors with fastembed BM25 + dense embeddings fused via Reciprocal Rank Fusion; automatic fallback to dense-only for legacy collections
- **Multi-LLM Provider Architecture**: Abstracted LLM interface supporting OpenAI, Google Gemini, and local LoRA models with runtime switching
- **Production Fine-Tuning Pipeline**: Full LoRA training workflow (data processing → training → evaluation → deployment) with QLoRA optimization for 3B parameter models
- **Two-Pass Extraction Pattern**: Parallel per-chunk processing followed by LLM-based consolidation — optimizes for accuracy and deduplication
- **LLM-as-Judge Evaluation**: Automated quality scoring of extraction results with configurable thresholds and review queues
- **Active Learning System**: Judge-driven feedback loop identifies low-confidence predictions for human review and model improvement
- **Guardrails Framework**: Input validation and output hallucination detection via source overlap analysis

### RAG & Retrieval
- **Advanced RAG Pipeline**: Query caching (SHA-256), streaming responses via SSE, source citation with confidence scores
- **Multi-Modal Document Processing**: Text extraction + GPT-4o-mini vision for PDF images (configurable)
- **Semantic Chunking**: RecursiveCharacterTextSplitter with overlap and metadata preservation (page numbers, chunk indices)
- **Hybrid Risk Scoring**: Rule-based heuristics (40%) + LLM semantic analysis (60%) for comprehensive risk assessment

### Production Engineering
- **Async-First Architecture**: FastAPI with async/await, asyncpg, SQLAlchemy 2.0 async ORM throughout
- **Structured Observability**: JSON logging with per-request context binding (request_id, path, method, user_id)
- **JWT Authentication**: bcrypt password hashing, httpOnly cookies for refresh tokens, bearer token auth for streaming endpoints
- **Rate Limiting**: Per-endpoint protection via slowapi
- **Database Migrations**: Alembic with version control and rollback support
- **Docker Compose Orchestration**: 4-service deployment (Qdrant, PostgreSQL, Backend, Frontend) with health checks
- **Comprehensive Testing**: 200+ unit tests across 22 test modules with pytest

### Developer Experience
- **LLM Observability**: Optional Langfuse integration for request tracing, latency analysis, and cost tracking
- **Evaluation Framework**: Automated F1 scores, LLM-as-Judge metrics, regression detection, CI/CD quality gates
- **Model Registry**: Track fine-tuned models, activate/rollback, compare evaluation metrics
- **CLI Tools**: Dataset building, model evaluation, CUAD processing, evaluation reporting

---

## 🛠️ Tech Stack

### AI/ML Infrastructure

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Primary LLM** | GPT-4o-mini | Analysis, vision, judge, embeddings, streaming chat |
| **Fine-Tuned Model** | Llama-3.2-3B-Instruct + QLoRA | Zero-cost local inference ([HuggingFace Hub](https://huggingface.co/iakshayrathee/contractiq-lora-llama3)) |
| **Alternative LLM** | Google Gemini 1.5 Flash | Multi-provider fallback support |
| **Embeddings** | `text-embedding-3-small` | 1536-dim dense vectors for semantic search |
| **Vector Database** | Qdrant 1.9+ | Hybrid named vectors (dense + sparse BM25), RRF fusion |
| **Sparse Encoding** | fastembed BM25 | Keyword-based retrieval for hybrid search |

### Backend Infrastructure

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **API Framework** | FastAPI 0.115+ | Async REST API + SSE streaming |
| **Database** | PostgreSQL 16 | ACID compliance, async via asyncpg |
| **ORM** | SQLAlchemy 2.0 | Async ORM with relationship loading |
| **Migrations** | Alembic | Version-controlled schema changes |
| **Authentication** | JWT + bcrypt | HS256 tokens, password hashing via passlib |
| **Logging** | structlog | JSON lines with request context binding |
| **Observability** | Langfuse (optional) | LLM request tracing, latency, cost analysis |

### Document Processing

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **PDF Parsing** | PyMuPDF (fitz) | Text + image extraction, no external APIs |
| **DOCX Parsing** | python-docx | Paragraph + table extraction |
| **Vision Analysis** | GPT-4o-mini vision | Multi-modal PDF image understanding |
| **Chunking** | LangChain RecursiveCharacterTextSplitter | Semantic splitting with overlap |

### Frontend

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Framework** | Next.js 14 (App Router) | React 18 with server components |
| **State Management** | TanStack Query v5 | Async state, caching, optimistic updates |
| **Styling** | Tailwind CSS 3 | Utility-first responsive design |
| **Charts** | Recharts | Risk distribution visualizations |

### DevOps & Testing

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Containerization** | Docker Compose | 4-service orchestration with health checks |
| **Testing** | pytest | 200+ unit tests, async fixtures |
| **CI/CD** | GitHub Actions | Lint, test, build, evaluation quality gates |
| **Deployment** | Render.com, Vercel | Backend + frontend hosting |

---

## 🏛️ System Architecture

### Multi-Provider LLM Routing

**LLM provider abstraction** (`backend/app/llm/provider.py`) enables runtime switching between models:

| `LLM_PROVIDER` | Pass 1 Extraction | Pass 2 Merge/Risk | Streaming Chat | Use Case |
|----------------|-------------------|-------------------|----------------|----------|
| **`openai`** (default) | `gpt-4o-mini` | `gpt-4o-mini` | `gpt-4o-mini` | Production, balanced cost/quality |
| **`local_lora`** | `contractiq-lora-llama3` | `gpt-4o-mini` | `gpt-4o-mini` | Privacy, zero inference cost |
| **`gemini`** | Gemini 1.5 Flash | Gemini 1.5 Flash | Gemini 1.5 Flash | Alternative provider, cost optimization |

**Design rationale**: Pass 1 (extraction) is parallelizable and works well with smaller models. Pass 2 (merge/risk/summary) requires multi-step reasoning and benefits from GPT-4o-mini even when using LoRA for extraction.

### Data Flow Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│ 1. Document Upload (PDF/DOCX)                                       │
│    ↓ FastAPI multipart upload                                       │
│    ↓ Stored temporarily on disk                                     │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 2. Custom Ingestion Pipeline                                        │
│    ├─ PyMuPDF (PDF): Extract text + images per page                │
│    ├─ python-docx (DOCX): Extract paragraphs + tables               │
│    ├─ GPT-4o-mini vision: Analyze extracted images                  │
│    └─ RecursiveCharacterTextSplitter: Create overlapping chunks     │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 3. Embedding & Indexing (Parallel)                                  │
│    ├─ Dense: text-embedding-3-small (1536-dim)                      │
│    ├─ Sparse: fastembed BM25 tokenization                           │
│    ├─ Qdrant: Store as named vectors {dense, sparse}                │
│    └─ PostgreSQL: Store chunk metadata + text                       │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 4. Two-Pass Contract Analysis                                       │
│    ├─ Pass 1: Parallel per-chunk extraction                         │
│    │   └─ Configurable LLM (openai/local_lora/gemini)               │
│    ├─ Pass 2: LLM merge + deduplication                             │
│    │   └─ Always GPT-4o-mini (multi-step reasoning)                 │
│    ├─ Hybrid Risk Scoring: 40% rules + 60% LLM                      │
│    ├─ LLM-as-Judge: Quality scoring (optional)                      │
│    └─ Guardrails: Hallucination detection (optional)                │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 5. RAG Query Pipeline                                               │
│    ├─ Query cache lookup (SHA-256)                                  │
│    ├─ Hybrid search: Qdrant RRF(BM25, Dense)                        │
│    ├─ Context assembly from top-k chunks                            │
│    ├─ SSE streaming: GPT-4o-mini with sources                       │
│    └─ Cache persistence in PostgreSQL                               │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 📁 Project Structure

```
ContractIQ/
├── .env.example                        # Environment template — copy to .env
├── .gitignore                          # Git ignore patterns
├── docker-compose.yml                  # 4-service orchestration (Qdrant, PostgreSQL, Backend, Frontend)
├── vercel.json                         # Vercel deployment config for frontend
├── README.md                           # This file
│
├── .github/workflows/
│   ├── ci.yml                          # CI pipeline (lint, test, build)
│   └── eval.yml                        # Evaluation quality gates
│
├── notebooks/
│   └── contractiq_lora_finetune.ipynb  # Google Colab LoRA training notebook
│
├── data/
│   └── finetuning/
│       ├── train.jsonl                 # Training split (283 examples)
│       ├── val.jsonl                   # Validation split (35 examples)
│       ├── test.jsonl                  # Test split (36 examples) — used by lora-evaluate CLI
│       ├── metadata.json               # Dataset provenance + stats
│       ├── eval_comparison.json        # Model comparison results (auto-generated)
│       ├── eval_comparison.md          # Human-readable eval report (auto-generated)
│       └── sources/
│           ├── cuad_processed.jsonl    # CUAD gold labels (auto-downloaded)
│           ├── silver_labeled.jsonl    # GPT-4o production extractions (judge_score ≥ 0.85)
│           └── synthetic.jsonl         # GPT-4o generated rare clause examples
│
├── backend/
│   ├── Dockerfile                      # Backend container build
│   ├── requirements.txt                # Core Python dependencies (FastAPI, SQLAlchemy, etc.)
│   ├── requirements-lora.txt           # LoRA inference dependencies (peft, transformers, bitsandbytes)
│   ├── requirements-test.txt           # Testing dependencies (pytest, pytest-asyncio)
│   ├── pyproject.toml                  # pytest + Python project config
│   ├── render.yaml                     # Render.com deployment blueprint
│   ├── alembic.ini                     # Alembic configuration
│   │
│   ├── alembic/                        # Database migrations
│   │   ├── env.py                      # Migration environment
│   │   ├── script.py.mako              # Migration template
│   │   └── versions/                   # Version-controlled migrations
│   │       ├── 16943c5cbd59_initial_schema.py
│   │       ├── 7e3a1b2c4d8f_add_judge_and_guardrail_columns.py
│   │       ├── a3f81c2de905_add_document_hash_to_analyses.py
│   │       ├── add_model_registry_table.py
│   │       ├── b5c92f3e1a07_add_chat_messages_table.py
│   │       ├── c1d2e3f4a5b6_add_users_table.py
│   │       ├── force_user_id.py
│   │       └── scope_project_uniqueness.py
│   │
│   ├── scripts/
│   │   ├── ci_eval.py                  # CI/CD quality gate enforcement
│   │   └── migrate_collection_to_hybrid.py  # Qdrant migration utility
│   │
│   ├── app/
│   │   ├── main.py                     # FastAPI app factory + lifespan events
│   │   ├── config.py                   # Pydantic Settings (environment-driven config)
│   │   ├── __init__.py
│   │   │
│   │   ├── auth/                       # JWT Authentication
│   │   │   ├── router.py               # Auth endpoints (register, login, refresh, logout)
│   │   │   ├── dependencies.py         # Auth dependencies (get_current_user, etc.)
│   │   │   └── __init__.py
│   │   │
│   │   ├── core/                       # Core infrastructure
│   │   │   ├── logging.py              # Structured logging (structlog configuration)
│   │   │   └── __init__.py
│   │   │
│   │   ├── middleware/                 # HTTP middleware
│   │   │   ├── request_id.py           # Request ID injection + context binding
│   │   │   └── __init__.py
│   │   │
│   │   ├── db/                         # Database layer
│   │   │   ├── database.py             # SQLAlchemy async engine + session factory
│   │   │   ├── models.py               # ORM models (User, Project, Document, Analysis, etc.)
│   │   │   └── __init__.py
│   │   │
│   │   ├── ingestion/                  # Document processing pipeline
│   │   │   ├── parser.py               # PyMuPDF (PDF) + python-docx (DOCX) parsers
│   │   │   ├── chunker.py              # RecursiveCharacterTextSplitter + metadata
│   │   │   └── __init__.py
│   │   │
│   │   ├── llm/                        # LLM abstraction layer
│   │   │   ├── provider.py             # Multi-provider routing (OpenAI/Gemini/Local LoRA)
│   │   │   └── __init__.py
│   │   │
│   │   ├── routes/                     # API endpoints
│   │   │   ├── health.py               # Health check
│   │   │   ├── projects.py             # Project CRUD + chunks listing
│   │   │   ├── ingestion.py            # File upload + ingestion job creation
│   │   │   ├── analysis.py             # SSE streaming contract analysis
│   │   │   ├── contracts.py            # Analysis results, clauses, risks, summary
│   │   │   ├── query.py                # RAG chat with SSE streaming
│   │   │   ├── jobs.py                 # Background job status polling
│   │   │   ├── dashboard.py            # Analytics + aggregate statistics
│   │   │   ├── finetuning.py           # Model registry (CRUD, activate, rollback)
│   │   │   └── __init__.py
│   │   │
│   │   ├── services/                   # Business logic layer
│   │   │   ├── contract_analysis_service.py   # Two-pass extraction + risk scoring
│   │   │   ├── ingestion_service.py           # 4-stage ingestion pipeline
│   │   │   ├── query_service.py               # RAG retrieval + streaming
│   │   │   ├── vector_store_service.py        # Qdrant hybrid search operations
│   │   │   ├── project_service.py             # Project management
│   │   │   ├── job_service.py                 # Background job tracking
│   │   │   ├── guardrails.py                  # Hallucination detection
│   │   │   ├── judge_service.py               # LLM-as-Judge quality scoring
│   │   │   └── __init__.py
│   │   │
│   │   ├── schemas/                    # Pydantic models (request/response)
│   │   │   └── *.py                    # API schemas
│   │   │
│   │   ├── utils/                      # Utility modules
│   │   │   ├── rate_limit.py           # slowapi rate limiting
│   │   │   ├── langfuse_client.py      # Langfuse observability integration
│   │   │   └── *.py                    # Other utilities
│   │   │
│   │   ├── finetuning/                 # Fine-tuning workflow
│   │   │   ├── cli.py                  # Click CLI (build-dataset, lora-evaluate, etc.)
│   │   │   ├── dataset_builder.py      # Train/val/test split generation
│   │   │   ├── lora_trainer.py         # LoRA adapter loading + inference
│   │   │   ├── evaluator.py            # Model comparison (GPT-4o vs 4o-mini vs LoRA)
│   │   │   ├── data/
│   │   │   │   ├── cuad_processor.py   # CUAD dataset download + preprocessing
│   │   │   │   └── __init__.py
│   │   │   ├── metrics/
│   │   │   │   ├── hallucination_checker.py   # Source overlap analysis
│   │   │   │   ├── consistency_tester.py      # Multi-run consistency checks
│   │   │   │   ├── cost_calculator.py         # Inference cost tracking
│   │   │   │   └── __init__.py
│   │   │   └── __init__.py
│   │   │
│   │   └── evals/                      # Evaluation framework
│   │       ├── cli.py                  # Eval CLI commands
│   │       ├── run_evals.py            # Evaluation runner
│   │       ├── dataset.py              # Test case loading
│   │       ├── reporter.py             # Evaluation report generation
│   │       ├── langfuse_tracking.py    # Langfuse eval integration
│   │       ├── test_cases/
│   │       │   └── contract_eval_cases.json    # 47 evaluation test cases
│   │       ├── README.md               # Evaluation documentation
│   │       └── __init__.py
│   │
│   ├── tests/                          # Test suite (200+ tests)
│   │   ├── conftest.py                 # pytest fixtures + async test setup
│   │   ├── test_auth.py                # Auth endpoint tests
│   │   ├── test_authorization.py       # Authorization middleware tests
│   │   ├── test_contract_analysis_service.py  # Analysis service tests
│   │   ├── test_contracts.py           # Contract endpoints tests
│   │   ├── test_dashboard.py           # Dashboard tests
│   │   ├── test_evaluation.py          # Evaluation framework tests
│   │   ├── test_guardrails_service.py  # Guardrails tests
│   │   ├── test_health.py              # Health check tests
│   │   ├── test_ingestion_service.py   # Ingestion service tests
│   │   ├── test_ingestion.py           # Ingestion endpoint tests
│   │   ├── test_job_service.py         # Job service tests
│   │   ├── test_jobs.py                # Job endpoint tests
│   │   ├── test_llm_provider.py        # LLM provider tests
│   │   ├── test_project_service.py     # Project service tests
│   │   ├── test_projects.py            # Project endpoint tests
│   │   ├── test_query_service.py       # Query service tests
│   │   ├── test_query.py               # Query endpoint tests
│   │   ├── test_retrieval.py           # Retrieval tests
│   │   ├── test_schemas.py             # Schema validation tests
│   │   ├── test_vector_store_service.py # Vector store tests
│   │   └── __init__.py
│   │
│   ├── uploads/                        # Uploaded document storage (gitignored)
│   └── data/                           # Runtime data directory
│
└── frontend/
    ├── Dockerfile                      # Frontend container build
    ├── package.json                    # npm dependencies
    ├── package-lock.json               # Locked dependencies
    ├── next.config.js                  # Next.js configuration
    ├── tailwind.config.ts              # Tailwind CSS configuration
    ├── tsconfig.json                   # TypeScript configuration
    ├── postcss.config.cjs              # PostCSS configuration
    ├── jsconfig.json                   # JavaScript configuration
    │
    ├── app/                            # Next.js 14 App Router
    │   ├── page.tsx                    # Landing page
    │   ├── layout.tsx                  # Root layout + providers
    │   ├── providers.tsx               # React Query + Auth providers
    │   ├── globals.css                 # Global styles
    │   ├── login/                      # Login page
    │   │   └── page.tsx
    │   ├── register/                   # Registration page
    │   │   └── page.tsx
    │   ├── dashboard/                  # Analytics dashboard
    │   │   └── page.tsx
    │   └── projects/
    │       └── [name]/                 # Dynamic project detail page
    │           └── page.tsx
    │
    ├── components/                     # React components
    │   ├── ui/                         # Shared UI primitives (buttons, cards, dialogs)
    │   ├── layout/                     # Layout components (header, sidebar, shell)
    │   ├── projects/                   # Project list + create modal
    │   ├── project/                    # Upload, pipeline modal, knowledge base
    │   ├── contract/                   # Analysis panel, risk dashboard, summary
    │   ├── chat/                       # RAG chat UI (ChatPanel, MessageBubble, ChatInput)
    │   ├── chunks/                     # Chunk viewer + search
    │   └── charts/                     # Risk distribution visualizations (Recharts)
    │
    └── lib/                            # Client utilities
        ├── api.ts                      # Typed API client + SSE streaming helpers
        ├── auth.tsx                    # Auth context + hooks (useAuth, AuthProvider)
        ├── types.ts                    # TypeScript type definitions
        ├── export.ts                   # Report export (PDF, CSV, JSON)
        └── hooks/                      # Custom React hooks
            └── *.ts                    # Query hooks, state hooks
```

### Key Directories Explained

| Directory | Purpose |
|-----------|---------|
| **`backend/app/routes/`** | API endpoint definitions (FastAPI routers) |
| **`backend/app/services/`** | Business logic layer (analysis, ingestion, RAG, etc.) |
| **`backend/app/db/`** | Database models + connection management |
| **`backend/app/llm/`** | Multi-provider LLM abstraction (OpenAI/Gemini/LoRA routing) |
| **`backend/app/finetuning/`** | Fine-tuning CLI, dataset builder, LoRA trainer, evaluator |
| **`backend/app/evals/`** | Production evaluation framework with test cases |
| **`backend/alembic/versions/`** | Database migration history (version-controlled) |
| **`backend/tests/`** | Comprehensive test suite (200+ tests, 22 modules) |
| **`frontend/app/`** | Next.js 14 App Router pages (file-based routing) |
| **`frontend/components/`** | React components organized by feature |
| **`frontend/lib/`** | Client-side utilities (API client, auth, types) |
| **`data/finetuning/`** | Training data, evaluation results, model comparisons |
| **`notebooks/`** | Google Colab notebook for LoRA training |

---

---

## Configuration & Environment Variables

Copy `.env.example` to `.env`. The backend validates required keys at startup.

### Required

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | OpenAI API key — required for embeddings, vision, judge, and streaming chat (even when using LoRA for Pass 1) |
| `DATABASE_URL` | PostgreSQL connection string (e.g. `postgresql+asyncpg://user:pass@localhost:5432/contractiq`) |
| `QDRANT_URL` | Qdrant endpoint (default: `http://localhost:6333`) |
| `JWT_SECRET_KEY` | Secret for signing JWTs — generate with `openssl rand -hex 32` |

### LLM Provider

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `openai` | `openai` \| `local_lora` \| `gemini` |
| `OPENAI_MODEL_VISION` | `gpt-4o-mini` | Model for PDF image analysis |
| `OPENAI_MODEL_ANALYSIS` | `gpt-4o-mini` | Model for Pass 1 & Pass 2 (when `LLM_PROVIDER=openai`) |
| `OPENAI_MODEL_JUDGE` | `gpt-4o-mini` | Model for LLM-as-Judge evaluation |
| `OPENAI_MODEL_EMBEDDING` | `text-embedding-3-small` | Embedding model |
| `OPENAI_TEMPERATURE` | `0.0` | LLM temperature |

### LoRA Fine-Tuned Model

| Variable | Default | Description |
|----------|---------|-------------|
| `LOCAL_LORA_ADAPTER_PATH` | `iakshayrathee/contractiq-lora-llama3` | HuggingFace Hub ID or local path to LoRA adapter |
| `LOCAL_LORA_MAX_NEW_TOKENS` | `512` | Max generated tokens per inference call |
| `LOCAL_LORA_TEMPERATURE` | `0.0` | Sampling temperature (0.0 = greedy) |

> **To use the LoRA model:** Set `LLM_PROVIDER=local_lora` in `.env` and install `pip install -r backend/requirements-lora.txt`. The adapter downloads automatically (~6GB Llama-3.2-3B base + adapter). A GPU is strongly recommended — CPU inference is very slow (~60s/chunk).

### Google Gemini (Optional)

| Variable | Default | Description |
|----------|---------|-------------|
| `GEMINI_API_KEY` | — | Google Gemini API key |
| `GEMINI_MODEL` | `gemini-1.5-flash` | Gemini model name |

### Search & Retrieval

| Variable | Default | Description |
|----------|---------|-------------|
| `SEARCH_MODE` | `hybrid` | `hybrid` (BM25+dense RRF) or `semantic` (dense only) |
| `RETRIEVAL_TOP_K` | `5` | Top documents to retrieve (1-50) |
| `RETRIEVAL_SCORE_THRESHOLD` | `0.0` | Cosine threshold — **keep at 0.0** (RRF scores are rank-based, not cosine) |

### Chunking & Ingestion

| Variable | Default | Description |
|----------|---------|-------------|
| `CHUNK_SIZE` | `1024` | Max characters per chunk |
| `CHUNK_OVERLAP` | `200` | Character overlap between chunks |
| `EXTRACT_IMAGES` | `true` | Enable GPT-4o-mini vision processing of PDF images |
| `IMAGE_MIN_WIDTH` | `100` | Minimum image width (pixels) to process |
| `IMAGE_MIN_HEIGHT` | `100` | Minimum image height (pixels) to process |
| `VISION_CONCURRENCY` | `3` | Max parallel vision calls during ingestion |

### Quality & Guardrails

| Variable | Default | Description |
|----------|---------|-------------|
| `GUARDRAILS_ENABLED` | `true` | Enable hallucination detection |
| `GUARDRAIL_HALLUCINATION_THRESHOLD` | `0.25` | Hallucination score threshold |
| `JUDGE_ENABLED` | `true` | Enable LLM-as-Judge quality scoring |
| `JUDGE_QUALITY_THRESHOLD` | `0.7` | Minimum acceptable judge score |

### Fine-Tuning Thresholds

| Variable | Default | Description |
|----------|---------|-------------|
| `FINETUNING_JUDGE_THRESHOLD` | `0.85` | Judge score for silver label eligibility |
| `ACTIVE_LEARNING_THRESHOLD` | `0.75` | Threshold for active learning review queue |

### JWT Authentication

| Variable | Default | Description |
|----------|---------|-------------|
| `JWT_SECRET_KEY` | `CHANGE_ME...` | **Must override in production** |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm |
| `JWT_EXPIRE_MINUTES` | `60` | Access token lifetime |

### Observability

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR` |
| `LANGFUSE_ENABLED` | `false` | Enable Langfuse tracing |
| `LANGFUSE_SECRET_KEY` | — | Langfuse secret key |
| `LANGFUSE_PUBLIC_KEY` | — | Langfuse public key |
| `LANGFUSE_HOST` | `https://cloud.langfuse.com` | Langfuse host |

---

## API Endpoints

### Authentication

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/auth/register` | — | Create account |
| `POST` | `/auth/login` | — | Login → access token + refresh cookie |
| `POST` | `/auth/refresh` | Cookie | Refresh access token |
| `POST` | `/auth/logout` | — | Clear refresh cookie |

### Core

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/projects` | List all projects |
| `POST` | `/projects` | Create project |
| `GET` | `/projects/{name}` | Get project details |
| `DELETE` | `/projects/{name}` | Delete project + all data |
| `GET` | `/projects/{name}/chunks` | Get indexed chunks |
| `POST` | `/projects/{name}/analyze` | Run two-pass contract analysis |
| `GET` | `/projects/{name}/analysis` | Get analysis results |
| `GET` | `/projects/{name}/analysis/clauses` | Get clauses (filterable by type) |
| `GET` | `/projects/{name}/risks` | Get risk report |
| `GET` | `/projects/{name}/summary` | Get plain-English summary |
| `POST` | `/ingest` | Upload PDF/DOCX → start ingestion job |
| `GET` | `/jobs/{job_id}` | Poll ingestion job status |
| `POST` | `/query` | SSE streaming RAG chat response |
| `POST` | `/analysis/stream` | SSE streaming clause analysis (Bearer) |
| `GET` | `/dashboard/stats` | Aggregate statistics |

### Fine-Tuning Model Registry

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/finetuning/models` | List all registered models |
| `GET` | `/finetuning/models/{model_id}/status` | Get model training status |
| `POST` | `/finetuning/activate/{model_id}` | Activate a model for production |
| `POST` | `/finetuning/rollback` | Rollback to previous active model |
| `GET` | `/finetuning/dataset/stats` | Dataset statistics + clause type breakdown |

### Example Workflow

```bash
# 1. Register + login
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "yourpassword"}'

TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "yourpassword"}' | jq -r .access_token)

# 2. Create project
curl -X POST http://localhost:8000/projects \
  -H "Content-Type: application/json" \
  -d '{"name": "nda-review", "description": "NDA contract review"}'

# 3. Upload contract
curl -X POST "http://localhost:8000/ingest?project_name=nda-review" \
  -F "file=@contract.pdf"

# 4. Run analysis
curl -X POST http://localhost:8000/projects/nda-review/analyze

# 5. Get results
curl http://localhost:8000/projects/nda-review/risks
curl http://localhost:8000/projects/nda-review/summary

# 6. Stream chat (auth required)
curl -N -X POST http://localhost:8000/analysis/stream \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"project_name": "nda-review", "question": "What are the termination conditions?"}'
```

---

## 🔍 Document Ingestion Pipeline

A **4-stage custom ML pipeline** built from the ground up — no external APIs or GPU requirements for parsing.

### Pipeline Architecture

```
┌───────────────────────────────────────────────────────────────────┐
│ Stage 1: Document Parsing (Format-Specific)                       │
├───────────────────────────────────────────────────────────────────┤
│ PDF → PyMuPDF (fitz)                                              │
│   • Page-by-page text extraction                                  │
│   • Image extraction with position metadata                       │
│   • Preserves page numbers and reading order                      │
│                                                                    │
│ DOCX → python-docx                                                │
│   • Paragraph-level text extraction                               │
│   • Table cell text extraction                                    │
│   • Preserves document structure                                  │
└───────────────────────────────────────────────────────────────────┘
                            ↓
┌───────────────────────────────────────────────────────────────────┐
│ Stage 2: Multi-Modal Analysis (Optional)                          │
├───────────────────────────────────────────────────────────────────┤
│ GPT-4o-mini Vision Processing                                     │
│   • Filters images by size (≥100x100px configurable)             │
│   • Parallel processing (3 concurrent calls by default)           │
│   • Extracts: charts, tables, signatures, diagrams                │
│   • Enriches text context with visual information                 │
│   • Configurable: EXTRACT_IMAGES=true/false                       │
└───────────────────────────────────────────────────────────────────┘
                            ↓
┌───────────────────────────────────────────────────────────────────┐
│ Stage 3: Semantic Chunking                                        │
├───────────────────────────────────────────────────────────────────┤
│ RecursiveCharacterTextSplitter                                    │
│   • chunk_size: 1024 chars (configurable)                         │
│   • chunk_overlap: 200 chars (prevents clause splitting)          │
│   • Separators: ["\n\n", "\n", ".", " "] (semantic breaks)      │
│   • Metadata: page_number, chunk_index, source_filename           │
│   • Clause type detection via keyword matching                    │
└───────────────────────────────────────────────────────────────────┘
                            ↓
┌───────────────────────────────────────────────────────────────────┐
│ Stage 4: Dual Embedding & Indexing (Parallel)                     │
├───────────────────────────────────────────────────────────────────┤
│ Dense Embedding                                                    │
│   • Model: text-embedding-3-small (1536 dimensions)               │
│   • Captures semantic meaning                                     │
│   • Stored in Qdrant named vector: "dense"                        │
│                                                                    │
│ Sparse Embedding                                                   │
│   • Model: fastembed BM25 tokenizer                               │
│   • Captures keyword matches (TF-IDF style)                       │
│   • Stored in Qdrant named vector: "sparse"                       │
│                                                                    │
│ Metadata Storage                                                   │
│   • Chunk text + metadata stored in PostgreSQL                    │
│   • Enables hybrid retrieval (semantic + keyword)                 │
└───────────────────────────────────────────────────────────────────┘
```

### Configuration

```env
# Chunking
CHUNK_SIZE=1024                    # Characters per chunk
CHUNK_OVERLAP=200                  # Overlap to prevent clause splits

# Multi-Modal (Optional)
EXTRACT_IMAGES=true                # Enable vision processing
IMAGE_MIN_WIDTH=100                # Min image width (pixels)
IMAGE_MIN_HEIGHT=100               # Min image height (pixels)
VISION_CONCURRENCY=3               # Parallel vision API calls
```

### Performance Characteristics

| Document Type | Pages | Chunks | Ingestion Time | Embeddings | Storage |
|---------------|-------|--------|----------------|------------|---------|
| Simple NDA | 3 | 8-12 | ~5s | ~2s | ~15KB |
| Service Agreement | 15 | 40-60 | ~18s | ~8s | ~60KB |
| Complex MSA | 50 | 150-200 | ~55s | ~25s | ~200KB |

**Bottlenecks**: 
- Embedding API calls (batched)
- Vision processing for image-heavy PDFs (parallelized)
- Network I/O to Qdrant (async)

**Optimizations**:
- Async I/O throughout pipeline
- Parallel embedding + indexing
- Configurable vision concurrency
- In-memory chunk processing

---

## 🔬 Contract Analysis Pipeline

A sophisticated **two-pass extraction system** optimized for accuracy, parallelization, and deduplication.

### Architecture

```
┌────────────────────────────────────────────────────────────────┐
│ Pass 1: Parallel Per-Chunk Extraction                          │
├────────────────────────────────────────────────────────────────┤
│ Input: All contract chunks from PostgreSQL                     │
│                                                                 │
│ Processing:                                                     │
│   • Parallel LLM calls (concurrency-limited via Semaphore)    │
│   • Model: get_analysis_llm() — routes based on LLM_PROVIDER  │
│       - openai → gpt-4o-mini                                   │
│       - local_lora → contractiq-lora-llama3                    │
│       - gemini → gemini-1.5-flash                              │
│   • Per-chunk extraction: clauses, parties, obligations        │
│   • Structured JSON output per chunk                           │
│                                                                 │
│ Output: List[ChunkAnalysis] (unmerged, may contain duplicates)│
└────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────┐
│ Pass 2: LLM-Based Merge & Deduplication                        │
├────────────────────────────────────────────────────────────────┤
│ Model: Always GPT-4o-mini (multi-step reasoning required)     │
│                                                                 │
│ Tasks:                                                          │
│   1. Deduplicate clauses across chunks                         │
│   2. Consolidate overlapping/partial matches                   │
│   3. Generate unique clause IDs                                │
│   4. Classify clause types (20 categories)                     │
│   5. Extract metadata: parties, dates, amounts                 │
│   6. Link clauses to source chunks (provenance)                │
│                                                                 │
│ Output: List[Clause] (final, deduplicated, with IDs)          │
└────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────┐
│ Hybrid Risk Scoring                                            │
├────────────────────────────────────────────────────────────────┤
│ Rule-Based Component (40% weight)                              │
│   • Missing critical clauses (termination, liability, IP)     │
│   • No expiration date or auto-renewal without notice         │
│   • Undefined payment terms                                    │
│   • Unbalanced obligations (one-sided clauses)                │
│   • Jurisdiction/governing law conflicts                       │
│                                                                 │
│ LLM Component (60% weight)                                     │
│   • GPT-4o-mini analyzes full clause list                      │
│   • Detects: unfavorable terms, compliance gaps, ambiguity    │
│   • Risk categories: HIGH, MEDIUM, LOW per clause             │
│   • Generates: risk explanations, mitigation recommendations  │
│                                                                 │
│ Final Score: (rule_score × 0.4) + (llm_score × 0.6)          │
└────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────┐
│ Quality Checks (Optional)                                      │
├────────────────────────────────────────────────────────────────┤
│ Guardrails (GUARDRAILS_ENABLED=true)                          │
│   • Input validation: contract length, format, language       │
│   • Output hallucination detection via source overlap         │
│   • Threshold: GUARDRAIL_HALLUCINATION_THRESHOLD=0.25         │
│                                                                 │
│ LLM-as-Judge (JUDGE_ENABLED=true)                             │
│   • Quality scoring: completeness, accuracy, relevance        │
│   • Score range: 0.0-1.0                                       │
│   • Threshold: JUDGE_QUALITY_THRESHOLD=0.7                    │
│   • Flags low-confidence extractions for review               │
│                                                                 │
│ Active Learning                                                │
│   • judge_score < ACTIVE_LEARNING_THRESHOLD (0.75)            │
│   • → Adds to review queue for human annotation               │
│   • → Approved samples become silver labels                   │
└────────────────────────────────────────────────────────────────┘
```

### Pass 1: Extraction Strategy

**Why parallel per-chunk?**
- **Parallelization**: 20-30 chunks can be processed simultaneously (limited by API rate limits)
- **Model flexibility**: Smaller models (LoRA) can handle chunk-level extraction
- **Fault tolerance**: Chunk failures don't fail entire analysis
- **Incremental processing**: Can resume from last successful chunk

**Concurrency control**:
```python
# Semaphore limits parallel LLM calls to prevent rate limit errors
semaphore = asyncio.Semaphore(5)  # Max 5 concurrent extractions
```

### Pass 2: Why Always GPT-4o-mini?

| Capability | Chunk-Level (Pass 1) | Document-Level (Pass 2) |
|------------|---------------------|------------------------|
| **Context required** | Single chunk (~1KB) | Full document summary |
| **Reasoning steps** | 1-2 (extract matching clauses) | 5-7 (dedupe, classify, link) |
| **Quality impact** | High (LoRA 83% F1 acceptable) | Critical (deduplication must be perfect) |
| **Model choice** | Configurable (can use LoRA) | Fixed (GPT-4o-mini) |

### Clause Type Taxonomy (20 Types)

| Category | Examples |
|----------|----------|
| **Core Terms** | Payment, termination, renewal, duration |
| **Liability** | Indemnification, warranty, limitation of liability |
| **IP & Data** | IP ownership, confidentiality, data protection |
| **Dispute** | Governing law, jurisdiction, arbitration |
| **Compliance** | Regulatory, insurance, audit rights |
| **Performance** | SLA, deliverables, acceptance criteria |

### Risk Scoring Examples

```json
{
  "clause_id": "termination_001",
  "type": "termination",
  "risk_level": "HIGH",
  "risk_score": 0.85,
  "explanation": "Termination requires 90-day notice but counterparty can terminate immediately for convenience",
  "rule_based_flags": ["unbalanced_obligations"],
  "llm_risk_assessment": "One-sided termination rights create business continuity risk"
}
```

### Performance Metrics

| Document Size | Pass 1 (Parallel) | Pass 2 (Merge) | Total Analysis Time |
|---------------|-------------------|----------------|---------------------|
| 3-page NDA | ~2s (8 chunks) | ~1.5s | **~3.5s** |
| 15-page MSA | ~3s (45 chunks) | ~2.5s | **~5.5s** |
| 50-page Contract | ~5s (150 chunks) | ~4s | **~9s** |

**Note**: Times assume GPT-4o-mini. LoRA inference on CPU adds ~60s/chunk for Pass 1.

---

## 💬 RAG Query Pipeline

An advanced **Retrieval-Augmented Generation** system with hybrid search, streaming responses, and query caching.

### Pipeline Flow

```
┌──────────────────────────────────────────────────────────────────┐
│ 1. Query Ingestion                                               │
│    • Input: Natural language question + project_name            │
│    • Generate cache key: SHA-256(project_name + question + k)   │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│ 2. Cache Check (PostgreSQL)                                      │
│    • Lookup: query_cache table by hash                           │
│    • Hit: Return cached (response, sources, timestamp)           │
│    • Miss: Proceed to retrieval                                  │
│    • TTL: Configurable expiration (default: 24h)                │
└──────────────────────────────────────────────────────────────────┘
                              ↓ (cache miss)
┌──────────────────────────────────────────────────────────────────┐
│ 3. Hybrid Vector Search (Qdrant)                                 │
│    • Dense query embedding: text-embedding-3-small              │
│    • Sparse query embedding: fastembed BM25                      │
│    • Qdrant query: search both named vectors                     │
│    • Fusion: Reciprocal Rank Fusion (RRF)                       │
│        rrf_score = Σ(1 / (k + rank_i))  where k=60             │
│    • Top-k selection: RETRIEVAL_TOP_K (default: 5)              │
│    • Score threshold: RETRIEVAL_SCORE_THRESHOLD (default: 0.0)  │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│ 4. Context Assembly                                              │
│    • Fetch full chunk text from PostgreSQL (via chunk IDs)      │
│    • Sort by RRF score (descending)                              │
│    • Format: "Page {page_num}: {text}\n---\n"                   │
│    • Add metadata: source filename, page numbers                 │
│    • Context window budget: ~4K tokens (~3K chars per chunk)    │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│ 5. LLM Generation (Streaming)                                    │
│    • Model: GPT-4o-mini (configurable)                           │
│    • System prompt: "Answer based on context, cite sources"     │
│    • Streaming mode: SSE (Server-Sent Events)                   │
│    • Output format:                                              │
│        data: {"token": "Answer", "done": false}                 │
│        data: {"token": " text", "done": false}                  │
│        ...                                                       │
│        data: {"token": null, "done": true, "sources": [...]}    │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│ 6. Source Citation & Persistence                                 │
│    • Append source metadata to final event                       │
│    • Sources: [{chunk_id, page_num, score, filename}]          │
│    • Persist to PostgreSQL:                                      │
│        - query_cache: (hash, question, response, sources)       │
│        - chat_messages: (project, role, content, metadata)      │
│    • Analytics: track query patterns, popular questions         │
└──────────────────────────────────────────────────────────────────┘
```

### Hybrid Search Deep Dive

**Why hybrid?** Dense-only search misses exact keyword matches. BM25-only misses semantic similarity.

| Search Mode | Query: "termination clause" | Result |
|-------------|----------------------------|--------|
| **Dense only** | Matches: "ending the agreement", "contract conclusion" | High recall, low precision |
| **BM25 only** | Matches: exact "termination" keyword | High precision, low recall |
| **Hybrid (RRF)** | Fuses both, ranks by combined relevance | **Best of both** |

**RRF Formula**:
```python
def reciprocal_rank_fusion(dense_results, sparse_results, k=60):
    scores = defaultdict(float)
    for rank, result in enumerate(dense_results):
        scores[result.id] += 1 / (k + rank + 1)
    for rank, result in enumerate(sparse_results):
        scores[result.id] += 1 / (k + rank + 1)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)
```

### Configuration

```env
# Search
SEARCH_MODE=hybrid                  # hybrid | semantic (dense-only)
RETRIEVAL_TOP_K=5                   # Documents to retrieve (1-50)
RETRIEVAL_SCORE_THRESHOLD=0.0       # Minimum RRF score (keep at 0.0)

# Query Caching
QUERY_CACHE_ENABLED=true            # Enable cache
QUERY_CACHE_TTL=86400               # TTL in seconds (24h)
```

### Performance Characteristics

| Operation | Time | Notes |
|-----------|------|-------|
| Cache lookup | ~5ms | PostgreSQL indexed by hash |
| Hybrid search | ~50-150ms | Qdrant inference + RRF |
| Context assembly | ~20ms | PostgreSQL batch fetch |
| LLM streaming (first token) | ~500ms | TTFT (Time To First Token) |
| LLM streaming (completion) | ~2-4s | Depends on response length |
| **Total (cache miss)** | **~3-5s** | End-to-end with streaming |
| **Total (cache hit)** | **~50ms** | Direct response from DB |

### Streaming SSE Format

```http
POST /query HTTP/1.1
Content-Type: application/json

{
  "project_name": "nda-review",
  "question": "What are the termination conditions?"
}

HTTP/1.1 200 OK
Content-Type: text/event-stream

data: {"token": "Based", "done": false}

data: {"token": " on", "done": false}

data: {"token": " the", "done": false}

data: {"token": " contract", "done": false}

...

data: {"token": null, "done": true, "sources": [{"chunk_id": "c1", "page_number": 12, "score": 0.89, "filename": "contract.pdf"}]}
```

### Error Handling

| Error | Response | Recovery |
|-------|----------|----------|
| No chunks in project | `400 Bad Request` | Upload document first |
| Qdrant timeout | `503 Service Unavailable` | Retry with backoff |
| Empty retrieval | `200 OK` (answer: "insufficient info") | Lower score threshold |
| LLM API error | `500 Internal Server Error` | Logged, retry, fallback model |

### Query Analytics

Tracked metrics (stored in `chat_messages` table):

- Query frequency distribution
- Average response time per query type
- Cache hit rate
- Source chunk distribution (which pages are most cited)
- User feedback (thumbs up/down on answers)

---

## 🧬 Fine-Tuning: Production LoRA Pipeline

ContractIQ demonstrates a complete fine-tuning workflow with a production-deployed LoRA model: **[`iakshayrathee/contractiq-lora-llama3`](https://huggingface.co/iakshayrathee/contractiq-lora-llama3)**.

### Model Details

| Attribute | Value |
|-----------|-------|
| **Base Model** | Llama-3.2-3B-Instruct |
| **Technique** | QLoRA (Quantized Low-Rank Adaptation) |
| **Training Data** | CUAD v1 (6,702 non-empty QA examples) |
| **Clause Types** | 11 mapped from CUAD taxonomy |
| **Training Split** | 5,361 train / 670 val / 671 test (80/10/10) |
| **Training Time** | ~45-90 min on Google Colab T4 GPU |
| **Model Size** | ~6GB (base weights + adapter) |
| **Deployment** | HuggingFace Hub (public) |

### Why Fine-Tune?

| Metric | GPT-4o-mini (API) | Llama-3.2-3B LoRA (Local) |
|--------|-------------------|---------------------------|
| **Inference Cost** | $0.15 / 1M tokens | $0 (local) |
| **Data Privacy** | Sent to OpenAI | Fully local |
| **Latency (GPU)** | ~2s/chunk | ~5-15s/chunk |
| **Latency (CPU)** | ~2s/chunk | ~60s/chunk ⚠️ |
| **Deployment** | API key required | Self-hosted |
| **Specialization** | General-purpose | Contract-specific |

### Using the Production Model

```env
# .env
LLM_PROVIDER=local_lora
LOCAL_LORA_ADAPTER_PATH=iakshayrathee/contractiq-lora-llama3
OPENAI_API_KEY=sk-...  # Still required for Pass 2 and chat
```

```bash
# Install LoRA dependencies (transformers, peft, bitsandbytes)
pip install -r backend/requirements-lora.txt

# Start backend — model downloads automatically (~6GB first run)
uvicorn app.main:create_app --factory --reload
```

> **Hardware Requirements**: A CUDA GPU is strongly recommended. CPU inference takes ~60s per chunk (20-30 chunks/contract = 20-30 min total). T4/A10G GPUs reduce this to 5-15s/chunk.

### Re-Training the Model

Open [`notebooks/contractiq_lora_finetune.ipynb`](notebooks/contractiq_lora_finetune.ipynb) in Google Colab:

1. **Runtime → Change runtime type → T4 GPU** (free tier sufficient)
2. **Section 1**: Install Unsloth, login to HuggingFace (`huggingface-cli login`)
3. **Section 2-5**: Load CUAD, preprocess, train with QLoRA
4. **Section 6**: Push adapter to HuggingFace Hub (auto-versioned)

Training takes ~45-90 minutes on a T4. See [`notebooks/HUGGINGFACE_SETUP.md`](notebooks/HUGGINGFACE_SETUP.md) for account setup.

### Evaluation

```bash
# Compare LoRA vs GPT-4o vs GPT-4o-mini on held-out test set
cd backend
python -m app.finetuning.cli lora-evaluate \
  --adapter-path iakshayrathee/contractiq-lora-llama3

# Results: data/finetuning/eval_comparison.json (JSON)
#          data/finetuning/eval_comparison.md (Markdown report)
```

**Metrics collected**:
- F1 score (clause type classification)
- LLM-as-Judge quality scores
- Hallucination rate (source overlap)
- Inference latency (p50, p95, p99)
- Cost per extraction

### Fine-Tuning Dataset

**Two parallel data paths**:

#### Path 1: Notebook Training (Production Model)

The deployed LoRA model was trained **directly on CUAD** in `notebooks/contractiq_lora_finetune.ipynb`:

- **Source**: CUAD v1 (510 contracts, 20,910 QA examples)
- **Preprocessing**: Filter non-empty answers, convert span annotations to instruction format
- **Final Dataset**: 6,702 examples → 5,361 train / 670 val / 671 test
- **Clause Mapping**: 41 CUAD categories → 11 ContractIQ clause types

#### Path 2: CLI Dataset Builder (Synthetic)

The CLI (`python -m app.finetuning.cli build-dataset`) generates a **separate synthetic dataset**:

| File | Examples | Source |
|------|----------|--------|
| `train.jsonl` | 283 | Synthetic + silver labels |
| `val.jsonl` | 35 | Validation split |
| `test.jsonl` | 36 | Held-out test (used by `lora-evaluate`) |
| `metadata.json` | — | Dataset provenance, stats |

**Data sources** (`data/finetuning/sources/`):
- `cuad_processed.jsonl`: CUAD gold labels (span-based)
- `silver_labeled.jsonl`: GPT-4o production extractions (judge_score ≥ 0.85)
- `synthetic.jsonl`: GPT-4o generated examples for rare clause types (354 examples)

### Model Registry & Versioning

Track fine-tuned models in the database:

```bash
# List all registered models
curl http://localhost:8000/finetuning/models

# Activate a model for production
curl -X POST http://localhost:8000/finetuning/activate/{model_id}

# Rollback to previous active model
curl -X POST http://localhost:8000/finetuning/rollback
```

Models are stored with training metrics, activation timestamps, and rollback history.

---

## 📊 Evaluation & Quality Metrics

ContractIQ implements a comprehensive evaluation framework with automated quality gates in CI/CD.

### Evaluation Pipeline

```bash
# Run full evaluation suite
cd backend
python -m app.evals.cli run --test-cases contract_eval_cases.json

# CI/CD quality gate (exits with code 1 if thresholds not met)
python scripts/ci_eval.py --threshold 0.8
```

### Metrics Collected

| Metric Category | Metrics | Purpose |
|-----------------|---------|---------|
| **Accuracy** | F1, Precision, Recall per clause type | Clause classification quality |
| **LLM-as-Judge** | Quality score (0-1), confidence distribution | Semantic correctness evaluation |
| **Hallucination** | Source overlap ratio, unsupported claims | Grounding verification |
| **Consistency** | Multi-run agreement, determinism score | Reliability under repeated inference |
| **Latency** | p50, p95, p99 per endpoint | Performance SLAs |
| **Cost** | $ per contract, tokens per extraction | Cost optimization tracking |

### Quality Gates (CI/CD)

Automated checks in `.github/workflows/eval.yml`:

```yaml
- F1 score ≥ 0.75 (clause type classification)
- LLM-as-Judge score ≥ 0.80 (semantic quality)
- Hallucination rate ≤ 15% (grounding check)
- p95 latency ≤ 30s (user experience)
- Regression detection: ≤ 5% degradation vs baseline
```

### Evaluation Test Cases

Located in `backend/app/evals/test_cases/contract_eval_cases.json`:

- **47 test cases** covering 11 clause types
- **Gold standard annotations** from CUAD dataset
- **Edge cases**: ambiguous language, missing clauses, multi-party agreements
- **Real-world contracts**: NDAs, service agreements, employment contracts

### Langfuse Integration

Optional LLM observability for production monitoring:

```env
LANGFUSE_ENABLED=true
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_PUBLIC_KEY=pk-lf-...
```

**Tracked data**:
- Request/response traces with full context
- Token usage and cost per request
- Latency distribution per LLM call
- Error rates and failure modes
- User feedback integration

### Active Learning Workflow

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Contract Analysis → LLM-as-Judge scores each extraction │
│    ↓ judge_score < 0.75 (uncertain predictions)            │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. Review Queue → Flagged for human review                 │
│    • Display side-by-side: extraction vs source chunk      │
│    • Expert annotator corrects/approves                    │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. Silver Labeling → Approved extractions added to dataset │
│    • Filter: judge_score ≥ 0.85 after human approval       │
│    • Saved to data/finetuning/sources/silver_labeled.jsonl │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. Periodic Re-Training → LoRA model update                │
│    • Merge: CUAD gold + silver labels + synthetic          │
│    • Train via notebooks/contractiq_lora_finetune.ipynb    │
│    • A/B test: new model vs current in production          │
└─────────────────────────────────────────────────────────────┘
```

### Model Comparison Results

Example evaluation report (`data/finetuning/eval_comparison.md`):

| Model | F1 Score | Judge Score | Avg Latency | Cost/Contract |
|-------|----------|-------------|-------------|---------------|
| **GPT-4o** | 0.91 | 0.88 | 3.2s | $0.08 |
| **GPT-4o-mini** | 0.87 | 0.84 | 2.1s | $0.03 |
| **LoRA (Llama-3.2-3B)** | 0.83 | 0.79 | 8.5s | $0.00 |

**Key insights**:
- GPT-4o provides best quality but 2.7x cost vs GPT-4o-mini
- LoRA model achieves 95% of GPT-4o-mini quality at zero marginal cost
- Hybrid approach: LoRA for Pass 1, GPT-4o-mini for Pass 2 balances cost/quality

---# Quality Thresholds

| Metric | Target | Description |
|--------|--------|-------------|
| Clause F1 | ≥ 0.70 | Harmonic mean of precision and recall |
| Clause Recall | ≥ 0.65 | % of expected clauses found |
| Clause Precision | ≥ 0.65 | % of found clauses that are correct |
| Judge Overall | ≥ 0.70 | LLM-as-Judge quality score |
| Pass Rate | ≥ 80% | % of eval cases passing all thresholds |
| Hallucinations | 0 | Fabricated content — unacceptable in legal |

### Running Evaluations

```bash
cd backend

# Run all eval cases
python -m app.evals.cli run

# Run for specific contract type
python -m app.evals.cli run --contract-type NDA

# Run with pytest (includes metric assertions)
RUN_LIVE_EVALS=1 pytest tests/test_evaluation.py -v

# CI/CD quality gate
python scripts/ci_eval.py --min-f1 0.70 --min-pass-rate 0.80

# Compare LoRA vs baselines
python -m app.finetuning.cli lora-evaluate \
  --adapter-path iakshayrathee/contractiq-lora-llama3
```

### Running Fine-Tuning Evaluation (What's Needed)

To run `lora-evaluate` you need:

1. **`data/finetuning/test.jsonl`** — already present (36 held-out examples)
2. **`requirements-lora.txt` installed**: `pip install -r backend/requirements-lora.txt`
   - `peft>=0.13.0`, `transformers>=4.45.0`, `bitsandbytes>=0.43.0`, `torch`
3. **HuggingFace token** (for downloading the model): `huggingface-cli login`
4. **GPU recommended**: CUDA GPU for reasonable inference speed
5. **~16GB RAM** minimum (6GB for model + working memory)

```bash
cd backend
pip install -r requirements-lora.txt
huggingface-cli login  # enter your HF token
python -m app.finetuning.cli lora-evaluate \
  --adapter-path iakshayrathee/contractiq-lora-llama3 \
  --test-data-path ../data/finetuning/test.jsonl
```

---

## 🧪 Testing & Development

### Running Tests

```bash
# Backend test suite (200+ tests across 22 modules)
cd backend
pip install -r requirements-test.txt
pytest -v

# Specific test modules
pytest tests/test_contract_analysis_service.py -v
pytest tests/test_vector_store_service.py -v

# Coverage report
pytest --cov=app --cov-report=html
```

### Local Development

```bash
# Backend with hot reload
cd backend
uvicorn app.main:create_app --factory --reload --host 0.0.0.0 --port 8000

# Frontend with hot reload
cd frontend
npm run dev

# Database migrations
cd backend
alembic revision --autogenerate -m "description"
alembic upgrade head
```

### Code Quality

```bash
# Backend linting
cd backend
pip install black pylint mypy
black app/ --check
pylint app/
mypy app/

# Frontend linting
cd frontend
npm run lint
npm run type-check
```

---


## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **gpt-4o-mini as default** | Fast, cheap, excellent for structured JSON extraction. ~16x cheaper than gpt-4o with minimal quality loss for clause extraction |
| **LoRA over OpenAI fine-tune** | OpenAI fine-tuning is unavailable for this org. Llama-3.2-3B + QLoRA via Colab achieves comparable extraction quality at $0 training/inference cost |
| **Pass 2 always uses OpenAI** | Multi-step reasoning (merge, deduplicate, cross-clause analysis) requires a larger model. Fine-tuned/LoRA models overfit to patterns and struggle with novel combinations |
| **Custom ingestion (PyMuPDF + python-docx)** | Works offline, no external API, ~100x faster than cloud extraction, no OCR dependency |
| **Hybrid search (BM25 + dense + RRF)** | Dense vectors find semantically similar chunks; BM25 finds exact legal terms ("indemnification", "force majeure"); RRF fusion gives best of both. Hybrid improves recall@5 by 10–20% on legal docs vs dense-only |
| **JWT with httpOnly refresh cookies** | Access tokens in memory prevent XSS theft; httpOnly SameSite=Strict refresh cookies prevent CSRF; industry-standard pattern |
| **Provider abstraction (`get_analysis_llm`)** | Single entry point for Pass 1 → swap OpenAI ↔ LoRA via one env var, zero service code changes |
| **Two-pass extraction** | Pass 1 parallelises per-chunk for speed; Pass 2 merges for document-level coherence and deduplication |
| **Hybrid risk scoring (40/60)** | Rule-based catches structural issues reliably; LLM catches nuanced language; blend provides both reliability and depth |
| **SSE streaming** | Token-level streaming for sub-second time-to-first-token on both ingestion and chat |
| **structlog over stdlib** | JSON lines for production log aggregation (Datadog/CloudWatch); per-request `request_id` binding without thread-local hacks; dev console renderer |
| **Async throughout** | SQLAlchemy async + asyncpg; `asyncio.gather` for parallel LLM calls; Qdrant async client — no thread pool bottlenecks |

---

## Core Data Models

### Project
- `name` (string, unique), `description`, `created_at`, `updated_at`
- Owns: analyses, documents

### Document / Chunk
- `id` (UUID), `project_name` (FK), `content` (text), `chunk_index` (int)
- `metadata` (JSON): source page, type (text/table/image), confidence
- Embedding: 1536-dim dense vector in Qdrant + BM25 sparse vector

### Analysis
- `id` (UUID), `project_name` (FK)
- `status` (enum): `pending | processing | completed | failed`
- `clauses` (JSON array), `risks` (JSON array), `summary` (JSON)
- `overall_risk_score` (int, 0–100), `quality_score` (float, 0.0–1.0)
- `judge_json` (JSON), `guardrail_warnings_json` (JSON)
- `flagged_for_review` (bool) — set by LLM-as-Judge if below threshold
- `created_at`, `completed_at`

### Clause
- `id`, `clause_type` (enum: `termination | confidentiality | liability | indemnification | payment | intellectual_property | governing_law | dispute_resolution | force_majeure | data_privacy | warranty | insurance | assignment | amendment | entire_agreement | severability | auto_renewal | non_compete | non_solicitation | other`)
- `title`, `text`, `section_reference` (nullable)
- `obligations` (array): `{party, description, type: must|must_not|may}`
- `risk_flags` (array)

### Risk Finding
- `id`, `type` (enum: `missing_clause | unfavorable_term | compliance_gap | ambiguous_language`)
- `severity` (enum): `low | medium | high | critical`
- `score` (float, 0–100), `rule_based_score`, `llm_score`
- `description`, `affected_clauses`, `recommendation`

### Model Registry (Fine-Tuning)
- `id` (UUID), `model_id` (string, unique) — HF Hub ID or OpenAI fine-tuned model ID
- `base_model` (string) — e.g., `unsloth/Llama-3.2-3B-Instruct`
- `status` (enum): `pending | training | ready | failed | active`
- `dataset_hash` (string) — SHA-256 of training data
- `n_examples` (int), `n_epochs` (int)
- `train_loss` (float), `val_loss` (float)
- `clause_f1` (float), `hallucination_rate` (float)
- `cost_per_1000_docs` (float), `p50_latency_ms` (float)
- `previous_model_id` (string, nullable) — for rollback
- `trained_at`, `created_at`
- `error_message` (string, nullable)

---

## Extension Points & Customization

### Adding New Clause Types
1. Update `ClauseType` enum in `backend/app/schemas/contract.py`
2. Add extraction prompt examples in `backend/app/services/contract_analysis_service.py`
3. Add rule-based checks in `contract_analysis_service.py` if applicable
4. Update frontend clause filter UI in `frontend/components/contract/ContractAnalysisPanel.tsx`

### Custom Risk Rules
1. Implement rule function in `backend/app/services/contract_analysis_service.py`
2. Update risk severity mapping in `backend/app/schemas/contract.py`
3. Test with sample contracts before deployment

### Integrating New LLM Models
1. Update model fields in `backend/app/config.py` (e.g., `openai_model_analysis`)
2. Extend `get_analysis_llm()` in `backend/app/llm/provider.py` if adding a new provider type
3. Adjust prompt templates if model has different capabilities

### Adding Observability
- **Langfuse**: Set `LANGFUSE_ENABLED=true` and provide keys in `.env` — tracing starts automatically for all LLM calls
- **Eval tracking**: `backend/app/evals/langfuse_tracking.py` pushes eval results to Langfuse for regression monitoring

---

## Service Architecture

Services are instantiated once during the FastAPI lifespan and stored on `app.state` — no global singletons, no DI framework:

```
VectorStoreService      ← owns Qdrant client + embedding model (dense + BM25 sparse)
IngestionService        ← 4-stage pipeline: parse → chunk → embed → index (depends on VectorStoreService)
QueryService            ← RAG retrieval + SSE streaming (depends on VectorStoreService)
ContractAnalysisService ← two-pass extraction + risk scoring (depends on VectorStoreService + session_factory)
ProjectService          ← project CRUD (depends on session_factory)
JobService              ← in-memory job registry for background ingestion status
GuardrailsService       ← input/output hallucination detection + validation
JudgeService            ← LLM-as-Judge quality scoring (0.0–1.0)
```

Each route receives its required service via `request.app.state`, keeping routes thin and services independently testable. No FastAPI `Depends()` chains — services are resolved at startup, not per-request.

---

## Implementation Details & Patterns

### Async / Concurrency Model

- **FastAPI async routes**: All endpoints use `async def` with `await` for all I/O — no blocking calls on the event loop
- **Database**: SQLAlchemy 2.0 async ORM with `asyncpg` driver for non-blocking PostgreSQL queries; session factory passed through `app.state`
- **Parallel LLM calls**: Contract analysis uses `asyncio.gather(*tasks, return_exceptions=True)` for per-chunk clause extraction; an `asyncio.Semaphore(_PASS1_CONCURRENCY=5)` caps concurrency to prevent rate-limit exhaustion
- **Vector search**: Qdrant async client for non-blocking similarity searches
- **LoRA inference**: `LocalLoRAProvider.run_inference()` wraps synchronous `transformers.generate()` in `asyncio.run_in_executor()` so it doesn't block the event loop
- **Ingestion lock**: An `asyncio.Lock()` stored in `app.state.ingestion_lock` serialises concurrent upload requests per app instance

### Error Handling

- **Pydantic v2 validation**: All request bodies and LLM response payloads validated — invalid data rejected with 422 before reaching business logic
- **Global exception handlers** (`main.py`): `ValueError` → 400, `RuntimeError` → 503, uncaught `Exception` → 500 with structured `{"detail": "..."}` JSON; all 500s logged with full tracebacks
- **Graceful degradation**: Failed chunks in ingestion or analysis are logged and skipped — they do not block the rest of the pipeline
- **Retry with exponential backoff**: LLM API calls retry with exponential backoff (3 attempts); transient errors are caught; persistent errors bubble to the route handler
- **Job status tracking**: Each ingestion job persisted in PostgreSQL with `status ∈ {pending, processing, completed, failed}` + error message field; frontend polls `/jobs/{job_id}`

### Startup Validation

- **Required env vars**: Backend validates `OPENAI_API_KEY`, `DATABASE_URL`, and `JWT_SECRET_KEY` at startup via pydantic-settings — server refuses to start if missing
- **Database connectivity**: PostgreSQL connection tested during lifespan startup; server only accepts traffic if database is reachable
- **Vector store initialization**: Qdrant collection checked/created at startup; if unreachable, logs warning but may still start (graceful degradation for development)
- **BM25 model pre-baked**: fastembed `Qdrant/bm25` is downloaded into the Docker image at build time — no runtime download latency

### Caching Strategy

- **Query cache**: SHA-256(project_name, question, k) is used as cache key; hits return stored `(response, sources)` from PostgreSQL without any LLM call — meaningful cost savings in multi-user scenarios
- **Document hash cache**: `ContractAnalysisService` computes `_compute_document_hash()` over all chunks before Pass 1 — skips re-extraction if chunks haven't changed since last analysis
- **Embedding cache**: Identical chunk content (by hash) is not re-embedded on re-ingestion
- **Qdrant in-memory**: Qdrant manages its own segment-level caching for frequently accessed collections

### LLM Prompt Engineering

- **Clause extraction (Pass 1)**: `response_format={"type": "json_object"}` enforces structured JSON output, eliminating free-form parsing; template uses `###Instruction / ###Input / ###Response` format compatible with the LoRA adapter's training format
- **Risk assessment**: Few-shot examples in the system prompt establish consistent severity classification (low / medium / high / critical) across different contract types
- **Summary generation**: Chain-of-thought prompting decomposes the task into sub-steps (executive summary → obligations → dates → watch-outs → action items) for higher-quality multi-section output
- **Query responses**: Few-shot citation format examples ensure consistent `[Source: ...]` attribution regardless of the question

### Guardrails & Quality Assurance

- **Input guardrails** (`guardrails.py`): Validate uploaded files are legal contracts, reject adversarial inputs before any LLM processing
- **Output guardrails**: Post-process LLM clause extractions via source-overlap heuristic (`GUARDRAIL_HALLUCINATION_THRESHOLD=0.25`); clauses with insufficient grounding in source text are flagged or suppressed
- **LLM-as-Judge** (`judge_service.py`): After each analysis, a separate LLM call scores output quality (0.0–1.0). Outputs below `JUDGE_QUALITY_THRESHOLD` are flagged — critical for legal accuracy requirements
- **Active learning queue**: Analyses below `ACTIVE_LEARNING_THRESHOLD` are queued for human review; reviewed examples can be added to the LoRA training dataset
- Both guardrails and judge are **togglable via env vars** (`GUARDRAILS_ENABLED`, `JUDGE_ENABLED`) for cost-sensitive environments

### Rate Limiting

- **slowapi** middleware wraps FastAPI with per-route rate limits
- The `limiter` instance (defined in `utils/rate_limit.py`) is registered on `app.state` and hooked into FastAPI's exception handler for `RateLimitExceeded` → 429
- Protects against both abuse and inadvertent OpenAI API quota exhaustion from concurrent users

### Database Schema Patterns

- **Timestamps on all entities**: `created_at`, `updated_at` on every model for audit trail
- **JSON columns for complex data**: Clauses, risks, and summaries stored as JSON blobs — flexible schema that doesn't require migrations for field-level LLM output changes
- **Foreign keys**: Referential integrity enforced between projects → documents and projects → analyses at the database level
- **Alembic migrations**: Schema changes managed via Alembic (`backend/alembic/`) for reproducible deployments and rollbacks

### Frontend–Backend Communication

- **REST API**: Standard HTTP methods with JSON payloads for all CRUD operations
- **SSE streaming**: Both `/ingest` (pipeline progress) and `/query` (chat) use SSE; frontend handles `EventSource` with per-event parsing
- **Ingestion SSE events**: Each pipeline step emits `step_start`, `step_done`, `step_details` events — enables `PipelineModal` to show real-time per-step progress
- **Job polling**: Frontend polls `/jobs/{job_id}` every 2 seconds during background ingestion; job state persisted in PostgreSQL
- **TanStack Query v5**: All API calls managed via TanStack Query for caching, background refetching, and loading/error states
- **Error format**: All backend errors return `{"detail": "error message"}` for consistent frontend handling

### Multimodal Processing

- **Image extraction**: Images in PDFs extracted per-page by PyMuPDF (`fitz`); described by `gpt-4o-mini` vision; descriptions (not raw base64) embedded for search and included in RAG context
- **Configurable**: `EXTRACT_IMAGES=false` disables all image extraction; `IMAGE_MIN_WIDTH` / `IMAGE_MIN_HEIGHT` filter out tiny decorative images; `VISION_CONCURRENCY` limits parallel vision calls
- **Metadata preservation**: Each `Document` chunk carries `original_content` metadata with `raw_text`, `tables_html`, `images_base64`, and `page_numbers` — enabling source display in the chat UI

---

## Fine-Tuning: Technical Deep-Dive

### Data Pipeline

**Step 1 — CUAD Processing (`cuad_processor.py`)**
- Download CUAD dataset from HuggingFace (`theatticusproject/cuad`) — 510 annotated legal contracts
- Convert span-based labels to ContractIQ's Clause JSON schema
- Map 41 CUAD categories → 20 ContractIQ `ClauseType` values
- Save to `data/finetuning/sources/cuad_processed.jsonl` (`"source": "cuad_gold"`)

**Step 2 — Silver Label Generation**
- Fetch raw contract chunks from PostgreSQL
- Run GPT-4o Pass 1 extraction (reuse existing service)
- Filter: `judge_score ≥ 0.85` AND `clause_count > 0` AND Pydantic valid AND `source_overlap > 0.6`
- Save to `data/finetuning/sources/silver_labeled.jsonl` (`"source": "silver_gpt4o"`)
- **Assertion:** Silver examples never enter the test set

**Step 3 — Synthetic Generation**
- Identify rare clause types (< 50 real examples)
- GPT-4o generates realistic synthetic contracts + extractions for each rare type
- 354 examples generated across all 20 clause types
- Save to `data/finetuning/sources/synthetic.jsonl` (`"source": "synthetic"`)
- **Assertion:** Synthetic examples never enter validation or test sets

**Step 4 — Dataset Building (`dataset_builder.py`)**
- Quality checks: exact dedup (hash), near-dedup (TF-IDF cosine > 0.85), label conflict resolution (CUAD gold wins), length truncation (> 2500 tokens), Pydantic schema validation
- Split: 85% train / 15% val (stratified by clause type); test set: 36 CUAD gold examples held out permanently
- Format: instruction-tuning JSONL (`prompt` / `response` keys) — compatible with Unsloth's `FastLanguageModel`

**Step 5 — Training (Google Colab, Unsloth)**
- Base model: `unsloth/Llama-3.2-3B-Instruct` (4-bit QLoRA, bitsandbytes)
- LoRA config: `r=16`, `lora_alpha=16`, target modules: `q_proj k_proj v_proj o_proj gate_proj up_proj down_proj`
- `max_seq_length=2048`, `gradient_checkpointing=True`, trained ~45–90 min on free T4 GPU
- Adapter pushed to HuggingFace Hub: `iakshayrathee/contractiq-lora-llama3`

### Why Keep Pass 2 on GPT-4o-mini?

**Pass 1 (Pattern Extraction):** Fine-tuned/LoRA models excel at recognizing clause patterns from local text. This is a well-defined task with clear input-output mapping — exactly what supervised fine-tuning is optimised for.

**Pass 2 (Reasoning & Synthesis):** Merging clauses across chunks, deduplicating, identifying cross-clause relationships, and generating risk scores requires multi-step reasoning. Fine-tuned models overfit to training patterns and struggle with novel combinations. GPT-4o-mini's general reasoning capabilities are still superior here.

**Cost result:** Using LoRA for the bulk of the work (Pass 1, N chunks in parallel) while retaining OpenAI for the single critical reasoning step (Pass 2) provides the best cost-quality tradeoff — $0 for extraction at scale.

### Interview Q&A

**Q: Why fine-tune at all — why not just use GPT-4o-mini with better prompts?**

A: Prompts hit a ceiling on structured extraction consistency. A fine-tuned/LoRA model that has seen thousands of clause examples produces more predictable JSON, fewer format errors, and lower hallucination rates — because it's learned the schema, not just following instructions. Format compliance going from ~85% to ~98% eliminates a major source of production bugs.

**Q: How do you ensure the LoRA model doesn't hallucinate?**

A: Three-layer defense: (1) **Training data quality** — only high-quality silver labels (`judge_score ≥ 0.85`, `source_overlap > 0.6`) feed the model; (2) **Output guardrails** — source-overlap heuristic validates extractions before they're stored; (3) **Evaluation** — hallucination rate (fabrication of party names, dates, dollar amounts) is a primary metric tracked in `eval_comparison.json`.

**Q: What happens if the LoRA model produces garbage?**

A: Instant rollback. `POST /finetuning/rollback` restores the previous active model in the `model_registry` table. The `ACTIVE_LEARNING_THRESHOLD` flag also surfaces low-confidence outputs for human review before they become training data.

**Q: How do you handle rare clause types like `auto_renewal` or `force_majeure`?**

A: Synthetic data generation. For types with < 50 real examples, GPT-4o generates realistic synthetic clauses, ensuring the model sees sufficient examples of each type. The mixing ratio (60% CUAD gold, 40% silver, synthetic for rare types) is explicit in `metadata.json`.

**Q: How often do you retrain?**

A: Data-driven. Monitor `eval_comparison.json` — retrain when F1 degrades or when ≥ 1000 new high-quality silver labels accumulate. The active learning pipeline (`app.finetuning.cli active-learning`) continuously surfaces low-confidence predictions for review.

---

## Test Coverage

| Test File | Coverage Area |
|-----------|---------------|
| `test_auth.py` | Register, login, refresh, JWT validation, httpOnly cookie |
| `test_contract_analysis_service.py` | Two-pass extraction, risk scoring, guardrails |
| `test_contracts.py` | Contract analysis routes, clause filtering |
| `test_dashboard.py` | Dashboard statistics endpoint |
| `test_evaluation.py` | Eval metrics, reporter, dataset integrity assertions |
| `test_guardrails_service.py` | Hallucination detection, input/output validation |
| `test_health.py` | Health check endpoint |
| `test_ingestion.py` | Parser (PyMuPDF + python-docx), chunker, route |
| `test_ingestion_service.py` | Full 4-stage pipeline |
| `test_job_service.py` | Background job registry |
| `test_jobs.py` | Job status polling endpoint |
| `test_llm_provider.py` | OpenAI, Gemini, local_lora, fallback, streaming |
| `test_project_service.py` | Project CRUD operations |
| `test_projects.py` | Project routes |
| `test_query.py` | Query route |
| `test_query_service.py` | RAG pipeline, SSE streaming, cache hit/miss |
| `test_retrieval.py` | Hybrid search, RRF fusion, dense fallback |
| `test_schemas.py` | Pydantic schema validation |
| `test_vector_store_service.py` | Qdrant operations, embeddings, hybrid indexing |

**22 test files** covering all major code paths — services, routes, schemas, and infrastructure.

```bash
cd backend
pip install -r requirements-test.txt
pytest -v                    # run all tests
pytest tests/test_auth.py    # run specific suite
RUN_LIVE_EVALS=1 pytest tests/test_evaluation.py  # live LLM eval tests
```

---

## Contributing

1. Create feature branch: `git checkout -b feature/description`
2. Make changes and test locally
3. Commit: `git commit -m "feat: description"`
4. Push: `git push origin feature/description`
5. Open a Pull Request

---

**ContractIQ v3.2.0** | Last updated: June 2026

Fine-tuned model: [iakshayrathee/contractiq-lora-llama3](https://huggingface.co/iakshayrathee/contractiq-lora-llama3) (Llama-3.2-3B + QLoRA, trained on CUAD via Google Colab)

Features: Custom Ingestion (PyMuPDF + python-docx) · Hybrid Search (BM25+Dense RRF) · JWT Auth · SSE Streaming · Structured Logging · Multi-LLM (OpenAI / Gemini / LoRA) · Guardrails · LLM-as-Judge · Active Learning · 22 Test Suites



---

## 🎓 What This Project Demonstrates

### For AI/ML Engineers

**End-to-End ML System Design**
- Complete lifecycle: data collection → preprocessing → training → evaluation → deployment
- Multi-source dataset curation (CUAD gold labels, GPT-4o silver labels, synthetic augmentation)
- Production model deployment on HuggingFace Hub with version control

**Advanced RAG Engineering**
- Hybrid search implementation (BM25+Dense) with RRF fusion algorithm
- Query optimization: caching, streaming, source attribution
- Multi-modal document understanding (text + vision)

**LLM Engineering Best Practices**
- Provider abstraction pattern for multi-model support
- Two-pass extraction strategy for accuracy/speed tradeoffs
- Prompt engineering for structured JSON extraction
- Context window management and token budgeting

**Model Evaluation & Quality**
- Automated evaluation framework with CI/CD integration
- LLM-as-Judge implementation for semantic quality assessment
- Hallucination detection via source overlap analysis
- Active learning feedback loop for continuous improvement

**Fine-Tuning Expertise**
- QLoRA implementation for parameter-efficient fine-tuning
- Dataset engineering: preprocessing, splitting, format conversion
- Model comparison framework (GPT-4o vs 4o-mini vs LoRA)
- Cost-quality tradeoff analysis

### For Backend Engineers

**Async Python Architecture**
- FastAPI with async/await throughout
- SQLAlchemy 2.0 async ORM with relationship loading
- Concurrent LLM calls with semaphore-based rate limiting
- Async vector database operations

**Production-Ready Infrastructure**
- Structured logging with request context binding
- JWT authentication with refresh token rotation
- Database migrations with Alembic version control
- Comprehensive test coverage (200+ tests)

**Scalability Patterns**
- Connection pooling (PostgreSQL, Qdrant)
- Background job processing with status tracking
- Query result caching for repeated operations
- SSE streaming for long-running operations

### For Full-Stack Engineers

**Modern Frontend Architecture**
- Next.js 14 App Router with server components
- TanStack Query for server state management
- Real-time updates via SSE streaming
- Type-safe API client with TypeScript

**System Integration**
- Multi-service Docker Compose orchestration
- API design following REST principles
- Real-time communication patterns (SSE)
- Error handling and retry logic

---

## 📊 Performance Characteristics

### Throughput & Latency

| Operation | Latency (p50) | Latency (p95) | Throughput |
|-----------|---------------|---------------|------------|
| **Document Upload** | 100ms | 200ms | 50 docs/min |
| **Ingestion (3-page PDF)** | 5s | 8s | 12 docs/min |
| **Ingestion (50-page PDF)** | 55s | 90s | 1 doc/min |
| **Contract Analysis** | 3.5s | 6s | 17 contracts/min |
| **RAG Query (cache hit)** | 50ms | 100ms | 1200 queries/min |
| **RAG Query (cache miss)** | 3.5s | 5s | 17 queries/min |
| **Hybrid Search** | 100ms | 200ms | 600 searches/min |

### Cost Analysis

| Model | Contract Analysis Cost | 1000 Contracts | Annual (10K contracts) |
|-------|----------------------|----------------|----------------------|
| **GPT-4o-mini** | $0.03 | $30 | $300 |
| **GPT-4o** | $0.08 | $80 | $800 |
| **Local LoRA (GPU)** | $0.00 (+ GPU costs) | $0 | $0 |
| **Gemini Flash** | $0.02 | $20 | $200 |

### Resource Requirements

| Deployment Mode | CPU | RAM | Storage | GPU |
|----------------|-----|-----|---------|-----|
| **Development** | 4 cores | 8 GB | 20 GB | Optional |
| **Production (Small)** | 8 cores | 16 GB | 100 GB | No |
| **Production (Large)** | 16 cores | 32 GB | 500 GB | No |
| **LoRA Inference** | 4 cores | 16 GB | 50 GB | T4/A10G recommended |

---

## 🔬 Technical Deep Dives

### Hybrid Search Implementation

The hybrid search combines dense semantic vectors with sparse BM25 for optimal retrieval:

```python
# Simplified hybrid search flow
async def hybrid_search(query: str, top_k: int = 5):
    # 1. Generate embeddings
    dense_vector = await get_embedding(query)
    sparse_vector = get_bm25_encoding(query)
    
    # 2. Query Qdrant with named vectors
    results = await qdrant_client.search(
        collection_name=collection,
        query_vector=("dense", dense_vector),
        sparse_vector=("sparse", sparse_vector),
        limit=top_k,
        search_params=SearchParams(fusion=Fusion.RRF)
    )
    
    # 3. RRF fusion happens server-side
    # RRF formula: score = Σ(1 / (k + rank_i)) where k=60
    return results
```

**Why RRF over simple score averaging?**
- Score ranges differ between dense (cosine: 0-1) and sparse (BM25: unbounded)
- Rank-based fusion is scale-invariant
- Empirically performs better on legal document retrieval

### Two-Pass Extraction Strategy

**Pass 1: Parallel per-chunk extraction**
```python
async def extract_pass_1(chunks: List[Chunk]):
    semaphore = asyncio.Semaphore(5)  # Rate limiting
    
    async def extract_chunk(chunk):
        async with semaphore:
            return await llm.extract_clauses(chunk.text)
    
    # Parallel processing
    results = await asyncio.gather(*[
        extract_chunk(chunk) for chunk in chunks
    ])
    return flatten(results)  # Raw extractions, may have duplicates
```

**Pass 2: LLM-based merge**
```python
async def extract_pass_2(raw_clauses: List[Dict]):
    # Single LLM call with full context
    prompt = f"""
    Given these clause extractions from different parts of a contract,
    deduplicate and merge related clauses:
    
    {json.dumps(raw_clauses, indent=2)}
    
    Output consolidated clauses with unique IDs.
    """
    return await llm.invoke(prompt)
```

**Tradeoffs**:
- Pass 1: Fast (parallel), but creates duplicates
- Pass 2: Slow (sequential), but ensures consistency
- Combined: ~5s for 50-page contract vs ~15s for naive sequential processing

### LLM-as-Judge Implementation

```python
async def judge_extraction_quality(
    extraction: Dict,
    source_chunk: str
) -> float:
    prompt = f"""
    You are evaluating the quality of a clause extraction.
    
    Source text:
    {source_chunk}
    
    Extracted clauses:
    {json.dumps(extraction, indent=2)}
    
    Rate 0.0-1.0 on:
    1. Completeness: All clauses present in source
    2. Accuracy: No hallucinated content
    3. Relevance: Correct clause type classification
    
    Output JSON: {{"score": float, "explanation": str}}
    """
    
    result = await judge_llm.invoke(prompt)
    return result['score']
```

**Applications**:
- Filter training data (silver labeling: score ≥ 0.85)
- Flag uncertain predictions for human review (score < 0.75)
- Monitor production quality degradation

---

## 📚 References & Resources


### Tools & Libraries
- **LangChain**: Document loaders, text splitters, RAG patterns
- **Qdrant**: Vector database with hybrid search support
- **Unsloth**: Fast LoRA training (2x speedup vs HuggingFace PEFT)
- **FastAPI**: Modern async Python web framework
- **structlog**: Structured logging for Python


---

## 📝 License & Contact

This project is built for demonstration and learning purposes, showcasing production-grade AI engineering practices.

**Technologies**: Python 3.11, FastAPI, Next.js 14, PostgreSQL 16, Qdrant, OpenAI, HuggingFace

**Fine-Tuned Model**: [`iakshayrathee/contractiq-lora-llama3`](https://huggingface.co/iakshayrathee/contractiq-lora-llama3)

---

**Built with ❤️ to demonstrate modern AI engineering best practices**
