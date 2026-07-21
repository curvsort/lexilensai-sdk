"""
End-to-end workflow test: SDK → JSONL → lexilens report.

This test verifies the COMPLETE local workflow without any external services:
1. Initialize LexiLens with mocked Anthropic SDK
2. Run multiple model calls with varied token patterns
3. Close session → JSONL file written
4. Parse JSONL → verify all spans present
5. Run report generation → verify expected metrics and anomalies

Runs in CI with no API keys, no Docker, no network.
"""
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest


# ─── Mock Anthropic Fixtures ────────────────────────────────────────────────


class MockUsage:
    """Simulates anthropic response.usage."""

    def __init__(self, input_tokens=100, output_tokens=50,
                 cache_creation_input_tokens=None, cache_read_input_tokens=None):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_creation_input_tokens = cache_creation_input_tokens
        self.cache_read_input_tokens = cache_read_input_tokens


class MockContentBlock:
    """Simulates a content block in the response."""

    def __init__(self, type="text", text="Mock response", thinking=""):
        self.type = type
        self.text = text
        self.thinking = thinking


class MockResponse:
    """Simulates anthropic.messages.create() response."""

    def __init__(self, usage=None, content=None):
        self.usage = usage or MockUsage()
        self.content = content or [MockContentBlock()]


def make_response(input_tokens, output_tokens, cache_create=None, cache_read=None):
    """Helper to create a mock response with specific token counts."""
    return MockResponse(
        usage=MockUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_creation_input_tokens=cache_create,
            cache_read_input_tokens=cache_read,
        )
    )


# ─── Test: Full SDK → JSONL → Report Workflow ────────────────────────────────


@pytest.fixture(autouse=True)
def reset_anthropic_module():
    """Reset anthropic instrumentation state between tests."""
    import lexilensai.frameworks.anthropic as mod
    mod._original_messages_create = None
    mod._original_messages_stream = None
    yield
    mod._original_messages_create = None
    mod._original_messages_stream = None


@pytest.fixture
def work_dir(tmp_path):
    """Create a temporary working directory and cd into it."""
    original_dir = os.getcwd()
    os.chdir(tmp_path)
    yield tmp_path
    os.chdir(original_dir)


