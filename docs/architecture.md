# Architecture Overview

This document describes the high-level architecture of Trace, a macOS application that continuously observes digital activity and converts it into searchable knowledge.

> **Data Location**: All user data is stored in `~/Library/Application Support/Trace/` on macOS.

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           TRACE ARCHITECTURE                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    ELECTRON DESKTOP APP                          │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐            │   │
│  │  │   React UI   │  │  Chat View   │  │  Settings    │            │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘            │   │
│  │                              │                                   │   │
│  │                    IPC (subprocess)                              │   │
│  └──────────────────────────────┼───────────────────────────────────┘   │
│                                 │                                       │
│  ┌──────────────────────────────▼───────────────────────────────────┐   │
│  │                     PYTHON BACKEND                               │   │
│  │                                                                  │   │
│  │  ┌─────────────────────────────────────────────────────────────┐ │   │
│  │  │                   SERVICE MANAGER                           │ │   │
│  │  │  - Auto-start all services                                  │ │   │
│  │  │  - Health monitoring & restart                              │ │   │
│  │  │  - Sleep/wake detection                                     │ │   │
│  │  │  - Backfill coordination                                    │ │   │
│  │  └─────────────────────────────────────────────────────────────┘ │   │
│  │                                                                  │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐               │   │
│  │  │   CAPTURE   │  │   HOURLY    │  │    DAILY    │               │   │
│  │  │   DAEMON    │  │  SCHEDULER  │  │  SCHEDULER  │               │   │
│  │  │  (1 sec)    │  │   (1 hr)    │  │   (3 AM)    │               │   │
│  │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘               │   │
│  │         │                │                │                      │   │
│  │         ▼                ▼                ▼                      │   │
│  │  ┌─────────────────────────────────────────────────────────────┐ │   │
│  │  │                    CHAT API                                 │ │   │
│  │  │  - Query classification                                     │ │   │
│  │  │  - Agentic planning                                         │ │   │
│  │  │  - Answer synthesis                                         │ │   │
│  │  └─────────────────────────────────────────────────────────────┘ │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                 │                                       │
│  ┌──────────────────────────────▼───────────────────────────────────┐   │
│  │                       DATA LAYER                                 │   │
│  │                                                                  │   │
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐         │   │
│  │  │    SQLite     │  │   Markdown    │  │     Cache     │         │   │
│  │  │  (metadata,   │  │    Notes      │  │ (screenshots, │         │   │
│  │  │   graph,      │  │  (durable)    │  │  text, temp)  │         │   │
│  │  │  embeddings)  │  │               │  │               │         │   │
│  │  └───────────────┘  └───────────────┘  └───────────────┘         │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. Capture Daemon (`src/capture/`)

The capture daemon runs continuously at 1-second intervals, collecting:

| Capture Type | Source | Storage |
|-------------|--------|---------|
| Screenshots | Multi-monitor CGImage | `cache/screenshots/` |
| Foreground App | Accessibility API | `events` table |
| Window Titles | Accessibility API | `events` table |
| Browser URLs | AppleScript (Safari, Chrome) | `events` table |
| Now Playing | MediaRemote (Spotify, Apple Music) | `events` table |
| Location | CoreLocation | `events` table |

**Key Features:**
- Perceptual hash deduplication (avoids storing duplicate frames)
- Event span tracking (groups similar activity into spans)
- Screenshot capping to 1080p maximum
- Configurable capture interval

**Files:**
- `src/capture/daemon.py` - Main orchestrator
- `src/capture/screenshots.py` - Multi-monitor capture
- `src/capture/foreground.py` - App/window detection
- `src/capture/urls.py` - Browser URL extraction
- `src/capture/now_playing.py` - Music detection
- `src/capture/media_remote.py` - macOS MediaRemote integration
- `src/capture/location.py` - Location tracking
- `src/capture/dedup.py` - Screenshot deduplication
- `src/capture/events.py` - Event span management

### 2. Hourly Summarizer (`src/summarize/`)

Runs every hour to convert raw captures into structured notes:

```
Raw Data                     LLM Processing                    Output
─────────────────────────────────────────────────────────────────────────
Screenshots ─┐
Events      ─┼─▶ Keyframe Selection ─▶ Vision LLM ─▶ Structured JSON
Text buffers─┘     (top 10 frames)      (gpt-5-mini)      │
                                                          ▼
                                               Markdown Note
                                                    │
                                                    ▼
                                             Entity Extraction
                                                    │
                                                    ▼
                                              Embeddings
```

**Pipeline Steps:**
1. Aggregate evidence from the past hour
2. Triage screenshots (heuristic or vision-based)
3. Select keyframes (representative screenshots)
4. Call Vision LLM with screenshots + activity timeline
5. Validate JSON output against schema
6. Render Markdown note to disk
7. Extract and store entities
8. Compute and store embedding

**Files:**
- `src/summarize/summarizer.py` - Main orchestrator
- `src/summarize/triage.py` - Frame importance scoring
- `src/summarize/keyframes.py` - Representative frame selection
- `src/summarize/evidence.py` - Evidence aggregation
- `src/summarize/schemas.py` - JSON schema validation
- `src/summarize/render.py` - Markdown generation
- `src/summarize/entities.py` - Entity extraction
- `src/summarize/embeddings.py` - Vector embedding computation

