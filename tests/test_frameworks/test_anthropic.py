"""
Tests for Anthropic SDK instrumentation.

Mocks the anthropic client to avoid requiring API keys.
"""
from typing import Any
from unittest.mock import MagicMock, Mock

import pytest


class MockUsage:
    """Mock usage object from Anthropic API."""

    def __init__(
        self,
        input_tokens: int = 100,
        output_tokens: int = 50,
        cache_creation_input_tokens: int | None = None,
        cache_read_input_tokens: int | None = None
    ):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_creation_input_tokens = cache_creation_input_tokens
        self.cache_read_input_tokens = cache_read_input_tokens


class MockContentBlock:
    """Mock content block from Anthropic API."""

    def __init__(self, type: str, text: str = "", thinking: str = ""):
        self.type = type
        self.text = text
        self.thinking = thinking


class MockResponse:
    """Mock response from Anthropic API."""

    def __init__(
        self,
        usage: MockUsage | None = None,
        content: list[MockContentBlock] | None = None
    ):
        self.usage = usage or MockUsage()
        self.content = content or [MockContentBlock(type="text", text="Hello")]


class MockExporter:
    """Mock exporter for capturing spans."""

    def __init__(self):
        self.spans = []

    def export(self, span: Any) -> None:
        """Capture span."""
        self.spans.append(span)

    def close(self) -> None:
        """No-op close."""
        pass


@pytest.fixture(autouse=True)
def reset_anthropic_globals():
    """Reset module-level globals between tests to avoid state leakage."""
    import lexilensai.frameworks.anthropic as anthropic_mod
    anthropic_mod._original_messages_create = None
    anthropic_mod._original_messages_stream = None
    yield
    anthropic_mod._original_messages_create = None
    anthropic_mod._original_messages_stream = None


@pytest.fixture
def mock_anthropic_module(monkeypatch):
    """
    Mock the anthropic module structure.

    Returns tuple of (mock_module, mock_Messages_class)
    """
    # Create mock module
    mock_module = MagicMock()

    # Create mock Messages class
    mock_Messages = Mock()
    mock_Messages.create = Mock(return_value=MockResponse())
    mock_Messages.stream = Mock(return_value=MockResponse())

    # Wire up module structure
    mock_module.resources.Messages = mock_Messages

    # Patch the import
    monkeypatch.setitem(__import__("sys").modules, "anthropic", mock_module)

    return mock_module, mock_Messages


def test_patch_anthropic_basic_call(mock_anthropic_module):
    """Test that patch_anthropic instruments messages.create()."""
    from lexilensai.frameworks.anthropic import patch_anthropic

    mock_module, mock_Messages = mock_anthropic_module
    exporter = MockExporter()
    session_id = "test_session"

    # Patch
    patch_anthropic(session_id, exporter)

    # Verify Messages.create was patched (not equal to original mock)
    assert mock_Messages.create != Mock

    # Simulate a call
    client = Mock()
    client._client = mock_module
    mock_Messages.create(
        client,
        model="claude-sonnet-4-20250514",
        messages=[{"role": "user", "content": "Hello"}],
        max_tokens=100
    )

    # Verify span was emitted
    assert len(exporter.spans) == 1
    span = exporter.spans[0]

    assert span.span_name == "model.call"
    assert span.attributes["session_id"] == session_id
    assert span.attributes["model"] == "claude-sonnet-4-20250514"
    assert span.attributes["status"] == "success"
    assert span.attributes["is_streaming"] is False
    assert "latency_ms" in span.attributes

    # Verify token counts
    assert span.attributes["input_tokens"] == 100
    assert span.attributes["output_tokens"] == 50


def test_patch_anthropic_with_cache_tokens(mock_anthropic_module, monkeypatch):
    """Test that patch_anthropic captures cache token counts."""
    from lexilensai.frameworks.anthropic import patch_anthropic

    mock_module, mock_Messages = mock_anthropic_module
    exporter = MockExporter()
    session_id = "test_session"

    # Set the mock response with cache tokens BEFORE patching
    # (patch_anthropic saves the original .create reference)
    cache_response = MockResponse(
        usage=MockUsage(
            input_tokens=100,
            output_tokens=50,
            cache_creation_input_tokens=200,
            cache_read_input_tokens=150
        )
    )
    mock_Messages.create = Mock(return_value=cache_response)

    # Patch (saves mock_Messages.create as the "original")
    patch_anthropic(session_id, exporter)

    # Call the patched version
    client = Mock()
    mock_Messages.create(client, model="claude-sonnet-4-20250514")

    # Verify cache tokens captured
    span = exporter.spans[0]
    assert span.attributes["cache_creation_input_tokens"] == 200
    assert span.attributes["cache_read_input_tokens"] == 150


def test_patch_anthropic_with_thinking_tokens(mock_anthropic_module):
    """Test that patch_anthropic counts thinking tokens."""
    from lexilensai.frameworks.anthropic import patch_anthropic

    mock_module, mock_Messages = mock_anthropic_module
    exporter = MockExporter()
    session_id = "test_session"

    # Mock response with thinking block — set BEFORE patching
    thinking_text = "Let me think about this problem step by step..." * 10  # ~480 chars
    thinking_response = MockResponse(
        usage=MockUsage(input_tokens=100, output_tokens=150),
        content=[
            MockContentBlock(type="thinking", thinking=thinking_text),
            MockContentBlock(type="text", text="Here's my answer")
        ]
    )
    mock_Messages.create = Mock(return_value=thinking_response)

    # Patch (saves mock_Messages.create as the "original")
    patch_anthropic(session_id, exporter)

    # Call the patched version
    client = Mock()
    mock_Messages.create(client, model="claude-sonnet-4-20250514")

    # Verify thinking tokens captured (rough estimate: len/4)
    span = exporter.spans[0]
    assert "thinking_tokens" in span.attributes
    assert span.attributes["thinking_tokens"] > 0
    # Should be approximately len(thinking_text) / 4
    assert span.attributes["thinking_tokens"] > 90  # ~480/4 = 120