def test_full_e2e_jsonl_report_workflow(work_dir, monkeypatch):
    """
    Full end-to-end: init SDK → make model calls → close → verify JSONL → run report.

    Simulates a realistic session with:
    - Call 1: Initial call with cache creation (1500 in / 300 out / 2000 cache_create)
    - Call 2: Same prefix, cache hit (1500 in / 200 out / 2000 cache_read)
    - Call 3: Changed prefix, cache miss → new cache create (3000 in / 500 out / 1500 cache_create)
    - Call 4: Massive token spike (25000 in / 3000 out) → should trigger >3x anomaly
    - Call 5: Normal call with error
    """
    # Set up mock anthropic module
    mock_anthropic = MagicMock()
    mock_Messages = MagicMock()

    # Sequence of responses for each call
    responses = [
        make_response(1500, 300, cache_create=2000, cache_read=None),
        make_response(1500, 200, cache_create=None, cache_read=2000),
        make_response(3000, 500, cache_create=1500, cache_read=None),  # cache miss (new create after hit)
        make_response(25000, 3000, cache_create=None, cache_read=None),  # massive spike
        Exception("RateLimitError: Too many requests"),
    ]

    call_counter = {"n": 0}

    def mock_create(self, *args, **kwargs):
        idx = call_counter["n"]
        call_counter["n"] += 1
        if idx < len(responses):
            result = responses[idx]
            if isinstance(result, Exception):
                raise result
            return result
        return make_response(100, 50)

    mock_Messages.create = mock_create
    mock_Messages.stream = MagicMock(return_value=MockResponse())
    mock_anthropic.resources.Messages = mock_Messages

    monkeypatch.setitem(sys.modules, "anthropic", mock_anthropic)

    # Import AFTER mocking
    from lexilensai import LexiLens
    from lexilensai.report import parse_spans, group_by_session, build_session_report

    # ── Step 1: Initialize SDK with JSONL exporter ──
    lexilens = LexiLens.init(
        exporter="jsonl",
        tenant_id="test_tenant",
        application_id="e2e_test_app",
        objective="E2E integration test",
    )
    session_id = lexilens.session_id
    assert session_id.startswith("sess_")

    # ── Step 2: Simulate model calls ──
    # Calls 1-4 succeed, Call 5 raises
    for i in range(4):
        mock_Messages.create(
            None,  # self
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[{"role": "user", "content": f"Question {i+1}"}],
        )

    # Call 5: Error call
    try:
        mock_Messages.create(
            None,
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[{"role": "user", "content": "This will fail"}],
        )
    except Exception:
        pass  # Expected

    # ── Step 3: Close session ──
    lexilens.close()

    # ── Step 4: Verify JSONL file was created ──
    jsonl_path = work_dir / "lexilens_spans.jsonl"
    assert jsonl_path.exists(), f"JSONL file not created at {jsonl_path}"

    # Parse and verify spans
    spans = parse_spans(jsonl_path)
    assert len(spans) >= 2, f"Expected at least session.start + session.end, got {len(spans)}"

    # Check session.start span
    start_spans = [s for s in spans if s["span_name"] == "session.start"]
    assert len(start_spans) == 1
    start_span = start_spans[0]
    assert start_span["attributes"]["session_id"] == session_id
    assert start_span["attributes"]["tenant_id"] == "test_tenant"
    assert start_span["attributes"]["application_id"] == "e2e_test_app"
    assert start_span["attributes"]["objective"] == "E2E integration test"

    # Check session.end span
    end_spans = [s for s in spans if s["span_name"] == "session.end"]
    assert len(end_spans) == 1

    # Check model.call spans
    model_spans = [s for s in spans if s["span_name"] == "model.call"]
    assert len(model_spans) >= 4, f"Expected 4+ model.call spans, got {len(model_spans)}"

    # Verify token counts in first model call
    first_call = model_spans[0]
    assert first_call["attributes"]["input_tokens"] == 1500
    assert first_call["attributes"]["output_tokens"] == 300
    assert first_call["attributes"]["model"] == "claude-sonnet-4-20250514"

    # ── Step 5: Run report generation and verify output ──
    sessions = group_by_session(spans)
    assert session_id in sessions

    report = build_session_report(session_id, sessions[session_id])

    # Verify report metrics
    assert report.session_id == session_id
    assert len(report.calls) >= 4

    # Verify individual call metrics
    assert report.calls[0].input_tokens == 1500
    assert report.calls[0].cache_creation_input_tokens == 2000
    assert report.calls[1].cache_read_input_tokens == 2000

    # Verify totals
    assert report.total_input_tokens >= 31000  # 1500+1500+3000+25000
    assert report.total_output_tokens >= 4000  # 300+200+500+3000
    assert report.total_cache_write_tokens >= 3500  # 2000+1500
    assert report.total_cache_read_tokens >= 2000

    # Verify cache efficiency (at least 1 of 4+ calls hit cache)
    assert report.cache_efficiency > 0

    # Verify cost estimation produces a positive number
    cost = report.estimated_cost()
    assert cost > 0, "Cost should be positive"
    assert cost < 1.0, "Cost should be less than $1 for this test"

    # Verify anomaly detection found issues
    # Call 3 is cache miss after hit (cache_create > 0 after previous cache_read > 0)
    # Call 4 is massive token spike (28000 total vs avg ~8875 → 3.15x)
    # Call 5 error should be flagged
    assert len(report.anomalies) >= 1, f"Expected anomalies, got: {report.anomalies}"

    # Verify at least one anomaly mentions cache miss or spike or error
    all_anomaly_text = " ".join(report.anomalies).lower()
    assert any(keyword in all_anomaly_text for keyword in ["cache", "spike", "error"]), (
        f"Expected cache/spike/error anomaly. Got: {report.anomalies}"
    )


