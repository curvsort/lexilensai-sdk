# LexiLensAI SDK Quick Reference

## Installation

```bash
pip install lexilensai-sdk
```

## Basic Usage

```python
from lexilensai import LexiLens

# Initialize
lexilens = LexiLens.init(
    tenant_id="acme_corp",
    application_id="research_app"
)

# Your agent code here...

# Close
lexilens.close()
```

## Configuration

### Environment Variables

```bash
export LEXILENS_TENANT_ID=acme_corp
export LEXILENS_APPLICATION_ID=research_app
export LEXILENS_EXPORTER=otel              # otel | jsonl | console
export LEXILENS_COLLECTOR_ENDPOINT=http://localhost:4317
```

### Programmatic

```python
LexiLens.init(
    tenant_id="acme",
    application_id="app",
    exporter="jsonl",                      # Override env
    collector_endpoint="http://localhost:4317",
    objective="Session goal"
)
```

## Exporters

| Exporter | Output | Use Case |
|----------|--------|----------|
| `otel` | gRPC to collector | Production |
| `jsonl` | Local file | Development/Testing |
| `console` | Stdout | Debugging |

## Span Format

```json
{
  "span_name": "agent.start",
  "start_time": "2026-07-21T10:00:00Z",
  "attributes": {
    "span_id": "span_...",
    "session_id": "sess_...",
    "agent_id": "agent_name",
    "parent_span_id": "span_..."
  }
}
```

## Span Names → EventTypes

| Span Name | EventType |
|-----------|-----------|
| `session.start` | SESSION_START |
| `session.end` | SESSION_END |
| `agent.start` | AGENT_START |
| `agent.end` | AGENT_END |
| `model.call` | MODEL_CALL |
| `tool.{name}` | TOOL_CALL |

## Testing

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# With coverage
pytest tests/ --cov=lexilensai
```

## Supported Frameworks

| Framework | Version | Status |
|-----------|---------|--------|
| Strands | v0.1.0+ | ✅ Supported |
| LangChain | — | Planned (v0.2.0) |
| Anthropic SDK | — | Planned (v0.2.0) |

## Common Patterns

### Context Manager

```python
with LexiLens.init(tenant_id="acme", application_id="app") as lexilens:
    # Your code here
    pass
# Automatically closes
```

### Error Handling

```python
lexilens = LexiLens.init(...)
try:
    # Your agent code
    pass
finally:
    lexilens.close()  # Always flush spans
```

### JSONL Export + Replay

```python
# 1. Capture spans
lexilens = LexiLens.init(exporter="jsonl")
# ... run agents ...
lexilens.close()

# 2. Replay through platform
from ingestion.span_normalizer import normalize_span
import json

with open("lexilens_spans.jsonl") as f:
    for idx, line in enumerate(f, 1):
        span = json.loads(line)
        event = normalize_span(span, session_id=span['attributes']['session_id'], seq=idx)
        print(event.event_type)
```

## Links

- **Docs:** https://github.com/curvsort/lexilensai-sdk
- **Issues:** https://github.com/curvsort/lexilensai-sdk/issues
- **PyPI:** https://pypi.org/project/lexilensai-sdk/
