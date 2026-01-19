# Database Schema

This document describes the SQLite database schema used by Trace.

## Overview

Trace uses a single SQLite database (`db/trace.sqlite`) with the sqlite-vec extension for vector embeddings. The schema supports:

- **Notes and entities** - Core knowledge storage
- **Graph edges** - Typed relationships between entities
- **Capture data** - Temporary activity captures
- **Job tracking** - Processing job management
- **Analytics** - Pre-computed aggregates

## Entity Relationship Diagram

```
┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│     notes       │──────▶│  note_entities  │◀──────│    entities     │
│                 │ 1:N   │                 │ N:1   │                 │
│  note_id (PK)   │       │  note_id (FK)   │       │ entity_id (PK)  │
│  note_type      │       │  entity_id (FK) │       │ entity_type     │
│  start_ts       │       │  strength       │       │ canonical_name  │
│  end_ts         │       │  context        │       │ aliases         │
│  file_path      │       └─────────────────┘       └────────┬────────┘
│  json_payload   │                                          │
│  embedding_id   │───────────────────────────────────────┐  │
└─────────────────┘                                       │  │
                                                          │  │
┌─────────────────┐       ┌─────────────────┐             │  │
│     edges       │       │   embeddings    │◀──────────-─┘  │
│                 │       │                 │                │
│  from_id (PK)   │◀──────│ embedding_id(PK)│                │
│  to_id (PK)     │◀──────│ source_type     │                │
│  edge_type (PK) │       │ source_id       │◀──────────────-┘
│  weight         │       │ model_name      │
│  evidence_notes │       │ dimensions      │
└─────────────────┘       └─────────────────┘

┌─────────────────┐       ┌─────────────────┐
│     events      │◀──────│  screenshots    │
│                 │ 1:N   │                 │
│  event_id (PK)  │       │ screenshot_id   │
│  start_ts       │       │ ts              │
│  app_name       │       │ path            │
│  window_title   │       │ fingerprint     │
│  url            │       │ diff_score      │
│  evidence_ids   │       └─────────────────┘
└─────────────────┘
         │
         │ linked via JSON
         ▼
┌─────────────────┐
│  text_buffers   │
│                 │
│  text_id (PK)   │
│  source_type    │
│  compressed_text│
│  event_id (FK)  │
└─────────────────┘
```

## Core Tables

### notes

Stores hourly and daily summary notes.

```sql
CREATE TABLE notes (
    note_id TEXT PRIMARY KEY,
    note_type TEXT NOT NULL CHECK (note_type IN ('hour', 'day')),
    start_ts TEXT NOT NULL,              -- ISO-8601 timestamp
    end_ts TEXT NOT NULL,                -- ISO-8601 timestamp
    file_path TEXT NOT NULL,             -- Path to Markdown file
    json_payload TEXT NOT NULL,          -- Validated structured output from LLM
    embedding_id TEXT,                   -- Reference to embedding
    created_ts TEXT NOT NULL DEFAULT (datetime('now')),
    updated_ts TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_notes_type ON notes(note_type);
CREATE INDEX idx_notes_time ON notes(start_ts, end_ts);
CREATE INDEX idx_notes_file_path ON notes(file_path);
```

**Fields:**
| Field | Type | Description |
|-------|------|-------------|
| `note_id` | TEXT | UUID primary key |
| `note_type` | TEXT | Either 'hour' or 'day' |
| `start_ts` | TEXT | Start of time window (ISO-8601) |
| `end_ts` | TEXT | End of time window (ISO-8601) |
| `file_path` | TEXT | Path to Markdown file on disk |
| `json_payload` | TEXT | Complete LLM output as JSON |
| `embedding_id` | TEXT | Reference to vector embedding |

### entities

Normalized entities extracted from notes.

```sql
CREATE TABLE entities (
    entity_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    aliases TEXT,                        -- JSON array of alternate names
    created_ts TEXT NOT NULL DEFAULT (datetime('now')),
    updated_ts TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_entities_type ON entities(entity_type);
CREATE INDEX idx_entities_name ON entities(canonical_name);
```

**Entity Types:**
| Type | Description | Examples |
|------|-------------|----------|
| `topic` | Abstract subjects | Python, machine learning |
| `app` | Applications | Visual Studio Code, Safari |
| `domain` | Web domains | github.com, stackoverflow.com |
| `document` | Specific files | report.pdf, main.py |
| `artist` | Musicians | Lofi Girl, Taylor Swift |
| `track` | Songs | Study Beats, Song Name |
| `video` | Videos/shows | Tutorial, Movie |
| `game` | Games | Minecraft, Chess.com |
| `person` | People | John, Team Lead |
| `project` | Projects | Trace, Client Project |

### note_entities

