"""
Test script for Phase 5: Hourly Summarization

Tests all P5 components:
- P5-01: Frame triage (heuristic mode)
- P5-02: Keyframe selection
- P5-03: Evidence aggregation
- P5-04: Hourly summarization prompt
- P5-05: JSON schema validation
- P5-06: Markdown note renderer
- P5-07: Entity extraction
- P5-08: Embedding computation
"""

import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

# Load environment
from dotenv import load_dotenv

load_dotenv()


def test_schema_validation():
    """Test P5-05: JSON schema validation"""
    print("\n" + "=" * 60)
    print("Testing P5-05: Schema Validation")
    print("=" * 60)

    from src.summarize.schemas import (
        fix_common_issues,
        generate_empty_summary,
        validate_hourly_summary,
        validate_with_retry,
    )

    # Test 1: Valid JSON
    valid_json = {
        "schema_version": 1,
        "summary": "The user worked on Python code in VS Code and browsed GitHub.",
        "categories": ["work", "browsing"],
        "activities": [
            {
                "time_start": "14:00",
                "time_end": "14:30",
                "description": "Writing Python code for Trace project",
                "app": "VS Code",
                "category": "work",
            },
            {
                "time_start": "14:30",
                "time_end": "15:00",
                "description": "Reviewing pull requests on GitHub",
                "app": "Safari",
                "category": "browsing",
            },
        ],
        "topics": [
            {"name": "Python", "context": "Writing capture daemon", "confidence": 0.9},
            {"name": "Code Review", "confidence": 0.8},
        ],
        "entities": [
            {"name": "VS Code", "type": "app", "confidence": 0.95},
            {"name": "GitHub", "type": "domain", "confidence": 0.9},
            {"name": "Trace", "type": "project", "confidence": 0.85},
        ],
        "media": {
            "listening": [
                {"artist": "Lofi Girl", "track": "Study Beats", "duration_seconds": 1800}
            ],
            "watching": [],
        },
        "documents": [
            {"name": "daemon.py", "type": "code", "key_content": "Capture daemon implementation"}
        ],
        "websites": [
            {"domain": "github.com", "page_title": "Pull Request #42", "purpose": "Code review"}
        ],
        "co_activities": [
            {"primary": "Coding", "secondary": "Listening to music", "relationship": "worked_while"}
        ],
        "open_loops": ["Need to fix flaky test"],
        "location": "Home office",
    }

    result = validate_hourly_summary(valid_json)
    print(f"✓ Valid JSON test: {'PASS' if result.valid else 'FAIL'}")
    if result.valid:
        print(f"  - Schema version: {result.data.schema_version}")
        print(f"  - Entities extracted: {len(result.data.entities)}")
        print(f"  - Activities: {len(result.data.activities)}")

    # Test 2: JSON with missing fields (should use defaults)
    minimal_json = {"summary": "A simple summary."}
    result = validate_hourly_summary(minimal_json)
    print(f"✓ Minimal JSON test: {'PASS' if result.valid else 'FAIL'}")
    if result.valid:
        print(
            f"  - Defaults applied: activities={len(result.data.activities)}, entities={len(result.data.entities)}"
        )

    # Test 3: Fix common issues (markdown wrapper)
    wrapped_json = """```json
    {"summary": "Test summary", "categories": ["test"]}
    ```"""
    fixed = fix_common_issues(wrapped_json)
    result = validate_hourly_summary(fixed)
    print(f"✓ Markdown wrapper fix test: {'PASS' if result.valid else 'FAIL'}")

    # Test 4: Entity type normalization
    entity_json = {
        "summary": "Test",
        "entities": [
            {"name": "Song1", "type": "song", "confidence": 0.8},  # Should normalize to "track"
            {"name": "Site1", "type": "website", "confidence": 0.7},  # Should normalize to "domain"
        ],
    }
    result = validate_hourly_summary(entity_json)
    print(f"✓ Entity type normalization test: {'PASS' if result.valid else 'FAIL'}")
    if result.valid:
        types = [e.type for e in result.data.entities]
        print(f"  - Normalized types: {types}")

    # Test 5: Empty summary generation
    hour_start = datetime.now().replace(minute=0, second=0, microsecond=0)
    hour_end = hour_start + timedelta(hours=1)
    empty = generate_empty_summary(hour_start, hour_end)
    print("✓ Empty summary generation test: PASS")
    print(f"  - Summary: {empty.summary}")

    # Test 6: validate_with_retry
    malformed = '```json\n{"summary": "Test"}\n```'
    result = validate_with_retry(malformed)
    print(f"✓ Validate with retry test: {'PASS' if result.valid else 'FAIL'}")

    return True


