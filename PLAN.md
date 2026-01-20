# Implementation Plan: Trace MVP

## Context

This plan is derived from [PRD.md](PRD.md) and clarifying discussions. Trace is a macOS app that captures digital activity, generates Markdown notes, builds a relationship graph, and provides time-aware chat/search.

**Tech Stack**:
- Backend: Python 3.11+
- Frontend: Electron + React
- Database: SQLite with sqlite-vec for embeddings
- LLM: OpenAI API (gpt-5-nano, gpt-5-mini, gpt-5.2)
- OCR: LLM-based (OpenAI vision API)

## Scope

MVP delivers:
1. Always-on capture daemon (screenshots, app metadata, now playing, location, URLs)
2. Real-time document text extraction
3. Hourly note generation with entity extraction
4. Daily revision with graph building
5. Desktop chat UI with time filtering
6. Automatic deletion of raw artifacts after successful processing

## Tasks

### Phase 1: Project Setup

| ID | Description | Files/Modules | Acceptance Criteria | Status |
|----|-------------|---------------|---------------------|--------|
| P1-01 | Initialize Python project with pyproject.toml, dependencies | `pyproject.toml`, `requirements.txt` | Poetry/pip install works, Python 3.11+ | [x] |
| P1-02 | Initialize Electron app scaffold | `electron/`, `package.json` | `npm start` launches empty Electron window | [x] |
| P1-03 | Set up Python-Electron IPC bridge | `src/trace_app/ipc/`, `electron/preload.js` | Electron can call Python functions and receive responses | [x] |
| P1-04 | Create SQLite schema and migrations | `src/db/schema.sql`, `src/db/migrations/` | All tables from PRD created, migrations versioned | [x] |
| P1-05 | Implement sqlite-vec integration | `src/db/vectors.py` | Can store and query 1536-dim embeddings | [x] |
| P1-06 | Set up data directories structure | `src/core/paths.py` | Creates `notes/`, `db/`, `cache/` directories on first run | [x] |

### Phase 2: Permissions & System Integration

| ID | Description | Files/Modules | Acceptance Criteria | Status |
|----|-------------|---------------|---------------------|--------|
| P2-01 | Implement macOS permission checker | `src/platform/permissions.py` | Detects Screen Recording, Accessibility, Location status | [x] |
| P2-02 | Create permission request UI flow | `electron/src/pages/permissions/` | Shows permission instructions, blocks until all granted | [x] |
| P2-03 | Implement permission polling/callback | `src/platform/permissions.py`, `electron/src/pages/permissions/` | App detects when permissions are granted without restart | [x] |

### Phase 3: Capture Daemon

| ID | Description | Files/Modules | Acceptance Criteria | Status |
|----|-------------|---------------|---------------------|--------|
| P3-01 | Multi-monitor screenshot capture | `src/capture/screenshots.py` | Captures all monitors every 1s, downscales to ≤1080p | [x] |
| P3-02 | Screenshot deduplication | `src/capture/dedup.py` | Computes perceptual hash, skips storing if diff < threshold | [x] |
| P3-03 | Foreground app/window metadata capture | `src/capture/foreground.py` | Captures bundle ID, app name, window title, monitor ID | [x] |
| P3-04 | Event span tracking | `src/capture/events.py` | Creates/updates event spans on app/window transitions | [x] |
| P3-05 | Now playing capture (Spotify) | `src/capture/now_playing.py` | Captures track, artist, album from Spotify via AppleScript | [x] |
| P3-06 | Now playing capture (Apple Music) | `src/capture/now_playing.py` | Captures track, artist, album from Music.app | [x] |
| P3-07 | Location capture | `src/capture/location.py` | Captures OS location snapshots with timestamps | [x] |
| P3-08 | Safari URL capture | `src/capture/urls.py` | Gets current URL/title from Safari via AppleScript | [x] |
| P3-09 | Chrome URL capture | `src/capture/urls.py` | Gets current URL/title from Chrome via CDP or AppleScript | [x] |
| P3-10 | Capture daemon orchestrator | `src/capture/daemon.py` | Coordinates all capture at 1s intervals, writes to SQLite | [x] |

### Phase 4: Evidence Builder

| ID | Description | Files/Modules | Acceptance Criteria | Status |
|----|-------------|---------------|---------------------|--------|
| P4-01 | Document context detector | `src/evidence/detector.py` | Detects PDF viewers, document editors from app/window info | [x] |
| P4-02 | PDF text extraction | `src/evidence/pdf.py` | Extracts text from PDF when file path is known | [x] |
| P4-03 | LLM-based OCR for screenshots | `src/evidence/ocr.py` | Sends screenshot to OpenAI vision API, extracts text | [x] |
| P4-04 | Text buffer storage | `src/evidence/buffers.py` | Stores compressed text buffers linked to time spans | [x] |
| P4-05 | Evidence builder orchestrator | `src/evidence/builder.py` | Triggers extraction on document context, manages buffers | [x] |

### Phase 5: Hourly Summarization

