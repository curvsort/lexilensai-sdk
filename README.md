# LexiLensAI SDK

**Session-aware instrumentation for multi-agent AI systems.**

The LexiLensAI SDK automatically instruments your agent framework to emit OpenTelemetry-compatible spans, enabling session-level observability, execution graph reconstruction, and anomaly detection.

## Features

- **Automatic instrumentation** — Monkey-patch agent frameworks with one line of code
- **Session-aware tracking** — Groups all spans by session with parent-child relationships
- **Multiple exporters** — Send to OTel collector (gRPC), local JSONL file, or console
- **Zero-config defaults** — Works out of the box with sensible defaults
- **Framework support** — Strands agents (v0.1.0), with LangChain and Anthropic SDK coming soon

## Installation

```bash
pip install lexilensai-sdk
```

## Quick Start

### Basic Usage (Strands Framework)

```python
from lexilensai import LexiLens
from strands import Agent

# Initialize instrumentation (emits session.start span)
lexilens = LexiLens.init(
    tenant_id="acme_corp",
    application_id="research_assistant"
)

# Your agent code runs here — spans are emitted automatically
agent = Agent(system_prompt="You are a helpful research assistant")
result = agent("What are the latest developments in AI?")

# Close session (emits session.end span)
lexilens.close()
```

### Context Manager Pattern

```python
from lexilensai import LexiLens
from strands import Agent

with LexiLens.init(tenant_id="acme", application_id="app") as lexilens:
    agent = Agent(system_prompt="You are a helpful assistant")
    result = agent("Hello!")
# Automatically closes and flushes spans
```

## Configuration

Configuration via environment variables (all optional):

```bash
# Required for production
export LEXILENS_TENANT_ID=acme_corp
export LEXILENS_APPLICATION_ID=research_app

# Exporter (default: otel)
export LEXILENS_EXPORTER=otel           # Options: otel, jsonl, console

# OTel collector endpoint (default: http://localhost:4317)
export LEXILENS_COLLECTOR_ENDPOINT=http://localhost:4317

# Optional
export LEXILENS_API_KEY=your-api-key    # For platform integration (future)
export LEXILENS_HARNESS=strands         # Framework name (default: strands)
export LEXILENS_HARNESS_VERSION=0.5.0   # Framework version
```

### Programmatic Configuration

```python
lexilens = LexiLens.init(
    tenant_id="acme_corp",
    application_id="research_app",
    exporter="jsonl",                   # Override env var
    objective="Research AI trends"      # Session-level metadata
)
```

## Exporters

### OTel Exporter (Production)

Sends spans to an OpenTelemetry collector via gRPC:

```python
lexilens = LexiLens.init(
    exporter="otel",
    collector_endpoint="http://localhost:4317"
)
```

**Requirements:**
- Running OTel collector (e.g., AWS ADOT, Jaeger, local collector)
- Collector configured to forward to your backend

### JSONL Exporter (Development)

Writes spans to a local file for offline replay and testing:

```python
lexilens = LexiLens.init(exporter="jsonl")
```

Output file: `lexilens_spans.jsonl` (one JSON object per line)

### Console Exporter (Debugging)

Prints spans to stdout in human-readable format:

```python
lexilens = LexiLens.init(exporter="console")
```

## What Gets Instrumented?

For Strands agents (v0.1.0):

| Event | Span Name | When |
|-------|-----------|------|
| Session start | `session.start` | `LexiLens.init()` |
| Session end | `session.end` | `lexilens.close()` |
| Agent call start | `agent.start` | `Agent.__call__` entry |
| Agent call end | `agent.end` | `Agent.__call__` exit |

**Coming in v0.2.0:**
- `model.call` / `model.response` spans (LLM calls)
- `tool.{name}` spans (tool invocations)
- LangChain/LangGraph callback handler
- Anthropic SDK instrumentation

## Span Format

Spans emitted by the SDK are compatible with LexiLensAI platform's ingestion pipeline. Example span:

```json
{
  "span_name": "agent.start",
  "start_time": "2026-07-21T10:00:00.123456Z",
  "attributes": {
    "span_id": "span_1721556000123456_5432",
    "session_id": "sess_1721556000_5432",
    "agent_id": "research_agent",
    "parent_span_id": "span_1721556000123455_1234"
  }
}
```

The platform's `span_normalizer.py` maps `span_name` patterns to 25 EventTypes (SESSION_START, AGENT_START, MODEL_CALL, TOOL_CALL, etc.).

## Testing

The SDK includes roundtrip tests with the platform's span normalizer:

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# With coverage
pytest tests/ --cov=lexilensai --cov-report=term-missing
```

## Architecture

```
Your Agent Code
      ↓
Strands Agent (monkey-patched)
      ↓
LexiLens SDK (span emission)
      ↓
Exporter (OTel / JSONL / Console)
      ↓
OTel Collector (optional)
      ↓
LexiLensAI Platform (ingestion pipeline)
```

The SDK is a **thin instrumentation layer** — it emits spans in OpenTelemetry format. All analysis (session reconstruction, anomaly detection, WHY reasoning) happens on the platform backend.

## Examples

See [`examples/`](examples/) directory:

- `quickstart.py` — Minimal Strands example
- `multi_agent.py` — Orchestrator with delegation
- `jsonl_export.py` — Local file export for testing

## Roadmap

| Version | Features |
|---------|----------|
| **v0.1.0** (current) | Strands agents, OTel/JSONL/Console exporters, session tracking |
| **v0.2.0** | LangChain support, Anthropic SDK support, platform HTTP exporter, async batching |
| **v0.3.0** | Auto-detect frameworks, memory operations, context compaction events |

## Contributing

Contributions welcome! This SDK is open-source (Apache 2.0) to enable community-driven framework adapters.

**Adding a new framework:**
1. Create `src/lexilensai/frameworks/{framework}.py`
2. Implement `patch_{framework}()` and `unpatch_{framework}()`
3. Add tests in `tests/test_{framework}.py`
4. Update README

## License

Apache License 2.0 — see [LICENSE](LICENSE)

## Links

- **GitHub:** https://github.com/curvsort/lexilensai-sdk
- **PyPI:** https://pypi.org/project/lexilensai-sdk/
- **Platform:** https://github.com/curvsort/lexilensai (private)
- **Session reconstruction library:** https://github.com/curvsort/agent-session-graph

## Support

- Issues: https://github.com/curvsort/lexilensai-sdk/issues
- Email: support@lexilensai.com
