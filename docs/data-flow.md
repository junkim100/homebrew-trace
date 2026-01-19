# Data Flow

This document describes how data moves through the Trace system from capture to query.

## Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              DATA FLOW OVERVIEW                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  CAPTURE (every 1 second)                                                   │
│  ════════════════════════                                                   │
│      Screenshots ───────────────┐                                           │
│      Foreground App ────────────┤                                           │
│      Window Titles ─────────────┼───▶ events table + cache/screenshots/     │
│      Browser URLs ──────────────┤                                           │
│      Now Playing ───────────────┤                                           │
│      Location ──────────────────┘                                           │
│                                   │                                          │
│                                   ▼                                          │
│  HOURLY SUMMARIZATION (every hour)                                          │
│  ═════════════════════════════════                                          │
│      events ─────────────────────┐                                          │
│      screenshots ────────────────┼───▶ Vision LLM ───▶ notes table          │
│      text_buffers ───────────────┘              │          │                │
│                                                  │          ▼                │
│                                                  ▼     entities table        │
│                                          notes/YYYY/MM/DD/                   │
│                                          hour-YYYYMMDD-HH.md                 │
│                                   │                                          │
│                                   ▼                                          │
│  DAILY REVISION (once per day at 3 AM)                                      │
│  ═════════════════════════════════════                                      │
│      hourly notes ───────────────────▶ LLM ───▶ revised notes               │
│                                            │                                 │
│                                            ├───▶ edges table (graph)        │
│                                            ├───▶ aggregates table           │
│                                            └───▶ notes/day-YYYYMMDD.md      │
│                                   │                                          │
│                                   ▼                                          │
│  CLEANUP (after successful revision)                                        │
│  ═══════════════════════════════════                                        │
│      DELETE: cache/screenshots/YYYYMMDD/                                    │
│      DELETE: cache/text_buffers/YYYYMMDD/                                   │
│      DELETE: events older than 7 days                                       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Phase 1: Capture

### Trigger
- Capture daemon runs continuously at 1-second intervals
- Each tick captures a snapshot of current activity

### Data Captured

```
CaptureSnapshot
├── timestamp: datetime
├── foreground: ForegroundApp
│   ├── bundle_id: str
│   ├── app_name: str
│   ├── window_title: str
│   └── focused_monitor: int
├── screenshots: list[CapturedScreenshot]
│   ├── screenshot_id: str
│   ├── path: Path
│   ├── width/height: int
│   ├── monitor_id: int
│   └── timestamp: datetime
├── url: str | None
├── page_title: str | None
├── now_playing_json: str | None
│   └── {track, artist, album, app, is_playing, duration, elapsed}
├── location_text: str | None
└── event_closed: bool
```

### Storage

| Data | Destination | Retention |
|------|-------------|-----------|
| Screenshot files | `cache/screenshots/YYYYMMDD/` | Until daily cleanup |
| Screenshot metadata | `screenshots` table | Until daily cleanup |
| Event spans | `events` table | 7 days |
| Foreground info | Part of event | 7 days |
| URLs | Part of event | 7 days |
| Now Playing | Part of event (JSON) | 7 days |
| Location | Part of event | 7 days |

### Deduplication

Screenshots are deduplicated using perceptual hashing:

```
New Screenshot
      │
      ▼
┌─────────────────┐
│ Compute pHash   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     Similar      ┌─────────────────┐
│ Compare to last │ ───────────────▶ │ Delete file     │
│ (per monitor)   │                  │ Increment dedup │
└────────┬────────┘                  └─────────────────┘
         │ Different
         ▼
┌─────────────────┐
│ Store file      │
│ Update hash     │
│ Link to event   │
└─────────────────┘
```

### Event Span Tracking

Continuous activity is grouped into event spans:

```
Time:  14:00    14:02    14:05    14:10    14:15
       ──────────────────────────────────────────▶

       ┌─────────────┐    ┌────────────────────┐
App:   │   Safari    │    │    VS Code         │
       └─────────────┘    └────────────────────┘
              │                    │
              ▼                    ▼
Event 1: Safari (14:00-14:05)  Event 2: VS Code (14:05-14:15)
         url: python.org                window: main.py
```

## Phase 2: Hourly Summarization

### Trigger
- Scheduler fires at the top of each hour
- Processes the previous hour's data

### Input Aggregation