| ID | Description | Files/Modules | Acceptance Criteria | Status |
|----|-------------|---------------|---------------------|--------|
| P5-01 | Frame triage with gpt-5-nano | `src/summarize/triage.py` | Classifies screenshots, scores importance for keyframe selection | [x] |
| P5-02 | Keyframe selection algorithm | `src/summarize/keyframes.py` | Selects representative frames (transitions, high-diff, anchors) | [x] |
| P5-03 | Evidence aggregation for hour | `src/summarize/evidence.py` | Builds timeline, selects text snippets within token budget | [x] |
| P5-04 | Hourly summarization prompt | `src/summarize/prompts/hourly.py` | Structured prompt with schema for gpt-5-mini | [x] |
| P5-05 | JSON schema validation | `src/summarize/schemas.py` | Validates LLM output against versioned schema, retries once | [x] |
| P5-06 | Markdown note renderer | `src/summarize/render.py` | Converts validated JSON to Markdown with YAML frontmatter | [x] |
| P5-07 | Entity extraction and storage | `src/summarize/entities.py` | Extracts entities from JSON, normalizes, stores in DB | [x] |
| P5-08 | Embedding computation | `src/summarize/embeddings.py` | Computes embeddings for note, stores via sqlite-vec | [x] |
| P5-09 | Hourly job scheduler | `src/jobs/hourly.py` | APScheduler job runs every hour, creates pending jobs | [x] |
| P5-10 | Hourly job executor | `src/jobs/hourly.py` | Executes hourly summarization, updates job status | [x] |

### Phase 6: Daily Revision & Graph

| ID | Description | Files/Modules | Acceptance Criteria | Status |
|----|-------------|---------------|---------------------|--------|
| P6-01 | Daily revision prompt | `src/revise/prompts/daily.py` | Prompt for gpt-5.2 with full day context | [x] |
| P6-02 | Entity normalization | `src/revise/normalize.py` | Deduplicates and normalizes entity names across notes | [x] |
| P6-03 | Hourly note revision | `src/revise/revise.py` | Updates hourly notes with day context, refreshes files | [x] |
| P6-04 | Daily summary note generation | `src/revise/daily_note.py` | Generates optional day-YYYYMMDD.md summary | [x] |
| P6-05 | Graph edge builder | `src/graph/edges.py` | Creates typed edges (ABOUT_TOPIC, WATCHED, etc.) with weights | [x] |
| P6-06 | Embedding refresh | `src/revise/embeddings.py` | Recomputes embeddings for revised notes | [x] |
| P6-07 | Aggregates computation | `src/revise/aggregates.py` | Computes daily rollups for "most" queries | [x] |
| P6-08 | Integrity checkpoint | `src/revise/integrity.py` | Validates all notes, embeddings, edges before deletion | [x] |
| P6-09 | Raw artifact deletion | `src/revise/cleanup.py` | Deletes screenshots, text buffers, OCR cache after checkpoint | [x] |
| P6-10 | Daily job scheduler | `src/jobs/daily.py` | APScheduler job runs once per day | [x] |

### Phase 7: Retrieval & Chat

| ID | Description | Files/Modules | Acceptance Criteria | Status |
|----|-------------|---------------|---------------------|--------|
| P7-01 | Time filter parser | `src/retrieval/time.py` | Parses natural language time references to date ranges | [x] |
| P7-02 | Vector search | `src/retrieval/search.py` | Searches notes by embedding similarity within time range | [x] |
| P7-03 | Graph expansion | `src/retrieval/graph.py` | Expands results using typed edges and weights | [x] |
| P7-04 | Aggregates lookup | `src/retrieval/aggregates.py` | Handles "most watched/listened" queries via aggregates table | [x] |
| P7-05 | Answer synthesis prompt | `src/chat/prompts/answer.py` | Generates grounded answer with citations | [x] |
| P7-06 | Chat API endpoint | `src/chat/api.py` | Python endpoint for chat queries | [x] |

### Phase 8: Desktop UI

| ID | Description | Files/Modules | Acceptance Criteria | Status |
|----|-------------|---------------|---------------------|--------|
| P8-01 | Electron main process setup | `electron/main.js` | Launches Python backend, manages lifecycle | [x] |
| P8-02 | React app scaffold | `electron/src/` | Basic React app with routing | [x] |
| P8-03 | Chat input component | `electron/src/components/ChatInput.tsx` | Text input with submit | [x] |
| P8-04 | Time filter component | `electron/src/components/TimeFilter.tsx` | Date picker, quick presets (today, this week, etc.) | [x] |
| P8-05 | Results list component | `electron/src/components/Results.tsx` | Shows relevant notes with timestamps | [x] |
| P8-06 | Note viewer component | `electron/src/components/NoteViewer.tsx` | Opens and displays Markdown note files | [x] |
| P8-07 | Answer display component | `electron/src/components/Answer.tsx` | Shows synthesized answer with citations | [x] |
| P8-08 | System tray integration | `electron/main.js` | Menu bar icon, quick access, status indicator | [x] |
| P8-09 | Settings UI | `electron/src/pages/Settings.tsx` | LLM API key config, data directory path | [x] |

