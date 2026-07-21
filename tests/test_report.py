"""
Tests for lexilensai.report — Token Usage Report CLI.
"""
import json
import tempfile
from pathlib import Path

import pytest

from lexilensai.report import (
    ModelCall,
    SessionReport,
    build_session_report,
    detect_anomalies,
    format_report_json,
    format_report_text,
    group_by_session,
    parse_spans,
    run_report,
)


# --- Fixtures ---


def _make_span(span_name: str, session_id: str = "sess_123", **attrs) -> dict:
    """Helper to build a span dict."""
    return {
        "span_name": span_name,
        "start_time": "2026-07-22T10:00:00+00:00",
        "attributes": {"session_id": session_id, **attrs},
    }


def _write_jsonl(spans: list[dict], tmp_path: Path) -> Path:
    """Write spans to a JSONL file and return path."""
    file_path = tmp_path / "test_spans.jsonl"
    with open(file_path, "w") as f:
        for span in spans:
            f.write(json.dumps(span) + "\n")
    return file_path


# --- parse_spans ---


class TestParseSpans:
    def test_parse_valid_file(self, tmp_path):
        spans = [_make_span("session.start"), _make_span("model.call", input_tokens=100)]
        file_path = _write_jsonl(spans, tmp_path)
        result = parse_spans(file_path)
        assert len(result) == 2
        assert result[0]["span_name"] == "session.start"

    def test_skip_empty_lines(self, tmp_path):
        file_path = tmp_path / "test.jsonl"
        with open(file_path, "w") as f:
            f.write(json.dumps(_make_span("session.start")) + "\n")
            f.write("\n")
            f.write("  \n")
            f.write(json.dumps(_make_span("model.call")) + "\n")
        result = parse_spans(file_path)
        assert len(result) == 2

    def test_skip_malformed_lines(self, tmp_path, capsys):
        file_path = tmp_path / "test.jsonl"
        with open(file_path, "w") as f:
            f.write(json.dumps(_make_span("session.start")) + "\n")
            f.write("not valid json\n")
            f.write(json.dumps(_make_span("model.call")) + "\n")
        result = parse_spans(file_path)
        assert len(result) == 2
        captured = capsys.readouterr()
        assert "Skipping malformed line 2" in captured.err


# --- group_by_session ---


class TestGroupBySession:
    def test_groups_correctly(self):
        spans = [
            _make_span("model.call", session_id="sess_1"),
            _make_span("model.call", session_id="sess_2"),
            _make_span("model.call", session_id="sess_1"),
        ]
        groups = group_by_session(spans)
        assert len(groups) == 2
        assert len(groups["sess_1"]) == 2
        assert len(groups["sess_2"]) == 1

    def test_missing_session_id(self):
        spans = [{"span_name": "model.call", "start_time": "", "attributes": {}}]
        groups = group_by_session(spans)
        assert "unknown" in groups


# --- build_session_report ---


class TestBuildSessionReport:
    def test_basic_report(self):
        spans = [
            _make_span("session.start"),
            _make_span("model.call", span_id="s1", model="claude-sonnet-4-20250514",
                       input_tokens=1500, output_tokens=800, latency_ms=450),
            _make_span("model.call", span_id="s2", model="claude-sonnet-4-20250514",
                       input_tokens=1500, output_tokens=200,
                       cache_read_input_tokens=2500, latency_ms=200),
            _make_span("session.end"),
        ]
        report = build_session_report("sess_123", spans)
        assert report.session_id == "sess_123"
        assert len(report.calls) == 2
        assert report.total_input_tokens == 3000
        assert report.total_output_tokens == 1000
        assert report.calls[0].latency_ms == 450
        assert report.calls[1].cache_read_input_tokens == 2500

    def test_thinking_tokens(self):
        spans = [
            _make_span("model.call", span_id="s1", model="claude-sonnet-4-20250514",
                       input_tokens=1000, output_tokens=500, thinking_tokens=300),
        ]
        report = build_session_report("sess_123", spans)
        assert report.total_thinking_tokens == 300
        assert report.thinking_overhead_pct == 60.0

    def test_empty_session(self):
        spans = [_make_span("session.start"), _make_span("session.end")]
        report = build_session_report("sess_123", spans)
        assert len(report.calls) == 0
        assert report.cache_efficiency == 0.0
        assert report.thinking_overhead_pct == 0.0


# --- SessionReport properties ---


