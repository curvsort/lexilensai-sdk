"""
Console exporter for debugging.

Prints spans to stdout in human-readable format.
"""
import json

from ..span import Span


class ConsoleExporter:
    """
    Console debug exporter.

    Prints each span to stdout with formatted JSON. Useful for
    development and debugging.
    """

    def __init__(self):
        """Initialize console exporter."""
        print("=== LexiLens ConsoleExporter initialized ===")

    def export(self, span: Span) -> None:
        """
        Export a span to console.

        Args:
            span: Span to print
        """
        print(f"\n--- Span: {span.span_name} ---")
        print(f"Timestamp: {span.start_time.isoformat()}")
        print("Attributes:")
        print(json.dumps(span.attributes, indent=2))
        print("---")

    def close(self) -> None:
        """Cleanup (no-op for console)."""
        print("=== LexiLens ConsoleExporter closed ===")