### Phase 9: Integration & Polish

| ID | Description | Files/Modules | Acceptance Criteria | Status |
|----|-------------|---------------|---------------------|--------|
| P9-01 | End-to-end capture test | `tests/e2e/test_capture.py` | Capture daemon runs for 5 minutes, data persisted | [x] |
| P9-02 | End-to-end summarization test | `tests/e2e/test_summarize.py` | Hourly note generated from test data | [x] |
| P9-03 | End-to-end chat test | `tests/e2e/test_chat.py` | Query returns relevant notes with citations | [x] |
| P9-04 | Error handling & retry logic | `src/core/retry.py` | LLM failures retry with exponential backoff | [x] |
| P9-05 | Logging infrastructure | `src/core/logging.py` | Structured logging to file and console | [x] |
| P9-06 | App packaging | `electron-builder.yml` | Builds .dmg for macOS distribution | [x] |
| P9-07 | GitHub release workflow | `.github/workflows/release.yml` | CI builds and publishes releases | [x] |

## Risks and Open Questions

### Risks

1. **Screen Recording permission UX**: macOS requires app restart after granting Screen Recording. May need to guide users through this clearly.

2. **Chrome CDP reliability**: Chrome DevTools Protocol requires Chrome to be launched with remote debugging flag, or use AppleScript fallback which is less reliable.

3. **LLM API latency**: Hourly summarization with vision models may take 30-60 seconds. Need async processing to not block capture.

4. **Token budget management**: Large hours (many screenshots, long documents) may exceed token limits. Need robust truncation strategy.

5. **sqlite-vec compatibility**: Ensure sqlite-vec extension works reliably across macOS versions.

### Open Questions

1. **Fallback note format**: When LLM is unavailable for extended periods, what minimal template should be generated? Just activity timeline?

2. **Entity merge strategy**: When daily revision normalizes entities, how to handle conflicts? Prefer most frequent name? Most recent?

3. **Graph edge weights**: What formula for edge weights? Time duration, frequency, or model-assigned confidence?

4. **Embedding model**: Use OpenAI text-embedding-3-small (1536 dims) or text-embedding-3-large (3072 dims)?

5. **Multi-user support**: PRD assumes single user. Should data directories support multiple profiles for shared machines?

---

## Future Enhancements

### Phase 10: User Experience & Privacy

| ID | Description | Files/Modules | Acceptance Criteria | Status |
|----|-------------|---------------|---------------------|--------|
| P10-01 | Selective capture blocklist | `src/capture/blocklist.py`, `electron/src/pages/Settings.tsx` | Users can block specific apps/domains from capture (banking, medical) | [x] |
| P10-02 | Export/backup functionality | `src/core/export.py` | Export all notes and graph to portable format (JSON, Markdown archive) | [x] |
| P10-03 | Open loop tracking UI | `electron/src/components/OpenLoops.tsx` | Surface incomplete tasks from notes with optional reminders | [x] |
| P10-04 | Graph visualization UI | `electron/src/pages/Graph.tsx` | Interactive knowledge graph explorer in desktop app | [x] |

### Phase 11: Platform Integration

| ID | Description | Files/Modules | Acceptance Criteria | Status |
|----|-------------|---------------|---------------------|--------|
| P11-01 | Spotlight integration | `src/platform/spotlight.py` | macOS Spotlight can search Trace notes | [x] |
| P11-02 | Global keyboard shortcuts | `electron/main.js`, `src/platform/shortcuts.py` | Hotkey to open chat, quick capture annotations | [x] |
| P11-03 | Menu bar quick actions | `electron/main.js` | Quick access to recent notes, current activity status | [x] |

### Phase 12: Analytics & Insights

| ID | Description | Files/Modules | Acceptance Criteria | Status |
|----|-------------|---------------|---------------------|--------|
| P12-01 | Activity dashboard | `electron/src/pages/Dashboard.tsx` | Visualizations: time per app/topic, trends, heatmaps | [ ] |
| P12-02 | Weekly digest | `src/insights/digest.py`, `src/platform/notifications.py` | Automated weekly summary notification | [ ] |
| P12-03 | Pattern detection | `src/insights/patterns.py` | Surface productivity patterns ("You code best in mornings") | [ ] |

### Phase 13: Future Platform Expansion

| ID | Description | Files/Modules | Acceptance Criteria | Status |
|----|-------------|---------------|---------------------|--------|
| P13-01 | iOS companion app | `ios/` | Read-only app for querying notes on mobile | [ ] |
| P13-02 | iCloud sync | `src/sync/icloud.py` | Optional sync of notes (not raw data) across devices | [ ] |
| P13-03 | Data retention policies | `src/core/retention.py`, `electron/src/pages/Settings.tsx` | Configurable auto-deletion of old notes (e.g., keep 1 year) | [ ] |