def test_e2e_multiple_sessions_in_same_file(work_dir, monkeypatch):
    """
    Verify that multiple SDK sessions can write to the same JSONL file
    and the report correctly separates them.
    """
    # Set up mock anthropic
    mock_anthropic = MagicMock()
    mock_Messages = MagicMock()
    mock_Messages.create = MagicMock(return_value=make_response(500, 100))
    mock_Messages.stream = MagicMock(return_value=MockResponse())
    mock_anthropic.resources.Messages = mock_Messages
    monkeypatch.setitem(sys.modules, "anthropic", mock_anthropic)

    from lexilensai import LexiLens
    from lexilensai.report import parse_spans, group_by_session, build_session_report

    # Session 1
    lexilens1 = LexiLens.init(exporter="jsonl", objective="Session 1")
    session_id_1 = lexilens1.session_id
    mock_Messages.create(None, model="claude-sonnet-4-20250514")
    mock_Messages.create(None, model="claude-sonnet-4-20250514")
    lexilens1.close()

    # Session 2 (appends to same JSONL file)
    lexilens2 = LexiLens.init(exporter="jsonl", objective="Session 2")
    session_id_2 = lexilens2.session_id
    mock_Messages.create(None, model="claude-sonnet-4-20250514")
    lexilens2.close()

    # Parse and verify
    jsonl_path = work_dir / "lexilens_spans.jsonl"
    spans = parse_spans(jsonl_path)

    sessions = group_by_session(spans)
    assert session_id_1 in sessions, f"Session 1 not found. Keys: {list(sessions.keys())}"
    assert session_id_2 in sessions, f"Session 2 not found. Keys: {list(sessions.keys())}"

    report1 = build_session_report(session_id_1, sessions[session_id_1])
    report2 = build_session_report(session_id_2, sessions[session_id_2])

    assert len(report1.calls) >= 2
    assert len(report2.calls) >= 1


def test_e2e_report_json_output_format(work_dir, monkeypatch):
    """
    Verify the JSON output mode produces valid, parseable JSON with expected structure.
    """
    mock_anthropic = MagicMock()
    mock_Messages = MagicMock()
    mock_Messages.create = MagicMock(return_value=make_response(1000, 200, cache_read=500))
    mock_Messages.stream = MagicMock(return_value=MockResponse())
    mock_anthropic.resources.Messages = mock_Messages
    monkeypatch.setitem(sys.modules, "anthropic", mock_anthropic)

    from lexilensai import LexiLens
    from lexilensai.report import parse_spans, group_by_session, build_session_report

    # Run a session
    lexilens = LexiLens.init(exporter="jsonl", objective="JSON report test")
    session_id = lexilens.session_id
    mock_Messages.create(None, model="claude-sonnet-4-20250514")
    mock_Messages.create(None, model="claude-sonnet-4-20250514")
    mock_Messages.create(None, model="claude-sonnet-4-20250514")
    lexilens.close()

    # Build report
    spans = parse_spans(work_dir / "lexilens_spans.jsonl")
    sessions = group_by_session(spans)
    report = build_session_report(session_id, sessions[session_id])

    # Verify the report can be serialized to JSON-compatible dict
    report_dict = {
        "session_id": report.session_id,
        "total_calls": len(report.calls),
        "total_input_tokens": report.total_input_tokens,
        "total_output_tokens": report.total_output_tokens,
        "cache_efficiency_pct": report.cache_efficiency,
        "estimated_cost_usd": report.estimated_cost(),
        "anomalies": report.anomalies,
        "calls": [
            {
                "call_number": c.call_number,
                "model": c.model,
                "input_tokens": c.input_tokens,
                "output_tokens": c.output_tokens,
                "cache_creation_input_tokens": c.cache_creation_input_tokens,
                "cache_read_input_tokens": c.cache_read_input_tokens,
                "latency_ms": c.latency_ms,
                "status": c.status,
            }
            for c in report.calls
        ],
    }

    # Verify it's valid JSON
    json_str = json.dumps(report_dict)
    parsed = json.loads(json_str)

    assert parsed["session_id"] == session_id
    assert parsed["total_calls"] >= 3
    assert parsed["total_input_tokens"] == 3000  # 1000 * 3
    assert parsed["total_output_tokens"] == 600  # 200 * 3
    assert parsed["estimated_cost_usd"] > 0
    assert parsed["cache_efficiency_pct"] > 0  # all 3 calls have cache_read=500


