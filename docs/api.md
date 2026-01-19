# API Reference

This document describes the Chat API and retrieval interfaces for querying Trace data.

## Chat API

The main interface for querying your activity history.

### ChatAPI Class

Located in `src/chat/api.py`.

```python
from src.chat.api import ChatAPI, ChatRequest

api = ChatAPI(db_path="/path/to/trace.sqlite", api_key="sk-...")

# Simple query
response = api.query("What did I work on yesterday?")
print(response.answer)

# Query with time filter
response = api.query("Most used apps", time_filter="last week")

# Full request object
request = ChatRequest(
    query="What music was I listening to while coding?",
    time_filter_hint="this month",
    include_graph_expansion=True,
    include_aggregates=True,
    max_results=10,
    use_agentic=True,
)
response = api.chat(request)
```

### ChatRequest

```python
@dataclass
class ChatRequest:
    query: str                          # User's question
    time_filter_hint: str | None        # Optional explicit time filter
    include_graph_expansion: bool       # Expand related entities (default: True)
    include_aggregates: bool            # Include time stats (default: True)
    max_results: int                    # Maximum notes to return (default: 10)
    use_agentic: bool                   # Use agentic pipeline for complex queries (default: True)
```

### ChatResponse

```python
@dataclass
class ChatResponse:
    answer: str                         # Generated answer text
    citations: list[Citation]           # Source note citations
    notes: list[NoteMatch]              # Retrieved notes
    time_filter: TimeFilter | None      # Parsed time filter
    related_entities: list[RelatedEntity]  # Graph-expanded entities
    aggregates: list[AggregateItem]     # Time statistics
    query_type: str                     # Detected query type
    confidence: float                   # Answer confidence (0.0-1.0)
    processing_time_ms: float           # Total processing time
    # Agentic pipeline metadata
    plan_summary: str | None            # Query plan description
    web_citations: list[dict]           # Web search results (if used)
    patterns: list[str]                 # Detected patterns
```

### Query Types

The API automatically routes queries based on detected type:

| Type | Detection Pattern | Handler |
|------|-------------------|---------|
| `aggregates` | "most", "top", "frequently" | `_handle_aggregates_query` |
| `entity` | "about X", "related to X" | `_handle_entity_query` |
| `timeline` | "what did I do", "activities" | `_handle_timeline_query` |
| `semantic` | General questions | `_handle_semantic_query` |
| Complex | Relationship, comparison queries | Agentic pipeline |

### CLI Usage

```bash
# Single query
uv run python -m src.chat.api chat "What did I work on today?"

# Query with time filter
uv run python -m src.chat.api chat "Most used apps" --time-filter "this week"

# Interactive mode
uv run python -m src.chat.api interactive
```

## Retrieval APIs

### VectorSearcher

Semantic similarity search using embeddings.

```python
from src.retrieval.search import VectorSearcher

searcher = VectorSearcher(db_path=db_path, api_key=api_key)

# Search by query text
results = searcher.search(
    query="Python machine learning",
    time_filter=time_filter,
    limit=10,
)

# Search by entity name
results = searcher.search_by_entity(
    entity_name="Python",
    time_filter=time_filter,
    limit=10,
)

# Get notes in time range
results = searcher.get_notes_in_range(time_filter, limit=20)
```

**SearchResult:**
```python
@dataclass
class SearchResult:
    matches: list[NoteMatch]            # Matched notes
    query: str                          # Original query
    time_filter: TimeFilter | None      # Applied filter
    total_notes_searched: int           # Total notes considered
```

**NoteMatch:**
```python
@dataclass
class NoteMatch:
    note_id: str
    note_type: str                      # 'hour' or 'day'
    start_ts: datetime
    end_ts: datetime
    file_path: str
    summary: str
    categories: list[str]
    entities: list[dict]                # {name, type, confidence}
    distance: float                     # Vector distance (lower = more similar)
    score: float                        # Relevance score (higher = better)
```

### HierarchicalSearcher

Two-stage search: daily summaries first, then hourly drilldown.

```python
from src.retrieval.hierarchical import HierarchicalSearcher

searcher = HierarchicalSearcher(db_path=db_path, api_key=api_key)

result = searcher.search(
    query="coding session",
    time_filter=time_filter,
    max_days=5,              # Top 5 relevant days
    max_hours_per_day=3,     # Top 3 hours per day
    include_hourly_drilldown=True,
)

# Get notes optimized for LLM context
notes = result.get_context_for_llm(max_notes=10)
```

### GraphExpander

Expand relationships from seed entities.

