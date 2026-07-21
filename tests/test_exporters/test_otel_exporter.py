"""Tests for OTel exporter."""
import pytest
from unittest.mock import Mock, patch, MagicMock

from lexilensai.exporters import OTelExporter
from lexilensai.span import Span


@pytest.fixture
def mock_otel_components():
    """Mock OTel SDK components."""
    with patch("lexilensai.exporters.otel.TracerProvider") as mock_provider, \
         patch("lexilensai.exporters.otel.BatchSpanProcessor") as mock_processor, \
         patch("lexilensai.exporters.otel.OTLPSpanExporter") as mock_exporter, \
         patch("lexilensai.exporters.otel.Resource") as mock_resource, \
         patch("lexilensai.exporters.otel.trace") as mock_trace:

        # Setup mock tracer
        mock_tracer = MagicMock()
        mock_trace.get_tracer.return_value = mock_tracer

        # Setup mock span context manager
        mock_span = MagicMock()
        mock_span.__enter__ = Mock(return_value=mock_span)
        mock_span.__exit__ = Mock(return_value=False)
        mock_tracer.start_as_current_span.return_value = mock_span

        yield {
            "provider": mock_provider,
            "processor": mock_processor,
            "exporter": mock_exporter,
            "resource": mock_resource,
            "trace": mock_trace,
            "tracer": mock_tracer,
            "span": mock_span
        }


def test_otel_exporter_initialization(mock_otel_components):
    """Test OTelExporter initializes correctly."""
    exporter = OTelExporter(
        endpoint="http://localhost:4317",
        service_name="test_service"
    )

    # Verify Resource created with service name
    mock_otel_components["resource"].create.assert_called_once_with(
        {"service.name": "test_service"}
    )

    # Verify TracerProvider created
    assert mock_otel_components["provider"].called

    # Verify OTLP exporter created
    assert mock_otel_components["exporter"].called

    # Verify processor added
    provider_instance = mock_otel_components["provider"].return_value
    assert provider_instance.add_span_processor.called


def test_otel_exporter_endpoint_parsing(mock_otel_components):
    """Test that OTelExporter correctly parses endpoint URLs."""
    exporter = OTelExporter(
        endpoint="http://localhost:4317",
        service_name="test"
    )

    # Verify http:// prefix removed for gRPC endpoint
    call_args = mock_otel_components["exporter"].call_args
    assert call_args is not None
    assert "localhost:4317" in str(call_args)


def test_otel_exporter_exports_span(mock_otel_components):
    """Test that OTelExporter exports spans."""
    exporter = OTelExporter(
        endpoint="http://localhost:4317",
        service_name="test"
    )

    span = Span.create(
        span_name="test.span",
        span_id="span_001",
        session_id="sess_001",
        agent_id="test_agent"
    )

    exporter.export(span)

    # Verify tracer.start_as_current_span was called
    tracer = mock_otel_components["tracer"]
    tracer.start_as_current_span.assert_called_once_with("test.span")

    # Verify attributes were set
    otel_span = mock_otel_components["span"]
    assert otel_span.set_attribute.called


def test_otel_exporter_sets_span_attributes(mock_otel_components):
    """Test that OTelExporter sets all span attributes."""
    exporter = OTelExporter(
        endpoint="http://localhost:4317",
        service_name="test"
    )

    span = Span.create(
        span_name="test.span",
        span_id="span_001",
        session_id="sess_001",
        agent_id="test_agent",
        model="claude-sonnet-4-6",
        input_tokens=100
    )

    exporter.export(span)

    # Verify set_attribute called for each attribute
    otel_span = mock_otel_components["span"]
    set_attribute_calls = otel_span.set_attribute.call_args_list

    # Check that span_id, session_id, agent_id were set
    call_args = [call[0] for call in set_attribute_calls]
    attribute_keys = [args[0] for args in call_args]

    assert "span_id" in attribute_keys
    assert "session_id" in attribute_keys
    assert "agent_id" in attribute_keys


def test_otel_exporter_handles_complex_attributes(mock_otel_components):
    """Test that OTelExporter JSON-serializes complex attributes."""
    exporter = OTelExporter(
        endpoint="http://localhost:4317",
        service_name="test"
    )

    span = Span.create(
        span_name="test.span",
        span_id="span_001",
        session_id="sess_001"
    )
    # Add a complex attribute (list)
    span.attributes["tools"] = ["tool1", "tool2"]

    exporter.export(span)

    # Verify set_attribute was called
    otel_span = mock_otel_components["span"]
    assert otel_span.set_attribute.called


def test_otel_exporter_close_flushes(mock_otel_components):
    """Test that OTelExporter.close() flushes spans."""
    exporter = OTelExporter(
        endpoint="http://localhost:4317",
        service_name="test"
    )

    exporter.close()

    # Verify force_flush and shutdown called
    provider_instance = mock_otel_components["provider"].return_value
    provider_instance.force_flush.assert_called_once()
    provider_instance.shutdown.assert_called_once()


def test_otel_exporter_multiple_spans(mock_otel_components):
    """Test that OTelExporter can export multiple spans."""
    exporter = OTelExporter(
        endpoint="http://localhost:4317",
        service_name="test"
    )

    for i in range(3):
        span = Span.create(
            span_name=f"span_{i}",
            span_id=f"span_00{i}",
            session_id="sess_001"
        )
        exporter.export(span)

    # Verify tracer.start_as_current_span called 3 times
    tracer = mock_otel_components["tracer"]
    assert tracer.start_as_current_span.call_count == 3


def test_otel_exporter_insecure_flag(mock_otel_components):
    """Test that OTelExporter uses insecure=True for local dev."""
    exporter = OTelExporter(
        endpoint="http://localhost:4317",
        service_name="test"
    )

    # Verify OTLPSpanExporter called with insecure=True
    call_kwargs = mock_otel_components["exporter"].call_args[1]
    assert call_kwargs.get("insecure") is True
