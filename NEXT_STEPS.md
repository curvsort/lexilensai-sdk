# Next Steps for LexiLensAI SDK

**Status:** ✅ SDK v0.1.0 complete and tested  
**Date:** 2026-07-21  
**Location:** `/Users/rbakshi/lexilensai/lexilensai-sdk/`

---

## Immediate Actions (Day 1)

### 1. Initialize Git Repository

```bash
cd /Users/rbakshi/lexilensai/lexilensai-sdk

git init
git add .
git commit -m "Initial commit: lexilensai-sdk v0.1.0

- Session-aware instrumentation for Strands agents
- OTel/JSONL/Console exporters
- 16 tests passing (including roundtrip with platform span_normalizer)
- Comprehensive README and examples"
```

### 2. Create GitHub Repository

**Option A:** Via GitHub CLI
```bash
gh repo create curvsort/lexilensai-sdk --public --source=. --remote=origin
gh repo edit --description "Session-aware instrumentation SDK for multi-agent AI systems"
gh repo edit --add-topic python --add-topic agents --add-topic observability --add-topic opentelemetry
git push -u origin main
```

**Option B:** Via GitHub Web UI
1. Go to https://github.com/new
2. Owner: `curvsort`
3. Repository name: `lexilensai-sdk`
4. Description: "Session-aware instrumentation SDK for multi-agent AI systems"
5. Public
6. Do NOT initialize with README (we have one)
7. Create repository
8. Back in terminal:
```bash
git remote add origin https://github.com/curvsort/lexilensai-sdk.git
git push -u origin main
```

### 3. Verify CI Works

After push, GitHub Actions will run automatically. Check:
- https://github.com/curvsort/lexilensai-sdk/actions

Expected: All tests pass on Python 3.11, 3.12, 3.13.

**Note:** The CI includes a `publish` job that auto-publishes to PyPI when you push a git tag matching `v*` (e.g., `v0.1.0`). This requires configuring PyPI Trusted Publishing (see below).

---

## Publishing to PyPI (Day 2)

### Prerequisites

**Option A: GitHub Trusted Publishing (Recommended)**

1. Go to https://pypi.org/manage/account/publishing/
2. Add a new publisher:
   - PyPI Project Name: `lexilensai-sdk`
   - Owner: `curvsort`
   - Repository: `lexilensai-sdk`
   - Workflow name: `test-sdk.yml`
   - Environment name: (leave blank)
3. Once configured, simply push a git tag to trigger auto-publish:
   ```bash
   git tag v0.1.0
   git push origin v0.1.0
   ```
   The CI `publish` job will build and upload to PyPI automatically.

**Option B: Manual Publish with API Token**

```bash
pip install build twine
```

### Test PyPI First (Recommended)

```bash
# 1. Build
python -m build

# 2. Check
twine check dist/*

# 3. Upload to Test PyPI
twine upload --repository testpypi dist/*

# 4. Test install from Test PyPI
pip install --index-url https://test.pypi.org/simple/ lexilensai-sdk

# 5. Verify
python -c "from lexilensai import LexiLens; print('OK')"
```

### Production PyPI

```bash
# Only after Test PyPI verification
twine upload dist/*

# Verify
pip install lexilensai-sdk
python -c "from lexilensai import LexiLens; print('OK')"
```

### Post-Publish

1. Update PLAN_SDK_AND_REPOS.md → Mark Workstream 3 as DONE
2. Create GitHub release: https://github.com/curvsort/lexilensai-sdk/releases/new
   - Tag: `v0.1.0`
   - Title: "v0.1.0 - Initial Release"
   - Body: Copy from CHANGELOG.md
3. Add PyPI badge to README:
   ```markdown
   [![PyPI](https://img.shields.io/pypi/v/lexilensai-sdk)](https://pypi.org/project/lexilensai-sdk/)
   ```

---

## Workstream 4: Production Example Notebook

After SDK is published to PyPI:

### Location

`agent-session-graph/examples/strands-multi-agent-observability/agent-as-tools-production.ipynb`

### Structure