```python
from src.retrieval.graph import GraphExpander

expander = GraphExpander(db_path=db_path)

# Get context for an entity
context = expander.get_entity_context(
    entity_name="Python",
    time_filter=time_filter,
)
# Returns: entity info, relationships (outgoing/incoming), statistics

# Expand from multiple entities
expansion = expander.expand_from_entities(
    entity_ids=["ent-001", "ent-002"],
    hops=1,                             # Traversal depth
    edge_types=["USED_APP", "ABOUT_TOPIC"],
    time_filter=time_filter,
)
```

**GraphExpansion:**
```python
@dataclass
class GraphExpansion:
    seed_entities: list[str]
    related_entities: list[RelatedEntity]
    edges_traversed: int
    hops: int
```

**RelatedEntity:**
```python
@dataclass
class RelatedEntity:
    entity_id: str
    entity_type: str
    canonical_name: str
    edge_type: str
    weight: float
    source_entity_id: str
    source_entity_name: str
    direction: str                      # 'to' or 'from'
```

### AggregatesLookup

Query pre-computed time statistics.

```python
from src.retrieval.aggregates import AggregatesLookup

lookup = AggregatesLookup(db_path=db_path)

# Get top items by type
result = lookup.get_top_by_key_type(
    key_type="app",                     # app, domain, category, entity
    time_filter=time_filter,
    limit=10,
)

# Get time for specific key
result = lookup.get_time_for_key(
    key="Visual Studio Code",
    time_filter=time_filter,
)

# Get summary for period
summary = lookup.get_summary_for_period(time_filter)
# Returns: {apps: {top_items: [...]}, domains: {...}, categories: {...}}

# Detect "most" queries
detected = lookup.detect_most_query("What were my most used apps?")
# Returns: ("most", "app") or None
```

**AggregateItem:**
```python
@dataclass
class AggregateItem:
    key: str                            # Entity/app/domain name
    key_type: str                       # Type of aggregate
    value: float                        # Time in minutes
    period_type: str                    # day, week, month, year
    period_start: datetime | None
    period_end: datetime | None
```

### TimeFilter

Parse and apply time constraints.

```python
from src.retrieval.time import TimeFilter, parse_time_filter

# Parse natural language
time_filter = parse_time_filter("last week")
time_filter = parse_time_filter("yesterday")
time_filter = parse_time_filter("this month")
time_filter = parse_time_filter("January 2025")

# Manual creation
from datetime import datetime, timedelta
time_filter = TimeFilter(
    start=datetime.now() - timedelta(days=7),
    end=datetime.now(),
    description="last 7 days",
)
```

**Supported Patterns:**
| Pattern | Example | Description |
|---------|---------|-------------|
| `today` | "today" | Current day |
| `yesterday` | "yesterday" | Previous day |
| `this week` | "this week" | Current week (Mon-Sun) |
| `last week` | "last week" | Previous week |
| `this month` | "this month" | Current month |
| `last month` | "last month" | Previous month |
| `N days` | "last 3 days" | Past N days |
| `N weeks` | "past 2 weeks" | Past N weeks |
| `Month Year` | "January 2025" | Specific month |
| `YYYY-MM-DD` | "2025-01-15" | Specific date |

## Agentic Pipeline

For complex queries, the API uses an agentic pipeline.

### Query Classifier

```python
from src.chat.agentic.classifier import QueryClassifier

classifier = QueryClassifier()
classification = classifier.classify("What music did I listen to while studying?")

print(classification.is_complex)        # True
print(classification.query_type)        # "relationship"
print(classification.signals)           # ["while"]
```

**Query Types:**
| Type | Description | Signal Words |
|------|-------------|--------------|
| `relationship` | Correlated activities | while, when, during, alongside |
| `comparison` | Compare time periods | compare, vs, versus, difference |
| `memory_recall` | Vague recollection | remember, there was, something about |
| `correlation` | Behavioral patterns | pattern, usually, tend to, typically |
| `web_augmented` | Needs external info | latest, current, recent news |

### Query Planner

```python
from src.chat.agentic.planner import QueryPlanner

planner = QueryPlanner(api_key=api_key)
plan = planner.plan_for_type(
    query="What music was I into while studying Python?",
    query_type="relationship",
    time_filter_description="last month",
)

print(plan.reasoning)
for step in plan.steps:
    print(f"{step.step_id}: {step.action}({step.params})")
```

**QueryPlan:**
```python
@dataclass
class QueryPlan:
    plan_id: str
    query: str
    query_type: str
    reasoning: str                      # LLM explanation
    steps: list[PlanStep]
    requires_web_search: bool
```

