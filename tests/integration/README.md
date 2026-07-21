# Integration Tests

End-to-end tests proving the full SDK workflow works.

## Test Files

| File | Requires | What It Tests |
|------|----------|---------------|
| `test_e2e_workflow.py` | Nothing (mocked) | SDK → JSONL → report generation. Verifies token counts, cache detection, anomalies, cost estimation. Runs in CI. |
| `test_platform_ingest.py` | Docker platform running | SDK → HTTP POST → platform → query back. Verifies sessions, events, graph, findings on the live platform. |

## Running

```bash
# E2E workflow tests (no external deps — runs in CI)
pytest tests/integration/test_e2e_workflow.py -v

# Platform round-trip tests (requires Docker)
docker compose up -d
pytest tests/integration/test_platform_ingest.py -v

# All integration tests (platform tests auto-skip if Docker not running)
pytest tests/integration/ -v
```

## What's Verified

### test_e2e_workflow.py (5 tests)

1. **Full workflow** — init → 4 model calls (cache create/hit/miss/spike) + error → close → parse JSONL → verify report metrics and anomaly detection
2. **Multiple sessions** — two sessions append to same JSONL, report separates them correctly
3. **JSON output format** — report data serializes to valid JSON with expected structure
4. **Context manager** — `with LexiLens.init(...) as l:` properly flushes on exit
5. **Cache miss detection** — cache read → new cache create detected as anomaly

### test_platform_ingest.py (4 tests, require Docker)

1. **Platform health** — `/` returns `{"status": "ok"}`
2. **Full round-trip** — SDK → platform → query sessions/events/graph/findings
3. **Multiple sessions** — two independent SDK sessions are queryable separately
4. **Token spike detection** — platform's anomaly detector catches spikes from SDK spans
