# LLM Pipeline

This document details the AI models, prompts, and inputs used throughout Trace's processing pipeline.

## Model Usage Overview

| Stage | Model | Purpose | Input | Output |
|-------|-------|---------|-------|--------|
| Frame Triage | gpt-5-nano-2025-08-07 | Score screenshot importance | Screenshot + context | Category + score |
| OCR | gpt-5-nano-2025-08-07 | Extract text from images | Screenshot | Extracted text |
| Hourly Summary | gpt-5-mini-2025-08-07 | Generate activity notes | Screenshots + timeline | Structured JSON |
| Daily Revision | gpt-5.2-2025-12-11 | Add context, normalize | Hourly notes | Revised JSON |
| Query Planning | gpt-4o | Decompose complex queries | User query | Execution plan |
| Answer Synthesis | gpt-5.2-2025-12-11 | Generate cited answers | Notes + context | Answer text |
| Embeddings | text-embedding-3-small | Semantic search vectors | Note text | 1536-dim vector |

## Expected API Cost

For a typical day with **10 hours of screen time**:

| Stage | API Calls/Day | Tokens (approx) | Est. Cost |
|-------|---------------|-----------------|-----------|
| Hourly Summarization | 10 | 20K input + 100 images + 8K output | ~$0.15 |
| Daily Revision | 1 | 8K input + 3K output | ~$0.05 |
| Embeddings | 11 | 4.4K tokens | ~$0.00 |
| OCR (document detection) | ~5 | 5 images + 1K output | ~$0.001 |
| Frame Triage | 0 (heuristic default) | - | $0.00 |
| **Total per day** | | | **~$0.20** |

**Monthly estimate**: ~$6/month for regular daily use
**Annual estimate**: ~$73/year

### Cost Variables

| Factor | Impact |
|--------|--------|
| Additional screen time | +$0.015/hour |
| Document reading (triggers OCR) | +$0.001/document |
| Chat queries | ~$0.001-0.005/query |
| Vision triage enabled | +$0.01/hour |

### Cost Optimization Strategies

| Strategy | Implementation |
|----------|----------------|
| Low detail images | `detail: "low"` for all vision API calls |
| Heuristic triage | Skip API for obvious frames (default behavior) |
| Batch embeddings | Process multiple notes together |
| Model selection | Use nano/mini models where possible |
| Token budgeting | Truncate long text inputs |
| Caching | Skip re-processing existing notes |

## 1. Frame Triage

**Purpose**: Classify and score screenshots for keyframe selection.

**Model**: `gpt-5-nano-2025-08-07` (fast, cheap vision model)

**Input**:
- Screenshot image (base64 encoded, low detail)
- Optional context: app name, window title

**System Prompt**:
```
You are a screenshot classifier for a personal activity tracker.

Analyze the screenshot and provide a JSON response with:
1. category: One of [transition, document, media, browsing, idle, communication, creative, gaming, other]
2. importance_score: 0.0 to 1.0 indicating how representative/important this frame is
3. description: Brief (1-2 sentences) description of what's visible
4. has_text: boolean - is there significant readable text on screen?
5. has_document: boolean - is a document, code file, or PDF being viewed?
6. has_media: boolean - is video/streaming content visible?

Scoring guidelines:
- High (0.8-1.0): Clear activity, transition moment, important content visible
- Medium (0.5-0.7): Normal activity, some useful context
- Low (0.2-0.4): Static content, minimal activity
- Very low (0.0-0.2): Idle, locked screen, screensaver
```

**Output Schema**:
```json
{
  "category": "document",
  "importance_score": 0.75,
  "description": "VS Code editor with Python file open",
  "has_text": true,
  "has_document": true,
  "has_media": false
}
```

**Heuristic Fallback**: When API is unavailable, a rule-based triager uses app bundle ID and window title to estimate importance.

## 2. Hourly Summarization

**Purpose**: Convert raw activity data into structured notes.

**Model**: `gpt-5-mini-2025-08-07` (vision-capable)

**Input Components**:

1. **Activity Timeline** - Structured text showing:
   - Event timestamps and durations
   - App names and window titles
   - Browser URLs visited
   - Files accessed

2. **Keyframe Observations** - For each selected screenshot:
   - Timestamp
   - Triage description
   - App/window context

3. **Extracted Text** - From OCR or PDF extraction:
   - Source type (pdf_extract, ocr, web_content)
   - Truncated text content (max 1000 chars)

4. **Media Playing** - Music/video consumption:
   - Artist, track, app
   - Duration