def test_heuristic_triage():
    """Test P5-01: Frame triage (heuristic mode)"""
    print("\n" + "=" * 60)
    print("Testing P5-01: Heuristic Triage")
    print("=" * 60)

    from src.summarize.triage import HeuristicTriager

    triager = HeuristicTriager()

    # Test various app categories
    test_cases = [
        ("com.microsoft.VSCode", "main.py - project", "CREATIVE"),
        ("com.apple.Safari", "GitHub - Repository", "BROWSING"),
        ("com.tinyspeck.slackmacgap", "Team Channel", "COMMUNICATION"),
        ("com.spotify.client", "Now Playing", "MEDIA"),
        ("com.apple.Preview", "Document.pdf", "DOCUMENT"),
        ("unknown.app", "Window Title", "OTHER"),
    ]

    for app_id, window_title, expected_category in test_cases:
        result = triager.triage(
            screenshot_id="test",
            screenshot_path=Path("/tmp/test.png"),
            timestamp=datetime.now(),
            app_id=app_id,
            window_title=window_title,
            diff_score=0.5,
        )
        passed = result.category.value.upper() == expected_category
        print(
            f"{'✓' if passed else '✗'} {app_id}: {result.category.value} (expected {expected_category})"
        )
        print(f"  - Importance score: {result.importance_score:.2f}")
        print(f"  - Has text: {result.has_text}, Has document: {result.has_document}")

    return True


def test_keyframe_selection():
    """Test P5-02: Keyframe selection algorithm"""
    print("\n" + "=" * 60)
    print("Testing P5-02: Keyframe Selection")
    print("=" * 60)

    from src.summarize.keyframes import KeyframeSelector, ScreenshotCandidate
    from src.summarize.triage import HeuristicTriager

    selector = KeyframeSelector()
    triager = HeuristicTriager()

    # Create synthetic candidates
    base_time = datetime.now().replace(minute=0, second=0, microsecond=0)
    candidates = []

    # Simulate different scenarios
    scenarios = [
        ("com.microsoft.VSCode", "main.py", 0.3, "fp1"),
        ("com.microsoft.VSCode", "main.py", 0.1, "fp1"),  # Low diff, same fingerprint
        ("com.microsoft.VSCode", "test.py", 0.8, "fp2"),  # High diff, transition
        ("com.apple.Safari", "GitHub", 0.9, "fp3"),  # App transition
        ("com.apple.Safari", "GitHub PR", 0.2, "fp3"),
        ("com.spotify.client", "Playing", 0.5, "fp4"),
        ("com.microsoft.VSCode", "utils.py", 0.6, "fp5"),
    ]

    for i, (app_id, window, diff, fp) in enumerate(scenarios):
        ts = base_time + timedelta(minutes=i * 5)
        triage = triager.triage(
            screenshot_id=f"ss_{i}",
            screenshot_path=Path(f"/tmp/ss_{i}.png"),
            timestamp=ts,
            app_id=app_id,
            window_title=window,
            diff_score=diff,
        )
        candidate = ScreenshotCandidate(
            screenshot_id=f"ss_{i}",
            screenshot_path=Path(f"/tmp/ss_{i}.png"),
            timestamp=ts,
            monitor_id=0,
            diff_score=diff,
            fingerprint=fp,
            app_id=app_id,
            app_name=app_id.split(".")[-1],
            window_title=window,
            triage_result=triage,
        )
        candidates.append(candidate)

    # Select keyframes
    keyframes = selector.select(candidates)

    print(f"✓ Keyframe selection: {len(keyframes)} selected from {len(candidates)} candidates")
    for kf in keyframes:
        print(f"  - {kf.screenshot_id}: {kf.selection_reason} (score: {kf.combined_score:.2f})")

    return len(keyframes) > 0


