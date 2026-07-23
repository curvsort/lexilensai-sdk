"""
Kinesis exporter — sends spans directly to a Kinesis Data Stream.

Bypasses the Lambda HTTP ingest path for higher throughput and lower latency.
Uses put_records for batched writes with session_id as partition key (guarantees
ordering within a session on a single shard).

Usage:
    lexilens = LexiLens.init(
        exporter="kinesis",
        stream_name="lexilensai-raw-events",
        region_name="ap-south-1",
    )

Requires: pip install lexilensai-sdk[kinesis]  (adds boto3)
"""
import json
import logging
import threading
import time
from typing import Any, Optional

from ..span import Span

logger = logging.getLogger("lexilensai.exporters.kinesis")


class KinesisExporter:
    """
    Kinesis exporter that writes spans directly to a Kinesis Data Stream.

    Features:
    - Batches spans for efficient put_records calls (max 500 per Kinesis API call)
    - Partition key = session_id (ordering guarantee within session)
    - Retry with exponential backoff on ProvisionedThroughputExceededException
    - Graceful degradation — never crashes the instrumented application
    - Thread-safe buffering with background flush
    - Handles partial failures (re-enqueues failed records)
    """

    # Kinesis limits
    MAX_RECORDS_PER_BATCH = 500
    MAX_RECORD_SIZE_BYTES = 1_048_576  # 1 MiB per record
    MAX_BATCH_SIZE_BYTES = 5_242_880  # 5 MiB per put_records call

    def __init__(
        self,
        stream_name: str = "lexilensai-raw-events",
        region_name: str = "ap-south-1",
        batch_size: int = 25,
        flush_interval: float = 5.0,
        max_retries: int = 3,
        boto3_session: Optional[Any] = None,
    ):
        """
        Initialize Kinesis exporter.

        Args:
            stream_name: Kinesis stream name (default: lexilensai-raw-events)
            region_name: AWS region (default: ap-south-1)
            batch_size: Number of spans to buffer before sending (default: 25)
            flush_interval: Max seconds between flushes (default: 5.0)
            max_retries: Max retries on throughput exceptions (default: 3)
            boto3_session: Optional boto3.Session for custom credentials
        """
        self.stream_name = stream_name
        self.region_name = region_name
        self.batch_size = min(batch_size, self.MAX_RECORDS_PER_BATCH)
        self.flush_interval = flush_interval
        self.max_retries = max_retries

        self._buffer: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._closed = False
        self._pending_threads: list[threading.Thread] = []
        self._client: Optional[Any] = None
        self._boto3_session = boto3_session

        # Start background flush timer
        self._flush_timer: Optional[threading.Timer] = None
        self._schedule_flush()

    def _get_client(self):
        """Lazy-init boto3 Kinesis client (defers import + connection)."""
        if self._client is None:
            if self._boto3_session:
                # Custom session provided — no need to import boto3 directly
                self._client = self._boto3_session.client(
                    "kinesis", region_name=self.region_name
                )
            else:
                try:
                    import boto3
                except ImportError:
                    raise ImportError(
                        "boto3 is required for KinesisExporter. "
                        "Install it with: pip install lexilensai-sdk[kinesis]"
                    )
                self._client = boto3.client(
                    "kinesis", region_name=self.region_name
                )
        return self._client

    def export(self, span: Span) -> None:
        """
        Buffer a span for sending to Kinesis.

        If the buffer reaches batch_size, triggers an immediate flush.
        Never raises — errors are logged and swallowed.

        Args:
            span: Span to export
        """
        if self._closed:
            return

        try:
            span_dict = span.to_dict()
            session_id = span.attributes.get("session_id", "unknown")

            # Build record matching consumer expected format
            record = {
                "Data": json.dumps({
                    "session_id": session_id,
                    "span_name": span_dict["span_name"],
                    "start_time": span_dict["start_time"],
                    "attributes": span_dict["attributes"],
                }).encode("utf-8"),
                "PartitionKey": session_id,
            }

            # Check record size (Kinesis 1MiB limit)
            if len(record["Data"]) > self.MAX_RECORD_SIZE_BYTES:
                logger.warning(
                    f"Span exceeds Kinesis 1MiB limit ({len(record['Data'])} bytes), dropping"
                )
                return

            with self._lock:
                self._buffer.append(record)

                if len(self._buffer) >= self.batch_size:
                    self._flush_buffer()

        except Exception as e:
            logger.warning(f"Failed to buffer span: {e}")

    def flush(self) -> None:
        """Force-flush all buffered spans to Kinesis."""
        with self._lock:
            self._flush_buffer()

    def close(self) -> None:
        """Flush remaining spans and close the exporter."""
        if self._closed:
            return

        self._closed = True

        # Cancel timer
        if self._flush_timer:
            self._flush_timer.cancel()

        # Final flush
        self.flush()

        # Wait for pending send threads (max 15s total)
        for thread in self._pending_threads:
            thread.join(timeout=15.0)
        self._pending_threads.clear()

    def _flush_buffer(self) -> None:
        """Send buffered records to Kinesis. Must be called with _lock held."""
        if not self._buffer:
            return

        # Take the buffer and clear
        records_to_send = self._buffer.copy()
        self._buffer.clear()

        # Send in background to avoid blocking the instrumented app
        thread = threading.Thread(
            target=self._send_batch,
            args=(records_to_send,),
            daemon=True,
        )
        thread.start()
        self._pending_threads.append(thread)

    def _send_batch(self, records: list[dict[str, Any]]) -> None:
        """
        Send a batch of records to Kinesis with retry on throughput errors.

        Handles partial failures by re-enqueuing FailedRecordCount items.
        """
        try:
            client = self._get_client()
        except ImportError as e:
            logger.error(str(e))
            return

        remaining = records
        for attempt in range(self.max_retries):
            if not remaining:
                return

            # Respect Kinesis batch limits (500 records, 5MiB)
            batch = remaining[: self.MAX_RECORDS_PER_BATCH]

            try:
                response = client.put_records(
                    StreamName=self.stream_name,
                    Records=batch,
                )

                failed_count = response.get("FailedRecordCount", 0)
                if failed_count == 0:
                    logger.debug(
                        f"Sent {len(batch)} records to Kinesis stream '{self.stream_name}'"
                    )
                    # Handle any records beyond this batch
                    remaining = remaining[self.MAX_RECORDS_PER_BATCH:]
                    if not remaining:
                        return
                    continue

                # Partial failure — re-enqueue only the failed records
                failed_records = []
                for i, record_result in enumerate(response.get("Records", [])):
                    if "ErrorCode" in record_result:
                        failed_records.append(batch[i])
                        if attempt == 0:
                            logger.debug(
                                f"Record failed: {record_result.get('ErrorCode')}: "
                                f"{record_result.get('ErrorMessage', '')}"
                            )

                remaining = failed_records + remaining[self.MAX_RECORDS_PER_BATCH:]
                logger.warning(
                    f"{failed_count} records failed (attempt {attempt + 1}/{self.max_retries}), "
                    f"retrying..."
                )

            except Exception as e:
                error_name = type(e).__name__
                if "ProvisionedThroughputExceededException" in error_name or (
                    hasattr(e, "response")
                    and e.response.get("Error", {}).get("Code")
                    == "ProvisionedThroughputExceededException"
                ):
                    logger.warning(
                        f"Kinesis throughput exceeded (attempt {attempt + 1}/{self.max_retries})"
                    )
                else:
                    logger.warning(
                        f"Kinesis put_records error (attempt {attempt + 1}/{self.max_retries}): {e}"
                    )

            # Exponential backoff
            if attempt < self.max_retries - 1:
                time.sleep(0.5 * (2**attempt))

        # All retries exhausted
        logger.error(
            f"Dropped {len(remaining)} records after {self.max_retries} failed attempts"
        )

    def _schedule_flush(self) -> None:
        """Schedule the next periodic flush."""
        if self._closed:
            return

        self._flush_timer = threading.Timer(self.flush_interval, self._periodic_flush)
        self._flush_timer.daemon = True
        self._flush_timer.start()

    def _periodic_flush(self) -> None:
        """Periodic flush triggered by timer."""
        if self._closed:
            return

        with self._lock:
            if self._buffer:
                self._flush_buffer()

        self._schedule_flush()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False
