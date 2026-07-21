"""
Roundtrip tests with platform span_normalizer.

These tests verify that spans emitted by the SDK can be successfully
processed by the platform's ingestion/span_normalizer.py without errors.
"""

# Import platform's span_normalizer
from ingestion.span_normalizer import normalize_span

from lexilensai.span import Span


def test_session_start_span_roundtrip():
    """Verify session.start span passes through normalizer."""
    span = Span.create(
        span_name="session.start",
        span_id="span_001",
        session_id="sess_test_001",
        tenant_id="acme_corp",
        application_id="test_app",
        harness="strands",
        harness_version="0.5.0",
        objective="Test session"
    )

    # Convert to dict (same format normalizer expects)
    span_dict = span.to_dict()

    # Normalize via platform code
    event = normalize_span(span_dict, session_id="sess_test_001", seq=1)

    # Verify event structure
    assert event.event_id == "span_001"
    assert event.session_id == "sess_test_001"
    assert event.event_type == "SESSION_START"
    assert event.payload["tenant_id"] == "acme_corp"
    assert event.payload["application_id"] == "test_app"
    assert event.payload["harness"] == "strands"


def test_agent_start_span_roundtrip():
    """Verify agent.start span passes through normalizer."""
    span = Span.create(
        span_name="agent.start",
        span_id="span_002",
        session_id="sess_test_001",
        agent_id="research_agent",
        parent_span_id="span_001"
    )

    span_dict = span.to_dict()
    event = normalize_span(span_dict, session_id="sess_test_001", seq=2)

    assert event.event_type == "AGENT_START"
    assert event.participant_id == "research_agent"
    assert event.parent_event_id == "span_001"


def test_agent_end_span_roundtrip():
    """Verify agent.end span passes through normalizer."""
    span = Span.create(
        span_name="agent.end",
        span_id="span_003",
        session_id="sess_test_001",
        agent_id="research_agent",
        parent_span_id="span_002",
        status="success"
    )

    span_dict = span.to_dict()
    event = normalize_span(span_dict, session_id="sess_test_001", seq=3)

    assert event.event_type == "AGENT_END"
    assert event.participant_id == "research_agent"
    assert event.payload["status"] == "success"


def test_tool_call_span_roundtrip():
    """Verify tool.{name} span passes through normalizer."""
    span = Span.create(
        span_name="tool.web_search",
        span_id="span_004",
        session_id="sess_test_001",
        agent_id="research_agent",
        parent_span_id="span_002",
        tool_name="web_search",
        query="test query"
    )

    span_dict = span.to_dict()
    event = normalize_span(span_dict, session_id="sess_test_001", seq=4)

    assert event.event_type == "TOOL_CALL"
    assert event.payload["tool_name"] == "web_search"
    assert event.payload["query"] == "test query"


def test_model_call_span_roundtrip():
    """Verify model.call span passes through normalizer."""
    span = Span.create(
        span_name="model.call",
        span_id="span_005",
        session_id="sess_test_001",
        agent_id="research_agent",
        parent_span_id="span_002",
        model="claude-sonnet-4-6",
        input_tokens=1500,
        output_tokens=300
    )

    span_dict = span.to_dict()
    event = normalize_span(span_dict, session_id="sess_test_001", seq=5)

    assert event.event_type == "MODEL_CALL"
    assert event.payload["model"] == "claude-sonnet-4-6"
    assert event.payload["input_tokens"] == 1500
    assert event.payload["output_tokens"] == 300


def test_session_end_span_roundtrip():
    """Verify session.end span passes through normalizer."""
    span = Span.create(
        span_name="session.end",
        span_id="span_006",
        session_id="sess_test_001"
    )

    span_dict = span.to_dict()
    event = normalize_span(span_dict, session_id="sess_test_001", seq=6)

    assert event.event_type == "SESSION_END"


def test_full_session_roundtrip():
    """
    Test a complete session flow through the normalizer.

    Simulates: session start → agent start → tool call → agent end → session end
    """
    session_id = "sess_integration_test"
    spans = []

    # 1. Session start
    spans.append(Span.create(
        span_name="session.start",
        span_id="span_001",
        session_id=session_id,
        tenant_id="test_tenant",
        application_id="test_app",
        harness="strands",
        harness_version="0.5.0"
    ))

    # 2. Agent start
    spans.append(Span.create(
        span_name="agent.start",
        span_id="span_002",
        session_id=session_id,
        agent_id="orchestrator",
        parent_span_id="span_001"
    ))

    # 3. Tool call
    spans.append(Span.create(
        span_name="tool.calculator",
        span_id="span_003",
        session_id=session_id,
        agent_id="orchestrator",
        parent_span_id="span_002",
        tool_name="calculator"
    ))

    # 4. Agent end
    spans.append(Span.create(
        span_name="agent.end",
        span_id="span_004",
        session_id=session_id,
        agent_id="orchestrator",
        parent_span_id="span_002",
        status="success"
    ))

    # 5. Session end
    spans.append(Span.create(
        span_name="session.end",
        span_id="span_005",
        session_id=session_id
    ))

    # Normalize all spans
    events = []
    for idx, span in enumerate(spans, start=1):
        span_dict = span.to_dict()
        event = normalize_span(span_dict, session_id=session_id, seq=idx)
        events.append(event)

    # Verify sequence
    assert len(events) == 5
    assert events[0].event_type == "SESSION_START"
    assert events[1].event_type == "AGENT_START"
    assert events[2].event_type == "TOOL_CALL"
    assert events[3].event_type == "AGENT_END"
    assert events[4].event_type == "SESSION_END"

    # Verify parent-child relationships
    assert events[1].parent_event_id == "span_001"
    assert events[2].parent_event_id == "span_002"
    assert events[3].parent_event_id == "span_002"
