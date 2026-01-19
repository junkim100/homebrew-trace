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
Window titles        ─┼──▶  Hourly Summarization  ──▶     ├─ Entity Graph
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

- macOS 12.0+ (Monterey or later)
- OpenAI API key ([get one here](https://platform.openai.com/api-keys))

### Permissions Required

| Permission | Purpose | Required |
|------------|---------|----------|
| Screen Recording | Capture screenshots | Yes |
| Accessibility | Read window titles and active app | Yes |
| Location Services | Add location context to notes | No (optional) |
| Automation | Read browser URLs from Safari/Chrome | No (optional) |

---

## Download

### macOS

1. **Download** the latest `.dmg` from [GitHub Releases](https://github.com/junkim100/Trace/releases):
   - **Apple Silicon** (M1/M2/M3/M4): `Trace-x.x.x-arm64.dmg`
   - **Intel Macs**: `Trace-x.x.x-x64.dmg`

2. **Install** - Open the DMG and drag Trace to your Applications folder

3. **First Launch** (important for unsigned apps):
   - Right-click (or Control-click) on Trace in Applications
   - Click **"Open"**
   - Click **"Open"** again in the security dialog
   - *This is only needed once*

4. **Grant Permissions** when prompted:
   - **Screen Recording** - Click "Open System Settings" and enable Trace
   - **Accessibility** - Enable Trace in Privacy & Security settings
   - **Location Services** - Optional, enable if you want location in your notes

5. **Configure** - Set your OpenAI API key in the app's Settings

### Troubleshooting

**"Trace is damaged and can't be opened"**
```bash
xattr -cr /Applications/Trace.app
```
Then try opening again.

**Permissions not working**
1. Quit Trace completely
2. Go to System Settings → Privacy & Security
3. Remove Trace from the permission list
4. Reopen Trace and grant permissions again

**App won't start**
Check the logs at `~/Library/Application Support/Trace/logs/`

---

## Development Setup

> For contributors and developers only. Regular users should use the [Download](#download) section above.

### Prerequisites

- Python 3.11+
- Node.js 18+
- [uv](https://github.com/astral-sh/uv) package manager

```bash
# Install uv (Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone the repository
git clone https://github.com/junkim100/Trace.git
cd Trace

# Install Python dependencies
uv sync

# Install Node.js dependencies
cd electron && npm install
```

### Running in Development

```bash
# Start the Electron app (includes Python backend)
cd electron && npm start

# Or run Python backend separately
uv run python -m src.trace_app.cli serve
```

### Building for Distribution

```bash
# Build Python backend with PyInstaller
./build-python.sh

# Build Electron app
cd electron && npm run build && npx electron-builder --mac
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

All data is stored locally in `~/Library/Application Support/Trace/`:

```
~/Library/Application Support/Trace/
├── notes/YYYY/MM/DD/           # Durable Markdown notes
│   ├── hour-YYYYMMDD-HH.md     # Hourly summaries
│   └── day-YYYYMMDD.md         # Daily summaries
├── db/trace.sqlite             # Metadata, entities, graph, embeddings
├── cache/                      # Temporary (deleted daily)
│   ├── screenshots/            # Raw screenshots
│   ├── text_buffers/           # Extracted text
│   └── ocr/                    # OCR results
├── logs/                       # Application logs
└── index/                      # Vector index (if external)
```

### LLM Models Used

| Task | Model | Purpose |
|------|-------|---------|
| Frame Triage | gpt-5-nano-2025-08-07 | Score screenshot importance (heuristic by default) |
| OCR | gpt-5-nano-2025-08-07 | Extract text from document screenshots |
| Hourly Summary | gpt-5-mini-2025-08-07 | Generate activity summaries with vision |
| Daily Revision | gpt-5.2-2025-12-11 | Add context, normalize entities, build graph |
| Query Planning | gpt-4o | Decompose complex queries |
| Answer Synthesis | gpt-5.2-2025-12-11 | Generate cited answers |
| Embeddings | text-embedding-3-small | Semantic search vectors (1536 dims) |

### Expected API Cost

For a typical day with **10 hours of screen time**:

| Stage | API Calls | Est. Cost |
|-------|-----------|-----------|
| Hourly Summarization | 10 (1 per hour) | ~$0.15 |
| Daily Revision | 1 | ~$0.05 |
| Embeddings | 11 | ~$0.00 |
| OCR (document detection) | ~5 | ~$0.001 |
| **Total per day** | | **~$0.20** |

**Monthly estimate**: ~$6/month for regular daily use

Cost factors:
- More screen time → +$0.015/hour
- Heavy document reading → +$0.001/document
- Chat queries → ~$0.001-0.005/query

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
# Start all services (capture, scheduler)
uv run python -m src.trace_app.cli serve

# Check service status
uv run python -m src.core.services status

# Manual hourly summarization
uv run python -m src.jobs.hourly trigger --hour "2024-01-15 14:00"

# Manual daily revision
uv run python -m src.jobs.daily trigger --day "2024-01-15"

# Chat query (CLI)
uv run python -m src.chat.api chat "What did I work on yesterday?"
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