def test_e2e_context_manager_workflow(work_dir, monkeypatch):
    """
    Verify the context manager (with statement) properly flushes spans.
    """
    mock_anthropic = MagicMock()
    mock_Messages = MagicMock()
    mock_Messages.create = MagicMock(return_value=make_response(800, 150))
    mock_Messages.stream = MagicMock(return_value=MockResponse())
    mock_anthropic.resources.Messages = mock_Messages
    monkeypatch.setitem(sys.modules, "anthropic", mock_anthropic)

    from lexilensai import LexiLens
    from lexilensai.report import parse_spans

    # Use context manager
    with LexiLens.init(exporter="jsonl", objective="Context manager test") as lexilens:
        session_id = lexilens.session_id
        mock_Messages.create(None, model="claude-sonnet-4-20250514")

    # After exiting context, JSONL should be written
    jsonl_path = work_dir / "lexilens_spans.jsonl"
    assert jsonl_path.exists()

    spans = parse_spans(jsonl_path)
    model_calls = [s for s in spans if s["span_name"] == "model.call"]
    assert len(model_calls) >= 1

    # Session should be properly closed (session.end span present)
    end_spans = [s for s in spans if s["span_name"] == "session.end"]
    assert len(end_spans) == 1


def test_e2e_cache_miss_anomaly_detection(work_dir, monkeypatch):
    """
    Verify that a cache miss after a cache hit is detected as an anomaly.

    Scenario: Call 1 creates cache, Call 2 reads cache, Call 3 has a new
    cache_creation (indicating the prefix changed and a new cache was created)
    → anomaly reported.

    The detection rule: if prev call had cache_read > 0, and this call has
    cache_creation > 0 (not cache_read), it means the prompt prefix changed.
    """
    mock_anthropic = MagicMock()
    mock_Messages = MagicMock()

    call_seq = [
        make_response(1000, 200, cache_create=1500, cache_read=None),  # creates cache
        make_response(1000, 150, cache_create=None, cache_read=1500),  # hits cache
        make_response(2000, 300, cache_create=1200, cache_read=None),  # miss → new create!
    ]
    call_counter = {"n": 0}

    def mock_create(self, *args, **kwargs):
        idx = call_counter["n"]
        call_counter["n"] += 1
        return call_seq[idx] if idx < len(call_seq) else make_response(100, 50)

    mock_Messages.create = mock_create
    mock_Messages.stream = MagicMock(return_value=MockResponse())
    mock_anthropic.resources.Messages = mock_Messages
    monkeypatch.setitem(sys.modules, "anthropic", mock_anthropic)

    from lexilensai import LexiLens
    from lexilensai.report import parse_spans, group_by_session, build_session_report

    lexilens = LexiLens.init(exporter="jsonl", objective="Cache anomaly test")
    session_id = lexilens.session_id

    for _ in range(3):
        mock_Messages.create(None, model="claude-sonnet-4-20250514")

    lexilens.close()

    # Verify anomaly detected
    spans = parse_spans(work_dir / "lexilens_spans.jsonl")
    sessions = group_by_session(spans)
    report = build_session_report(session_id, sessions[session_id])

    # Should detect cache miss anomaly (call 3 has no cache read after call 2 had one)
    cache_anomalies = [a for a in report.anomalies if "cache" in a.lower() or "miss" in a.lower()]
    assert len(cache_anomalies) >= 1, (
        f"Expected cache miss anomaly. Got anomalies: {report.anomalies}"
    )
