"""
Token Usage Report CLI for LexiLensAI SDK.

Reads JSONL span files produced by the SDK's JSONLExporter and generates
a human-readable report showing per-call token breakdown, cache efficiency,
thinking overhead, and anomaly detection.

Usage:
    python -m lexilensai.report                    # reads lexilens_spans.jsonl
    python -m lexilensai.report -f output.jsonl    # specific file
    python -m lexilensai.report --json             # JSON output mode
"""
import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Pricing per 1M tokens (Claude Sonnet 4 as default)
# https://docs.anthropic.com/en/docs/about-claude/models
MODEL_PRICING: dict[str, dict[str, float]] = {
    "claude-sonnet-4-20250514": {
        "input": 3.00, "output": 15.00, "cache_write": 3.75, "cache_read": 0.30,
    },
    "claude-opus-4-20250514": {
        "input": 15.00, "output": 75.00, "cache_write": 18.75, "cache_read": 1.50,
    },
    "claude-haiku-3-5-20241022": {
        "input": 0.80, "output": 4.00, "cache_write": 1.00, "cache_read": 0.08,
    },
    # Fallback
    "default": {
        "input": 3.00, "output": 15.00, "cache_write": 3.75, "cache_read": 0.30,
    },
}


@dataclass
class ModelCall:
    """A single model API call extracted from spans."""
    call_number: int
    span_id: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    thinking_tokens: int = 0
    latency_ms: int = 0
    is_streaming: bool = False
    status: str = "success"
    error: str | None = None
    timestamp: str = ""


@dataclass
class SessionReport:
    """Report for a single session."""
    session_id: str
    calls: list[ModelCall] = field(default_factory=list)
    duration_ms: int = 0
    start_time: str = ""
    end_time: str = ""
    anomalies: list[str] = field(default_factory=list)

    @property
    def total_input_tokens(self) -> int:
        return sum(c.input_tokens for c in self.calls)

    @property
    def total_output_tokens(self) -> int:
        return sum(c.output_tokens for c in self.calls)

    @property
    def total_cache_write_tokens(self) -> int:
        return sum(c.cache_creation_input_tokens for c in self.calls)

    @property
    def total_cache_read_tokens(self) -> int:
        return sum(c.cache_read_input_tokens for c in self.calls)

    @property
    def total_thinking_tokens(self) -> int:
        return sum(c.thinking_tokens for c in self.calls)

    @property
    def cache_efficiency(self) -> float:
        """Percentage of calls that hit cache."""
        if not self.calls:
            return 0.0
        hits = sum(1 for c in self.calls if c.cache_read_input_tokens > 0)
        return (hits / len(self.calls)) * 100

    @property
    def thinking_overhead_pct(self) -> float:
        """Percentage of output tokens spent on thinking."""
        total_out = self.total_output_tokens
        if total_out == 0:
            return 0.0
        return (self.total_thinking_tokens / total_out) * 100

    def estimated_cost(self) -> float:
        """Estimate cost in USD based on model pricing."""
        total_cost = 0.0
        for call in self.calls:
            pricing = MODEL_PRICING.get(call.model, MODEL_PRICING["default"])
            # Per-million token pricing
            cost = (
                (call.input_tokens * pricing["input"] / 1_000_000)
                + (call.output_tokens * pricing["output"] / 1_000_000)
                + (call.cache_creation_input_tokens * pricing["cache_write"] / 1_000_000)
                + (call.cache_read_input_tokens * pricing["cache_read"] / 1_000_000)
            )
            total_cost += cost
        return total_cost


def parse_spans(file_path: Path) -> list[dict[str, Any]]:
    """
    Parse JSONL span file.

    Args:
        file_path: Path to JSONL file

    Returns:
        List of span dicts
    """
    spans = []
    with open(file_path, encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                spans.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"Warning: Skipping malformed line {line_num}: {e}", file=sys.stderr)
    return spans


