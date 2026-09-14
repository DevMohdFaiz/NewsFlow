# News Intelligence Pipeline

> An AI-powered global news aggregation, analysis, and chat system built with a Python/FastAPI backend and a Next.js/TypeScript frontend.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [High-Level Architecture](#2-high-level-architecture)
3. [Technology Stack](#3-technology-stack)
4. [Repository Structure](#4-repository-structure)
5. [Backend — Deep Dive](#5-backend--deep-dive)
   - 5.1 [Configuration Layer](#51-configuration-layer)
   - 5.2 [Ingestion Layer](#52-ingestion-layer)
   - 5.3 [Processing Layer](#53-processing-layer)
   - 5.4 [Storage Layer](#54-storage-layer)
   - 5.5 [Scheduler Layer](#55-scheduler-layer)
   - 5.6 [API Layer](#56-api-layer)
   - 5.7 [Chat — RAG State Machine](#57-chat--rag-state-machine)
6. [Frontend — Deep Dive](#6-frontend--deep-dive)
   - 6.1 [Project Setup](#61-project-setup)
   - 6.2 [API Client & Types](#62-api-client--types)
   - 6.3 [Shared Utilities](#63-shared-utilities)
   - 6.4 [UI Components](#64-ui-components)
   - 6.5 [Dashboard Page](#65-dashboard-page)
   - 6.6 [Stories Page](#66-stories-page)
   - 6.7 [Chat Page](#67-chat-page)
7. [Data Flow — End to End](#7-data-flow--end-to-end)
8. [Scheduler — Job Timeline](#8-scheduler--job-timeline)
9. [Cost Analysis](#9-cost-analysis)
10. [Environment Variables Reference](#10-environment-variables-reference)
11. [Setup & Installation](#11-setup--installation)
12. [API Reference](#12-api-reference)

---

## 1. Project Overview

News Intelligence is a full-stack, AI-powered news platform that continuously ingests global news from multiple sources, processes it through a multi-stage intelligence pipeline, and surfaces the results through a real-time dashboard and a conversational chat interface grounded in recent articles.

The system is designed around three guiding principles:

**Accuracy over fluency.** Every answer the chat interface produces is grounded strictly in articles retrieved from the vector database. The system explicitly refuses to generate answers when no supporting evidence exists within the rolling news window.

**Decoupled subsystems.** The ingestion pipeline, processing pipeline, and serving layer are fully independent. Ingestion runs on a schedule regardless of user activity. The API layer reads from pre-computed storage — no user request ever triggers a live scrape or a model call in the critical path (except for chat).

**Full observability.** Every pipeline stage records its execution time in milliseconds. The chat interface can expose a pipeline trace showing exactly how long each state took — Planning, Retrieving, Generating — mirroring the observability pattern from the Serah AI project.

---

## 2. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        DATA SOURCES                              │
│   SerpAPI (Google News)   NewsAPI   RSS Feeds (25 outlets)       │
└────────────────────────┬────────────────────────────────────────┘
                         │ raw articles (title, url, snippet)
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                     INGESTION LAYER                              │
│  newspaper3k (full body extraction)                              │
│  Normalizer  (dedup · UTC timestamps · rolling window filter)    │
└────────────────────────┬────────────────────────────────────────┘
                         │ clean articles
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    PROCESSING LAYER                              │
│  spaCy NER       → entity extraction + candidate grouping        │
│  VoyageAI        → semantic embeddings (voyage-3)                │
│  SemanticCluster → cosine similarity clustering                  │
│  Keyword Map     → category classification (no API, zero cost)   │
│  Groq 8B         → cluster summarization + sentiment scoring     │
│  Groq 27B        → categorical briefing generation (11 cats)     │
└────────────────────────┬────────────────────────────────────────┘
                         │ enriched story clusters
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                      STORAGE LAYER                               │
│  Neon PostgreSQL   → source of truth (articles + clusters)       │
│  Qdrant Cloud      → vector store (3-day rolling window)         │
│  Upstash Redis     → pre-computed dashboard cache                │
└────────────────────────┬────────────────────────────────────────┘
                         │ stored, indexed, cached
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                       API LAYER                                  │
│  FastAPI  →  /api/dashboard  /api/briefings                      │
│           →  /api/stories    /api/chat  (RAG state machine)      │
└────────────────────────┬────────────────────────────────────────┘
                         │ JSON responses
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                     FRONTEND LAYER                               │
│  Next.js + TypeScript  →  Dashboard  /  Stories  /  Chat         │
└─────────────────────────────────────────────────────────────────┘
```

Everything left of the API layer runs on a schedule managed by APScheduler. Everything right of the storage layer is on-demand, triggered by user interaction.

---

## 3. Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| Backend framework | Python + FastAPI | Async REST API |
| LLM inference | Groq API (`qwen/qwen3.6-27b`) | Briefings, summarization, sentiment, chat |
| Classification | Keyword Map (no API) | Zero-cost, zero-latency category classification |
| Embeddings | VoyageAI (voyage-3) | Semantic clustering + chat retrieval |
| Vector database | Qdrant Cloud | Filtered semantic search |
| Relational database | Neon (PostgreSQL) | Persistent structured storage |
| Cache | Upstash (Redis) | Pre-computed dashboard reads |
| News discovery | SerpAPI (Google News) | Trending story discovery |
| News metadata | NewsAPI | Bulk article metadata + URLs |
| RSS parsing | feedparser | Real-time feed ingestion |
| Full-text extraction | newspaper3k | Article body extraction from URLs |
| NER | spaCy (en_core_web_sm) | Named entity extraction |
| Scheduler | APScheduler | Timed pipeline execution |
| Frontend framework | TanStack Start + TypeScript | Dashboard + chat UI |
| Styling | Tailwind CSS | Utility-first styling |
| Markdown rendering | react-markdown | AI briefing formatted output |
| Animation | Framer Motion | Page transitions + UI animation |
| Charts | Recharts | Sentiment visualizations |
| Icons | Lucide React | UI iconography |
| Backend hosting | Render (free tier) | FastAPI deployment |
| Frontend hosting | Vercel | Frontend deployment |

---

## 4. Repository Structure

```
news-intelligence/
│
├── backend/
│   ├── main.py                         # FastAPI app entry point + lifespan
│   ├── requirements.txt                # Python dependencies
│   ├── .env.example                    # Environment variable template
│   │
│   └── app/
│       ├── config.py                   # Pydantic settings + constants
│       │
│       ├── ingestion/
│       │   ├── news_fetcher.py         # NewsAPI + SerpAPI clients
│       │   ├── rss_fetcher.py          # RSS feed parser (25 outlets)
│       │   ├── extractor.py            # newspaper3k full body extraction
│       │   ├── normalizer.py           # Dedup, timestamps, window filter
│       │   └── pipeline.py             # Ingestion orchestrator
│       │
│       ├── processing/
│       │   ├── ner.py                  # spaCy entity extraction + candidate clustering
│       │   ├── embedder.py             # VoyageAI embedding client
│       │   ├── clusterer.py            # Semantic clustering via cosine similarity
│       │   ├── classifier.py           # Groq 8B category classification
│       │   ├── sentiment.py            # Groq 8B sentiment scoring
│       │   ├── summarizer.py           # Groq 8B summaries + Groq 27B briefings
│       │   └── pipeline.py             # Processing orchestrator
│       │
│       ├── storage/
│       │   ├── database.py             # SQLAlchemy models + engine + init_db
│       │   ├── postgres_store.py       # All Postgres read/write operations
│       │   ├── qdrant_store.py         # Qdrant collection setup + search + purge
│       │   ├── redis_store.py          # Redis cache read/write with TTLs
│       │   └── store.py                # Unified Store singleton
│       │
│       ├── scheduler/
│       │   ├── jobs.py                 # All four scheduled job functions
│       │   └── scheduler.py            # APScheduler registration + lifecycle
│       │
│       ├── chat/
│       │   └── state_machine.py        # RAG state machine (Plan→Retrieve→Generate)
│       │
│       └── api/
│           └── routes/
│               ├── dashboard.py        # GET /api/dashboard/
│               ├── briefings.py        # GET /api/briefings/{category}
│               ├── stories.py          # GET /api/stories/
│               └── chat.py             # POST /api/chat/
│
└── frontend/
    ├── .env.local                      # NEXT_PUBLIC_API_URL
    ├── tailwind.config.ts              # Design tokens
    ├── next.config.ts
    │
    ├── lib/
    │   ├── api.ts                      # Typed API client + all TypeScript interfaces
    │   └── utils.ts                    # Formatting helpers + sentiment utilities
    │
    ├── components/
    │   ├── Navbar.tsx                  # Sticky navigation bar
    │   └── ui/
    │       ├── Card.tsx                # Accent-bordered card container
    │       ├── Badge.tsx               # Color-coded label badge
    │       └── Spinner.tsx             # Loading spinner
    │
    └── app/
        ├── layout.tsx                  # Root layout (fonts, metadata, body)
        ├── globals.css                 # CSS variables + scrollbar + selection
        ├── page.tsx                    # Dashboard page (/)
        ├── stories/
        │   └── page.tsx                # Stories page (/stories)
        └── chat/
            └── page.tsx                # Chat page (/chat)
```

---

## 5. Backend — Deep Dive

### 5.1 Configuration Layer

**File:** `backend/app/config.py`

The entire backend is configured through a single `Settings` class powered by Pydantic's `BaseSettings`. This class reads every value from the `.env` file at startup and makes them available as typed Python attributes throughout the codebase.

The `@lru_cache` decorator on `get_settings()` ensures the `.env` file is read exactly once across the entire application lifetime, regardless of how many times `get_settings()` is called.

**Key constants defined here:**

| Constant | Value | Purpose |
|---|---|---|
| `qdrant_collection` | `"news_articles"` | Qdrant collection name |
| `rolling_window_days` | `3` | How far back the system looks |
| `briefing_categories` | 10 categories (plus 'All') | Valid category list |
| `ingestion_interval_minutes` | `30` | Ingestion scheduler frequency |
| `briefing_interval_hours` | `2` | Briefing regeneration frequency |
| `similarity_threshold` | `0.82` | Cosine similarity cutoff for clustering |
| `top_k_chat_retrieval` | `8` | How many chunks the chat RAG retrieves |

All pipeline components import `get_settings()` to access these constants, so changing any pipeline behaviour requires editing only the `.env` file or `config.py`.

---

### 5.2 Ingestion Layer

The ingestion layer is responsible for one thing: producing a clean list of deduplicated, full-text articles that fall within the 3-day rolling window. It does not perform any AI processing. It has four components that execute in a strict sequence.

---

#### `news_fetcher.py` — NewsAPI + SerpAPI

This module contains the `NewsFetcher` class, which queries two external news APIs:

**NewsAPI** is the primary bulk discovery source. It is queried with a 6-hour lookback window (`from_param`) requesting English-language articles sorted by publish date. The free tier returns up to 100 results per request with article metadata (title, URL, description, source name, published timestamp). Importantly, NewsAPI's free tier truncates the article body — this is intentional here because `newspaper3k` handles full-body extraction downstream.

**SerpAPI** complements NewsAPI by querying Google News for trending stories using a set of default queries (`"world news today"`, `"breaking news today"`, `"top stories today"`). This catches stories that may not appear in NewsAPI's feed ranking, particularly from sources not indexed by NewsAPI. SerpAPI returns a `news_results` array with title, link, source, date, and snippet.

Both clients normalize their responses into the same flat dictionary schema before returning:

```python
{
  "title":        str,
  "url":          str,
  "source":       str,
  "published_at": str | None,   # ISO 8601 string
  "description":  str,
  "body":         "",            # empty — filled by extractor
  "origin":       "newsapi" | "serpapi"
}
```

The `@retry` decorator from `tenacity` wraps both API calls with 3 retry attempts and exponential backoff, handling transient network failures gracefully.

`fetch_all()` calls both clients and concatenates their results before returning.

---

#### `rss_fetcher.py` — RSS Feed Parser

`RSSFetcher` runs in parallel with `NewsFetcher` as a real-time stream source. It polls 25 hardcoded RSS feeds across the following outlet categories:

- International wire services: Reuters, AP News, BBC World, Al Jazeera, DW, France 24
- US publications: NPR, CNN, NYT World, Washington Post
- UK publications: Guardian, The Independent
- Technology: TechCrunch, Ars Technica, The Verge
- Business/Economy: FT, Bloomberg, CNBC
- Science/Health: Science Daily, WHO
- Climate: Carbon Brief
- Africa/Global South: Africa News, Premium Times NG, The East African, Mail & Guardian

`feedparser.parse()` handles the actual RSS parsing. Each entry is normalized to the same flat schema as `NewsFetcher` with `"origin": "rss"`.

Date parsing is handled with a two-pass strategy: first attempting `entry.published_parsed` (a `time.struct_time` provided by feedparser), then falling back to parsing the raw `entry.published` string using `email.utils.parsedate_to_datetime`. Both are converted to UTC ISO 8601 strings.

The Africa/Global South feeds are included by design — the developer is based in Nigeria and this provides relevance for a potential local news expansion feature.

---

#### `extractor.py` — Full Body Extraction

`ArticleExtractor` solves the truncation problem created by NewsAPI's free tier and RSS snippets. It takes the list of raw articles (each containing only a URL and metadata) and extracts full article bodies using `newspaper3k`.

Extraction is performed in parallel using `ThreadPoolExecutor` with `MAX_WORKERS = 10`. For each article:

1. A `newspaper.Article` object is created with the article URL
2. `article.download()` fetches the HTML
3. `article.parse()` extracts the main text, stripping boilerplate (navigation, ads, footers)
4. Articles with fewer than `MIN_BODY_LEN = 150` characters are discarded — they are likely paywalled, redirected, or content-empty pages

If `newspaper3k` successfully extracts a publish date and the article has none, it is backfilled from `article.publish_date`.

Articles that fail extraction (network error, paywall, encoding issues) are silently dropped via `return None`. This is intentional — it is better to lose an article than to surface empty or malformed content downstream.

---

#### `normalizer.py` — Deduplication and Windowing

`Normalizer` is the final gate before articles enter the processing pipeline. It performs three operations in sequence:

**Date parsing:** Every article's `published_at` string is parsed with `dateutil.parser.parse()`, which handles virtually every date format encountered across RSS feeds, NewsAPI, and SerpAPI. All timestamps are normalized to UTC ISO 8601. Articles with completely unparseable dates are given the current timestamp rather than being discarded.

**Rolling window filter:** Articles older than `rolling_window_days × 24` hours are dropped. This enforces the 3-day scope at the ingestion boundary rather than relying on downstream filters.

**Deduplication:** Two passes are performed:
- **URL deduplication:** Exact URL matching (after stripping trailing slashes)
- **Title fingerprint deduplication:** The title is lowercased, stripped of punctuation, and MD5-hashed. This catches near-identical headlines from different outlets (e.g., `"Fed holds rates steady"` vs `"Fed Holds Rates Steady — Statement"`).

The normalizer logs a four-number summary: `in → parsed → in window → unique`, which makes it easy to see how much of the raw input survives to the processing stage.

---

#### `pipeline.py` (Ingestion) — Orchestrator

`IngestionPipeline.run()` sequences the four components:

```
NewsFetcher.fetch_all() + RSSFetcher.fetch_all()
    → ArticleExtractor.extract_batch()
        → Normalizer.normalize()
            → list[dict]  (clean articles)
```

The combined raw article list from both fetchers is passed to the extractor as a single batch to maximize parallelism. The normalized output is returned to the caller (the scheduler job) as a flat list of clean article dictionaries.

---

### 5.3 Processing Layer

The processing layer takes clean articles and produces enriched story clusters. It is the most computationally significant part of the system, involving two AI APIs (VoyageAI and Groq) and one local NLP model (spaCy).

---

#### `ner.py` — Named Entity Recognition + Candidate Clustering

`NERProcessor` uses spaCy's `en_core_web_sm` model, loaded once at module level to avoid repeated loading costs.

**Entity extraction** runs on a deliberately small text window: the article title plus the first two sentences of the body. This is a cost-reduction strategy — running spaCy on full article bodies would be slower with minimal benefit for entity identification, since entities are almost always named in the opening lines.

Entity types extracted: `PERSON`, `ORG`, `GPE` (geopolitical entity), `LOC`, `NORP` (nationalities/groups), `EVENT`.

**Candidate cluster formation** (`build_candidate_clusters`) is the key cost-reduction mechanism for VoyageAI calls. Two articles are placed into the same candidate cluster if they share 2 or more named entities AND were published within 6 hours of each other. The logic is:

- Two articles mentioning "IMF" and "Nigeria" within the same time window are almost certainly about the same story
- Instead of embedding both independently, the system identifies them as candidates for the same cluster and embeds only one

Articles that share no entities with any other article become singletons and are embedded individually.

This NER pre-filtering typically reduces VoyageAI API calls by approximately 40–45%, which extends the free token budget significantly.

---

#### `embedder.py` — VoyageAI Embedding Client

`Embedder` wraps the VoyageAI client for two use cases:

**Document embedding** (`embed_texts`): Used during ingestion to embed article representatives for clustering and storage. Uses `input_type="document"`. Handles batching internally with `BATCH_SIZE = 128` to respect VoyageAI's API limits.

**Query embedding** (`embed_query`): Used at chat time to embed the user's question. Uses `input_type="query"`, which VoyageAI optimizes differently for retrieval tasks — query embeddings are tuned to align well with document embeddings in semantic space.

The model used is `voyage-3` (not `voyage-3-lite`) for higher semantic quality. At the estimated volume of ~420,000 tokens/month, the 200M free token allowance provides approximately 15 months of free operation at normal scale.

The text fed to the embedder per article is: `title + ". " + description + ". " + body[:500]`. The 500-character body limit is deliberate — it captures the key facts of the article without bloating the embedding input.

---

#### `clusterer.py` — Semantic Clustering

`SemanticClusterer` takes the NER-formed candidate groups and singletons from `ner.py` and produces final story clusters.

**For candidate groups:** One representative article is chosen (the one with the longest body, as a proxy for information density). The representative is embedded. Then every other member of the group is also embedded, and its cosine similarity to the representative is computed. Members scoring at or above `SIMILARITY_THRESHOLD = 0.82` are confirmed as part of the cluster. Members falling below the threshold are split off and treated as independent singletons — this handles the case where NER false-positively grouped two articles that mention the same entities but cover different stories.

**For singletons:** Each is embedded individually.

The output is a flat list of cluster dictionaries, each containing:

```python
{
  "cluster_id":     str (UUID),
  "articles":       list[dict],        # all articles in cluster
  "representative": dict,              # the chosen representative article
  "embedding":      list[float],       # the representative's vector
  "entity_union":   list[str],         # merged entity list across all articles
  "source_count":   int,               # how many distinct articles
  "category":       None,              # filled by classifier
  "sentiment_score":None,              # filled by sentiment analyzer
  "summary":        None,              # filled by summarizer
}
```

Cosine similarity is computed using NumPy for performance.

---

#### `classifier.py` — Category Classification

`CategoryClassifier` uses a **zero-cost keyword map** to assign each cluster to one of 11 categories: All, Nigeria, Politics, Economy, Tech, Health, Science, Conflict, Climate, Culture, Sports. No API calls are made — classification runs entirely in-process in milliseconds.

**How it works:** The representative article's title and first 500 characters of description are lowercased into a single text string. Each category has a list of domain-specific keywords checked with `re.search` using word-boundary anchors (`\b`) to prevent partial matches. Each keyword hit increments that category's score. The category with the highest score wins.

**Ordering matters:** The keyword map is ordered from most-specific to most-general. Nigeria comes first (highly specific place names), Conflict comes before Climate (many overlap on disaster terms), and Sports is checked before Economy so that football vocabulary like `goal`, `transfer`, and `match` scores Sport before Economy's generic terms. Politics is always last and acts as a catch-all.

**Fallback:** If no category scores any keyword hits at all, the cluster defaults to `"Politics"` rather than silently defaulting to the first entry in the map.

**Sports vs Economy fix:** A historical bug where `""` (empty string) existed in the Economy keyword list caused Economy to unconditionally score +1 on every article — making it beat any sport article with zero keyword matches. This has been removed. Additionally, the Sports keyword list was expanded with 30+ football-specific terms (league names, player names, match vocabulary) to ensure football articles score Sports far higher than Economy.

---

#### `sentiment.py` — Sentiment Scoring

`SentimentAnalyzer` uses the same `llama-3.1-8b-instant` model to score each cluster's sentiment on a scale from -1.0 (very negative) to +1.0 (very positive).

The model returns a JSON object with `score` (float) and `label` (string). The score is clamped to [-1.0, 1.0] regardless of what the model returns, preventing edge-case values from corrupting downstream aggregations.

The label maps to one of seven strings: `very negative`, `negative`, `slightly negative`, `neutral`, `slightly positive`, `positive`, `very positive`.

Like classification, sentiment is run on only the title and a 200-character description snippet — not the full body. This keeps token consumption low while capturing the emotional register of the story accurately.

---

#### `summarizer.py` — Cluster Summaries + Categorical Briefings

`Summarizer` handles two distinct generation tasks using `qwen/qwen3.6-27b` via the Groq API:

**Cluster summarization:** For each story cluster, the representative article's title and up to 1,200 characters of body text are fed to the model. The model is instructed to produce a 3–5 sentence factual summary, avoiding editorializing. The summary is stored in Postgres and Qdrant's payload, and is the primary text surfaced in both the dashboard story cards and the chat retrieval context.

**Categorical briefings:** `generate_all_briefings()` generates one AI briefing per category — including the `"All"` category, which receives all top clusters across every category as input. It feeds the top 5 clusters per category to `qwen/qwen3.6-27b` with an editorial prompt encouraging **markdown formatting** (bold entity names, structured lists). The model is a reasoning model that produces `<think>` tags internally; these are stripped via regex before the result is stored. The frontend renders the markdown output via `react-markdown`.

Rate limiting is managed by running briefing generation with a `ThreadPoolExecutor(max_workers=2)` so at most 2 Groq API calls are in-flight simultaneously, staying within the free-tier rate limits.

---

#### `pipeline.py` (Processing) — Orchestrator

`ProcessingPipeline.run()` sequences the processing steps:

```
articles
  → NERProcessor.process_batch()              # entity extraction
      → NERProcessor.build_candidate_clusters()  # candidate grouping
          → SemanticClusterer.cluster()        # embedding + cosine clustering
              → CategoryClassifier.classify_batch()   # keyword map, no API
                  → SentimentAnalyzer.analyze_batch()  # Groq
                      → Summarizer.summarize_batch()   # Groq
                          → list[dict]  (enriched clusters)
```

`generate_all_briefings()` is a separate method called by the briefing scheduler job (not the ingestion job), because briefings are regenerated every 2 hours rather than every 30 minutes. It generates briefings for all 11 categories including `"All"`.

---

### 5.4 Storage Layer

The storage layer uses three distinct databases, each optimized for a different access pattern. They are unified behind a single `Store` singleton that the API and scheduler import.

---

#### `database.py` — PostgreSQL Schema

Three SQLAlchemy ORM models define the relational schema:

**`ArticleModel`** (table: `articles`): Stores individual raw articles. Fields include `id` (UUID), `cluster_id` (foreign reference), `title`, `url` (unique), `source`, `origin` (newsapi/serpapi/rss), `body`, `description`, `published_at`, `created_at`. Indexed on `published_at` and a composite `(published_at, cluster_id)` index for time-range + cluster queries.

**`ClusterModel`** (table: `clusters`): Stores one row per story cluster — the enriched result of the processing pipeline. Fields include `id` (cluster UUID), `representative_url`, `category`, `sentiment_score`, `sentiment_label`, `summary`, `entity_union` (JSON array), `source_count`, `published_at`, `created_at`. Indexed on `category`, `published_at`, and a composite `(category, published_at)` index for category-filtered time queries.

**`BriefingModel`** (table: `briefings`): Stores generated briefings with `category`, `content`, and `generated_at`. Multiple briefings per category are retained (one per generation cycle), allowing historical briefing lookups.

`init_db()` creates all tables using `Base.metadata.create_all` — it is idempotent and safe to call on every startup.

---

#### `postgres_store.py` — Postgres Read/Write

All Postgres operations are async, using SQLAlchemy's `AsyncSession` with the `asyncpg` driver for Neon PostgreSQL.

**Writes:** `save_clusters()` upserts both cluster rows and their child article rows. Upserts use PostgreSQL's `ON CONFLICT DO UPDATE` / `ON CONFLICT DO NOTHING` syntax to safely handle re-ingestion of the same articles across pipeline runs.

**Reads:**
- `get_clusters()` fetches clusters filtered by optional category, a date cutoff derived from the rolling window, with pagination (limit/offset)
- `get_sentiment_by_category()` runs a `GROUP BY` aggregate returning average sentiment score per category for the dashboard gauge
- `get_trending_entities()` fetches up to 200 clusters, flattens their `entity_union` JSON arrays, and uses a `Counter` to return the top N entities by frequency
- `get_latest_briefing()` fetches the most recently generated briefing for a given category

**Cleanup:** `purge_old_clusters()` is the weekly maintenance job — it deletes clusters older than 7 days, preventing unbounded table growth.

---

#### `qdrant_store.py` — Vector Store

Qdrant serves one purpose: fast, filtered semantic search for the chat layer.

**Collection setup** (`init_collection`): Creates the `news_articles` collection with `voyage-3`'s output dimension of 1024 and cosine distance. Two payload indexes are created: `category` (KEYWORD type for equality matching) and `published_at` (FLOAT type, storing Unix timestamps for range queries). These indexes are what enable Qdrant to filter during vector search rather than post-filter.

**Upsert:** Each cluster point contains its embedding vector plus a rich payload:

```python
{
  "title":           str,
  "url":             str,
  "source":          str,
  "all_sources":     list[str],
  "category":        str,
  "sentiment_score": float,
  "sentiment_label": str,
  "summary":         str,
  "entity_union":    list[str],
  "source_count":    int,
  "published_at":    float,    # Unix timestamp for range filter
  "published_iso":   str,      # human-readable for display
}
```

**Search:** `search()` builds a Qdrant `Filter` with two `must` conditions: `published_at >= cutoff_timestamp` (enforcing the rolling window) and optionally `category == category` (for category-scoped chat). The filter is applied during the ANN search, not after — this is the key advantage over FAISS, which cannot pre-filter. `top_k` defaults to 8 (configurable in settings).

**Purge:** `purge_old_points()` deletes all points with `published_at < cutoff_timestamp`, keeping the collection lean at the 3-day window boundary. This runs daily at midnight UTC.

---

#### `redis_store.py` — Dashboard Cache

Upstash Redis stores pre-computed dashboard aggregates so that dashboard API calls are near-instant reads rather than live database queries.

**What is cached and for how long:**

| Key | Content | TTL |
|---|---|---|
| `briefing:{category}` | Full briefing text per category | 2 hours |
| `dashboard:sentiment` | Avg sentiment score per category | 30 minutes |
| `dashboard:entities` | Top 20 trending entities | 30 minutes |
| `dashboard:top_stories:{category}` | Top 5 clusters per category | 30 minutes |
| `dashboard:summary` | Combined dashboard payload | 30 minutes |

All values are JSON-serialized before storage and deserialized on read. Every cache read falls back to Postgres if the key is absent (cold cache) — the API layer never fails due to a cache miss, it simply takes slightly longer on that request.

`refresh_dashboard_cache()` is called at the end of every ingestion job, ensuring the cache is updated within seconds of new data entering the system.

---

#### `store.py` — Unified Store Singleton

`Store` is a thin wrapper that instantiates `PostgresStore`, `QdrantStore`, and `RedisStore` as attributes (`store.postgres`, `store.qdrant`, `store.redis`). `store.init()` calls `init_db()` and `init_collection()` on startup.

The `store` singleton is imported once and shared across the entire application — API routes, scheduler jobs, and the chat state machine all reference the same instance.

---

### 5.5 Scheduler Layer

APScheduler's `AsyncIOScheduler` manages four recurring jobs, all running in UTC. The scheduler shares the same asyncio event loop as FastAPI, so async jobs (Postgres operations) work natively.

---

#### `jobs.py` — Job Functions

**`run_ingestion_pipeline` (every 30 minutes)**
The most frequently running job. Calls `IngestionPipeline().run()` to fetch and clean articles, then `ProcessingPipeline().run()` to produce enriched clusters, then saves to Postgres and Qdrant, and finally calls `_refresh_dashboard_cache()` to update Redis. The entire cycle is wrapped in a try/except so a single pipeline failure does not kill the scheduler. Execution time is logged.

**`run_briefing_generation` (every 2 hours)**
Fetches the most recent 500 clusters from Postgres, calls `ProcessingPipeline().generate_all_briefings()` to produce briefings for all 11 categories (including `"All"`) using the 27B model, persists them to Postgres, and caches them in Redis. Runs separately from ingestion because briefing generation is more expensive (11 × 27B calls) and does not need to happen as frequently as ingestion.

**`run_qdrant_purge` (daily at 00:00 UTC)**
Calls `store.qdrant.purge_old_points(days=3)` to delete vectors older than the rolling window. Keeps the Qdrant collection within the 1GB free tier limit.

**`run_postgres_trim` (weekly, Sunday 01:00 UTC)**
Calls both `store.postgres.purge_old_clusters(days=7)` and `store.postgres.purge_old_briefings(days=7)` to trim the relational database. Briefings run every 2 hours for 11 categories, generating over 130 rows per day — without regular cleanup this would accumulate ~50,000 dead rows per year. Postgres retains a longer 7-day history than Qdrant (3 days) to support weekly trend analysis.

---

#### `scheduler.py` — Registration

`create_scheduler()` builds and returns an `AsyncIOScheduler` with all jobs registered:
- `IntervalTrigger` for the pipeline job (ingestion + briefing in one pass)
- `CronTrigger` for the weekly Postgres trim (Sunday 01:00 UTC)

`max_instances=1` prevents job overlap — if an ingestion run takes longer than the interval, the next scheduled run is skipped rather than spawning a parallel process. `misfire_grace_time` gives the scheduler a tolerance window if the server was briefly overloaded at the scheduled time.

---

### 5.6 API Layer

#### `main.py` — Application Entry Point

FastAPI's `lifespan` context manager handles the startup and shutdown sequence:

**Startup:**
1. `store.init()` — creates Postgres tables and Qdrant collection
2. `run_ingestion_pipeline()` — runs immediately so the app has data before the first scheduler tick
3. `run_briefing_generation()` — generates initial briefings on boot
4. `init_scheduler()` — registers and starts all four jobs

**Shutdown:**
`shutdown_scheduler()` gracefully stops the APScheduler.

CORS middleware is configured to allow `http://localhost:3000` (Next.js dev server). This should be updated to the production Vercel URL before deployment.

---

#### `routes/dashboard.py`

`GET /api/dashboard/` returns the entire dashboard payload in a single request:

1. Checks Redis for `dashboard:sentiment` → falls back to Postgres `get_sentiment_by_category()`
2. Checks Redis for `dashboard:entities` → falls back to Postgres `get_trending_entities()`
3. For each of the 10 categories (plus 'All'), checks Redis for `dashboard:top_stories:{category}` → falls back to Postgres `get_clusters(category, days=3, limit=5)`

All three components are assembled into one response. This single-call pattern minimizes frontend request overhead.

`GET /api/dashboard/sentiment` and `GET /api/dashboard/entities` are individual endpoints for components that need to refresh independently.

---

#### `routes/briefings.py`

`GET /api/briefings/` returns all category briefings at once, reading from Redis with Postgres fallback.

`GET /api/briefings/{category}` returns a single category's briefing. Returns 400 if the category is not in the valid list, 404 if no briefing has been generated yet.

#### `routes/clusters.py`

`GET /api/clusters` is the primary data endpoint. It supports five query parameters:
- `category` — filter by any of the 11 valid categories (`All`, `Nigeria`, `Politics`, etc.)
- `entity` — **filter to clusters whose `entity_union` array contains this named entity**. Uses PostgreSQL's native JSON containment operator (`@>`), so the filter runs in-database with no post-processing. When an entity filter is active the Redis cache is bypassed, since cached results are not entity-scoped.
- `days` — rolling window (1–3, default from `settings.rolling_window_days`)
- `limit` / `offset` — pagination (max 100 per page)

The Redis top-stories cache is used for page 1 of category-only requests (no entity filter) for sub-millisecond response. All other requests go directly to Postgres via a `LEFT JOIN` with `ArticleModel` to include the representative article title and source.

`GET /api/clusters/{cluster_id}` returns a single cluster with all its child articles included.

`GET /api/clusters/search` performs semantic search via Qdrant using a natural-language query (`?q=`), with optional `?category=` scoping.

---

#### `routes/briefings.py`

`GET /api/briefings/` returns all category briefings at once, reading from Redis with Postgres fallback.

`GET /api/briefings/{category}` returns a single category's briefing — including `"All"`, which is AI-generated from cross-category clusters like every other category. Returns 400 if the category is not valid, 404 if no briefing has been generated yet.

---

Input validation: empty queries return 400; invalid category filters return 400 with the valid options listed.

---

### 5.7 Chat — RAG State Machine

The chat layer is modelled after the same state machine pattern used in the Serah AI project. Rather than using LangChain or another black-box orchestration framework, every step of the RAG pipeline is an explicit, inspectable state transition.

---

#### States

```
PLANNING → RETRIEVING → GENERATING → DONE
                    ↘
                     ERROR (any state can transition here)
```

---

#### `ChatContext`

A dataclass that carries the full state of a single chat request through the pipeline:

```python
@dataclass
class ChatContext:
    query:           str               # the user's question
    category_filter: str | None        # optional category scope
    history:         list[dict]        # last N conversation turns
    intent:          str               # (same as query for news chat)
    search_vector:   list[float]       # query embedding
    retrieved_docs:  list[dict]        # Qdrant search results
    answer:          str               # final generated answer
    sources:         list[dict]        # attributed source list
    state:           State             # current state
    trace:           dict[str, float]  # ms timing per state
    error:           str               # error message if state == ERROR
```

---

#### State: PLANNING

Embeds the user's query using `Embedder.embed_query()` with `input_type="query"` (VoyageAI optimizes query vectors differently from document vectors for better retrieval alignment). The resulting vector is stored in `ctx.search_vector`. Records `planning_ms` in the trace.

---

#### State: RETRIEVING

Calls `store.qdrant.search()` with the query vector, the optional category filter, the 3-day rolling window, and `top_k=8`. If no results are returned, the state machine transitions directly to `DONE` with a "no relevant news found" message, bypassing the generation step entirely. Records `retrieving_ms` in the trace.

---

#### State: GENERATING

Builds a context block from the retrieved documents:

```
[1] Title of article
Source: Reuters | Date: 2026-05-06
Summary: 3-5 sentence summary...

[2] Title of article
Source: BBC | Date: 2026-05-07
Summary: ...
```

This context block, the system prompt (with citation rules), and the conversation history (last 10 turns) are assembled into a messages array and sent to `llama-3.1-8b-instant`.

The system prompt enforces attribution: every factual claim must be attributed to a source in brackets (e.g., `[BBC World]`). The model is instructed to say explicitly when the context does not contain enough information, rather than guessing. Records `generating_ms` in the trace.

---

#### Trace Output

When `show_trace: true` is passed in the request, the response includes:

```json
{
  "trace": {
    "planning_ms":   12.4,
    "retrieving_ms": 38.7,
    "generating_ms": 821.3
  }
}
```

This allows the frontend to display latency breakdowns and makes performance profiling straightforward.

---

## 6. Frontend — Deep Dive

The frontend is a Next.js 14 application using the App Router, TypeScript, and Tailwind CSS. It communicates with the FastAPI backend exclusively through the typed API client in `lib/api.ts`.

---

### 6.1 Project Setup

The application uses two Google Fonts loaded via `next/font/google`:
- `Space Mono` — monospace font used for labels, badges, navigation, and headings
- `DM Sans` — sans-serif font used for body text and descriptions

Both are injected as CSS variables (`--font-mono`, `--font-sans`) in the root layout and mapped to Tailwind's `font-mono` and `font-sans` utilities via `tailwind.config.ts`.

The design system is built around a dark colour palette defined as CSS variables in `globals.css` and as Tailwind colour extensions in `tailwind.config.ts`. Every component references these tokens rather than hardcoded hex values.

---

### 6.2 API Client & Types

**File:** `frontend/lib/api.ts`

The Axios instance is pre-configured with `baseURL` from `NEXT_PUBLIC_API_URL`. All API functions are typed end-to-end: TypeScript interfaces define every response shape, so any backend schema change that breaks a frontend usage is caught at compile time.

Interfaces defined:

| Interface | Description |
|---|---|
| `StoryCluster` | Single story cluster from Postgres |
| `TrendingEntity` | Entity name + frequency count |
| `DashboardData` | Full dashboard response payload |
| `BriefingsData` | All category briefings |
| `StoriesData` | Paginated stories response |
| `ChatSource` | Single attributed source in a chat response |
| `ChatMessage` | A single turn in the conversation history |
| `ChatResponse` | Full chat API response |

---

### 6.3 Shared Utilities

**File:** `frontend/lib/utils.ts`

`cn()` — A `clsx` wrapper for conditional Tailwind class composition.

`formatDate()` — Converts ISO 8601 strings to locale-aware short date strings.

`sentimentColor()` / `sentimentBg()` — Return the appropriate Tailwind class for a sentiment score. Scores > 0.2 map to emerald (positive), scores < -0.2 map to red (negative), and scores in between map to zinc (neutral).

`sentimentLabel()` — Converts a float score to a human-readable label.

`CATEGORY_ICONS` — Maps each of the 10 categories (plus 'All') to an emoji used consistently across all pages.

---

### 6.4 UI Components

**`Card.tsx`** — A container with a dark background, border, and an optional 2px top accent bar. The accent colour is passed as a prop (`cyan | green | amber | purple | red`). Used throughout the dashboard and stories page for consistent visual grouping.

**`Badge.tsx`** — A small pill-shaped label rendered in `Space Mono` font. Colour variants match the design system tokens. Used for category labels, sentiment labels, and source attribution.

**`Spinner.tsx`** — An SVG-based CSS spinner used for loading states across all three pages.

**`Navbar.tsx`** — The sticky navigation bar. Uses `usePathname()` from Next.js to highlight the active route. The active link receives a cyan-tinted background and border. The logo uses `Space Mono` with a cyan accent on "Intel".

---

### 6.5 Dashboard Page

**File:** `frontend/src/routes/index.tsx`

The dashboard is the default route (`/`) and the most data-dense page. It runs a background pipeline status poller every 5 seconds — when the poller detects that a pipeline run just finished (was running → now idle), it automatically refreshes all dashboard data so users see fresh stories without manual intervention.

**Layout:** Three-column on large screens — left sidebar (category nav), main content, right panel (trending + sentiment).

**Sections:**

**AI Briefings** — The top of the main content area shows the currently selected category's briefing, rendered via `react-markdown`. This gives the AI freedom to use **bold entity names**, bullet points, and structured headings. A "Read full briefing" toggle shows/hides content beyond the initial visible height, with a gradient fade-out to indicate there is more. The `"All"` tab shows an AI-generated cross-category briefing, not a hardcoded aggregate.

**Entity Filtering** — The right-hand Trending Entities panel is fully interactive. Clicking any entity chip:
1. Highlights the chip with an accent ring and accent-coloured text
2. Shows a dismissable filter banner in the main content area ("Filtering by entity: Mbappe")
3. Fires `GET /api/clusters?entity=<name>` to filter the stories grid server-side using Postgres JSON containment
4. Clicking the same entity again (or the "Clear ✕" link) toggles the filter off
5. Changing the category tab always clears the active entity filter

**Sentiment Panel** — A ranked bar chart showing average sentiment per category, colour-coded by polarity (emerald positive, red negative, zinc neutral).

**Top Stories Grid** — A paginated grid of story cluster cards. Each card shows title, source count, sentiment badge, category badge, entity tags, and published timestamp. Clicking a card opens a `StoryDrawer` with the full cluster detail and an inline story-scoped AI chat.

**Semantic Search** — A search box in the header debounces 500ms before calling `GET /api/clusters/search?q=` via Qdrant. Results replace the grid while a search is active; clearing the box reverts to the category feed.

All sections show skeleton loading states during data fetches and toast notifications when a fresh pipeline run completes.

---

### 6.6 Stories Page

**File:** `frontend/app/stories/page.tsx`

The stories page provides a filterable, paginated view of all story clusters in the rolling window.

**Filters (top bar):**
- Category dropdown (All + 10 categories)
- Sentiment filter (All / Positive / Negative / Neutral)
- Results per page selector

**Story list:** Each story is rendered as a Card with full summary text, entity tags, multi-source attribution, sentiment badge, and a link to the representative article. The page number is tracked in React state. Previous/Next pagination buttons call `fetchStories` with the updated `offset`.

---

### 6.7 Chat Page

**File:** `frontend/app/chat/page.tsx`

The chat page provides a conversational interface grounded in the last 3 days of news.

**Conversation area:** Messages are rendered in a scrolling list. User messages are right-aligned; assistant messages are left-aligned. Each assistant message includes a collapsible `Sources` section showing the attributed articles (title, outlet, date, relevance score).

**Category filter:** An optional dropdown scopes the RAG retrieval to a single category. When set, only articles from that category are searched, producing more focused answers on domain-specific questions.

**Pipeline trace:** A toggle button reveals the `trace` object if `show_trace` is enabled, displaying the millisecond timing for each state (Planning, Retrieving, Generating).

**Conversation history:** The last 10 turns are sent with every request in the `history` field, enabling context-aware follow-up questions.

**Input area:** A text input with a send button. Pressing Enter or clicking Send calls `sendChatMessage()`, appends the user message to the local state, then appends the assistant response on completion. A Spinner replaces the send button during in-flight requests.

---

## 7. Data Flow — End to End

Here is the complete journey of a single news article through the system, from source to user:

```
1. APScheduler fires run_ingestion_pipeline() every 30 minutes

2. NewsFetcher queries NewsAPI (last 6 hours) and SerpAPI (trending queries)
   RSSFetcher polls 25 RSS feeds in parallel
   → ~750 raw article dicts (title, url, snippet, no body)

3. ArticleExtractor.extract_batch() spawns 10 threads
   Each thread: Article(url).download() → .parse() → body text
   Articles with body < 150 chars are dropped
   → ~420 articles with full body text

4. Normalizer.normalize()
   - Parses all timestamps to UTC ISO 8601
   - Drops articles older than 72 hours
   - Deduplicates by URL and title fingerprint
   → ~350 unique clean articles

5. NERProcessor.process_batch()
   spaCy runs on title + first 2 sentences of each article
   Extracts PERSON, ORG, GPE, LOC, NORP, EVENT entities
   → each article gains an "entities": ["IMF", "Nigeria", ...] field

6. NERProcessor.build_candidate_clusters()
   Groups articles sharing 2+ entities within 6 hours
   → ~80 candidate clusters + ~200 singletons

7. SemanticClusterer.cluster()
   Embeds one representative per candidate cluster + all singletons
   ~280 VoyageAI API calls instead of ~350 (saves ~20%)
   Verifies cosine similarity ≥ 0.82 within candidate groups
   Splits non-similar members into independent singletons
   → ~310 final story clusters with embeddings

8. CategoryClassifier.classify_batch()
   Groq 8B: one API call per cluster (title + 300-char description)
   → each cluster gains "category": "Tech" | "Politics" | ...

9. SentimentAnalyzer.analyze_batch()
   Groq 8B: one API call per cluster (title + 200-char description)
   → each cluster gains "sentiment_score": 0.34, "sentiment_label": "positive"

10. Summarizer.summarize_batch()
    Groq 8B: one API call per cluster (title + 1200-char body)
    → each cluster gains "summary": "3-5 sentence factual summary..."

11. PostgresStore.save_clusters()
    Upserts 310 cluster rows + their child article rows to Neon Postgres
    
12. QdrantStore.upsert_clusters()
    Stores 310 vectors with rich payloads to Qdrant Cloud

13. _refresh_dashboard_cache()
    Reads fresh aggregates from Postgres
    Writes sentiment, entities, top_stories to Upstash Redis

--- user opens the dashboard ---

14. Browser calls GET /api/dashboard/
    FastAPI reads sentiment, entities, top_stories from Redis (< 5ms)
    Returns full dashboard payload

15. User selects "Tech" briefing tab
    Browser calls GET /api/briefings/Tech
    FastAPI reads cached briefing from Redis
    Returns 3-4 paragraph Tech narrative

--- user opens the chat page ---

16. User types: "What is happening with AI regulation in Europe?"
    Browser calls POST /api/chat/ with query + history

17. State: PLANNING
    Embedder.embed_query("What is happening with AI regulation in Europe?")
    → query vector (1024 floats), input_type="query"

18. State: RETRIEVING
    QdrantStore.search(query_vector, days=3, top_k=8)
    Qdrant applies filter: published_at >= 72h_ago
    Returns 8 most semantically similar clusters

19. State: GENERATING
    Context block built from 8 cluster summaries + sources
    Groq 8B generates attributed answer:
    "The EU AI Act's enforcement timeline has been updated... [Reuters]
     MEPs also raised concerns about foundation model oversight... [Guardian]"

20. Response returned:
    { answer, sources: [{title, source, url, date, score}], trace: {...} }

21. Frontend renders answer with collapsible sources section
    User sees: answer text + "Sources (8)" expandable list
```

---

## 8. Scheduler — Job Timeline

```
T+00:00  Server starts
         → init_db(), init_collection()
         → run_ingestion_pipeline()   (immediate boot run)
         → run_briefing_generation()  (immediate boot run)
         → init_scheduler()

T+00:30  run_ingestion_pipeline()     (first scheduled run)
T+01:00  run_ingestion_pipeline()
T+02:00  run_ingestion_pipeline()
         run_briefing_generation()    (first scheduled briefing run)
T+02:30  run_ingestion_pipeline()
...
T+24:00  run_qdrant_purge()           (midnight UTC — purge vectors > 3 days old)
...
Sun 01:00 run_postgres_trim()         (weekly — purge clusters > 7 days old)
```

The boot-time immediate runs are critical. Without them, the app would start with an empty database and serve blank responses until the first 30-minute tick.

---

## 9. Cost Analysis

The entire system runs on free tiers. Below is the monthly cost breakdown at normal operating scale (~750 raw articles/day, ~310 clusters/day).

| Service | Usage | Free Tier | Monthly Cost |
|---|---|---|---|
| VoyageAI (voyage-3) | ~12.6M tokens/month | 200M tokens free | **$0** |
| Groq (8B + 70B) | Classification + sentiment + summarization | Generous free RPM/TPM | **$0** |
| Qdrant Cloud | ~9,300 vectors (3-day window) | 1GB free cluster | **$0** |
| Neon PostgreSQL | ~90MB/month growth | 512MB free | **$0** |
| Upstash Redis | ~2,000 commands/day | 10,000 commands/day free | **$0** |
| Render (backend) | 1 free web service | Free (spins down idle) | **$0** |
| Vercel (frontend) | Hobby tier | Free | **$0** |
| NewsAPI | ~48 requests/day | 100 requests/day free | **$0** |
| SerpAPI | ~144 requests/day (3 queries × 48 runs) | 100 free searches/month | ⚠️ |
| **Total** | | | **~$0/month** |

**Note on SerpAPI:** The free tier provides only 100 searches/month. At 3 queries per ingestion run × 48 daily runs, this is exhausted quickly. Mitigation options: reduce SerpAPI query frequency (run only every 4 hours instead of every 30 minutes), reduce the number of queries per run to 1, or rely primarily on NewsAPI + RSS and remove SerpAPI from the default ingestion cycle for the free tier.

The VoyageAI 200M token free budget provides approximately **15 months** of free operation at normal scale before any cost is incurred.

---

## 10. Environment Variables Reference

All variables are defined in `backend/.env` (copy from `backend/.env.example`):

| Variable | Description | Where to get it |
|---|---|---|
| `GROQ_API_KEY` | Groq inference API key | console.groq.com |
| `VOYAGE_API_KEY` | VoyageAI embedding API key | dash.voyageai.com |
| `NEWS_API_KEY` | NewsAPI key | newsapi.org |
| `SERP_API_KEY` | SerpAPI key | serpapi.com |
| `NEON_DATABASE_URL` | Neon Postgres async connection string | neon.tech |
| `QDRANT_URL` | Qdrant Cloud cluster URL | cloud.qdrant.io |
| `QDRANT_API_KEY` | Qdrant API key | cloud.qdrant.io |
| `UPSTASH_REDIS_URL` | Upstash Redis REST URL | console.upstash.com |
| `UPSTASH_REDIS_TOKEN` | Upstash Redis REST token | console.upstash.com |
| `APP_ENV` | `development` or `production` | manually set |
| `LOG_LEVEL` | `INFO` or `DEBUG` | manually set |

Frontend variable in `frontend/.env.local`:

| Variable | Description |
|---|---|
| `NEXT_PUBLIC_API_URL` | FastAPI backend URL (e.g. `http://localhost:8000`) |

---

## 11. Setup & Installation

### Prerequisites

- Python 3.11+
- Node.js 18+
- Git

### Backend

```bash
# 1. Clone the repository
git clone https://github.com/your-username/news-intelligence.git
cd news-intelligence

# 2. Set up Python environment
cd backend
python -m venv venv

# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Download spaCy language model
python -m spacy download en_core_web_sm

# 5. Configure environment
cp .env.example .env
# Fill in all values in .env

# 6. Start the backend
uvicorn main:app --reload --port 8000
```

On first start, the server will:
- Create Postgres tables
- Create the Qdrant collection with payload indexes
- Run a full ingestion + processing cycle
- Generate initial briefings for all 10 categories (plus 'All')
- Start the APScheduler

### Frontend

```bash
# From the project root
cd frontend

# 1. Install dependencies
npm install

# 2. Configure environment
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local

# 3. Start the dev server
npm run dev
```

Open `http://localhost:3000`.

### Verifying the setup

```bash
# Backend health
curl http://localhost:8000/health
# Expected: {"status":"ok","env":"development"}

# Dashboard data
curl http://localhost:8000/api/dashboard/

# Chat test
curl -X POST http://localhost:8000/api/chat/ \
  -H "Content-Type: application/json" \
  -d '{"query": "What is happening in global politics?", "show_trace": true}'
```

---

## 12. API Reference

### `GET /health`

Returns server status.

```json
{ "status": "ok", "env": "development" }
```

---

### `GET /api/dashboard/`

Returns the full dashboard payload in a single call.

```json
{
  "sentiment_by_category": {
    "Politics": -0.12,
    "Tech": 0.34,
    "Economy": -0.08
  },
  "trending_entities": [
    { "entity": "IMF", "count": 14 },
    { "entity": "Elon Musk", "count": 11 }
  ],
  "top_stories": {
    "Tech": [ { "cluster_id": "...", "summary": "...", ... } ]
  },
  "categories": ["All", "Nigeria", "Politics", "Economy", "Tech", "Health", "Science", "Conflict", "Climate", "Culture", "Sports"]
}
```

---

### `GET /api/briefings/`

Returns all category briefings.

```json
{
  "briefings": {
    "Tech": "The technology sector this week saw...",
    "Politics": "Global political developments centered on..."
  }
}
```

### `GET /api/briefings/{category}`

Returns a single category briefing.

**Path parameters:** `category` — one of the 11 valid categories.

```json
{
  "category": "Tech",
  "content": "The technology sector this week...",
  "source": "cache"
}
```

---

### `GET /api/stories/`

Returns paginated story clusters.

**Query parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `category` | string | null | Filter by category |
| `days` | integer | 3 | Rolling window (1–3) |
| `limit` | integer | 20 | Results per page (1–100) |
| `offset` | integer | 0 | Pagination offset |
| `sentiment` | string | null | `positive`, `negative`, or `neutral` |

```json
{
  "stories": [
    {
      "cluster_id": "uuid",
      "category": "Tech",
      "sentiment_score": 0.41,
      "sentiment_label": "positive",
      "summary": "OpenAI announced...",
      "entity_union": ["OpenAI", "Sam Altman", "Microsoft"],
      "source_count": 7,
      "published_at": "2026-05-07T14:30:00+00:00",
      "representative_url": "https://..."
    }
  ],
  "count": 1,
  "offset": 0,
  "limit": 20,
  "category": "Tech"
}
```

---

### `POST /api/chat/`

Sends a query to the RAG state machine.

**Request body:**

```json
{
  "query": "What is happening with AI regulation?",
  "category_filter": "Tech",
  "history": [
    { "role": "user",      "content": "Tell me about the EU AI Act" },
    { "role": "assistant", "content": "The EU AI Act..." }
  ],
  "show_trace": true
}
```

**Response:**

```json
{
  "answer": "The EU AI Act's enforcement provisions... [Reuters]. Meanwhile, US regulators... [NYT World].",
  "sources": [
    {
      "title": "EU AI Act enforcement timeline updated",
      "source": "Reuters",
      "url": "https://...",
      "date": "2026-05-07",
      "score": 0.912
    }
  ],
  "state": "done",
  "trace": {
    "planning_ms": 11.2,
    "retrieving_ms": 42.7,
    "generating_ms": 803.5
  },
  "error": null
}
```

---

*Built with Python, FastAPI, Next.js, TypeScript, Groq, VoyageAI, Qdrant, Neon, and Upstash.*