Many-to-many relationship between notes and entities.

```sql
CREATE TABLE note_entities (
    note_id TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    strength REAL NOT NULL CHECK (strength >= 0 AND strength <= 1),
    context TEXT,
    PRIMARY KEY (note_id, entity_id),
    FOREIGN KEY (note_id) REFERENCES notes(note_id) ON DELETE CASCADE,
    FOREIGN KEY (entity_id) REFERENCES entities(entity_id) ON DELETE CASCADE
);

CREATE INDEX idx_note_entities_entity ON note_entities(entity_id);
```

**Fields:**
| Field | Type | Description |
|-------|------|-------------|
| `strength` | REAL | Association strength (0.0-1.0) |
| `context` | TEXT | Optional context about the association |

### edges

Typed, weighted edges for the relationship graph.

```sql
CREATE TABLE edges (
    from_id TEXT NOT NULL,
    to_id TEXT NOT NULL,
    edge_type TEXT NOT NULL CHECK (edge_type IN (
        'ABOUT_TOPIC', 'WATCHED', 'LISTENED_TO', 'USED_APP',
        'VISITED_DOMAIN', 'DOC_REFERENCE', 'CO_OCCURRED_WITH', 'STUDIED_WHILE'
    )),
    weight REAL NOT NULL CHECK (weight >= 0),
    start_ts TEXT,
    end_ts TEXT,
    evidence_note_ids TEXT,              -- JSON list of note_ids
    created_ts TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (from_id, to_id, edge_type)
);

CREATE INDEX idx_edges_from ON edges(from_id);
CREATE INDEX idx_edges_to ON edges(to_id);
CREATE INDEX idx_edges_type ON edges(edge_type);
CREATE INDEX idx_edges_time ON edges(start_ts, end_ts);
```

**Edge Types:**
| Type | Description | Example |
|------|-------------|---------|
| `ABOUT_TOPIC` | Entity relates to topic | Python → machine learning |
| `WATCHED` | User watched media | User → Tutorial Video |
| `LISTENED_TO` | User listened to audio | User → Study Beats |
| `USED_APP` | Topic/project used app | Python → VS Code |
| `VISITED_DOMAIN` | Topic visited domain | Research → arxiv.org |
| `DOC_REFERENCE` | Document references entity | report.pdf → dataset |
| `CO_OCCURRED_WITH` | Entities appeared together | Spotify → Coding |
| `STUDIED_WHILE` | Learning with activity | ML Course → Lofi Girl |

## Capture Tables (Transient)

### events

Time-ranged activity spans.

```sql
CREATE TABLE events (
    event_id TEXT PRIMARY KEY,
    start_ts TEXT NOT NULL,
    end_ts TEXT NOT NULL,
    app_id TEXT,                         -- Bundle ID
    app_name TEXT,
    window_title TEXT,
    focused_monitor INTEGER,
    url TEXT,
    page_title TEXT,
    file_path TEXT,
    location_text TEXT,
    now_playing_json TEXT,               -- JSON: {track, artist, album, app}
    evidence_ids TEXT,                   -- JSON list of screenshot_ids
    created_ts TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_events_time ON events(start_ts, end_ts);
CREATE INDEX idx_events_app ON events(app_id);
```

### screenshots

Captured screen frames.

```sql
CREATE TABLE screenshots (
    screenshot_id TEXT PRIMARY KEY,
    ts TEXT NOT NULL,
    monitor_id INTEGER NOT NULL,
    path TEXT NOT NULL,
    fingerprint TEXT NOT NULL,           -- Perceptual hash
    diff_score REAL NOT NULL,
    width INTEGER,
    height INTEGER,
    created_ts TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_screenshots_ts ON screenshots(ts);
CREATE INDEX idx_screenshots_monitor ON screenshots(monitor_id);
CREATE INDEX idx_screenshots_fingerprint ON screenshots(fingerprint);
```

### text_buffers

Extracted text (deleted daily).

```sql
CREATE TABLE text_buffers (
    text_id TEXT PRIMARY KEY,
    ts TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN ('pdf_extract', 'ocr', 'web_content')),
    ref TEXT,                            -- File path or screenshot_id
    compressed_text BLOB NOT NULL,       -- zlib compressed
    token_estimate INTEGER NOT NULL,
    event_id TEXT,
    created_ts TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (event_id) REFERENCES events(event_id) ON DELETE SET NULL
);

CREATE INDEX idx_text_buffers_ts ON text_buffers(ts);
CREATE INDEX idx_text_buffers_source ON text_buffers(source_type);
```

## Processing Tables

### jobs

Track processing jobs.