class TestSessionReport:
    def test_cache_efficiency(self):
        report = SessionReport(session_id="test", calls=[
            ModelCall(call_number=1, span_id="s1", model="m", cache_read_input_tokens=100),
            ModelCall(call_number=2, span_id="s2", model="m", cache_read_input_tokens=0),
            ModelCall(call_number=3, span_id="s3", model="m", cache_read_input_tokens=200),
            ModelCall(call_number=4, span_id="s4", model="m", cache_read_input_tokens=0),
        ])
        assert report.cache_efficiency == 50.0

    def test_estimated_cost_sonnet(self):
        report = SessionReport(session_id="test", calls=[
            ModelCall(call_number=1, span_id="s1", model="claude-sonnet-4-20250514",
                      input_tokens=1_000_000, output_tokens=100_000),
        ])
        # $3/M input + $15/M output = $3 + $1.5 = $4.5
        cost = report.estimated_cost()
        assert abs(cost - 4.5) < 0.01

    def test_estimated_cost_with_cache(self):
        report = SessionReport(session_id="test", calls=[
            ModelCall(call_number=1, span_id="s1", model="claude-sonnet-4-20250514",
                      input_tokens=0, output_tokens=0,
                      cache_creation_input_tokens=1_000_000,
                      cache_read_input_tokens=1_000_000),
        ])
        # $3.75/M cache write + $0.30/M cache read = $3.75 + $0.30 = $4.05
        cost = report.estimated_cost()
        assert abs(cost - 4.05) < 0.01

    def test_estimated_cost_unknown_model_uses_default(self):
        report = SessionReport(session_id="test", calls=[
            ModelCall(call_number=1, span_id="s1", model="my-custom-model",
                      input_tokens=1_000_000, output_tokens=0),
        ])
        # Default pricing: $3/M input
        cost = report.estimated_cost()
        assert abs(cost - 3.0) < 0.01


# --- detect_anomalies ---


class TestDetectAnomalies:
    def test_cache_miss_after_hit(self):
        calls = [
            ModelCall(call_number=1, span_id="s1", model="m",
                      cache_read_input_tokens=2500),
            ModelCall(call_number=2, span_id="s2", model="m",
                      cache_creation_input_tokens=2500),  # MISS after HIT
        ]
        anomalies = detect_anomalies(calls)
        assert any("Cache miss after cache hit" in a for a in anomalies)

    def test_no_cache_miss_on_first_call(self):
        calls = [
            ModelCall(call_number=1, span_id="s1", model="m",
                      cache_creation_input_tokens=2500),  # First call creating cache is normal
        ]
        anomalies = detect_anomalies(calls)
        assert not any("Cache miss" in a for a in anomalies)

    def test_token_spike(self):
        calls = [
            ModelCall(call_number=1, span_id="s1", model="m",
                      input_tokens=100, output_tokens=50),
            ModelCall(call_number=2, span_id="s2", model="m",
                      input_tokens=100, output_tokens=50),
            ModelCall(call_number=3, span_id="s3", model="m",
                      input_tokens=100, output_tokens=50),
            ModelCall(call_number=4, span_id="s4", model="m",
                      input_tokens=1000, output_tokens=500),  # 10x spike
        ]
        anomalies = detect_anomalies(calls)
        assert any("token spike" in a for a in anomalies)

    def test_no_spike_when_uniform(self):
        calls = [
            ModelCall(call_number=i, span_id=f"s{i}", model="m",
                      input_tokens=100, output_tokens=50)
            for i in range(1, 5)
        ]
        anomalies = detect_anomalies(calls)
        assert not any("spike" in a for a in anomalies)

    def test_high_thinking_overhead(self):
        calls = [
            ModelCall(call_number=1, span_id="s1", model="m",
                      output_tokens=100, thinking_tokens=80),  # 80% thinking
        ]
        anomalies = detect_anomalies(calls)
        assert any("thinking tokens" in a for a in anomalies)

    def test_error_call_reported(self):
        calls = [
            ModelCall(call_number=1, span_id="s1", model="m",
                      status="error", error="rate_limit_exceeded"),
        ]
        anomalies = detect_anomalies(calls)
        assert any("Error" in a and "rate_limit_exceeded" in a for a in anomalies)

    def test_empty_calls(self):
        assert detect_anomalies([]) == []


# --- format_report_text ---


