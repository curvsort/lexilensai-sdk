"""Tests for Kinesis exporter."""
import json
import time
from unittest.mock import MagicMock, patch

import pytest

from lexilensai.exporters.kinesis import KinesisExporter
from lexilensai.span import Span

# botocore needed for ClientError test — skip gracefully if missing
try:
    import botocore.exceptions  # noqa: F401
    HAS_BOTOCORE = True
except ImportError:
    HAS_BOTOCORE = False


def _make_span(session_id: str = "sess_001", span_name: str = "test.span") -> Span:
    """Helper to create a test span."""
    return Span.create(
        span_name=span_name,
        span_id="span_001",
        session_id=session_id,
        agent_id="test_agent",
    )


class TestKinesisExporterInit:
    """Tests for KinesisExporter initialization."""

    def test_default_config(self):
        """Test default configuration values."""
        exporter = KinesisExporter()
        assert exporter.stream_name == "lexilensai-raw-events"
        assert exporter.region_name == "ap-south-1"
        assert exporter.batch_size == 25
        assert exporter.flush_interval == 5.0
        assert exporter.max_retries == 3
        assert not exporter._closed
        exporter.close()

    def test_custom_config(self):
        """Test custom configuration overrides."""
        exporter = KinesisExporter(
            stream_name="my-stream",
            region_name="us-east-1",
            batch_size=10,
            flush_interval=2.0,
            max_retries=5,
        )
        assert exporter.stream_name == "my-stream"
        assert exporter.region_name == "us-east-1"
        assert exporter.batch_size == 10
        assert exporter.flush_interval == 2.0
        assert exporter.max_retries == 5
        exporter.close()

    def test_batch_size_capped_at_500(self):
        """Test that batch_size is capped at Kinesis limit."""
        exporter = KinesisExporter(batch_size=1000)
        assert exporter.batch_size == 500
        exporter.close()


class TestKinesisExporterExport:
    """Tests for span export and buffering."""

    def test_export_buffers_span(self):
        """Test that export() buffers span without immediate send."""
        exporter = KinesisExporter(batch_size=10)
        span = _make_span()
        exporter.export(span)

        assert len(exporter._buffer) == 1
        exporter.close()

    def test_export_record_format(self):
        """Test the Kinesis record format matches consumer expectations."""
        exporter = KinesisExporter(batch_size=10)
        span = _make_span(session_id="sess_abc")
        exporter.export(span)

        record = exporter._buffer[0]
        assert record["PartitionKey"] == "sess_abc"

        data = json.loads(record["Data"].decode("utf-8"))
        assert data["session_id"] == "sess_abc"
        assert data["span_name"] == "test.span"
        assert "start_time" in data
        assert data["attributes"]["span_id"] == "span_001"
        assert data["attributes"]["session_id"] == "sess_abc"
        assert data["attributes"]["agent_id"] == "test_agent"
        exporter.close()

    def test_export_after_close_is_noop(self):
        """Test that export() does nothing after close."""
        exporter = KinesisExporter(batch_size=10)
        exporter.close()

        span = _make_span()
        exporter.export(span)
        assert len(exporter._buffer) == 0

    def test_oversized_record_dropped(self):
        """Test that records exceeding 1MiB are dropped."""
        exporter = KinesisExporter(batch_size=10)

        # Create span with huge attributes (> 1MiB)
        span = Span.create(
            span_name="big.span",
            span_id="span_big",
            session_id="sess_001",
            large_data="x" * (1024 * 1024 + 100),  # > 1MiB
        )
        exporter.export(span)
        assert len(exporter._buffer) == 0
        exporter.close()


class TestKinesisExporterBatching:
    """Tests for batch flush behavior."""

    @patch("lexilensai.exporters.kinesis.KinesisExporter._send_batch")
    def test_flush_triggered_at_batch_size(self, mock_send):
        """Test that reaching batch_size triggers a flush."""
        exporter = KinesisExporter(batch_size=3)

        for i in range(3):
            span = Span.create(
                span_name=f"span_{i}",
                span_id=f"span_00{i}",
                session_id="sess_001",
            )
            exporter.export(span)

        # Give background thread a moment to start
        time.sleep(0.1)

        assert mock_send.called
        records = mock_send.call_args[0][0]
        assert len(records) == 3
        exporter.close()

    @patch("lexilensai.exporters.kinesis.KinesisExporter._send_batch")
    def test_manual_flush(self, mock_send):
        """Test manual flush() sends buffered records."""
        exporter = KinesisExporter(batch_size=100)  # Won't auto-flush

        span = _make_span()
        exporter.export(span)
        assert len(exporter._buffer) == 1

        exporter.flush()
        time.sleep(0.1)

        assert mock_send.called
        assert len(exporter._buffer) == 0
        exporter.close()

    @patch("lexilensai.exporters.kinesis.KinesisExporter._send_batch")
    def test_close_flushes_remaining(self, mock_send):
        """Test that close() flushes remaining buffered records."""
        exporter = KinesisExporter(batch_size=100)

        for i in range(5):
            span = Span.create(
                span_name=f"span_{i}",
                span_id=f"span_00{i}",
                session_id="sess_001",
            )
            exporter.export(span)

        exporter.close()
        time.sleep(0.1)

        assert mock_send.called
        records = mock_send.call_args[0][0]
        assert len(records) == 5


