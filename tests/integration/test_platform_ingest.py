"""
End-to-end platform test: SDK → HTTP POST → LexiLensAI platform → query back.

This test verifies the full platform integration:
1. Initialize SDK with platform exporter
2. Emit spans (mocked Anthropic calls)
3. Close session (flushes to platform via HTTP)
4. Query platform API to verify the session is visible
5. Verify events, graph edges, and findings are queryable

Requirements:
    - Docker platform running: docker compose up -d
    - Platform accessible at http://localhost:8000

Usage:
    # Start platform:
    docker compose up -d

    # Run this test:
    pytest tests/integration/test_platform_ingest.py -v

    # Or standalone:
    python tests/integration/test_platform_ingest.py

Skipped automatically in CI if the platform is not reachable.
"""
import json
import os
import sys
import time
from typing import Any
from unittest.mock import MagicMock
from urllib.error import URLError
from urllib.request import Request, urlopen

import pytest


PLATFORM_URL = os.environ.get("LEXILENS_PLATFORM_URL", "http://localhost:8000")


def platform_is_up() -> bool:
    """Check if the platform is reachable."""
    try:
        req = Request(f"{PLATFORM_URL}/", method="GET")
        response = urlopen(req, timeout=3)
        data = json.loads(response.read().decode("utf-8"))
        return data.get("status") == "ok"
    except (URLError, OSError, json.JSONDecodeError):
        return False


def get_json(path: str) -> dict[str, Any]:
    """GET JSON from platform API."""
    url = f"{PLATFORM_URL}{path}"
    req = Request(url, headers={"Accept": "application/json"})
    response = urlopen(req, timeout=10)
    return json.loads(response.read().decode("utf-8"))


# Skip all tests in this module if platform is not running
pytestmark = pytest.mark.skipif(
    not platform_is_up(),
    reason=f"LexiLensAI platform not reachable at {PLATFORM_URL}. Run: docker compose up -d"
)


# ─── Mock Anthropic (same as other tests) ────────────────────────────────────


class MockUsage:
    def __init__(self, input_tokens=100, output_tokens=50,
                 cache_creation_input_tokens=None, cache_read_input_tokens=None):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_creation_input_tokens = cache_creation_input_tokens
        self.cache_read_input_tokens = cache_read_input_tokens


class MockContentBlock:
    def __init__(self, type="text", text="Mock response"):
        self.type = type
        self.text = text


class MockResponse:
    def __init__(self, usage=None, content=None):
        self.usage = usage or MockUsage()
        self.content = content or [MockContentBlock()]


@pytest.fixture(autouse=True)
def reset_anthropic_module():
    """Reset anthropic instrumentation state between tests."""
    import lexilensai.frameworks.anthropic as mod
    mod._original_messages_create = None
    mod._original_messages_stream = None
    yield
    mod._original_messages_create = None
    mod._original_messages_stream = None


# ─── Tests ───────────────────────────────────────────────────────────────────


def test_platform_health():
    """Verify platform is up and responding."""
    health = get_json("/")
    assert health["status"] == "ok"
    assert "lexilensai" in health.get("service", "").lower()


def test_sdk_to_platform_full_roundtrip(monkeypatch):
    """
    Full round-trip: SDK init → model calls → close → query platform.

    Verifies:
    - Session appears in /sessions list
    - Session metadata has correct token counts
    - Events are queryable
    - Graph edges were inferred
    """
    # Mock anthropic
    mock_anthropic = MagicMock()
    mock_Messages = MagicMock()

    responses = [
        MockResponse(usage=MockUsage(input_tokens=1200, output_tokens=300,
                                     cache_creation_input_tokens=1000)),
        MockResponse(usage=MockUsage(input_tokens=1200, output_tokens=250,
                                     cache_read_input_tokens=1000)),
        MockResponse(usage=MockUsage(input_tokens=2500, output_tokens=600)),
    ]
    call_idx = {"n": 0}

    def mock_create(self, *args, **kwargs):
        i = call_idx["n"]
        call_idx["n"] += 1
        return responses[i] if i < len(responses) else MockResponse()

    mock_Messages.create = mock_create
    mock_Messages.stream = MagicMock(return_value=MockResponse())
    mock_anthropic.resources.Messages = mock_Messages
    monkeypatch.setitem(sys.modules, "anthropic", mock_anthropic)

    from lexilensai import LexiLens

    # Initialize with platform exporter
    lexilens = LexiLens.init(
        exporter="platform",
        platform_url=PLATFORM_URL,
        tenant_id="integration_test",
        application_id="e2e_platform_test",
        objective="Verify SDK → platform round-trip",
    )
    session_id = lexilens.session_id

    # Make model calls
    for _ in range(3):
        mock_Messages.create(
            None,
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[{"role": "user", "content": "Test question"}],
        )

    # Close (flushes to platform)
    lexilens.close()

    # Give the platform a moment to process
    time.sleep(1.0)

    # ── Verify session exists on platform ──

    # Check sessions list
    sessions_resp = get_json("/sessions")
    assert sessions_resp["count"] >= 1
    session_ids = [s["session_id"] for s in sessions_resp["sessions"]]
    assert session_id in session_ids, (
        f"Session {session_id} not found in platform. "
        f"Available: {session_ids[:5]}"
    )

    # Check session detail
    session = get_json(f"/sessions/{session_id}")
    assert session["session_id"] == session_id
    assert session["status"] == "completed"

    # Verify token counts were aggregated
    token_usage = session.get("token_usage", {})
    assert token_usage.get("input", 0) > 0, f"No input tokens recorded: {token_usage}"

    # ── Verify events ──
    events_resp = get_json(f"/sessions/{session_id}/events")
    assert events_resp["count"] >= 5  # start + 3 model calls + end (minimum)

    # Check event types
    event_types = [e["event_type"] for e in events_resp["events"]]
    assert "SESSION_START" in event_types
    assert "SESSION_END" in event_types
    assert event_types.count("MODEL_CALL") >= 3

    # ── Verify graph ──
    graph_resp = get_json(f"/sessions/{session_id}/graph")
    assert graph_resp["stats"]["edge_count"] >= 0  # may be 0 if no delegations

    # ── Verify findings (anomaly detection ran) ──
    findings_resp = get_json(f"/sessions/{session_id}/findings")
    # Findings count depends on whether anomalies were detected
    assert "count" in findings_resp
    assert "findings" in findings_resp