class TestFormatReportText:
    def test_includes_session_id(self):
        report = SessionReport(session_id="sess_abc", calls=[
            ModelCall(call_number=1, span_id="s1", model="claude-sonnet-4-20250514",
                      input_tokens=1000, output_tokens=500, latency_ms=300),
        ])
        text = format_report_text([report])
        assert "sess_abc" in text
        assert "1,000 in" in text
        assert "500 out" in text
        assert "300ms" in text

    def test_shows_cache_hit_indicator(self):
        report = SessionReport(session_id="test", calls=[
            ModelCall(call_number=1, span_id="s1", model="m",
                      input_tokens=100, output_tokens=50,
                      cache_read_input_tokens=2000),
        ])
        text = format_report_text([report])
        assert "cache HIT" in text

    def test_shows_anomalies(self):
        report = SessionReport(
            session_id="test",
            calls=[ModelCall(call_number=1, span_id="s1", model="m",
                             status="error", error="timeout")],
            anomalies=["Call 1: Error — timeout"],
        )
        text = format_report_text([report])
        assert "Anomalies detected" in text
        assert "timeout" in text

    def test_empty_session(self):
        report = SessionReport(session_id="test")
        text = format_report_text([report])
        assert "no model calls recorded" in text


# --- format_report_json ---


class TestFormatReportJson:
    def test_valid_json_output(self):
        report = SessionReport(session_id="sess_test", calls=[
            ModelCall(call_number=1, span_id="s1", model="claude-sonnet-4-20250514",
                      input_tokens=1000, output_tokens=500),
        ])
        result = format_report_json([report])
        data = json.loads(result)
        assert isinstance(data, list)
        assert data[0]["session_id"] == "sess_test"
        assert data[0]["summary"]["total_input_tokens"] == 1000
        assert data[0]["summary"]["total_output_tokens"] == 500
        assert len(data[0]["calls"]) == 1

    def test_json_includes_anomalies(self):
        report = SessionReport(
            session_id="test",
            calls=[],
            anomalies=["Something bad"],
        )
        result = format_report_json([report])
        data = json.loads(result)
        assert "Something bad" in data[0]["anomalies"]


# --- run_report (integration) ---


class TestRunReport:
    def test_file_not_found(self):
        result = run_report("/nonexistent/path.jsonl")
        assert "File not found" in result

    def test_empty_file(self, tmp_path):
        file_path = tmp_path / "empty.jsonl"
        file_path.write_text("")
        result = run_report(str(file_path))
        assert "empty" in result.lower()

    def test_full_report(self, tmp_path):
        spans = [
            _make_span("session.start"),
            _make_span("model.call", span_id="s1", model="claude-sonnet-4-20250514",
                       input_tokens=1500, output_tokens=800,
                       cache_creation_input_tokens=2500, latency_ms=500),
            _make_span("model.call", span_id="s2", model="claude-sonnet-4-20250514",
                       input_tokens=1500, output_tokens=200,
                       cache_read_input_tokens=2500, latency_ms=150),
            _make_span("session.end"),
        ]
        file_path = _write_jsonl(spans, tmp_path)
        result = run_report(str(file_path))
        assert "sess_123" in result
        assert "cache HIT" in result
        assert "Cache efficiency" in result

    def test_json_mode(self, tmp_path):
        spans = [
            _make_span("model.call", span_id="s1", model="claude-sonnet-4-20250514",
                       input_tokens=100, output_tokens=50),
        ]
        file_path = _write_jsonl(spans, tmp_path)
        result = run_report(str(file_path), output_json=True)
        data = json.loads(result)
        assert data[0]["calls"][0]["input_tokens"] == 100

    def test_session_filter(self, tmp_path):
        spans = [
            _make_span("model.call", session_id="sess_1", span_id="s1",
                       model="m", input_tokens=100),
            _make_span("model.call", session_id="sess_2", span_id="s2",
                       model="m", input_tokens=200),
        ]
        file_path = _write_jsonl(spans, tmp_path)
        result = run_report(str(file_path), session_filter="sess_1")
        assert "sess_1" in result
        assert "sess_2" not in result

    def test_session_filter_not_found(self, tmp_path):
        spans = [_make_span("model.call", session_id="sess_1", span_id="s1", model="m")]
        file_path = _write_jsonl(spans, tmp_path)
        result = run_report(str(file_path), session_filter="nonexistent")
        assert "not found" in result
        assert "sess_1" in result  # Shows available sessions


# --- Multi-session ---


class TestMultiSession:
    def test_multiple_sessions_in_report(self, tmp_path):
        spans = [
            _make_span("session.start", session_id="sess_1"),
            _make_span("model.call", session_id="sess_1", span_id="s1",
                       model="claude-sonnet-4-20250514", input_tokens=1000, output_tokens=500),
            _make_span("session.end", session_id="sess_1"),
            _make_span("session.start", session_id="sess_2"),
            _make_span("model.call", session_id="sess_2", span_id="s2",
                       model="claude-sonnet-4-20250514", input_tokens=2000, output_tokens=1000),
            _make_span("session.end", session_id="sess_2"),
        ]
        file_path = _write_jsonl(spans, tmp_path)
        result = run_report(str(file_path))
        assert "sess_1" in result
        assert "sess_2" in result