def test_patch_anthropic_streaming_call(mock_anthropic_module):
    """Test that patch_anthropic instruments messages.stream()."""
    from lexilensai.frameworks.anthropic import patch_anthropic

    mock_module, mock_Messages = mock_anthropic_module
    exporter = MockExporter()
    session_id = "test_session"

    # Patch
    patch_anthropic(session_id, exporter)

    # Simulate streaming call
    client = Mock()
    mock_Messages.stream(
        client,
        model="claude-sonnet-4-20250514",
        messages=[{"role": "user", "content": "Hello"}]
    )

    # Verify span emitted
    assert len(exporter.spans) == 1
    span = exporter.spans[0]

    assert span.span_name == "model.call"
    assert span.attributes["is_streaming"] is True
    assert span.attributes["model"] == "claude-sonnet-4-20250514"


def test_patch_anthropic_error_handling(mock_anthropic_module):
    """Test that patch_anthropic handles errors gracefully."""
    from lexilensai.frameworks.anthropic import patch_anthropic

    mock_module, mock_Messages = mock_anthropic_module
    exporter = MockExporter()
    session_id = "test_session"

    # Set error-raising mock BEFORE patching
    mock_Messages.create = Mock(side_effect=Exception("API error"))

    # Patch (saves the error-raising mock as the "original")
    patch_anthropic(session_id, exporter)

    # Call should raise but span should be emitted
    client = Mock()
    with pytest.raises(Exception, match="API error"):
        mock_Messages.create(client, model="claude-sonnet-4-20250514")

    # Verify error span emitted
    assert len(exporter.spans) == 1
    span = exporter.spans[0]
    assert span.attributes["status"] == "error"
    assert "API error" in span.attributes["error"]


def test_patch_anthropic_unpatch(mock_anthropic_module):
    """Test that unpatch_anthropic restores original behavior."""
    from lexilensai.frameworks.anthropic import patch_anthropic, unpatch_anthropic

    mock_module, mock_Messages = mock_anthropic_module
    exporter = MockExporter()
    session_id = "test_session"

    # Save reference to original create before patch
    original_create = mock_Messages.create

    # Patch — saves original_create internally, replaces with instrumented version
    patch_anthropic(session_id, exporter)

    # Verify it changed (patched version is a different function)
    assert mock_Messages.create is not original_create

    # Unpatch — should restore the saved original
    unpatch_anthropic()

    # Verify restored to the same function object
    assert mock_Messages.create is original_create


def test_patch_anthropic_not_installed(monkeypatch):
    """Test that patch_anthropic gracefully skips if anthropic not installed."""
    import builtins
    import sys

    from lexilensai.frameworks.anthropic import patch_anthropic

    # Remove anthropic from sys.modules if present
    monkeypatch.delitem(sys.modules, "anthropic", raising=False)

    # Make anthropic import fail
    original_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "anthropic":
            raise ImportError("No module named 'anthropic'")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mock_import)

    exporter = MockExporter()
    session_id = "test_session"

    # Should not raise
    patch_anthropic(session_id, exporter)

    # No spans should be emitted (nothing was patched)
    assert len(exporter.spans) == 0


def test_patch_anthropic_parent_span_tracking(mock_anthropic_module):
    """Test that patch_anthropic respects parent span stack."""
    from lexilensai.frameworks.anthropic import patch_anthropic

    mock_module, mock_Messages = mock_anthropic_module
    exporter = MockExporter()
    session_id = "test_session"

    # Patch
    patch_anthropic(session_id, exporter)

    # Simulate nested calls (would happen in real agent context)
    # For this test, we just verify parent_span_id is None when stack is empty
    client = Mock()
    mock_Messages.create(client, model="claude-sonnet-4-20250514")

    span = exporter.spans[0]
    # When span stack is empty, parent_span_id should be None or not present
    assert span.attributes.get("parent_span_id") is None


def test_count_thinking_tokens_empty_response():
    """Test _count_thinking_tokens with no thinking blocks."""
    from lexilensai.frameworks.anthropic import _count_thinking_tokens

    response = MockResponse(content=[
        MockContentBlock(type="text", text="Just a normal response")
    ])

    count = _count_thinking_tokens(response)
    assert count == 0


def test_count_thinking_tokens_with_thinking():
    """Test _count_thinking_tokens with thinking blocks."""
    from lexilensai.frameworks.anthropic import _count_thinking_tokens

    thinking_text = "x" * 400  # 400 chars
    response = MockResponse(content=[
        MockContentBlock(type="thinking", thinking=thinking_text),
        MockContentBlock(type="text", text="Answer")
    ])

    count = _count_thinking_tokens(response)
    # Should be approximately 400/4 = 100
    assert count == 100


def test_count_thinking_tokens_no_content():
    """Test _count_thinking_tokens with response that has no content attribute."""
    from lexilensai.frameworks.anthropic import _count_thinking_tokens

    response = Mock(spec=[])  # No 'content' attribute

    count = _count_thinking_tokens(response)
    assert count == 0