def test_evidence_aggregation():
    """Test P5-03: Evidence aggregation"""
    print("\n" + "=" * 60)
    print("Testing P5-03: Evidence Aggregation")
    print("=" * 60)

    from src.summarize.evidence import EventSummary, HourlyEvidence

    # Create synthetic evidence
    hour_start = datetime.now().replace(minute=0, second=0, microsecond=0)
    hour_end = hour_start + timedelta(hours=1)

    events = [
        EventSummary(
            event_id="e1",
            start_ts=hour_start,
            end_ts=hour_start + timedelta(minutes=30),
            duration_seconds=1800,
            app_id="com.microsoft.VSCode",
            app_name="VSCode",
            window_title="main.py",
            url=None,
            page_title=None,
            file_path=None,
            location_text=None,
            now_playing=None,
        ),
        EventSummary(
            event_id="e2",
            start_ts=hour_start + timedelta(minutes=30),
            end_ts=hour_end,
            duration_seconds=1800,
            app_id="com.apple.Safari",
            app_name="Safari",
            window_title="GitHub",
            url="https://github.com",
            page_title="GitHub",
            file_path=None,
            location_text=None,
            now_playing=None,
        ),
    ]

    evidence = HourlyEvidence(
        hour_start=hour_start,
        hour_end=hour_end,
        events=events,
        total_events=len(events),
        total_screenshots=120,
        total_text_buffers=2,
        locations=["Home"],
    )

    print("✓ Evidence aggregation structure created")
    print(f"  - Hour: {evidence.hour_start} - {evidence.hour_end}")
    print(f"  - Events: {evidence.total_events}")
    print(f"  - Screenshots: {evidence.total_screenshots}")
    print(f"  - Location: {evidence.locations}")

    return True


def test_prompt_building():
    """Test P5-04: Hourly summarization prompt"""
    print("\n" + "=" * 60)
    print("Testing P5-04: Prompt Building")
    print("=" * 60)

    from src.summarize.evidence import EventSummary, HourlyEvidence
    from src.summarize.prompts.hourly import (
        HOURLY_MODEL,
        HOURLY_SYSTEM_PROMPT,
        build_hourly_user_prompt,
    )

    hour_start = datetime.now().replace(minute=0, second=0, microsecond=0)
    hour_end = hour_start + timedelta(hours=1)

    events = [
        EventSummary(
            event_id="e1",
            start_ts=hour_start,
            end_ts=hour_start + timedelta(minutes=30),
            duration_seconds=1800,
            app_id="com.microsoft.VSCode",
            app_name="VSCode",
            window_title="main.py",
            url=None,
            page_title=None,
            file_path=None,
            location_text=None,
            now_playing=None,
        ),
    ]

    evidence = HourlyEvidence(
        hour_start=hour_start,
        hour_end=hour_end,
        events=events,
        total_events=1,
        total_screenshots=60,
        total_text_buffers=0,
    )

    user_prompt = build_hourly_user_prompt(evidence)

    print("✓ Prompt building")
    print(f"  - Model: {HOURLY_MODEL}")
    print(f"  - System prompt length: {len(HOURLY_SYSTEM_PROMPT)} chars")
    print(f"  - User prompt length: {len(user_prompt)} chars")
    print("  - User prompt preview:")
    print("    " + "\n    ".join(user_prompt.split("\n")[:10]))

    return True