def group_by_session(spans: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Group spans by session_id."""
    sessions: dict[str, list[dict[str, Any]]] = {}
    for span in spans:
        session_id = span.get("attributes", {}).get("session_id", "unknown")
        sessions.setdefault(session_id, []).append(span)
    return sessions


def build_session_report(session_id: str, spans: list[dict[str, Any]]) -> SessionReport:
    """
    Build a SessionReport from a list of spans for one session.

    Args:
        session_id: Session identifier
        spans: All spans for this session

    Returns:
        SessionReport with calls and anomalies
    """
    report = SessionReport(session_id=session_id)

    # Extract model.call spans
    call_number = 0
    for span in spans:
        span_name = span.get("span_name", "")
        attrs = span.get("attributes", {})
        timestamp = span.get("start_time", "")

        if span_name == "session.start":
            report.start_time = timestamp

        elif span_name == "session.end":
            report.end_time = timestamp

        elif span_name == "model.call":
            call_number += 1
            call = ModelCall(
                call_number=call_number,
                span_id=attrs.get("span_id", ""),
                model=attrs.get("model", "unknown"),
                input_tokens=attrs.get("input_tokens", 0),
                output_tokens=attrs.get("output_tokens", 0),
                cache_creation_input_tokens=attrs.get("cache_creation_input_tokens", 0),
                cache_read_input_tokens=attrs.get("cache_read_input_tokens", 0),
                thinking_tokens=attrs.get("thinking_tokens", 0),
                latency_ms=attrs.get("latency_ms", 0),
                is_streaming=attrs.get("is_streaming", False),
                status=attrs.get("status", "success"),
                error=attrs.get("error"),
                timestamp=timestamp,
            )
            report.calls.append(call)

    # Detect anomalies
    report.anomalies = detect_anomalies(report.calls)

    return report


def detect_anomalies(calls: list[ModelCall]) -> list[str]:
    """
    Detect anomalies in model call patterns.

    Rules:
    1. Cache miss after cache hit (prompt prefix likely changed)
    2. Token spike (>3x average for that session)
    3. Retry storm (3+ calls within 2s with same token count)
    4. High thinking overhead (>50% of output is thinking)
    5. Error calls

    Args:
        calls: List of model calls in order

    Returns:
        List of anomaly description strings
    """
    anomalies = []

    if not calls:
        return anomalies

    # Rule 1: Cache miss after cache hit
    prev_had_cache_hit = False
    for call in calls:
        if call.cache_read_input_tokens > 0:
            prev_had_cache_hit = True
        elif prev_had_cache_hit and call.cache_creation_input_tokens > 0:
            anomalies.append(
                f"Call {call.call_number}: Cache miss after cache hit — "
                f"prompt prefix likely changed between calls"
            )
            prev_had_cache_hit = False
        elif call.cache_creation_input_tokens == 0 and call.cache_read_input_tokens == 0:
            # No caching involved, reset
            prev_had_cache_hit = False

    # Rule 2: Token spike (>3x average)
    if len(calls) >= 3:
        total_tokens_per_call = [
            c.input_tokens + c.output_tokens for c in calls
        ]
        avg_tokens = sum(total_tokens_per_call) / len(total_tokens_per_call)
        if avg_tokens > 0:
            for i, call in enumerate(calls):
                call_total = total_tokens_per_call[i]
                if call_total > avg_tokens * 3:
                    ratio = call_total / avg_tokens
                    anomalies.append(
                        f"Call {call.call_number}: {ratio:.1f}x token spike vs average — "
                        f"possible retry or expanded context"
                    )

    # Rule 3: High thinking overhead per call
    for call in calls:
        if call.output_tokens > 0 and call.thinking_tokens > 0:
            thinking_pct = (call.thinking_tokens / call.output_tokens) * 100
            if thinking_pct > 50:
                anomalies.append(
                    f"Call {call.call_number}: {thinking_pct:.0f}% of output was thinking tokens — "
                    f"consider if extended thinking is needed for this call"
                )

    # Rule 4: Error calls
    for call in calls:
        if call.status == "error":
            error_msg = call.error or "unknown error"
            anomalies.append(
                f"Call {call.call_number}: Error — {error_msg}"
            )

    return anomalies


def format_report_text(reports: list[SessionReport]) -> str:
    """
    Format reports as human-readable text.

    Args:
        reports: List of session reports

    Returns:
        Formatted text string
    """
    lines = []
    lines.append("=" * 70)
    lines.append("  LexiLensAI — Token Usage Report")
    lines.append("=" * 70)

    for report in reports:
        lines.append("")
        lines.append(f"Session: {report.session_id}")
        if report.start_time:
            lines.append(f"Started: {report.start_time}")
        lines.append(f"Total calls: {len(report.calls)}")
        lines.append("")

        if not report.calls:
            lines.append("  (no model calls recorded)")
            continue

        # Per-call breakdown
        lines.append("Token Breakdown:")
        lines.append("-" * 70)

        for call in report.calls:
            # Model name (shortened)
            model_short = call.model.split("-")[0:2]
            model_display = "-".join(model_short) if model_short else call.model
            if len(model_display) > 16:
                model_display = model_display[:16]

            # Format token counts
            parts = [f"{call.input_tokens:,} in", f"{call.output_tokens:,} out"]

            if call.cache_creation_input_tokens:
                parts.append(f"{call.cache_creation_input_tokens:,} cache_create")
            if call.cache_read_input_tokens:
                parts.append(f"{call.cache_read_input_tokens:,} cache_read")
            if call.thinking_tokens:
                parts.append(f"{call.thinking_tokens:,} thinking")

            tokens_str = " / ".join(parts)

            # Status indicator
            status_indicator = ""
            if call.status == "error":
                status_indicator = " ✗ ERROR"
            elif call.cache_read_input_tokens > 0:
                status_indicator = " ← cache HIT"
            elif call.cache_creation_input_tokens > 0 and call.call_number > 1:
                status_indicator = " ← cache MISS"

            # Latency
            latency_str = f" ({call.latency_ms}ms)" if call.latency_ms else ""

            lines.append(
                f"  Call {call.call_number}: {model_display:<16} → "
                f"{tokens_str}{latency_str}{status_indicator}"
            )

        # Summary
        lines.append("")
        lines.append("Summary:")
        lines.append(f"  Total tokens: {report.total_input_tokens:,} input / "
                     f"{report.total_output_tokens:,} output")

        # Cache efficiency
        cache_calls = sum(
            1 for c in report.calls
            if c.cache_creation_input_tokens > 0 or c.cache_read_input_tokens > 0
        )
        if cache_calls > 0:
            cache_hits = sum(1 for c in report.calls if c.cache_read_input_tokens > 0)
            lines.append(
                f"  Cache efficiency: {report.cache_efficiency:.0f}% "
                f"({cache_hits}/{len(report.calls)} calls hit cache)"
            )

        # Thinking overhead
        if report.total_thinking_tokens > 0:
            lines.append(
                f"  Thinking overhead: {report.total_thinking_tokens:,} tokens "
                f"({report.thinking_overhead_pct:.0f}% of output was thinking)"
            )

        # Cost estimate
        cost = report.estimated_cost()
        if cost > 0:
            lines.append(f"  Estimated cost: ${cost:.4f}")

        # Anomalies
        if report.anomalies:
            lines.append("")
            lines.append("⚠️  Anomalies detected:")
            for anomaly in report.anomalies:
                lines.append(f"  - {anomaly}")

    lines.append("")
    lines.append("=" * 70)
    return "\n".join(lines)


def format_report_json(reports: list[SessionReport]) -> str:
    """
    Format reports as JSON.

    Args:
        reports: List of session reports

    Returns:
        JSON string
    """
    output = []
    for report in reports:
        session_data = {
            "session_id": report.session_id,
            "start_time": report.start_time,
            "end_time": report.end_time,
            "total_calls": len(report.calls),
            "summary": {
                "total_input_tokens": report.total_input_tokens,
                "total_output_tokens": report.total_output_tokens,
                "total_cache_write_tokens": report.total_cache_write_tokens,
                "total_cache_read_tokens": report.total_cache_read_tokens,
                "total_thinking_tokens": report.total_thinking_tokens,
                "cache_efficiency_pct": round(report.cache_efficiency, 1),
                "thinking_overhead_pct": round(report.thinking_overhead_pct, 1),
                "estimated_cost_usd": round(report.estimated_cost(), 6),
            },
            "calls": [
                {
                    "call_number": c.call_number,
                    "model": c.model,
                    "input_tokens": c.input_tokens,
                    "output_tokens": c.output_tokens,
                    "cache_creation_input_tokens": c.cache_creation_input_tokens,
                    "cache_read_input_tokens": c.cache_read_input_tokens,
                    "thinking_tokens": c.thinking_tokens,
                    "latency_ms": c.latency_ms,
                    "is_streaming": c.is_streaming,
                    "status": c.status,
                    "error": c.error,
                }
                for c in report.calls
            ],
            "anomalies": report.anomalies,
        }
        output.append(session_data)

    return json.dumps(output, indent=2)


def run_report(
    file_path: str = "lexilens_spans.jsonl",
    output_json: bool = False,
    session_filter: str | None = None,
) -> str:
    """
    Run the token usage report.

    Args:
        file_path: Path to JSONL spans file
        output_json: If True, output JSON format
        session_filter: If set, only report on this session ID

    Returns:
        Formatted report string
    """
    path = Path(file_path)

    if not path.exists():
        return (
            f"Error: File not found: {file_path}\n\n"
            "Hint: Run your agent with LexiLens.init(exporter='jsonl') to generate spans."
        )

    if path.stat().st_size == 0:
        return "Error: Spans file is empty. No model calls recorded yet."

    # Parse spans
    spans = parse_spans(path)
    if not spans:
        return "Error: No valid spans found in file."

    # Group by session
    sessions = group_by_session(spans)

    # Filter if requested
    if session_filter:
        if session_filter in sessions:
            sessions = {session_filter: sessions[session_filter]}
        else:
            available = ", ".join(sorted(sessions.keys()))
            return f"Error: Session '{session_filter}' not found.\nAvailable sessions: {available}"

    # Build reports
    reports = []
    for sid, session_spans in sessions.items():
        reports.append(build_session_report(sid, session_spans))

    # Format output
    if output_json:
        return format_report_json(reports)
    else:
        return format_report_text(reports)


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="lexilens-report",
        description="LexiLensAI Token Usage Report — see where your tokens go",
    )
    parser.add_argument(
        "-f", "--file",
        default="lexilens_spans.jsonl",
        help="Path to JSONL spans file (default: lexilens_spans.jsonl)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Output in JSON format",
    )
    parser.add_argument(
        "-s", "--session",
        default=None,
        help="Filter to specific session ID",
    )

    args = parser.parse_args()

    result = run_report(
        file_path=args.file,
        output_json=args.output_json,
        session_filter=args.session,
    )
    print(result)


if __name__ == "__main__":
    main()
