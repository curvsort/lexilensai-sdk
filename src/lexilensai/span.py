"""
Span data structure for LexiLensAI instrumentation.

Spans emitted by the SDK match the format expected by
ingestion/span_normalizer.py on the platform side.
"""
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any


@dataclass
class Span:
    """
    LexiLensAI span structure.

    This format matches what the platform's span_normalizer.py expects:
    - span_name: Determines the EventType via pattern matching
    - start_time: ISO 8601 timestamp
    - attributes: Dict with span_id, parent_span_id, session_id, etc.
    """

    span_name: str
    start_time: datetime
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """
        Serialize to dict for export.

        Returns:
            Dict with span_name, start_time (ISO string), and attributes
        """
        return {
            "span_name": self.span_name,
            "start_time": self.start_time.isoformat(),
            "attributes": self.attributes
        }

    @classmethod
    def create(
        cls,
        span_name: str,
        span_id: str,
        session_id: str,
        agent_id: str | None = None,
        parent_span_id: str | None = None,
        **extra_attrs
    ) -> "Span":
        """
        Create a span with required attributes.

        Args:
            span_name: Span name (determines EventType on platform)
            span_id: Unique span identifier
            session_id: Session grouping ID
            agent_id: Acting agent name
            parent_span_id: Parent span ID for call hierarchy
            **extra_attrs: Additional attributes (model, tool_name, tokens, etc.)

        Returns:
            Span instance
        """
        attributes = {
            "span_id": span_id,
            "session_id": session_id,
        }

        if agent_id:
            attributes["agent_id"] = agent_id

        if parent_span_id:
            attributes["parent_span_id"] = parent_span_id

        # Merge extra attributes
        attributes.update(extra_attrs)

        return cls(
            span_name=span_name,
            start_time=datetime.now(timezone.utc),
            attributes=attributes
        )


def generate_span_id(prefix: str = "span") -> str:
    """
    Generate a unique span ID.

    Uses timestamp + random component for uniqueness.

    Args:
        prefix: ID prefix (default: "span")

    Returns:
        Unique span ID string
    """
    import time
    import random
    timestamp = int(time.time() * 1000000)  # microseconds
    random_part = random.randint(1000, 9999)
    return f"{prefix}_{timestamp}_{random_part}"