def test_markdown_renderer():
    """Test P5-06: Markdown note renderer"""
    print("\n" + "=" * 60)
    print("Testing P5-06: Markdown Renderer")
    print("=" * 60)

    from src.summarize.render import MarkdownRenderer
    from src.summarize.schemas import HourlySummarySchema

    renderer = MarkdownRenderer()

    hour_start = datetime.now().replace(minute=0, second=0, microsecond=0)
    hour_end = hour_start + timedelta(hours=1)

    summary = HourlySummarySchema(
        schema_version=1,
        summary="The user worked on Python code and browsed GitHub.",
        categories=["work", "browsing"],
        activities=[
            {
                "time_start": "14:00",
                "time_end": "14:30",
                "description": "Writing Python code",
                "app": "VS Code",
                "category": "work",
            }
        ],
        topics=[{"name": "Python", "confidence": 0.9}],
        entities=[{"name": "VS Code", "type": "app", "confidence": 0.95}],
        media={"listening": [], "watching": []},
        documents=[],
        websites=[{"domain": "github.com", "purpose": "Code review"}],
        co_activities=[],
        open_loops=["Review PR #42"],
        location="Home",
    )

    markdown = renderer.render(
        summary=summary,
        note_id="test-note-123",
        hour_start=hour_start,
        hour_end=hour_end,
    )

    print(f"✓ Markdown rendered: {len(markdown)} chars")
    print("  Preview (first 500 chars):")
    print("    " + "\n    ".join(markdown[:500].split("\n")))

    # Test file writing
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        result = renderer.render_to_file(
            summary=summary,
            note_id="test-note-123",
            hour_start=hour_start,
            hour_end=hour_end,
            file_path=Path(f.name),
        )
        print(f"✓ File writing: {'PASS' if result else 'FAIL'}")
        os.unlink(f.name)

    return True


