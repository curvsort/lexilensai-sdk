"""
Pytest configuration and shared fixtures.
"""
import sys
from pathlib import Path

# Add SDK to path
sdk_root = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(sdk_root))

# Add platform root to path (for span_normalizer import)
platform_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(platform_root))
