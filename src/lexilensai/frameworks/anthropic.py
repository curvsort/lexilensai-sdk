"""
Anthropic SDK instrumentation.

Monkey-patches anthropic.Anthropic.messages.create() and .stream()
to emit model.call spans with token usage, latency, and thinking metrics.
"""
import threading
import time
from typing import Any, Callable

from ..span import Span, generate_span_id

# Thread-local span stack for parent tracking
_span_stack = threading.local()


def _get_span_stack() -> list[str]:
    """Get the current thread's span stack."""
    if not hasattr(_span_stack, "stack"):
        _span_stack.stack = []
    return _span_stack.stack


# Store original methods for unpatch
_original_messages_create: Callable | None = None
_original_messages_stream: Callable | None = None


def patch_anthropic(session_id: str, exporter: Any) -> None:
    """
    Patch anthropic.Anthropic.messages to emit model.call spans.

    Args:
        session_id: Session ID for all spans
        exporter: Exporter instance (OTelExporter, JSONLExporter, or ConsoleExporter)
    """
    try:
        import anthropic
    except ImportError:
        # Silently skip if anthropic not installed
        return

    global _original_messages_create, _original_messages_stream

    # Get Messages class
    try:
        Messages = anthropic.resources.Messages
    except AttributeError:
        print("Warning: anthropic SDK structure changed. Skipping instrumentation.")
        return

    # Save originals if not already patched
    if _original_messages_create is None:
        _original_messages_create = Messages.create

    if _original_messages_stream is None:
        _original_messages_stream = Messages.stream

    def instrumented_create(self, *args, **kwargs):
        """Instrumented messages.create() that emits model.call spans."""
        return _instrument_model_call(
            _original_messages_create,
            self,
            args,
            kwargs,
            session_id,
            exporter,
            is_streaming=False
        )

    def instrumented_stream(self, *args, **kwargs):
        """Instrumented messages.stream() that emits model.call spans."""
        # For streaming, we still emit one span per call
        # The span captures total tokens after stream completes
        return _instrument_model_call(
            _original_messages_stream,
            self,
            args,
            kwargs,
            session_id,
            exporter,
            is_streaming=True
        )

    # Apply patches
    Messages.create = instrumented_create
    Messages.stream = instrumented_stream


def unpatch_anthropic() -> None:
    """Restore original messages.create() and .stream()."""
    global _original_messages_create, _original_messages_stream

    if _original_messages_create is None:
        return

    try:
        import anthropic
        Messages = anthropic.resources.Messages
        Messages.create = _original_messages_create
        Messages.stream = _original_messages_stream
        _original_messages_create = None
        _original_messages_stream = None
    except ImportError:
        pass


def _instrument_model_call(
    original_func: Callable,
    self: Any,
    args: tuple,
    kwargs: dict,
    session_id: str,
    exporter: Any,
    is_streaming: bool
) -> Any:
    """
    Instrument a model call (create or stream).

    Args:
        original_func: Original messages.create or messages.stream
        self: Messages instance
        args: Positional arguments
        kwargs: Keyword arguments
        session_id: Session ID
        exporter: Exporter instance
        is_streaming: Whether this is a streaming call

    Returns:
        Original function result
    """
    # Generate span IDs
    span_id = generate_span_id(prefix="model")
    stack = _get_span_stack()
    parent_span_id = stack[-1] if stack else None

    # Extract model name from kwargs
    model_name = kwargs.get("model", "unknown")

    # Measure latency
    start_time = time.time()

    try:
        # Call original function
        result = original_func(self, *args, **kwargs)

        # Calculate latency
        latency_ms = int((time.time() - start_time) * 1000)

        # Extract usage metrics
        usage_attrs = _extract_usage(result, is_streaming)

        # Emit model.call span
        span = Span.create(
            span_name="model.call",
            span_id=span_id,
            session_id=session_id,
            parent_span_id=parent_span_id,
            model=model_name,
            latency_ms=latency_ms,
            is_streaming=is_streaming,
            status="success",
            **usage_attrs
        )
        exporter.export(span)

        return result

    except Exception as e:
        # Calculate latency for failed call
        latency_ms = int((time.time() - start_time) * 1000)

        # Emit model.call span with error
        span = Span.create(
            span_name="model.call",
            span_id=span_id,
            session_id=session_id,
            parent_span_id=parent_span_id,
            model=model_name,
            latency_ms=latency_ms,
            is_streaming=is_streaming,
            status="error",
            error=str(e)
        )
        exporter.export(span)
        raise


def _extract_usage(result: Any, is_streaming: bool) -> dict[str, Any]:
    """
    Extract token usage from API response.

    Args:
        result: Response from messages.create() or messages.stream()
        is_streaming: Whether this is a streaming response

    Returns:
        Dict with token usage attributes
    """
    usage_attrs = {}

    if is_streaming:
        # For streaming, we need to consume the stream to get usage
        # Return the stream wrapper and extract usage later
        # For now, just return empty - full streaming support is future work
        return usage_attrs

    # Non-streaming response
    if hasattr(result, "usage"):
        usage = result.usage

        # Standard token counts
        if hasattr(usage, "input_tokens"):
            usage_attrs["input_tokens"] = usage.input_tokens
        if hasattr(usage, "output_tokens"):
            usage_attrs["output_tokens"] = usage.output_tokens

        # Prompt caching tokens
        if hasattr(usage, "cache_creation_input_tokens") and usage.cache_creation_input_tokens:
            usage_attrs["cache_creation_input_tokens"] = usage.cache_creation_input_tokens
        if hasattr(usage, "cache_read_input_tokens") and usage.cache_read_input_tokens:
            usage_attrs["cache_read_input_tokens"] = usage.cache_read_input_tokens

    # Extract thinking tokens if present
    thinking_tokens = _count_thinking_tokens(result)
    if thinking_tokens > 0:
        usage_attrs["thinking_tokens"] = thinking_tokens

    return usage_attrs


def _count_thinking_tokens(result: Any) -> int:
    """
    Count tokens used for extended thinking.

    Extended thinking appears as content blocks with type="thinking".

    Args:
        result: API response

    Returns:
        Number of thinking tokens
    """
    if not hasattr(result, "content"):
        return 0

    thinking_count = 0

    for block in result.content:
        # Check if this is a thinking block
        if hasattr(block, "type") and block.type == "thinking":
            # Rough token count: ~4 chars per token
            if hasattr(block, "thinking"):
                text = block.thinking
            elif hasattr(block, "text"):
                text = block.text
            else:
                continue

            # Estimate tokens (rough approximation)
            thinking_count += len(text) // 4

    return thinking_count