5. **Screenshot Images** - Up to 10 keyframes:
   - Base64 encoded
   - Low detail mode for cost efficiency

**System Prompt** (abbreviated):
```
You are a personal activity summarizer for Trace.
Your task is to analyze the user's digital activity for one hour and generate a structured summary.

Output Requirements:
- schema_version: 1
- summary: 2-3 sentence overview
- categories: activity types present
- activities: timeline with time boundaries
- topics: subjects encountered
- entities: named entities with types
- media: listening/watching data
- documents: files read/edited
- websites: significant visits
- co_activities: overlapping activities
- open_loops: incomplete tasks
- location: geographic if known

Guidelines:
- Keep all descriptions concise
- Use exact timestamps from evidence
- Confidence scores should reflect certainty (0.0-1.0)
- Do NOT include full document contents
```

**User Prompt Structure**:
```
# Hour: 2025-01-15 14:00 - 15:00

## Activity Timeline
- [14:00:23] (5m) Visual Studio Code - main.py
- [14:05:45] (12m) Chrome - docs.python.org
- [14:17:30] (8m) Visual Studio Code - test_main.py
...

## Keyframe Observations
- [14:02:15] VS Code with Python code visible
- [14:08:30] Python documentation page
...

## Extracted Text (Document/OCR)
### [14:03:00] Source: ocr
```
def calculate_metrics():
    # Function implementation
```

## Media Playing During This Hour
- Lofi Girl - Study Beats (45m via Spotify)

## Evidence Statistics
- Total events: 12
- Total screenshots: 245
- Selected keyframes: 8
```

**Output Schema**:
```json
{
  "schema_version": 1,
  "summary": "Productive coding session focused on Python development...",
  "categories": ["work", "coding", "learning"],
  "activities": [
    {
      "time_start": "14:00",
      "time_end": "14:30",
      "description": "Writing Python code",
      "app": "Visual Studio Code",
      "category": "work"
    }
  ],
  "topics": [
    {"name": "Python", "context": "Primary development language", "confidence": 0.95}
  ],
  "entities": [
    {"name": "Visual Studio Code", "type": "app", "confidence": 0.95},
    {"name": "Python", "type": "topic", "confidence": 0.9}
  ],
  "media": {
    "listening": [
      {"artist": "Lofi Girl", "track": "Study Beats", "duration_seconds": 2700}
    ],
    "watching": []
  },
  "documents": [],
  "websites": [
    {"domain": "docs.python.org", "page_title": "Python Documentation", "purpose": "Reference"}
  ],
  "co_activities": [
    {"primary": "Coding", "secondary": "Listening to music", "relationship": "worked_while"}
  ],
  "open_loops": [],
  "location": "Home Office"
}
```

## 3. Daily Revision

**Purpose**: Improve notes with full-day context, normalize entities, build graph.

**Model**: `gpt-5.2-2025-12-11` (most capable model for analysis)

**Input**: All hourly notes from a single day, including:
- Note IDs and timestamps
- Summaries and categories
- Entities and topics
- Activities and media
- Open loops

**System Prompt** (abbreviated):
```
You are a daily revision agent for Trace.

Your tasks:
1. Revise Hourly Notes: Improve summaries with day-level context
2. Normalize Entities: Group variants (e.g., "VSCode", "VS Code" → "Visual Studio Code")
3. Build Graph Edges: Identify relationships between entities
4. Generate Day Summary: Comprehensive overview

Edge types:
- ABOUT_TOPIC: Entity relates to a topic
- WATCHED: User watched media
- LISTENED_TO: User listened to music
- USED_APP: Topic/project used this app
- VISITED_DOMAIN: Topic/project visited this domain
- DOC_REFERENCE: Document references entity
- CO_OCCURRED_WITH: Entities appeared together
- STUDIED_WHILE: Learning paired with activity
```

**Output Schema**:
```json
{
  "schema_version": 1,
  "day_summary": "A productive day focused on Python development...",
  "primary_focus": "Software Development",
  "accomplishments": ["Completed API implementation", "Fixed 3 bugs"],
  "hourly_revisions": [
    {
      "hour": "14:00",
      "note_id": "abc-123",
      "revised_summary": "Improved summary with day context...",
      "revised_entities": [
        {
          "original_name": "VS Code",
          "canonical_name": "Visual Studio Code",
          "type": "app",
          "confidence": 0.95
        }
      ],
      "additional_context": "Part of multi-hour coding session"
    }
  ],
  "entity_normalizations": [
    {
      "original_names": ["VSCode", "VS Code", "Visual Studio Code"],
      "canonical_name": "Visual Studio Code",
      "entity_type": "app",
      "confidence": 0.95
    }
  ],
  "graph_edges": [
    {
      "from_entity": "Python",
      "from_type": "topic",
      "to_entity": "Visual Studio Code",
      "to_type": "app",
      "edge_type": "USED_APP",
      "weight": 0.9,
      "evidence": "Python development in VS Code for 4 hours"
    }
  ],
  "top_entities": {
    "topics": [{"name": "Python", "total_minutes": 180}],
    "apps": [{"name": "Visual Studio Code", "total_minutes": 240}]
  },
  "open_loops": ["Reply to client email"],
  "patterns": ["Deep work in morning hours", "Context switching after lunch"]
}
```

