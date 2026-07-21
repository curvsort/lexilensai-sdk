"""
OpenTelemetry gRPC exporter.

Sends spans to an OTel collector (default: localhost:4317) using the
OTLP protocol. The collector then forwards to the platform's Kinesis stream.
"""

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from ..span import Span


class OTelExporter:
    """
    OpenTelemetry exporter using gRPC to local collector.

    Wraps OTel SDK's TracerProvider and OTLP exporter. Spans are sent
    in batches to minimize overhead.
    """

    def __init__(self, endpoint: str, service_name: str):
        """
        Initialize OTel exporter.

        Args:
            endpoint: OTel collector endpoint (e.g., "http://localhost:4317")
            service_name: Service name for resource attributes
        """
        self.endpoint = endpoint
        self.service_name = service_name

        # Create resource with service name
        resource = Resource.create({"service.name": service_name})

        # Create tracer provider
        self.provider = TracerProvider(resource=resource)

        # Create OTLP exporter
        # Parse endpoint to remove http:// prefix for gRPC
        grpc_endpoint = endpoint.replace("http://", "").replace("https://", "")

        exporter = OTLPSpanExporter(
            endpoint=grpc_endpoint,
            insecure=True  # Use insecure for local development
        )

        # Add batch processor
        processor = BatchSpanProcessor(exporter)
        self.provider.add_span_processor(processor)

        # Set as global provider
        trace.set_tracer_provider(self.provider)

        # Get tracer
        self.tracer = trace.get_tracer(service_name)

    def export(self, span: Span) -> None:
        """
        Export a span to the OTel collector.

        Args:
            span: Span to export
        """
        # Create OTel span
        with self.tracer.start_as_current_span(span.span_name) as otel_span:
            # Set all attributes from the span
            for key, value in span.attributes.items():
                # OTel attributes must be primitive types
                if isinstance(value, (str, int, float, bool)):
                    otel_span.set_attribute(key, value)
                else:
                    # Convert complex types to JSON strings
                    import json
                    otel_span.set_attribute(key, json.dumps(value))

            # Set timestamp
            # Note: OTel SDK handles timestamp automatically on span start
            # For custom timestamps, we'd need to use the lower-level API

    def close(self) -> None:
        """Flush and shutdown the exporter."""
        # Force flush all pending spans
        self.provider.force_flush()
        self.provider.shutdown()