### 3. Daily Reviser (`src/revise/`)

Runs once per day (3 AM) to improve notes with full-day context:

**Tasks:**
1. Review all hourly notes from the day
2. Revise summaries with day-level insights
3. Normalize entity names across notes
4. Build typed graph edges between entities
5. Generate daily summary note
6. Compute aggregates (time per app, topic, etc.)
7. Clean up raw artifacts after successful processing

**Files:**
- `src/revise/revise.py` - Note revision logic
- `src/revise/normalize.py` - Entity normalization
- `src/revise/aggregates.py` - Time aggregation
- `src/revise/cleanup.py` - Artifact deletion
- `src/revise/integrity.py` - Integrity verification
- `src/revise/daily_note.py` - Daily summary generation

### 4. Chat API (`src/chat/`)

Handles natural language queries with intelligent routing:

```
User Query
    │
    ▼
┌─────-────────────┐
│ Query Classifier │ ─── Simple ──▶ Direct Handlers
└────-─────────────┘                (aggregates, entity, timeline, semantic)
    │ Complex
    ▼
┌─────-────────────┐
│  Query Planner   │ ─── LLM generates QueryPlan
└────-─────────────┘
    │
    ▼
┌─────-────────────┐
│ Plan Executor    │ ─── Execute steps (parallel where possible)
└────-─────────────┘
    │
    ▼
┌─────────────────-┐
│Answer Synthesizer│ ─── Generate answer with citations
└─────────────────-┘
```

**Query Types:**
- `aggregates` - "Most used apps", "Top topics"
- `entity` - "Tell me about Python"
- `timeline` - "What did I do yesterday?"
- `semantic` - Free-form questions
- Complex queries via agentic pipeline

**Files:**
- `src/chat/api.py` - Main API endpoint
- `src/chat/prompts/answer.py` - Answer synthesis
- `src/chat/agentic/classifier.py` - Query classification
- `src/chat/agentic/planner.py` - Plan generation
- `src/chat/agentic/executor.py` - Plan execution

### 5. Retrieval System (`src/retrieval/`)

Multiple search strategies for finding relevant notes:

| Strategy | Use Case | Implementation |
|----------|----------|----------------|
| Vector Search | Semantic similarity | sqlite-vec embeddings |
| Hierarchical | Daily-first search | Two-stage retrieval |
| Graph Expansion | Related entities | Edge traversal |
| Aggregates | Time-based stats | Pre-computed rollups |
| Time Filter | Temporal constraints | SQL filtering |

**Files:**
- `src/retrieval/search.py` - Vector similarity search
- `src/retrieval/hierarchical.py` - Two-stage search
- `src/retrieval/graph.py` - Graph traversal
- `src/retrieval/aggregates.py` - Statistical queries
- `src/retrieval/time.py` - Time filter parsing

### 6. Service Manager (`src/core/services.py`)

Coordinates all background services:

**Features:**
- Auto-start all services on launch
- Health monitoring with automatic restart
- Sleep/wake detection for backfill
- Maximum 3 restart attempts before failing
- macOS notifications for errors

**Services Managed:**
1. Capture Daemon
2. Hourly Scheduler
3. Daily Scheduler
4. Sleep/Wake Detector
5. Backfill Detector

### 7. Platform Integration (`src/platform/`)

macOS-specific integrations:

- `src/platform/notifications.py` - macOS notification center
- `src/platform/sleep_wake.py` - NSWorkspace sleep/wake events

## Data Flow

See [data-flow.md](data-flow.md) for detailed data flow diagrams.

## Database Schema

See [database.md](database.md) for complete schema documentation.

## LLM Pipeline

See [llm-pipeline.md](llm-pipeline.md) for LLM models and prompts.

## Technology Stack

| Layer | Technology |
|-------|------------|
| Frontend | Electron + React |
| Backend | Python 3.11+ |
| Database | SQLite + sqlite-vec |
| LLM | OpenAI API (gpt-4o, gpt-4o-mini) |
| Package Manager | uv |
| IPC | Python subprocess |

## Directory Structure

```
Trace/
├── src/
│   ├── capture/        # Activity capture modules
│   ├── evidence/       # Text extraction (OCR, PDF)
│   ├── summarize/      # Hourly summarization
│   ├── revise/         # Daily revision
│   ├── jobs/           # Job scheduling
│   ├── chat/           # Chat interface
│   │   └── agentic/    # Multi-step query planning
│   ├── retrieval/      # Search strategies
│   ├── graph/          # Graph operations
│   ├── db/             # Database operations
│   ├── core/           # Service management
│   └── platform/       # macOS integrations
├── electron/           # Desktop UI
├── docs/               # Documentation
├── tests/              # Test suite
└── notes/              # Generated notes (gitignored)
```

## Security & Privacy

- **Local-only**: All data stays on the user's machine
- **No cloud sync**: Only OpenAI API calls leave the machine
- **Ephemeral artifacts**: Raw screenshots deleted daily
- **Minimal retention**: Only structured notes kept long-term
- **Low-detail images**: Screenshots sent to API with `detail: low`