## 4. Query Planning (Agentic Pipeline)

**Purpose**: Decompose complex queries into execution plans.

**Model**: `gpt-4o-mini`

**Input**:
- User query
- Query type (relationship, memory_recall, comparison, correlation, web_augmented)
- Available actions
- Time context

**System Prompt** (abbreviated):
```
You are a query planner for a personal knowledge base.

Given a query, generate an execution plan with steps that can be run in parallel where possible.

Available actions:
- semantic_search: Vector similarity search
- entity_search: Search by entity name
- graph_expand: Follow graph edges
- aggregates_query: Get time rollups
- hierarchical_search: Daily-first search
- compare_periods: Compare time ranges
- temporal_sequence: Activities before/after
- web_search: External web search (optional)
- merge_results: Combine step outputs
```

**Output Schema**:
```json
{
  "plan_id": "plan-abc123",
  "query": "What music was I listening to while studying Python?",
  "query_type": "relationship",
  "reasoning": "Need to find Python study sessions, then get co-occurring music",
  "steps": [
    {
      "step_id": "step1",
      "action": "entity_search",
      "params": {"entity_name": "Python", "entity_type": "topic"},
      "depends_on": [],
      "required": true
    },
    {
      "step_id": "step2",
      "action": "graph_expand",
      "params": {"edge_types": ["STUDIED_WHILE", "LISTENED_TO"]},
      "depends_on": ["step1"],
      "required": true
    }
  ],
  "requires_web_search": false
}
```

## 5. Answer Synthesis

**Purpose**: Generate natural language answers with citations.

**Model**: `gpt-4o-mini`

**Input**:
- User question
- Retrieved notes (with metadata)
- Aggregates data
- Related entities
- Time filter context

**System Prompt**:
```
You are a helpful assistant that answers questions about a user's digital activity history.

Guidelines:
1. ALWAYS cite sources using [Note: HH:00] or [Note: YYYY-MM-DD] format
2. Only make claims supported by provided notes
3. If information isn't in notes, say so honestly
4. Use aggregates data for "most/top" questions
5. Keep answers concise but informative
6. Mention time context when relevant

Example citations:
- "You spent 3 hours coding in VS Code [Note: 14:00]."
- "On Monday, you focused on Python development [Note: 2025-01-13]."
```

**User Prompt Template**:
```
Question: {question}

Time context: {time_description}

## Relevant Notes
{formatted_notes}

## Aggregates Data
{aggregates}

## Related Topics
{related_entities}

---
Answer based on the information above. Remember to cite sources.
```

## 6. Embeddings

**Purpose**: Enable semantic similarity search.

**Model**: `text-embedding-3-small`

**Input**: Concatenated note text including:
- Summary
- Entity names (with types)
- Topic names
- Category names
- Key content from documents/websites

**Output**: 1536-dimensional vector stored in sqlite-vec.

**Search Process**:
1. Query text → embedding
2. Vector similarity search in sqlite-vec
3. Filter by time constraints
4. Rank by distance + recency

## Cost Optimization

| Strategy | Implementation |
|----------|----------------|
| Low detail images | `detail: "low"` for vision API |
| Heuristic triage | Skip API for obvious frames |
| Batch embeddings | Process multiple notes together |
| Model selection | Use mini/nano models where possible |
| Token budgeting | Truncate long text inputs |
| Caching | Skip re-processing existing notes |

## Error Handling

| Scenario | Handling |
|----------|----------|
| API timeout | Retry with exponential backoff |
| Invalid JSON | Parse with retry, fallback to defaults |
| Rate limiting | Queue with delays |
| No activity | Generate empty note with placeholder |
| Low confidence | Flag for review, keep in pipeline |

## Schema Versioning

All LLM outputs include `schema_version` field for:
- Backward compatibility
- Migration support
- Validation enforcement

Current versions:
- Hourly summary: v1
- Daily revision: v1
