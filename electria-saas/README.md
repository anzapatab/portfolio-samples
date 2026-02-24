# ELECTRIA - AI-Powered SaaS for LATAM Electricity Markets

> **Status: Work in Progress** - This project is under active development.

## Overview

ELECTRIA is a SaaS platform that brings AI-powered intelligence to Latin American electricity markets. Starting with Chile, the platform provides chat-based expert consultations, real-time market dashboards, regulatory document search, and intelligent alerts -- all at a fraction of the cost of traditional energy consulting firms.

**Value proposition**: "All the intelligence of the electricity market, accessible to any company, for less than $200/month" -- targeting a market where the main competitor charges ~$1,800 USD/month.

## Architecture Highlights

### Multi-Country Architecture

The core system is **country-agnostic**. Each country is a configuration module that plugs into the base platform via the `CountryConfig` abstract interface:

- Abstract base classes define regulatory bodies, market config, data sources, glossaries, and system prompts
- Chile is the first fully implemented country module
- New countries (Colombia, Peru, Mexico) can be added by implementing the `CountryConfig` interface
- Each country gets its own Pinecone namespace and TimescaleDB schema

### RAG Pipeline with LlamaIndex

The Retrieval-Augmented Generation pipeline ingests regulatory documents (laws, technical standards, resolutions, reports) from official sources:

1. **Scrapers** detect new/changed documents from CNE, Coordinador Electrico Nacional, SEC, and Diario Oficial
2. **Document processing** with PyMuPDF, chunking strategies vary by document type (articles for regulations, clauses for contracts, chapters for reports)
3. **Embeddings** via OpenAI `text-embedding-3-large` (3072 dimensions)
4. **Vector storage** in Pinecone with metadata filtering
5. **Hybrid search** combining vector similarity + BM25 keyword search
6. **Reranking** with Cohere for precision
7. **Generation** via Claude API with mandatory source citations

### Claude API Integration

The chat service uses Claude (Sonnet for RAG queries, Haiku for classification/routing) with:

- Country-specific system prompts with domain terminology
- Streaming responses for real-time output
- Strict citation rules -- the AI must always reference source documents
- Usage tracking and plan-based rate limiting

### Dual Database Architecture

| Database | Purpose | Content |
|----------|---------|---------|
| **Pinecone** (Vector DB) | Regulatory knowledge base | Laws, decrees, technical standards, resolutions, reports |
| **PostgreSQL** (Supabase) | Operational data + metadata | Users, subscriptions, document catalog, conversations |
| **TimescaleDB** | Time-series market data | Marginal costs, generation, demand (hourly) |
| **Redis** | Cache + task queue | Frequent queries, Celery background jobs |

## Tech Stack

### Backend (FastAPI)
- **Framework**: FastAPI with async/await, Pydantic v2 settings
- **LLM**: Claude API (Anthropic) -- primary model for all generation
- **RAG**: LlamaIndex orchestration, Pinecone vector DB, Cohere reranking
- **Embeddings**: OpenAI text-embedding-3-large
- **Database**: PostgreSQL (Supabase) + TimescaleDB for time-series
- **Background Jobs**: Celery + Redis
- **Document Processing**: PyMuPDF, BeautifulSoup
- **Storage**: Cloudflare R2 for PDF documents

### Frontend (Next.js)
- **Framework**: Next.js 14 (App Router)
- **Styling**: Tailwind CSS with custom design system (sky/cyan brand palette)
- **State**: Zustand + React Query (TanStack Query)
- **UI Components**: Custom shadcn/ui-based component library
- **Charts**: Recharts for market data visualization
- **Animations**: Framer Motion

### Infrastructure
- Vercel (frontend hosting)
- Railway (backend hosting)
- Supabase (auth + PostgreSQL)
- Pinecone (vector database)
- Cloudflare R2 (document storage)
- Stripe (billing)
- Resend (transactional email)
- Langfuse (LLM observability)

## Project Structure

```
electria-saas/
├── electria-api/                    # FastAPI Backend
│   ├── app/
│   │   ├── main.py                  # Application factory with lifespan
│   │   ├── core/
│   │   │   └── config.py            # Pydantic Settings (all env vars)
│   │   └── api/v1/
│   │       ├── auth/                # Supabase Auth integration
│   │       ├── chat/                # RAG-powered chat with Claude
│   │       ├── search/              # Hybrid document search
│   │       ├── dashboard/           # Market data endpoints (CMg, generation, demand)
│   │       ├── alerts/              # Price threshold + regulatory alerts
│   │       └── users/               # Profile + usage + billing
│   ├── packages/
│   │   └── countries/
│   │       ├── base/config.py       # Abstract CountryConfig interface
│   │       └── chile/config.py      # Chile: regulators, data sources, prompts, glossary
│   ├── pyproject.toml
│   └── .env.example
│
├── electria-web/                    # Next.js Frontend
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx           # Root layout with Inter + JetBrains Mono
│   │   │   ├── page.tsx             # Landing page (hero, features, pricing)
│   │   │   ├── providers.tsx        # React Query + Sonner toast
│   │   │   └── globals.css          # CSS variables + custom utilities
│   │   ├── components/ui/
│   │   │   └── button.tsx           # CVA-based button with brand variants
│   │   └── lib/utils/
│   │       └── cn.ts                # clsx + tailwind-merge utility
│   ├── tailwind.config.ts           # Full design system (brand colors, gradients, animations)
│   ├── next.config.js               # Security headers, image optimization
│   ├── package.json
│   └── .env.example
│
└── README.md
```

## Key Design Decisions

1. **Country-as-configuration**: Adding a new country requires only implementing the `CountryConfig` interface -- no core code changes
2. **Strict citation policy**: The Claude system prompt enforces that every response must cite source documents with `[1]`, `[2]` format
3. **Chunking by document type**: Regulatory articles get different chunk sizes than reports or contracts, improving retrieval precision
4. **Dual-database separation**: Regulatory knowledge (vectors) and operational market data (time-series) live in purpose-built databases
5. **Usage-based rate limiting**: Plan tiers control queries/month and tokens/day, tracked in real-time

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/chat` | RAG-powered chat with Claude (streaming) |
| GET | `/api/v1/search` | Hybrid document search with filters |
| GET | `/api/v1/dashboard/summary` | Market overview (CMg, demand, renewables %) |
| GET | `/api/v1/dashboard/cmg` | Marginal cost time series |
| GET | `/api/v1/dashboard/generation` | Generation mix by technology |
| POST | `/api/v1/alerts` | Create price/document/regulatory alerts |
| POST | `/api/v1/auth/signup` | User registration |
| GET | `/api/v1/users/me/usage` | Usage statistics and plan limits |

## Running Locally

```bash
# Backend
cd electria-api
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env  # Fill in API keys
uvicorn app.main:app --reload

# Frontend
cd electria-web
pnpm install
cp .env.example .env.local  # Fill in values
pnpm dev
```

## Note

This is a portfolio code sample extracted from the full ELECTRIA project. Some service implementations are stubbed with TODOs where they depend on external services (Supabase, Pinecone, Stripe, etc.). The architecture, API design, country configuration system, and frontend are all real production code.