```
┌──────────────────────────────────────────────────────────────────┐
│                    EVIDENCE AGGREGATION                          │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  events table (hour window)                                      │
│  ───────────────────────────                                     │
│  ┌─────────┬───────────┬──────────────┬─────────────────┐       │
│  │event_id │ start_ts  │ app_name     │ window_title    │       │
│  ├─────────┼───────────┼──────────────┼─────────────────┤       │
│  │ ev-001  │ 14:00:23  │ VS Code      │ main.py         │       │
│  │ ev-002  │ 14:05:45  │ Chrome       │ Python Docs     │       │
│  └─────────┴───────────┴──────────────┴─────────────────┘       │
│                              │                                    │
│                              ▼                                    │
│  screenshots table ──────────┼──────────────────────────────────│
│                              │                                    │
│  text_buffers table ─────────┼──────────────────────────────────│
│                              │                                    │
│                              ▼                                    │
│  ┌────────────────────────────────────────────────────────┐     │
│  │                    HourlyEvidence                       │     │
│  │  hour_start: 2025-01-15 14:00:00                       │     │
│  │  hour_end: 2025-01-15 15:00:00                         │     │
│  │  events: [Event(...), Event(...)]                      │     │
│  │  screenshots: [ScreenshotCandidate(...), ...]          │     │
│  │  text_snippets: [TextSnippet(...), ...]                │     │
│  │  now_playing_spans: [NowPlayingSpan(...), ...]         │     │
│  │  locations: ["Home Office"]                            │     │
│  └────────────────────────────────────────────────────────┘     │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

### Keyframe Selection

```
245 Screenshots (1 hour)
         │
         ▼
┌─────────────────┐
│   Triage        │  Score each frame by importance
│   (heuristic    │  Categories: document, media, idle, etc.
│    or vision)   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Select        │  Pick top 10 representative frames
│   Keyframes     │  Ensure temporal coverage
│                 │  Prefer high-importance, unique content
└────────┬────────┘
         │
         ▼
10 Keyframes with paths, timestamps, descriptions
```

### LLM Processing

```
┌─────────────────────────────────────────────────────────────┐
│                     VISION LLM CALL                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Input:                                                      │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ System Prompt: Schema + guidelines                    │   │
│  ├──────────────────────────────────────────────────────┤   │
│  │ User Content:                                         │   │
│  │   - Activity timeline (text)                          │   │
│  │   - Keyframe observations (text)                      │   │
│  │   - Extracted text (OCR/PDF)                          │   │
│  │   - Media playing (text)                              │   │
│  │   - 10 screenshot images (base64, low detail)         │   │
│  └──────────────────────────────────────────────────────┘   │
│                              │                               │
│                              ▼                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              gpt-5-mini-2025-08-07                    │   │
│  └──────────────────────────────────────────────────────┘   │
│                              │                               │
│                              ▼                               │
│  Output:                                                     │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ HourlySummarySchema (JSON)                            │   │
│  │   summary, categories, activities, topics,            │   │
│  │   entities, media, documents, websites,               │   │
│  │   co_activities, open_loops, location                 │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Output Storage

```
LLM Output
    │
    ├───▶ Markdown file: notes/YYYY/MM/DD/hour-YYYYMMDD-HH.md
    │
    ├───▶ notes table:
    │     ┌──────────┬───────────┬───────────┬──────────────┐
    │     │ note_id  │ start_ts  │ file_path │ json_payload │
    │     └──────────┴───────────┴───────────┴──────────────┘
    │
    ├───▶ entities table (extracted):
    │     ┌───────────┬─────────────┬────────────────┐
    │     │ entity_id │ entity_type │ canonical_name │
    │     └───────────┴─────────────┴────────────────┘
    │
    ├───▶ note_entities table (links):
    │     ┌─────────┬───────────┬──────────┐
    │     │ note_id │ entity_id │ strength │
    │     └─────────┴───────────┴──────────┘
    │
    └───▶ embeddings:
          - Compute text-embedding-3-small
          - Store in sqlite-vec virtual table
```

## Phase 3: Daily Revision

### Trigger
- Daily scheduler fires at 3:00 AM
- Processes the previous day's hourly notes

### Input Collection

```
Load all hourly notes for day
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│  Notes: hour-20250115-00.md through hour-20250115-23.md     │
│                                                              │
│  For each note:                                              │
│    - note_id                                                 │
│    - hour (0-23)                                             │
│    - summary (HourlySummarySchema)                           │
│    - file_path                                               │
└─────────────────────────────────────────────────────────────┘
```

### LLM Processing

