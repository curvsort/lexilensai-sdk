"""Tests for configuration management."""
import os

import pytest

from lexilensai.config import Config


def test_config_from_env_defaults():
    """Test config loads with default values."""
    # Clear all env vars
    for key in os.environ.copy():
        if key.startswith("LEXILENS_"):
            del os.environ[key]

    config = Config.from_env()

    assert config.tenant_id == "default"
    assert config.application_id == "default_app"
    assert config.collector_endpoint == "http://localhost:4317"
    assert config.exporter == "otel"
    assert config.api_key is None
    assert config.harness == "strands"
    assert config.harness_version == "unknown"


def test_config_from_env_overrides():
    """Test config respects environment variables."""
    os.environ["LEXILENS_TENANT_ID"] = "acme_corp"
    os.environ["LEXILENS_APPLICATION_ID"] = "research_app"
    os.environ["LEXILENS_EXPORTER"] = "jsonl"

    config = Config.from_env()

    assert config.tenant_id == "acme_corp"
    assert config.application_id == "research_app"
    assert config.exporter == "jsonl"

    # Cleanup
    del os.environ["LEXILENS_TENANT_ID"]
    del os.environ["LEXILENS_APPLICATION_ID"]
    del os.environ["LEXILENS_EXPORTER"]


def test_config_programmatic_overrides():
    """Test config allows programmatic overrides."""
    config = Config.from_env(
        tenant_id="override_tenant",
        application_id="override_app",
        exporter="console"
    )

    assert config.tenant_id == "override_tenant"
    assert config.application_id == "override_app"
    assert config.exporter == "console"


def test_config_invalid_exporter():
    """Test config rejects invalid exporter values."""
    with pytest.raises(ValueError, match="Invalid LEXILENS_EXPORTER"):
        Config.from_env(exporter="invalid")
