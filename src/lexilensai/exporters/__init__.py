"""Exporters for LexiLensAI spans."""
from .console import ConsoleExporter
from .jsonl import JSONLExporter
from .platform import PlatformExporter

# OTel exporter requires opentelemetry — import lazily
try:
    from .otel import OTelExporter
except ImportError:
    OTelExporter = None  # type: ignore[assignment,misc]

# Kinesis exporter requires boto3 — import lazily
try:
    from .kinesis import KinesisExporter
except ImportError:
    KinesisExporter = None  # type: ignore[assignment,misc]

__all__ = [
    "ConsoleExporter",
    "JSONLExporter",
    "PlatformExporter",
    "OTelExporter",
    "KinesisExporter",
]