```
┌─────────────────────────────────────────────────────────────┐
│                    DAILY REVISION LLM                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Input:                                                      │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ System Prompt: Revision guidelines + graph edge types │   │
│  ├──────────────────────────────────────────────────────┤   │
│  │ User Content:                                         │   │
│  │   - Day overview statistics                           │   │
│  │   - All hourly notes with summaries, entities, etc.   │   │
│  │   - Revision instructions                             │   │
│  └──────────────────────────────────────────────────────┘   │
│                              │                               │
│                              ▼                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              gpt-5.2-2025-12-11                       │   │
│  └──────────────────────────────────────────────────────┘   │
│                              │                               │
│                              ▼                               │
│  Output:                                                     │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ DailyRevisionSchema (JSON)                            │   │
│  │   day_summary, hourly_revisions,                      │   │
│  │   entity_normalizations, graph_edges,                 │   │
│  │   top_entities, patterns                              │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Output Updates

```
Revision Output
    │
    ├───▶ Update hourly notes (revised summaries)
    │     - Re-render Markdown files
    │     - Update json_payload in notes table
    │
    ├───▶ Normalize entities
    │     - Merge duplicates (VS Code → Visual Studio Code)
    │     - Update canonical_name
    │     - Store aliases
    │
    ├───▶ Build graph edges:
    │     ┌───────────┬──────────┬───────────┬────────┐
    │     │ from_id   │ to_id    │ edge_type │ weight │
    │     ├───────────┼──────────┼───────────┼────────┤
    │     │ python    │ vs-code  │ USED_APP  │ 0.9    │
    │     │ python    │ lofi-girl│STUDIED_WHILE│ 0.7   │
    │     └───────────┴──────────┴───────────┴────────┘
    │
    ├───▶ Compute aggregates:
    │     ┌─────────────┬──────────┬───────────┬───────┐
    │     │ period_type │ key_type │ key       │ value │
    │     ├─────────────┼──────────┼───────────┼───────┤
    │     │ day         │ app      │ VS Code   │ 240   │
    │     │ day         │ topic    │ Python    │ 180   │
    │     └─────────────┴──────────┴───────────┴───────┘
    │
    └───▶ Generate daily summary note:
          notes/YYYY/MM/DD/day-YYYYMMDD.md
```

### Cleanup

After successful revision:

```
┌─────────────────────────────────────────────────────────────┐
│                    INTEGRITY CHECK                           │
├─────────────────────────────────────────────────────────────┤
│  ✓ All hourly notes exist                                   │
│  ✓ All embeddings computed                                  │
│  ✓ Graph edges stored                                       │
│  ✓ Aggregates computed                                      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼ (if passed)
┌─────────────────────────────────────────────────────────────┐
│                      DELETE                                  │
├─────────────────────────────────────────────────────────────┤
│  cache/screenshots/YYYYMMDD/  (raw screenshot files)        │
│  cache/text_buffers/YYYYMMDD/ (extracted text)              │
│  screenshots table entries for YYYYMMDD                     │
│  text_buffers table entries for YYYYMMDD                    │
│  events older than 7 days                                   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   LOG DELETION                               │
│  deletion_log: date, artifact_type, count, integrity_passed │
└─────────────────────────────────────────────────────────────┘
```

## Phase 4: Query Flow

### Query Processing

```
User Query: "What was I working on while listening to Lofi Girl last week?"
         │
         ▼
┌─────────────────┐
│ Time Filter     │  Parse "last week" → TimeFilter(start, end)
│ Parsing         │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Query           │  Is this complex? → Yes (relationship query)
│ Classification  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Query Planning  │  Generate execution plan
│ (LLM)           │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│                    EXECUTION PLAN                            │
├─────────────────────────────────────────────────────────────┤
│  Step 1: entity_search("Lofi Girl", time_filter=last_week)  │
│  Step 2: graph_expand(edges=["STUDIED_WHILE", "LISTENED_TO"])│
│  Step 3: merge_results                                       │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────┐
│ Plan Execution  │  Run steps (parallel where possible)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Answer          │  Generate response with citations
│ Synthesis       │
└────────┬────────┘
         │
         ▼
"You were primarily working on Python development while
listening to Lofi Girl last week [Note: 14:00 on 2025-01-10].
Specifically, you studied machine learning concepts and
wrote code in VS Code [Note: 15:00 on 2025-01-10]."
```

### Retrieval Strategies

```
Query
  │
  ├──▶ Vector Search (semantic similarity)
  │    └── notes table via sqlite-vec embeddings
  │
  ├──▶ Graph Expansion (relationships)
  │    └── edges table → related entities → linked notes
  │
  ├──▶ Aggregates Query (statistics)
  │    └── aggregates table → top apps, topics, etc.
  │
  ├──▶ Hierarchical Search (daily-first)
  │    └── daily summaries → hourly drilldown
  │
  └──▶ Time Filter (temporal constraints)
       └── SQL WHERE clause on start_ts/end_ts
```

## Data Retention Summary

| Data Type | Location | Retention |
|-----------|----------|-----------|
| Raw screenshots | `cache/screenshots/` | Until daily cleanup |
| Screenshot metadata | `screenshots` table | Until daily cleanup |
| Text buffers | `cache/text_buffers/` | Until daily cleanup |
| Events | `events` table | 7 days |
| Hourly notes | `notes/` + `notes` table | Permanent |
| Daily notes | `notes/` + `notes` table | Permanent |
| Entities | `entities` table | Permanent |
| Graph edges | `edges` table | Permanent |
| Aggregates | `aggregates` table | Permanent |
| Embeddings | sqlite-vec | Permanent |