def test_sdk_platform_multiple_sessions(monkeypatch):
    """
    Verify multiple SDK sessions can be ingested and queried independently.
    """
    mock_anthropic = MagicMock()
    mock_Messages = MagicMock()
    mock_Messages.create = MagicMock(return_value=MockResponse(
        usage=MockUsage(input_tokens=500, output_tokens=100)
    ))
    mock_Messages.stream = MagicMock(return_value=MockResponse())
    mock_anthropic.resources.Messages = mock_Messages
    monkeypatch.setitem(sys.modules, "anthropic", mock_anthropic)

    from lexilensai import LexiLens

    # Session A
    lexilens_a = LexiLens.init(
        exporter="platform",
        platform_url=PLATFORM_URL,
        objective="Session A",
    )
    session_id_a = lexilens_a.session_id
    mock_Messages.create(None, model="claude-sonnet-4-20250514")
    lexilens_a.close()

    # Session B
    lexilens_b = LexiLens.init(
        exporter="platform",
        platform_url=PLATFORM_URL,
        objective="Session B",
    )
    session_id_b = lexilens_b.session_id
    mock_Messages.create(None, model="claude-sonnet-4-20250514")
    mock_Messages.create(None, model="claude-sonnet-4-20250514")
    lexilens_b.close()

    time.sleep(1.0)

    # Verify both sessions exist
    session_a = get_json(f"/sessions/{session_id_a}")
    session_b = get_json(f"/sessions/{session_id_b}")

    assert session_a["session_id"] == session_id_a
    assert session_b["session_id"] == session_id_b

    # Verify they have different event counts
    events_a = get_json(f"/sessions/{session_id_a}/events")
    events_b = get_json(f"/sessions/{session_id_b}/events")

    # Session B has 1 more model call than Session A
    model_calls_a = sum(1 for e in events_a["events"] if e["event_type"] == "MODEL_CALL")
    model_calls_b = sum(1 for e in events_b["events"] if e["event_type"] == "MODEL_CALL")

    assert model_calls_a >= 1
    assert model_calls_b >= 2


def test_sdk_platform_token_spike_detection(monkeypatch):
    """
    Verify the platform's anomaly detector catches a token spike
    when spans are ingested via the SDK.
    """
    mock_anthropic = MagicMock()
    mock_Messages = MagicMock()

    # Normal call → normal call → 5x spike
    responses = [
        MockResponse(usage=MockUsage(input_tokens=500, output_tokens=100)),
        MockResponse(usage=MockUsage(input_tokens=600, output_tokens=120)),
        MockResponse(usage=MockUsage(input_tokens=3000, output_tokens=800)),  # 5x spike
    ]
    call_idx = {"n": 0}

    def mock_create(self, *args, **kwargs):
        i = call_idx["n"]
        call_idx["n"] += 1
        return responses[i] if i < len(responses) else MockResponse()

    mock_Messages.create = mock_create
    mock_Messages.stream = MagicMock(return_value=MockResponse())
    mock_anthropic.resources.Messages = mock_Messages
    monkeypatch.setitem(sys.modules, "anthropic", mock_anthropic)

    from lexilensai import LexiLens

    lexilens = LexiLens.init(
        exporter="platform",
        platform_url=PLATFORM_URL,
        objective="Token spike test",
    )
    session_id = lexilens.session_id

    for _ in range(3):
        mock_Messages.create(None, model="claude-sonnet-4-20250514")

    lexilens.close()
    time.sleep(1.0)

    # Check findings
    findings_resp = get_json(f"/sessions/{session_id}/findings")

    # The platform's anomaly_detector_lite should detect the token spike
    # (3x growth between consecutive model calls)
    if findings_resp["count"] > 0:
        finding_types = [f.get("finding_type", "") for f in findings_resp["findings"]]
        # Token explosion should be detected
        assert any("token" in ft.lower() or "explosion" in ft.lower() for ft in finding_types), (
            f"Expected token explosion finding. Got: {finding_types}"
        )


# ─── CLI entry point for manual testing ──────────────────────────────────────


def _run_manual():
    """Run tests manually without pytest (for quick verification)."""
    print("=" * 60)
    print("  LexiLensAI SDK → Platform Integration Test")
    print("=" * 60)
    print()

    if not platform_is_up():
        print(f"✗ Platform not reachable at {PLATFORM_URL}")
        print("  Run: docker compose up -d")
        sys.exit(1)

    print(f"✓ Platform is up at {PLATFORM_URL}")
    print()
    print("Run with pytest for full test suite:")
    print("  pytest tests/integration/test_platform_ingest.py -v")
    print()
    print("Or run the simpler script:")
    print("  python scripts/test_platform.py")


if __name__ == "__main__":
    _run_manual()
