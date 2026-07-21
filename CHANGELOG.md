# Changelog

All notable changes to lexilensai-sdk will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-07-22

### Added
- Anthropic SDK instrumentation via monkey-patching `anthropic.Anthropic.messages.create()` and `.stream()`
- Automatic token usage tracking: `input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`
- Extended thinking token counting for prompts with `thinking` content blocks
- Latency measurement for all model calls
- Model name and streaming status tracking in `model.call` spans
- Auto-detection: patches Anthropic SDK only if installed (graceful skip if not present)
- Comprehensive test coverage: 14 new tests for Anthropic instrumentation

### Framework Support
- Strands agents (v0.1.0)
- **NEW:** Anthropic SDK direct usage (no Strands required)

### Changed
- `LexiLens.init()` now patches both Strands and Anthropic SDK automatically
- `LexiLens.close()` unpatches both frameworks

### Known Limitations
- Streaming calls emit spans but do not yet aggregate token usage across stream chunks
- No LangChain support yet (planned for v0.3.0)
- No platform HTTP exporter yet (planned for v0.2.1)

## [0.1.0] - 2026-07-21

### Added
- Initial release with Strands framework support
- CI/CD: GitHub Actions workflow with Python 3.11/3.12/3.13 matrix testing
- CI/CD: Automatic PyPI publishing on git tag push (trusted publishing)
- CI/CD: Coverage enforcement (85% minimum threshold)
- OTel gRPC exporter to localhost:4317
- JSONL exporter for local development and testing
- Console exporter for debugging
- Session-aware span emission with parent-child tracking
- Agent name extraction from Strands Agent attributes
- Environment-based configuration (LEXILENS_* vars)
- Session start/end span emission
- Agent start/end span emission with call stack tracking
- Roundtrip compatibility with LexiLensAI platform span_normalizer

### Framework Support
- Strands agents via monkey-patching

### Test Coverage
- 31 tests total (unit + integration + exporter-specific)
- Full roundtrip verification with platform `span_normalizer.py`
- JSONL exporter: 7 tests (file operations, context manager, error handling)
- OTel exporter: 8 tests (initialization, span export, mocked integration)

### Known Limitations
- No LangChain or Anthropic SDK support yet (planned for v0.2.0)
- No async batching (spans sent immediately)
- No platform HTTP exporter yet (planned for v0.2.0)
- Agent name extraction relies on simple heuristics