```sql
CREATE TABLE jobs (
    job_id TEXT PRIMARY KEY,
    job_type TEXT NOT NULL CHECK (job_type IN ('hourly', 'daily', 'embedding', 'cleanup')),
    window_start_ts TEXT NOT NULL,
    window_end_ts TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'success', 'failed')),
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    result_json TEXT,
    created_ts TEXT NOT NULL DEFAULT (datetime('now')),
    updated_ts TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_jobs_type_status ON jobs(job_type, status);
CREATE INDEX idx_jobs_window ON jobs(window_start_ts, window_end_ts);
```

### aggregates

Pre-computed rollups for analytics.

```sql
CREATE TABLE aggregates (
    agg_id TEXT PRIMARY KEY,
    period_type TEXT NOT NULL CHECK (period_type IN ('day', 'week', 'month', 'year')),
    period_start_ts TEXT NOT NULL,
    period_end_ts TEXT NOT NULL,
    key_type TEXT NOT NULL,              -- category, entity, app, domain
    key TEXT NOT NULL,
    value_num REAL NOT NULL,             -- Duration in minutes
    extra_json TEXT,
    created_ts TEXT NOT NULL DEFAULT (datetime('now')),
    updated_ts TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_aggregates_period ON aggregates(period_type, period_start_ts);
CREATE INDEX idx_aggregates_key ON aggregates(key_type, key);
```

**Key Types:**
| Type | Description |
|------|-------------|
| `app` | Time per application |
| `domain` | Time per website |
| `category` | Time per activity category |
| `entity` | Time per entity |
| `co_activity` | Time for paired activities |

## Embeddings

### embeddings (metadata)

```sql
CREATE TABLE embeddings (
    embedding_id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL CHECK (source_type IN ('note', 'entity', 'query')),
    source_id TEXT NOT NULL,
    model_name TEXT NOT NULL,
    dimensions INTEGER NOT NULL,
    created_ts TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_embeddings_source ON embeddings(source_type, source_id);
```

### sqlite-vec Virtual Table

Vector embeddings are stored in a sqlite-vec virtual table:

```sql
-- Created by sqlite-vec extension
CREATE VIRTUAL TABLE vec_embeddings USING vec0(
    embedding_id TEXT PRIMARY KEY,
    embedding FLOAT[1536]
);
```

**Search Query:**
```sql
SELECT e.embedding_id, e.source_id, distance
FROM vec_embeddings AS v
JOIN embeddings AS e ON v.embedding_id = e.embedding_id
WHERE v.embedding MATCH ?
  AND k = 10
ORDER BY distance
```

## Integrity Tracking

### deletion_log

Audit trail for artifact deletion.

```sql
CREATE TABLE deletion_log (
    deletion_id TEXT PRIMARY KEY,
    deletion_date TEXT NOT NULL,         -- YYYYMMDD
    artifact_type TEXT NOT NULL,
    artifact_count INTEGER NOT NULL,
    integrity_passed INTEGER NOT NULL,   -- 1 = true
    created_ts TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_deletion_log_date ON deletion_log(deletion_date);
```

### schema_version

Track schema migrations.

```sql
CREATE TABLE schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now')),
    description TEXT
);
```

## Common Queries

### Find notes by time range

```sql
SELECT * FROM notes
WHERE start_ts >= '2025-01-15T00:00:00'
  AND end_ts <= '2025-01-16T00:00:00'
ORDER BY start_ts;
```

### Get entities for a note

```sql
SELECT e.*, ne.strength
FROM entities e
JOIN note_entities ne ON e.entity_id = ne.entity_id
WHERE ne.note_id = ?
ORDER BY ne.strength DESC;
```

### Find related entities via graph

```sql
SELECT e.*, edges.edge_type, edges.weight
FROM edges
JOIN entities e ON edges.to_id = e.entity_id
WHERE edges.from_id = ?
ORDER BY edges.weight DESC;
```

### Get top apps by time

```sql
SELECT key, SUM(value_num) as total_minutes
FROM aggregates
WHERE key_type = 'app'
  AND period_start_ts >= '2025-01-01'
GROUP BY key
ORDER BY total_minutes DESC
LIMIT 10;
```

### Semantic search

```sql
-- Get embedding for query
-- Then search via sqlite-vec:
SELECT n.*, v.distance
FROM vec_embeddings v
JOIN embeddings e ON v.embedding_id = e.embedding_id
JOIN notes n ON e.source_id = n.note_id
WHERE v.embedding MATCH :query_embedding
  AND k = 10
  AND n.start_ts >= :time_start
ORDER BY v.distance;
```

## Migrations

Schema migrations are tracked in `schema_version` table. The migration system:

1. Checks current version on startup
2. Applies any pending migrations
3. Updates version number

Current schema version: **1**

Migration files: `src/db/migrations.py`
