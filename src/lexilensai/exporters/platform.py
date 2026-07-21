"""
Platform HTTP exporter — sends spans to a running LexiLensAI instance.

Posts batches of spans to POST /ingest on the platform. Designed for the
lightweight Docker deployment but also works with the full AWS deployment.

Usage:
    lexilens = LexiLens.init(exporter="platform", platform_url="http://localhost:8000")
"""
import json
import logging
import threading
import time
from typing import Any
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from ..span import Span

logger = logging.getLogger("lexilensai.exporters.platform")


class PlatformExporter:
    """
    HTTP exporter that sends spans to the LexiLensAI platform's /ingest endpoint.

    Features:
    - Batches spans to reduce HTTP overhead (default: every 10 spans or 5 seconds)
    - Retry with exponential backoff on transient failures
    - Graceful degradation — never crashes the instrumented application
    - Thread-safe buffering
    """

    def __init__(
        self,
        platform_url: str = "http://localhost:8000",
        batch_size: int = 10,
        flush_interval: float = 5.0,
        max_retries: int = 3,
        timeout: float = 10.0,
    ):
        """
        Initialize platform exporter.

        Args:
            platform_url: Base URL of the LexiLensAI platform (default: localhost:8000)
            batch_size: Number of spans to buffer before sending (default: 10)
            flush_interval: Max seconds between flushes (default: 5.0)
            max_retries: Max retries on failure (default: 3)
            timeout: HTTP request timeout in seconds (default: 10.0)
        """
        self.platform_url = platform_url.rstrip("/")
        self.ingest_url = f"{self.platform_url}/ingest"
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.max_retries = max_retries
        self.timeout = timeout

        self._buffer: list[dict] = []
        self._lock = threading.Lock()
        self._closed = False
        self._pending_threads: list[threading.Thread] = []

        # Start background flush timer
        self._flush_timer: threading.Timer | None = None
        self._schedule_flush()

    def export(self, span: Span) -> None:
        """
        Buffer a span for sending.

        If the buffer reaches batch_size, triggers an immediate flush.
        Never raises — errors are logged and swallowed.

        Args:
            span: Span to export
        """
        if self._closed:
            return

        try:
            span_dict = span.to_dict()

            # Add session_id at top level for the ingest endpoint
            session_id = span.attributes.get("session_id", "unknown")
            payload = {
                "session_id": session_id,
                "span_name": span_dict["span_name"],
                "start_time": span_dict["start_time"],
                "attributes": span_dict["attributes"],
            }

            with self._lock:
                self._buffer.append(payload)

                if len(self._buffer) >= self.batch_size:
                    self._flush_buffer()

        except Exception as e:
            logger.warning(f"Failed to buffer span: {e}")

    def flush(self) -> None:
        """Force-flush all buffered spans."""
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

        # Wait for all pending send threads to complete (max 15s total)
        for thread in self._pending_threads:
            thread.join(timeout=15.0)
        self._pending_threads.clear()

    def _flush_buffer(self) -> None:
        """Send buffered spans to the platform. Must be called with _lock held."""
        if not self._buffer:
            return

        # Take the buffer and clear it
        spans_to_send = self._buffer.copy()
        self._buffer.clear()

        # Send in background to avoid blocking the instrumented app
        thread = threading.Thread(
            target=self._send_batch,
            args=(spans_to_send,),
            daemon=True
        )
        thread.start()

        # Track thread so close() can wait for it
        self._pending_threads.append(thread)

    def _send_batch(self, spans: list[dict]) -> None:
        """Send a batch of spans to the platform with retry."""
        payload = json.dumps({"spans": spans}).encode("utf-8")

        for attempt in range(self.max_retries):
            try:
                req = Request(
                    self.ingest_url,
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                response = urlopen(req, timeout=self.timeout)
                response_data = json.loads(response.read().decode("utf-8"))

                logger.debug(
                    f"Sent {len(spans)} spans to platform: "
                    f"processed={response_data.get('processed', 0)}"
                )
                return  # Success

            except HTTPError as e:
                logger.warning(
                    f"Platform ingest HTTP {e.code} (attempt {attempt + 1}/{self.max_retries}): "
                    f"{e.read().decode('utf-8', errors='replace')[:200]}"
                )
            except URLError as e:
                logger.warning(
                    f"Platform unreachable (attempt {attempt + 1}/{self.max_retries}): {e.reason}"
                )
            except Exception as e:
                logger.warning(
                    f"Platform ingest error (attempt {attempt + 1}/{self.max_retries}): {e}"
                )

            # Exponential backoff
            if attempt < self.max_retries - 1:
                time.sleep(0.5 * (2 ** attempt))

        # All retries failed — drop the spans and log
        logger.error(f"Dropped {len(spans)} spans after {self.max_retries} failed attempts")

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

        # Reschedule
        self._schedule_flush()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False
