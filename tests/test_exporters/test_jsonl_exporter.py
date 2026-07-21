"""Tests for JSONL exporter."""
import json
import tempfile
from pathlib import Path

import pytest

from lexilensai.exporters import JSONLExporter
from lexilensai.span import Span


def test_jsonl_exporter_creates_file():
    """Test that JSONLExporter creates the output file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "test.jsonl"
        exporter = JSONLExporter(str(output_path))
        exporter.close()

        assert output_path.exists()


def test_jsonl_exporter_writes_span():
    """Test that JSONLExporter writes spans as JSON lines."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "test.jsonl"
        exporter = JSONLExporter(str(output_path))

        # Create and export a span
        span = Span.create(
            span_name="test.span",
            span_id="span_001",
            session_id="sess_001",
            agent_id="test_agent"
        )
        exporter.export(span)
        exporter.close()

        # Read and verify
        with open(output_path) as f:
            lines = f.readlines()

        assert len(lines) == 1
        span_dict = json.loads(lines[0])
        assert span_dict["span_name"] == "test.span"
        assert span_dict["attributes"]["span_id"] == "span_001"
        assert span_dict["attributes"]["session_id"] == "sess_001"


def test_jsonl_exporter_writes_multiple_spans():
    """Test that JSONLExporter writes multiple spans correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "test.jsonl"
        exporter = JSONLExporter(str(output_path))

        # Export multiple spans
        for i in range(3):
            span = Span.create(
                span_name=f"span_{i}",
                span_id=f"span_00{i}",
                session_id="sess_001"
            )
            exporter.export(span)

        exporter.close()

        # Read and verify
        with open(output_path) as f:
            lines = f.readlines()

        assert len(lines) == 3
        for i, line in enumerate(lines):
            span_dict = json.loads(line)
            assert span_dict["span_name"] == f"span_{i}"


def test_jsonl_exporter_context_manager():
    """Test JSONLExporter works as context manager."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "test.jsonl"

        with JSONLExporter(str(output_path)) as exporter:
            span = Span.create(
                span_name="test.span",
                span_id="span_001",
                session_id="sess_001"
            )
            exporter.export(span)

        # File should be closed and readable
        with open(output_path) as f:
            lines = f.readlines()

        assert len(lines) == 1


def test_jsonl_exporter_closed_raises_error():
    """Test that exporting to closed exporter raises error."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "test.jsonl"
        exporter = JSONLExporter(str(output_path))
        exporter.close()

        span = Span.create(
            span_name="test.span",
            span_id="span_001",
            session_id="sess_001"
        )

        with pytest.raises(RuntimeError, match="Exporter is closed"):
            exporter.export(span)


def test_jsonl_exporter_creates_parent_dirs():
    """Test that JSONLExporter creates parent directories if needed."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "nested" / "dir" / "test.jsonl"
        exporter = JSONLExporter(str(output_path))

        span = Span.create(
            span_name="test.span",
            span_id="span_001",
            session_id="sess_001"
        )
        exporter.export(span)
        exporter.close()

        assert output_path.exists()
        assert output_path.parent.exists()


def test_jsonl_exporter_appends_to_existing():
    """Test that JSONLExporter appends to existing file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "test.jsonl"

        # Write first span
        with JSONLExporter(str(output_path)) as exporter:
            span1 = Span.create(
                span_name="span_1",
                span_id="span_001",
                session_id="sess_001"
            )
            exporter.export(span1)

        # Write second span (should append)
        with JSONLExporter(str(output_path)) as exporter:
            span2 = Span.create(
                span_name="span_2",
                span_id="span_002",
                session_id="sess_001"
            )
            exporter.export(span2)

        # Verify both spans present
        with open(output_path) as f:
            lines = f.readlines()

        assert len(lines) == 2
        assert json.loads(lines[0])["span_name"] == "span_1"
        assert json.loads(lines[1])["span_name"] == "span_2"
