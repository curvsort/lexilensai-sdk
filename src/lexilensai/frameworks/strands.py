"""
Strands framework instrumentation.

Monkey-patches strands.Agent.__call__ to emit session-aware spans.
Tracks parent-child relationships via call stack.
"""
import threading
from typing import Any, Callable

from ..span import Span, generate_span_id

# Thread-local span stack for parent tracking
_span_stack = threading.local()


def _get_span_stack() -> list[str]:
    """Get the current thread's span stack."""
    if not hasattr(_span_stack, "stack"):
        _span_stack.stack = []
    return _span_stack.stack


# Store original __call__ for unpatch
_original_agent_call: Callable | None = None


def patch_strands(session_id: str, exporter: Any) -> None:
    """
    Patch strands.Agent to emit spans.

    Args:
        session_id: Session ID for all spans
        exporter: Exporter instance (OTelExporter, JSONLExporter, or ConsoleExporter)
    """
    try:
        from strands import Agent
    except ImportError:
        print("Warning: strands package not found. Skipping instrumentation.")
        return

    global _original_agent_call

    # Save original if not already patched
    if _original_agent_call is None:
        _original_agent_call = Agent.__call__

    def instrumented_call(self, *args, **kwargs):
        """Instrumented Agent.__call__ that emits spans."""
        # Extract agent name
        agent_name = _extract_agent_name(self)

        # Generate span IDs
        span_id = generate_span_id()
        stack = _get_span_stack()
        parent_span_id = stack[-1] if stack else None

        # Push to stack
        stack.append(span_id)

        # Emit agent.start span
        start_span = Span.create(
            span_name="agent.start",
            span_id=span_id,
            session_id=session_id,
            agent_id=agent_name,
            parent_span_id=parent_span_id
        )
        exporter.export(start_span)

        try:
            # Call original agent
            result = _original_agent_call(self, *args, **kwargs)

            # Emit agent.end span
            end_span = Span.create(
                span_name="agent.end",
                span_id=generate_span_id(),
                session_id=session_id,
                agent_id=agent_name,
                parent_span_id=span_id,
                status="success"
            )
            exporter.export(end_span)

            return result

        except Exception as e:
            # Emit agent.end with error
            end_span = Span.create(
                span_name="agent.end",
                span_id=generate_span_id(),
                session_id=session_id,
                agent_id=agent_name,
                parent_span_id=span_id,
                status="error",
                error=str(e)
            )
            exporter.export(end_span)
            raise

        finally:
            # Pop from stack
            stack.pop()

    # Apply patch
    Agent.__call__ = instrumented_call


def unpatch_strands() -> None:
    """Restore original Agent.__call__."""
    global _original_agent_call

    if _original_agent_call is None:
        return

    try:
        from strands import Agent
        Agent.__call__ = _original_agent_call
        _original_agent_call = None
    except ImportError:
        pass


def _extract_agent_name(agent: Any) -> str:
    """
    Extract agent name from Strands Agent instance.

    Heuristics:
    1. Check for explicit 'name' attribute
    2. Parse from system_prompt if it contains "You are X"
    3. Check for 'role' attribute
    4. Use class name as fallback

    Args:
        agent: Strands Agent instance

    Returns:
        Agent name string
    """
    # Try direct name attribute
    if hasattr(agent, "name") and agent.name:
        return str(agent.name)

    # Try parsing from system_prompt
    if hasattr(agent, "system_prompt") and agent.system_prompt:
        prompt = str(agent.system_prompt).lower()
        # Look for "you are X" pattern
        if "you are" in prompt:
            # Extract the next few words
            idx = prompt.index("you are")
            after = prompt[idx + 8:idx + 50]  # "you are " = 8 chars
            # Take first word or phrase (up to period/newline)
            name_part = after.split(".")[0].split("\n")[0].strip()
            if name_part:
                # Clean up and titlecase
                name = name_part.replace("an ", "").replace("a ", "").strip()
                return name.replace(" ", "_")

    # Try role attribute
    if hasattr(agent, "role") and agent.role:
        return str(agent.role)

    # Fallback to class name
    return agent.__class__.__name__