class TestKinesisExporterSendBatch:
    """Tests for the Kinesis put_records call."""

    def test_successful_put_records(self):
        """Test successful batch send to Kinesis."""
        mock_client = MagicMock()
        mock_client.put_records.return_value = {
            "FailedRecordCount": 0,
            "Records": [{"SequenceNumber": "1", "ShardId": "shard-0"}],
        }

        exporter = KinesisExporter(batch_size=100)
        exporter._client = mock_client

        span = _make_span()
        exporter.export(span)
        exporter.flush()
        time.sleep(0.2)

        mock_client.put_records.assert_called_once()
        call_kwargs = mock_client.put_records.call_args[1]
        assert call_kwargs["StreamName"] == "lexilensai-raw-events"
        assert len(call_kwargs["Records"]) == 1
        exporter.close()

    def test_partial_failure_retries(self):
        """Test that partial failures are retried."""
        mock_client = MagicMock()

        # First call: 1 of 2 records fails
        # Second call: all succeed
        mock_client.put_records.side_effect = [
            {
                "FailedRecordCount": 1,
                "Records": [
                    {"SequenceNumber": "1", "ShardId": "shard-0"},
                    {
                        "ErrorCode": "ProvisionedThroughputExceededException",
                        "ErrorMessage": "Rate exceeded",
                    },
                ],
            },
            {
                "FailedRecordCount": 0,
                "Records": [{"SequenceNumber": "2", "ShardId": "shard-0"}],
            },
        ]

        exporter = KinesisExporter(batch_size=100)
        exporter._client = mock_client

        for i in range(2):
            span = Span.create(
                span_name=f"span_{i}",
                span_id=f"span_00{i}",
                session_id="sess_001",
            )
            exporter.export(span)

        exporter.flush()
        time.sleep(0.5)

        assert mock_client.put_records.call_count == 2
        exporter.close()

    @pytest.mark.skipif(not HAS_BOTOCORE, reason="botocore not installed")
    def test_throughput_exception_retries(self):
        """Test retry on ProvisionedThroughputExceededException."""
        mock_client = MagicMock()

        # Simulate throughput exception then success
        from botocore.exceptions import ClientError

        error_response = {
            "Error": {
                "Code": "ProvisionedThroughputExceededException",
                "Message": "Rate exceeded",
            }
        }

        mock_client.put_records.side_effect = [
            ClientError(error_response, "PutRecords"),
            {
                "FailedRecordCount": 0,
                "Records": [{"SequenceNumber": "1", "ShardId": "shard-0"}],
            },
        ]

        exporter = KinesisExporter(batch_size=100)
        exporter._client = mock_client

        span = _make_span()
        exporter.export(span)
        exporter.flush()
        time.sleep(1.0)

        assert mock_client.put_records.call_count == 2
        exporter.close()

    def test_all_retries_exhausted_drops_records(self):
        """Test that records are dropped after all retries fail."""
        mock_client = MagicMock()
        mock_client.put_records.side_effect = Exception("Network error")

        exporter = KinesisExporter(batch_size=100, max_retries=2)
        exporter._client = mock_client

        span = _make_span()
        exporter.export(span)
        exporter.flush()
        time.sleep(1.5)

        assert mock_client.put_records.call_count == 2
        exporter.close()


class TestKinesisExporterPartitioning:
    """Tests for partition key behavior."""

    def test_partition_key_is_session_id(self):
        """Test that partition key equals session_id."""
        exporter = KinesisExporter(batch_size=100)

        span = _make_span(session_id="my-session-123")
        exporter.export(span)

        record = exporter._buffer[0]
        assert record["PartitionKey"] == "my-session-123"
        exporter.close()

    def test_different_sessions_different_partition_keys(self):
        """Test that different sessions get different partition keys."""
        exporter = KinesisExporter(batch_size=100)

        span1 = _make_span(session_id="sess_A")
        span2 = _make_span(session_id="sess_B")
        exporter.export(span1)
        exporter.export(span2)

        assert exporter._buffer[0]["PartitionKey"] == "sess_A"
        assert exporter._buffer[1]["PartitionKey"] == "sess_B"
        exporter.close()

    def test_missing_session_id_uses_unknown(self):
        """Test fallback partition key when session_id is absent."""
        exporter = KinesisExporter(batch_size=100)

        # Create span without session_id in attributes
        span = Span(
            span_name="orphan.span",
            start_time=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            attributes={"span_id": "s1"},
        )
        exporter.export(span)

        assert exporter._buffer[0]["PartitionKey"] == "unknown"
        exporter.close()


class TestKinesisExporterContextManager:
    """Tests for context manager protocol."""

    @patch("lexilensai.exporters.kinesis.KinesisExporter._send_batch")
    def test_context_manager_flushes_on_exit(self, mock_send):
        """Test that __exit__ calls close() which flushes."""
        with KinesisExporter(batch_size=100) as exporter:
            span = _make_span()
            exporter.export(span)

        time.sleep(0.1)
        assert mock_send.called


class TestKinesisExporterLazyClient:
    """Tests for lazy boto3 client initialization."""

    def test_client_not_created_on_init(self):
        """Test that boto3 client is not created until first send."""
        exporter = KinesisExporter()
        assert exporter._client is None
        exporter.close()

    @patch("boto3.client")
    def test_client_created_on_first_send(self, mock_boto3_client):
        """Test that boto3.client() is called on first _get_client()."""
        mock_kinesis = MagicMock()
        mock_boto3_client.return_value = mock_kinesis

        exporter = KinesisExporter(region_name="us-west-2")
        client = exporter._get_client()

        mock_boto3_client.assert_called_once_with("kinesis", region_name="us-west-2")
        assert client is mock_kinesis
        exporter.close()

    def test_custom_boto3_session(self):
        """Test using a custom boto3 session."""
        mock_session = MagicMock()
        mock_kinesis = MagicMock()
        mock_session.client.return_value = mock_kinesis

        exporter = KinesisExporter(boto3_session=mock_session, region_name="eu-west-1")
        client = exporter._get_client()

        mock_session.client.assert_called_once_with("kinesis", region_name="eu-west-1")
        assert client is mock_kinesis
        exporter.close()