```python
# Cell 1: Install
!pip install lexilensai-sdk strands-agents boto3

# Cell 2: Initialize (ONE LINE)
from lexilensai import LexiLens
lexilens = LexiLens.init(service_name="strands-demo")

# Cell 3-8: Same agent code as prototype notebook

# Cell 9: Close
lexilens.close()

# Cell 10: Optional platform integration
# Show how to configure for production use
```

### Key Differences from Prototype

| Aspect | Prototype Notebook | Production Notebook |
|--------|-------------------|---------------------|
| SDK code | Embedded inline (200 lines) | Imported from package (1 line) |
| Purpose | Educational demo | Production-ready template |
| Output | Console only | Multiple exporters shown |
| Platform integration | Not shown | Demonstrated in optional cells |

---

## Documentation Updates

### agent-session-graph README

Add a note at the top:

```markdown
## Client SDK

For production use, see the **LexiLensAI SDK**: https://github.com/curvsort/lexilensai-sdk

- Installable via PyPI: `pip install lexilensai-sdk`
- Auto-instruments Strands agents (LangChain coming soon)
- Exports to OTel collector or local files

The example notebooks in this repo contain inline prototypes for educational purposes.
```

### Platform README (Private Repo)

Add SDK section:

```markdown
## Client SDK

The open-source **LexiLensAI SDK** instruments agent frameworks and sends spans to this platform:

- **GitHub:** https://github.com/curvsort/lexilensai-sdk
- **PyPI:** https://pypi.org/project/lexilensai-sdk/
- **Docs:** See SDK README

The SDK emits spans in OTel format. The platform's `ingestion/span_normalizer.py`
converts them to SessionEvent objects.
```

---

## Future Enhancements (v0.2.0+)

### Priority 1: LangChain Support

```python
# src/lexilensai/frameworks/langchain.py
from langchain.callbacks.base import BaseCallbackHandler

class LexiLensCallback(BaseCallbackHandler):
    def on_llm_start(self, ...): ...
    def on_llm_end(self, ...): ...
    def on_tool_start(self, ...): ...
    def on_tool_end(self, ...): ...
```

### Priority 2: Model Call Instrumentation

Intercept LLM API calls to emit `model.call` and `model.response` spans with token counts.

### Priority 3: Platform HTTP Exporter

```python
class PlatformExporter:
    """HTTPS exporter to LexiLensAI API (api.lexilensai.com)."""
    def __init__(self, endpoint, api_key): ...
    def export(self, span): ...  # POST /v1/spans
```

### Priority 4: Async Batching

Buffer spans in memory and flush periodically to reduce HTTP overhead.

---

## Monitoring Post-Launch

### GitHub Metrics to Watch

- Stars (adoption indicator)
- Issues (bug reports, feature requests)
- Forks (community engagement)
- Pull requests (community contributions)

### PyPI Metrics

- Download counts: https://pypistats.org/packages/lexilensai-sdk
- Version distribution (are users upgrading?)

### Support Channels

- GitHub Issues: Primary support channel
- Email: support@lexilensai.com (for private inquiries)
- Slack/Discord: Consider later if community grows

---

## Maintenance Schedule

### Weekly
- Review new GitHub issues
- Merge community PRs (after review + tests)
- Monitor PyPI download trends

### Monthly
- Security audit (dependencies via `pip-audit`)
- Update dependencies if needed
- Review roadmap vs. user requests

### Quarterly
- Major version releases (v0.2.0, v0.3.0)
- Update documentation
- Write blog posts / demos

---

## Success Metrics (3 Months)

| Metric | Target | Stretch |
|--------|--------|---------|
| GitHub stars | 50 | 100 |
| PyPI downloads/month | 100 | 500 |
| Community PRs | 1 | 3 |
| Framework adapters | 2 (Strands + LangChain) | 3 (+ Anthropic SDK) |
| Platform users | 5 | 10 |

---

## Support Plan

### Free Tier (Community)
- GitHub Issues for bugs/questions
- README + examples
- No SLA

### Paid Tier (Platform Subscribers)
- Email support (support@lexilensai.com)
- Slack channel (private)
- 24h response SLA
- Custom framework adapters on request

---

## Contact

**Maintainer:** Rajeev Bakshi  
**GitHub:** https://github.com/curvsort/lexilensai-sdk  
**Issues:** https://github.com/curvsort/lexilensai-sdk/issues  
**Email:** support@lexilensai.com
