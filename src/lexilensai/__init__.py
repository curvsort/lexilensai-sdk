"""
LexiLensAI SDK - Session-aware instrumentation for multi-agent AI systems.

Usage:
    from lexilensai import LexiLens

    # Initialize (auto-instruments Strands agents)
    lexilens = LexiLens.init(
        tenant_id="acme_corp",
        application_id="research_assistant"
    )

    # Your agent code runs here...

    # Close and flush
    lexilens.close()
"""
from .lexilens import LexiLens
from .config import Config
from .span import Span, generate_span_id

__version__ = "0.1.0"
__all__ = ["LexiLens", "Config", "Span", "generate_span_id"]
