# Trace

**A second brain built from your digital activity.**

Trace is a macOS application that continuously observes your digital activity, converts it into durable Markdown notes using AI, stores typed relationships in a local knowledge graph, and enables time-aware chat and search over your past.

---

## How It Works

```
Your Activity                    AI Processing                    Your Knowledge
─────────────────────────────────────────────────────────────────────────────────

Screenshots          ─┐
Active apps          ─┤                                   ┌─ Markdown Notes
Window titles        ─┼──▶  Hourly Summarization  ──▶    ├─ Entity Graph
Browser URLs         ─┤     (Vision LLM)                  ├─ Vector Embeddings
Now playing music    ─┤                                   └─ Searchable Index
Location             ─┘
        │                           │
        │ (every 1 second)          │ (every hour)
        ▼                           ▼
   Raw Capture               Daily Revision
   (temporary)               (Context + Normalization)
                                    │
                                    ▼
                              Chat Interface
                              (Query your past)
```

### The Pipeline

1. **Capture** (every 1 second)
   - Multi-monitor screenshots (deduplicated, capped at 1080p)
   - Foreground app and window metadata
   - Browser URLs (Safari, Chrome)
   - Now playing (Spotify, Apple Music)
   - Location snapshots

2. **Hourly Summarization** (every hour)
   - AI triages screenshots to select important keyframes
   - Vision LLM analyzes keyframes + activity data
   - Generates structured summary with entities, topics, activities
   - Computes embeddings for semantic search

3. **Daily Revision** (once per day at 3 AM)
   - Reviews all hourly notes with full-day context
   - Normalizes entity names (e.g., "VSCode" + "VS Code" → "Visual Studio Code")
   - Builds relationship graph between entities
   - Deletes raw artifacts after successful processing

4. **Chat Interface**
   - Query your past activity with natural language
   - AI-powered answers with citations to specific notes
   - Time filtering, topic search, graph traversal

---

## Features

- **Automatic Capture** - Screenshots, apps, URLs, music, location tracked continuously
- **AI-Powered Notes** - Vision LLM converts activity into structured Markdown
- **Knowledge Graph** - Entities connected with typed relationships (ABOUT_TOPIC, LISTENED_TO, etc.)
- **Semantic Search** - Find notes by meaning, not just keywords
- **Time-Aware Chat** - "What was I working on last Tuesday?" with grounded answers
- **Privacy-First** - All data stays local, raw screenshots deleted daily

---

## Requirements

- macOS 14.0+ (Sonoma or later)
- Python 3.11+
- Node.js 18+
- OpenAI API key

### Permissions Required

| Permission | Purpose |
|------------|---------|
| Screen Recording | Capture screenshots |
| Accessibility | Read window titles |
| Location Services | Track location (optional) |
| Automation | Read browser URLs |

---

## Installation

### Prerequisites

```bash
# Install uv (Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install Node.js dependencies
cd electron && npm install
```

### Setup

```bash
# Clone the repository
git clone https://github.com/junkim100/Trace.git
cd Trace

# Create Python environment
uv sync

# Set up environment variables
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY
```

### Running

```bash
# Start the Electron app (includes all services)
cd electron && npm start

# Or run Python services directly
uv run python -m src.core.services start
```

---

## Architecture

### Components

| Component | Description | Location |
|-----------|-------------|----------|
| **Capture Daemon** | Collects activity data every second | `src/capture/` |
| **Evidence Builder** | Extracts text via OCR and PDF parsing | `src/evidence/` |
| **Hourly Summarizer** | Generates hourly notes with Vision LLM | `src/summarize/` |
| **Daily Reviser** | Adds context, normalizes entities, builds graph | `src/revise/` |
| **Job Scheduler** | Manages hourly/daily processing jobs | `src/jobs/` |
| **Chat API** | Handles queries with retrieval + synthesis | `src/chat/` |
| **Service Manager** | Orchestrates all background services | `src/core/services.py` |
| **Electron Frontend** | Desktop UI with chat interface | `electron/` |

### Data Storage

```
Trace/
├── notes/YYYY/MM/DD/           # Durable Markdown notes
│   ├── hour-YYYYMMDD-HH.md     # Hourly summaries
│   └── day-YYYYMMDD.md         # Daily summaries
├── db/trace.sqlite             # Metadata, entities, graph, embeddings
├── cache/                      # Temporary (deleted daily)
│   ├── screenshots/            # Raw screenshots
│   ├── text_buffers/           # Extracted text
│   └── ocr/                    # OCR results
└── index/                      # Vector index (if external)
```

### LLM Models Used

| Task | Model | Purpose |
|------|-------|---------|
| Frame Triage | gpt-4o-mini | Score screenshot importance |
| OCR | gpt-4o-mini | Extract text from images |
| Hourly Summary | gpt-4o | Generate activity summaries with vision |
| Daily Revision | gpt-4o | Add context, normalize entities |
| Query Planning | gpt-4o-mini | Decompose complex queries |
| Answer Synthesis | gpt-4o-mini | Generate cited answers |
| Embeddings | text-embedding-3-small | Semantic search vectors |

---

## Documentation

- **[Architecture Overview](docs/architecture.md)** - System design and components
- **[LLM Pipeline](docs/llm-pipeline.md)** - AI models, prompts, and inputs
- **[Data Flow](docs/data-flow.md)** - How data moves through the system
- **[Database Schema](docs/database.md)** - Tables and relationships
- **[API Reference](docs/api.md)** - Chat and retrieval APIs

---

## Development

### Project Structure

```
src/
├── capture/        # Activity capture (screenshots, apps, URLs, music)
├── evidence/       # Text extraction (OCR, PDF)
├── summarize/      # Hourly summarization with Vision LLM
├── revise/         # Daily revision and entity normalization
├── jobs/           # Job scheduling (hourly, daily, backfill)
├── chat/           # Chat interface and query handling
│   └── agentic/    # Multi-step query planning
├── retrieval/      # Search (vector, graph, hierarchical)
├── graph/          # Edge building and traversal
├── db/             # Database operations
├── core/           # Service management, paths, utilities
└── platform/       # macOS-specific (notifications, sleep/wake)
```

### Running Tests

```bash
uv run pytest tests/
```

### Linting

```bash
uv run ruff check --fix src/
uv run ruff format src/
```

### CLI Commands

```bash
# Capture daemon
uv run python -m src.capture.daemon start

# Manual hourly summarization
uv run python -m src.jobs.hourly trigger --hour "2024-01-15 14:00"

# Manual daily revision
uv run python -m src.jobs.daily trigger --day "2024-01-15"

# Chat query
uv run python -m src.chat.api chat "What did I work on yesterday?"

# Service health
uv run python -m src.core.services status
```

---

## Privacy & Security

- **Local-only**: All data stored on your machine
- **No cloud sync**: Nothing sent to external servers (except OpenAI API calls)
- **Ephemeral artifacts**: Raw screenshots deleted daily after processing
- **Minimal retention**: Only structured notes and metadata kept long-term
- **API calls**: Only summarization uses OpenAI; images sent with `detail: low` when possible

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## License

[MIT](LICENSE)

---

## Acknowledgments

- Built with [OpenAI API](https://openai.com/api/)
- Vector search via [sqlite-vec](https://github.com/asg017/sqlite-vec)
- UI powered by [Electron](https://www.electronjs.org/) + [React](https://react.dev/)