**PlanStep:**
```python
@dataclass
class PlanStep:
    step_id: str
    action: str                         # Action name
    params: dict                        # Action parameters
    depends_on: list[str]               # Dependency step IDs
    required: bool                      # Fail if this fails
    timeout_seconds: float
```

### Plan Executor

```python
from src.chat.agentic.executor import PlanExecutor

executor = PlanExecutor(db_path=db_path, api_key=api_key)
result = executor.execute(plan)

print(result.merged_notes)              # Combined note results
print(result.merged_entities)           # Combined entity results
print(result.aggregates)                # Aggregate data
print(result.web_results)               # Web search results
print(result.patterns)                  # Detected patterns
```

**Available Actions:**
| Action | Description | Parameters |
|--------|-------------|------------|
| `semantic_search` | Vector search | query, time_filter, limit |
| `entity_search` | Search by entity | entity_name, entity_type, time_filter |
| `graph_expand` | Follow edges | entity_name, edge_types, hops |
| `aggregates_query` | Get stats | key_type, time_filter, limit |
| `hierarchical_search` | Daily-first | query, time_filter, max_days |
| `compare_periods` | Compare ranges | period_a, period_b, focus |
| `merge_results` | Combine outputs | result_refs |

## Service Management

### ServiceManager

```python
from src.core.services import ServiceManager

manager = ServiceManager(db_path=db_path, api_key=api_key)

# Start all services
results = manager.start_all(notify=True)
# Returns: {"capture": True, "hourly": True, "daily": True}

# Get health status
health = manager.get_health_status()
# Returns: {"healthy": True, "services": {...}, "health_checks": 42}

# Restart a service
manager.restart_service("capture")

# Trigger backfill check
result = manager.trigger_backfill(notify=True)

# Stop all services
manager.stop_all()
```

### CLI Commands

```bash
# Start all services
uv run python -m src.core.services start

# Check service status
uv run python -m src.core.services status
```

## Job Scheduling

### Hourly Summarizer

```python
from src.summarize.summarizer import HourlySummarizer

summarizer = HourlySummarizer(api_key=api_key, db_path=db_path)

# Summarize specific hour
result = summarizer.summarize_hour(
    hour_start=datetime(2025, 1, 15, 14, 0),
    force=False,                        # Skip if note exists
)

print(result.success)
print(result.note_id)
print(result.file_path)
print(result.entities_count)
```

### CLI Commands

```bash
# Summarize previous hour
uv run python -m src.summarize.summarizer summarize

# Summarize specific hour
uv run python -m src.summarize.summarizer summarize --hour "2025-01-15T14:00:00"

# Batch summarize
uv run python -m src.summarize.summarizer batch \
    --start-hour "2025-01-15T00:00:00" \
    --end-hour "2025-01-16T00:00:00"
```

### Daily Scheduler

```bash
# Trigger daily revision
uv run python -m src.jobs.daily trigger --day "2025-01-15"
```

### Backfill

```bash
# Check for missing hours
uv run python -m src.jobs.backfill check

# Backfill missing hours
uv run python -m src.jobs.backfill run
```

## Error Handling

All APIs use consistent error handling:

```python
try:
    response = api.chat(request)
except Exception as e:
    # Logged automatically
    # Returns graceful degradation or error message
```

**Common Error Patterns:**
| Scenario | Handling |
|----------|----------|
| No notes found | Returns explanation, suggests broadening search |
| LLM API error | Retries, then falls back to simpler method |
| Time filter parse fail | Uses "all time" as fallback |
| Graph expansion empty | Returns empty related entities |
| Aggregates missing | Returns empty aggregates list |

## Response Formats

### JSON Serialization

All dataclasses support `.to_dict()` method:

```python
response = api.chat(request)
json_data = response.to_dict()

# Structure:
{
    "answer": "...",
    "citations": [{"note_id": "...", "label": "14:00", ...}],
    "notes": [{"note_id": "...", "summary": "...", ...}],
    "time_filter": {"start": "...", "end": "...", "description": "..."},
    "related_entities": [...],
    "aggregates": [...],
    "query_type": "semantic",
    "confidence": 0.85,
    "processing_time_ms": 1234.5,
}
```

### Citation Format

Citations in answers use the format:
- Hourly notes: `[Note: HH:00]` or `[Note: HH:00 on YYYY-MM-DD]`
- Daily notes: `[Note: YYYY-MM-DD]`

Example: "You worked on Python for 3 hours [Note: 14:00 on 2025-01-15]."