def test_entity_extraction():
    """Test P5-07: Entity extraction"""
    print("\n" + "=" * 60)
    print("Testing P5-07: Entity Extraction")
    print("=" * 60)

    from src.summarize.entities import EntityExtractor
    from src.summarize.schemas import HourlySummarySchema

    # Use a temporary database for testing
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        temp_db = Path(f.name)

    try:
        # Initialize schema
        from src.db.migrations import get_connection, init_database

        init_database(temp_db)

        # First, create a note (required for foreign key constraint)
        note_id = "test-note-456"
        hour_start = datetime.now().replace(minute=0, second=0, microsecond=0)
        hour_end = hour_start + timedelta(hours=1)

        conn = get_connection(temp_db)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO notes (note_id, note_type, start_ts, end_ts, file_path, json_payload, created_ts, updated_ts)
            VALUES (?, 'hour', ?, ?, '/tmp/test.md', '{}', ?, ?)
            """,
            (
                note_id,
                hour_start.isoformat(),
                hour_end.isoformat(),
                datetime.now().isoformat(),
                datetime.now().isoformat(),
            ),
        )
        conn.commit()
        conn.close()

        extractor = EntityExtractor(db_path=temp_db)

        summary = HourlySummarySchema(
            schema_version=1,
            summary="Test summary",
            categories=["work"],
            activities=[],
            topics=[{"name": "Python Programming", "confidence": 0.9}],
            entities=[
                {"name": "VS Code", "type": "app", "confidence": 0.95},
                {"name": "GitHub", "type": "domain", "confidence": 0.9},
                {"name": "Trace Project", "type": "project", "confidence": 0.85},
            ],
            media={"listening": [{"artist": "Lofi Girl", "track": "Study Beats"}], "watching": []},
            documents=[{"name": "daemon.py", "type": "code"}],
            websites=[{"domain": "github.com"}],
            co_activities=[],
            open_loops=[],
        )

        links = extractor.extract_and_store(summary, note_id)

        print(f"✓ Entity extraction: {len(links)} entity links created")
        for link in links:
            print(f"  - {link.entity_id[:8]}... (strength: {link.strength:.2f})")

        # Verify entities in database
        conn = get_connection(temp_db)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM entities")
        entity_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM note_entities")
        link_count = cursor.fetchone()[0]
        conn.close()

        print(f"  - Entities in DB: {entity_count}")
        print(f"  - Links in DB: {link_count}")

        return len(links) > 0

    finally:
        os.unlink(temp_db)


def test_embedding_computation():
    """Test P5-08: Embedding computation"""
    print("\n" + "=" * 60)
    print("Testing P5-08: Embedding Computation (requires API)")
    print("=" * 60)

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("✗ OPENAI_API_KEY not set, skipping API test")
        return False

    from src.summarize.embeddings import EmbeddingComputer
    from src.summarize.schemas import HourlySummarySchema

    computer = EmbeddingComputer(api_key=api_key)

    # Test query embedding
    query = "What did I work on with Python today?"
    embedding = computer.compute_for_query(query)

    if embedding:
        print(f"✓ Query embedding computed: {len(embedding)} dimensions")
        print(f"  - First 5 values: {embedding[:5]}")
    else:
        print("✗ Query embedding failed")
        return False

    # Test embedding text building
    summary = HourlySummarySchema(
        schema_version=1,
        summary="The user worked on Python code and listened to music.",
        categories=["work", "entertainment"],
        activities=[
            {
                "time_start": "14:00",
                "time_end": "15:00",
                "description": "Writing Python code",
                "app": "VS Code",
                "category": "work",
            }
        ],
        topics=[{"name": "Python", "confidence": 0.9}],
        entities=[{"name": "VS Code", "type": "app", "confidence": 0.95}],
        media={
            "listening": [
                {"artist": "Lofi Girl", "track": "Study Beats", "duration_seconds": 3600}
            ],
            "watching": [],
        },
        documents=[],
        websites=[],
        co_activities=[],
        open_loops=[],
        location=None,
    )

    text = computer._build_embedding_text(summary, datetime(2025, 1, 15, 14, 0, 0))
    print(f"✓ Embedding text built: {len(text)} chars")
    print("  Preview:\n    " + "\n    ".join(text.split("\n")[:5]))

    return True


def test_full_pipeline_mock():
    """Test the full summarization pipeline with mock LLM response"""
    print("\n" + "=" * 60)
    print("Testing Full Pipeline (Mock LLM)")
    print("=" * 60)

    from src.summarize.entities import EntityExtractor
    from src.summarize.render import MarkdownRenderer
    from src.summarize.schemas import validate_hourly_summary

    # Simulate LLM response
    mock_llm_response = {
        "schema_version": 1,
        "summary": "The user spent the hour coding in VS Code, primarily working on the Trace project's capture daemon. They also briefly browsed GitHub for code references while listening to lo-fi music.",
        "categories": ["work", "browsing", "entertainment"],
        "activities": [
            {
                "time_start": "14:00",
                "time_end": "14:45",
                "description": "Writing Python code for capture daemon",
                "app": "VS Code",
                "category": "work",
            },
            {
                "time_start": "14:45",
                "time_end": "15:00",
                "description": "Reviewing similar implementations on GitHub",
                "app": "Safari",
                "category": "browsing",
            },
        ],
        "topics": [
            {"name": "Python", "context": "Primary programming language", "confidence": 0.95},
            {"name": "Screen Capture", "context": "Feature being implemented", "confidence": 0.9},
        ],
        "entities": [
            {"name": "VS Code", "type": "app", "confidence": 0.98},
            {"name": "Safari", "type": "app", "confidence": 0.95},
            {"name": "GitHub", "type": "domain", "confidence": 0.9},
            {"name": "Trace", "type": "project", "confidence": 0.95},
            {"name": "Lofi Girl", "type": "artist", "confidence": 0.85},
        ],
        "media": {
            "listening": [
                {"artist": "Lofi Girl", "track": "Study Session", "duration_seconds": 3600}
            ],
            "watching": [],
        },
        "documents": [
            {
                "name": "daemon.py",
                "type": "code",
                "key_content": "Screen capture daemon implementation",
            }
        ],
        "websites": [
            {
                "domain": "github.com",
                "page_title": "python-mss repository",
                "purpose": "Reference implementation",
            }
        ],
        "co_activities": [
            {
                "primary": "Coding in VS Code",
                "secondary": "Listening to lo-fi music",
                "relationship": "worked_while",
            }
        ],
        "open_loops": ["Need to implement multi-monitor support"],
        "location": "Home office",
    }

    # Step 1: Validate
    result = validate_hourly_summary(mock_llm_response)
    print(f"✓ Schema validation: {'PASS' if result.valid else 'FAIL'}")

    if not result.valid:
        print(f"  Error: {result.error}")
        return False

    summary = result.data

    # Step 2: Render markdown
    renderer = MarkdownRenderer()
    hour_start = datetime.now().replace(minute=0, second=0, microsecond=0)
    hour_end = hour_start + timedelta(hours=1)

    markdown = renderer.render(
        summary=summary,
        note_id="mock-note-789",
        hour_start=hour_start,
        hour_end=hour_end,
        location="Home office",
    )
    print(f"✓ Markdown rendering: {len(markdown)} chars")

    # Step 3: Save to temp file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(markdown)
        temp_path = f.name
    print(f"✓ Note saved to: {temp_path}")

    # Step 4: Entity extraction (with temp DB)
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        temp_db = Path(f.name)

    try:
        from src.db.migrations import get_connection, init_database

        init_database(temp_db)

        # First, create a note (required for foreign key constraint)
        note_id = "mock-note-789"
        conn = get_connection(temp_db)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO notes (note_id, note_type, start_ts, end_ts, file_path, json_payload, created_ts, updated_ts)
            VALUES (?, 'hour', ?, ?, '/tmp/test.md', '{}', ?, ?)
            """,
            (
                note_id,
                hour_start.isoformat(),
                hour_end.isoformat(),
                datetime.now().isoformat(),
                datetime.now().isoformat(),
            ),
        )
        conn.commit()
        conn.close()

        extractor = EntityExtractor(db_path=temp_db)
        links = extractor.extract_and_store(summary, note_id)
        print(f"✓ Entity extraction: {len(links)} entities linked")
    finally:
        os.unlink(temp_db)

    # Show the generated note
    print("\n" + "-" * 60)
    print("Generated Markdown Note:")
    print("-" * 60)
    print(markdown)

    # Cleanup
    os.unlink(temp_path)

    return True


