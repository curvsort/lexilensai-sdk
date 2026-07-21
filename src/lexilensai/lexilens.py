"""
Main LexiLens SDK API.

Provides the LexiLens.init() entry point for session initialization
and framework instrumentation.
"""
import time
from typing import Any

from .config import Config
from .exporters import ConsoleExporter, JSONLExporter, OTelExporter, PlatformExporter
from .frameworks import patch_anthropic, patch_strands, unpatch_anthropic, unpatch_strands
from .span import Span, generate_span_id


class LexiLens:
    """
    Main SDK class for session-aware instrumentation.

    Usage:
        lexilens = LexiLens.init(tenant_id="acme", application_id="app")
        # ... run your agents ...
        lexilens.close()
    """

    def __init__(self, config: Config, exporter: Any, session_id: str):
        """
        Initialize LexiLens instance.

        Args:
            config: Configuration object
            exporter: Exporter instance
            session_id: Unique session identifier
        """
        self.config = config
        self.exporter = exporter
        self.session_id = session_id
        self._closed = False

    @classmethod
    def init(
        cls,
        tenant_id: str | None = None,
        application_id: str | None = None,
        exporter: str | None = None,
        collector_endpoint: str | None = None,
        platform_url: str | None = None,
        objective: str | None = None,
        **config_overrides
    ) -> "LexiLens":
        """
        Initialize LexiLens instrumentation.

        This method:
        1. Loads configuration from environment + overrides
        2. Creates the appropriate exporter (otel, jsonl, console, or platform)
        3. Generates a unique session ID
        4. Emits a session.start span
        5. Patches the Strands framework

        Args:
            tenant_id: Tenant identifier (overrides LEXILENS_TENANT_ID)
            application_id: Application identifier (overrides LEXILENS_APPLICATION_ID)
            exporter: Exporter type - "otel"|"jsonl"|"console"|"platform" (overrides LEXILENS_EXPORTER)
            collector_endpoint: OTel collector endpoint (overrides LEXILENS_COLLECTOR_ENDPOINT)
            platform_url: LexiLensAI platform URL for "platform" exporter (default: http://localhost:8000)
            objective: Session objective/goal (optional, stored in session metadata)
            **config_overrides: Additional config overrides

        Returns:
            LexiLens instance
        """
        # Build config overrides dict
        overrides = config_overrides.copy()
        if tenant_id:
            overrides["tenant_id"] = tenant_id
        if application_id:
            overrides["application_id"] = application_id
        if exporter:
            overrides["exporter"] = exporter
        if collector_endpoint:
            overrides["collector_endpoint"] = collector_endpoint

        # Load config
        config = Config.from_env(**overrides)

        # Generate session ID
        session_id = f"sess_{int(time.time())}_{generate_span_id().split('_')[-1]}"

        # Create exporter
        if config.exporter == "otel":
            if OTelExporter is None:
                raise ImportError(
                    "OTel exporter requires opentelemetry packages. "
                    "Install with: pip install opentelemetry-api opentelemetry-sdk "
                    "opentelemetry-exporter-otlp-proto-grpc"
                )
            exp = OTelExporter(
                endpoint=config.collector_endpoint,
                service_name=config.application_id
            )
        elif config.exporter == "jsonl":
            exp = JSONLExporter()
        elif config.exporter == "console":
            exp = ConsoleExporter()
        elif config.exporter == "platform":
            url = platform_url or config_overrides.get("platform_url") or "http://localhost:8000"
            exp = PlatformExporter(platform_url=url)
        else:
            raise ValueError(f"Unknown exporter: {config.exporter}")

        # Create instance
        instance = cls(config, exp, session_id)

        # Emit session.start span
        start_span = Span.create(
            span_name="session.start",
            span_id=generate_span_id(),
            session_id=session_id,
            tenant_id=config.tenant_id,
            application_id=config.application_id,
            harness=config.harness,
            harness_version=config.harness_version,
            objective=objective or "No objective specified"
        )
        exp.export(start_span)

        # Patch frameworks
        patch_strands(session_id, exp)
        patch_anthropic(session_id, exp)

        return instance

    def close(self) -> None:
        """
        Close the session and flush all spans.

        Emits a session.end span and unpatch frameworks.
        """
        if self._closed:
            return

        # Emit session.end span
        end_span = Span.create(
            span_name="session.end",
            span_id=generate_span_id(),
            session_id=self.session_id
        )
        self.exporter.export(end_span)

        # Unpatch frameworks
        unpatch_strands()
        unpatch_anthropic()

        # Close exporter
        self.exporter.close()

        self._closed = True

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False
