"""Tests for Span data structure."""
from lexilensai.span import Span, generate_span_id


def test_span_create():
    """Test Span.create with required attributes."""
    span = Span.create(
        span_name="test.span",
        span_id="span_001",
        session_id="sess_001",
        agent_id="test_agent"
    )

    assert span.span_name == "test.span"
    assert span.attributes["span_id"] == "span_001"
    assert span.attributes["session_id"] == "sess_001"
    assert span.attributes["agent_id"] == "test_agent"


def test_span_create_with_parent():
    """Test Span.create with parent_span_id."""
    span = Span.create(
        span_name="test.span",
        span_id="span_002",
        session_id="sess_001",
        parent_span_id="span_001"
    )

    assert span.attributes["parent_span_id"] == "span_001"


def test_span_create_with_extra_attrs():
    """Test Span.create with additional attributes."""
    span = Span.create(
        span_name="tool.web_search",
        span_id="span_003",
        session_id="sess_001",
        tool_name="web_search",
        query="test query",
        results_count=5
    )

    assert span.attributes["tool_name"] == "web_search"
    assert span.attributes["query"] == "test query"
    assert span.attributes["results_count"] == 5


def test_span_to_dict():
    """Test span serialization to dict."""
    span = Span.create(
        span_name="test.span",
        span_id="span_001",
        session_id="sess_001"
    )

    span_dict = span.to_dict()

    assert isinstance(span_dict, dict)
    assert span_dict["span_name"] == "test.span"
    assert isinstance(span_dict["start_time"], str)  # ISO format
    assert isinstance(span_dict["attributes"], dict)


def test_generate_span_id():
    """Test span ID generation."""
    span_id = generate_span_id()

    assert isinstance(span_id, str)
    assert span_id.startswith("span_")

    # Generate multiple IDs and verify uniqueness
    ids = {generate_span_id() for _ in range(100)}
    assert len(ids) == 100  # All unique
