# Push Instructions for v0.2.0

## Outstanding Commits (2 commits ahead of origin/main)

1. **Commit aad6c20**: "Add production examples and update README (Workstream 4)"
   - `examples/production_demo.ipynb`
   - `examples/quickstart_console.py`
   - Updated `README.md`

2. **Commit 37da0f9**: "Add Anthropic SDK instrumentation (v0.2.0)"
   - `src/lexilensai/frameworks/anthropic.py`
   - `tests/test_frameworks/test_anthropic.py`
   - Updated version to 0.2.0
   - Updated CHANGELOG.md

## To Push

```bash
cd /Users/rbakshi/lexilensai/lexilensai-sdk
git push origin main
```

## After Successful Push

### Option 1: Publish to PyPI with Tag
```bash
git tag v0.2.0
git push origin v0.2.0
# CI will auto-publish to PyPI via trusted publishing
```

### Option 2: Manual PyPI Publish (if CI unavailable)
```bash
# Build distribution
python3 -m build

# Upload to PyPI (requires PYPI_API_TOKEN)
python3 -m twine upload dist/lexilensai_sdk-0.2.0*
```

## Verify After Publish

```bash
# Wait ~5 minutes after tag push for CI to complete
pip install --upgrade lexilensai-sdk
python3 -c "import lexilensai; print(lexilensai.__version__)"  # Should show 0.2.0
```

## Test Anthropic Integration

```bash
pip install anthropic lexilensai-sdk

# Test script
cat > test_anthropic_integration.py << 'PYTHON'
from lexilensai import LexiLens
import anthropic

lexilens = LexiLens.init(exporter="console")

client = anthropic.Anthropic()
response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=100,
    messages=[{"role": "user", "content": "Hello"}]
)
print(response.content[0].text)

lexilens.close()
PYTHON

python3 test_anthropic_integration.py
# Should see model.call span emitted with token counts
```

## Network Issue Notes

The push failed due to proxy error (403 Forbidden). Options to resolve:
1. Disable/configure corporate proxy settings
2. Use VPN or different network
3. Push from a different machine/environment
4. Contact IT about GitHub access through proxy

Current error:
```
fatal: unable to access 'https://github.com/curvsort/lexilensai-sdk.git/': 
CONNECT tunnel failed, response 403
```
