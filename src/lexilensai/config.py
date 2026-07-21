"""
Configuration management for LexiLensAI SDK.

Loads from environment variables with sensible defaults.
All LEXILENS_* env vars override defaults.
"""
import os
from dataclasses import dataclass
from typing import Literal


@dataclass
class Config:
    """SDK configuration loaded from environment."""

    tenant_id: str
    application_id: str
    collector_endpoint: str
    exporter: Literal["otel", "jsonl", "console"]
    api_key: str | None
    harness: str
    harness_version: str

    @classmethod
    def from_env(cls, **overrides) -> "Config":
        """
        Load configuration from environment variables.

        Environment variables:
        - LEXILENS_TENANT_ID: Tenant identifier (default: "default")
        - LEXILENS_APPLICATION_ID: Application identifier (default: "default_app")
        - LEXILENS_COLLECTOR_ENDPOINT: OTel collector endpoint (default: "http://localhost:4317")
        - LEXILENS_EXPORTER: Exporter type - otel|jsonl|console (default: "otel")
        - LEXILENS_API_KEY: API key for platform integration (optional)
        - LEXILENS_HARNESS: Framework name (default: "strands")
        - LEXILENS_HARNESS_VERSION: Framework version (default: "unknown")

        Args:
            **overrides: Direct config overrides (take precedence over env vars)

        Returns:
            Config instance
        """
        config = {
            "tenant_id": os.getenv("LEXILENS_TENANT_ID", "default"),
            "application_id": os.getenv("LEXILENS_APPLICATION_ID", "default_app"),
            "collector_endpoint": os.getenv("LEXILENS_COLLECTOR_ENDPOINT", "http://localhost:4317"),
            "exporter": os.getenv("LEXILENS_EXPORTER", "otel"),
            "api_key": os.getenv("LEXILENS_API_KEY"),
            "harness": os.getenv("LEXILENS_HARNESS", "strands"),
            "harness_version": os.getenv("LEXILENS_HARNESS_VERSION", "unknown"),
        }

        # Apply overrides
        config.update(overrides)

        # Validate exporter choice
        valid_exporters = {"otel", "jsonl", "console"}
        if config["exporter"] not in valid_exporters:
            raise ValueError(
                f"Invalid LEXILENS_EXPORTER: {config['exporter']}. "
                f"Must be one of: {', '.join(valid_exporters)}"
            )

        return cls(**config)