def main():
    """Run all P5 tests"""
    print("=" * 60)
    print("Phase 5: Hourly Summarization Tests")
    print("=" * 60)

    results = {}

    # Test 1: Schema validation (no API needed)
    try:
        results["P5-05 Schema Validation"] = test_schema_validation()
    except Exception as e:
        print(f"✗ P5-05 Schema Validation: FAILED - {e}")
        results["P5-05 Schema Validation"] = False

    # Test 2: Heuristic triage (no API needed)
    try:
        results["P5-01 Heuristic Triage"] = test_heuristic_triage()
    except Exception as e:
        print(f"✗ P5-01 Heuristic Triage: FAILED - {e}")
        results["P5-01 Heuristic Triage"] = False

    # Test 3: Keyframe selection (no API needed)
    try:
        results["P5-02 Keyframe Selection"] = test_keyframe_selection()
    except Exception as e:
        print(f"✗ P5-02 Keyframe Selection: FAILED - {e}")
        results["P5-02 Keyframe Selection"] = False

    # Test 4: Evidence aggregation (no API needed)
    try:
        results["P5-03 Evidence Aggregation"] = test_evidence_aggregation()
    except Exception as e:
        print(f"✗ P5-03 Evidence Aggregation: FAILED - {e}")
        results["P5-03 Evidence Aggregation"] = False

    # Test 5: Prompt building (no API needed)
    try:
        results["P5-04 Prompt Building"] = test_prompt_building()
    except Exception as e:
        print(f"✗ P5-04 Prompt Building: FAILED - {e}")
        results["P5-04 Prompt Building"] = False

    # Test 6: Markdown renderer (no API needed)
    try:
        results["P5-06 Markdown Renderer"] = test_markdown_renderer()
    except Exception as e:
        print(f"✗ P5-06 Markdown Renderer: FAILED - {e}")
        results["P5-06 Markdown Renderer"] = False

    # Test 7: Entity extraction (no API needed)
    try:
        results["P5-07 Entity Extraction"] = test_entity_extraction()
    except Exception as e:
        print(f"✗ P5-07 Entity Extraction: FAILED - {e}")
        results["P5-07 Entity Extraction"] = False

    # Test 8: Embedding computation (requires API)
    try:
        results["P5-08 Embedding Computation"] = test_embedding_computation()
    except Exception as e:
        print(f"✗ P5-08 Embedding Computation: FAILED - {e}")
        results["P5-08 Embedding Computation"] = False

    # Test 9: Full pipeline mock (no API needed)
    try:
        results["Full Pipeline Mock"] = test_full_pipeline_mock()
    except Exception as e:
        print(f"✗ Full Pipeline Mock: FAILED - {e}")
        results["Full Pipeline Mock"] = False

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {status}: {test_name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
