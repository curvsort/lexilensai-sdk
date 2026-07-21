"""
JSONL file exporter for local development and testing.

Writes spans to a local .jsonl file in the exact format the platform's
span_normalizer.py expects. Useful for offline replay and testing.
"""
import json
from pathlib import Path
from typing import TextIO

from ..span import Span


class JSONLExporter:
    """
    JSONL file exporter.

    Writes each span as a JSON line to a local file. The format matches
    what span_normalizer.normalize_span() expects as input.
    """

    def __init__(self, output_path: str = "lexilens_spans.jsonl"):
        """
        Initialize JSONL exporter.

        Args:
            output_path: Path to output file (default: lexilens_spans.jsonl)
        """
        self.output_path = Path(output_path)
        self._file: TextIO | None = None

        # Create parent directory if needed
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

        # Open file in append mode
        self._file = open(self.output_path, "a", encoding="utf-8")

    def export(self, span: Span) -> None:
        """
        Export a span to the JSONL file.

        Args:
            span: Span to export
        """
        if self._file is None:
            raise RuntimeError("Exporter is closed")

        # Convert span to dict
        span_dict = span.to_dict()

        # Write as JSON line
        self._file.write(json.dumps(span_dict) + "\n")
        self._file.flush()  # Ensure immediate write

    def close(self) -> None:
        """Close the output file."""
        if self._file:
            self._file.close()
            self._file = None

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False
