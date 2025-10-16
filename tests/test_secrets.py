from __future__ import annotations

import json
import sys
import types
from typing import Any, cast

import pytest
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from firecrawl_demo import config, secrets
from firecrawl_demo.secrets import (
    AwsSecretsManagerProvider,
    AzureKeyVaultProvider,
    ChainedSecretsProvider,
    EnvSecretsProvider,
    SecretsProviderError,
    build_provider_from_environment,
)


class DummyProvider:
    def __init__(self, values: dict[str, str | None]) -> None:
        self.values = values
        self.calls: list[str] = []

    def get(self, name: str) -> str | None:  # pragma: no cover - exercised via tests
        self.calls.append(name)
        return self.values.get(name)


def test_chained_provider_prefers_first_non_empty_value() -> None:
    primary = DummyProvider({"SECRET": None})
    fallback = DummyProvider({"SECRET": "secondary"})
    provider = ChainedSecretsProvider((primary, fallback))

    assert provider.get("SECRET") == "secondary"
    assert primary.calls == ["SECRET"]
    assert fallback.calls == ["SECRET"]


def test_chained_provider_returns_none_when_all_missing() -> None:
    empty = DummyProvider({})
    provider = ChainedSecretsProvider((empty, empty))
    assert provider.get("MISSING") is None


def _install_azure_stubs(
    monkeypatch: pytest.MonkeyPatch,
    secret_client_cls: type,
    credential_cls: type,
) -> None:
    identity_module = cast(Any, types.ModuleType("azure.identity"))
    identity_module.DefaultAzureCredential = credential_cls

    secrets_module = cast(Any, types.ModuleType("azure.keyvault.secrets"))
    secrets_module.SecretClient = secret_client_cls

    keyvault_module = cast(Any, types.ModuleType("azure.keyvault"))
    keyvault_module.secrets = secrets_module

    azure_module = cast(Any, types.ModuleType("azure"))
    azure_module.identity = identity_module
    azure_module.keyvault = keyvault_module

    monkeypatch.setitem(sys.modules, "azure", azure_module)
    monkeypatch.setitem(sys.modules, "azure.identity", identity_module)
    monkeypatch.setitem(sys.modules, "azure.keyvault", keyvault_module)
    monkeypatch.setitem(sys.modules, "azure.keyvault.secrets", secrets_module)


def test_env_secrets_provider_defaults_to_os_env(monkeypatch):
    monkeypatch.setenv("SAMPLE_SECRET", "value")
    provider = EnvSecretsProvider()
    assert provider.get("SAMPLE_SECRET") == "value"


def test_env_secrets_provider_respects_custom_mapping():
    provider = EnvSecretsProvider({"KEY": "mapped"})
    assert provider.get("KEY") == "mapped"


def test_aws_secrets_manager_provider_returns_secret():
    class StubClient:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def get_secret_value(self, SecretId: str) -> dict[str, object]:
            self.calls.append(SecretId)
            return {"SecretString": "resolved"}

    class StubSession:
        def __init__(self, client: StubClient) -> None:
            self._client = client

        def client(self, service: str, region_name: str | None = None) -> StubClient:
            assert service == "secretsmanager"
            return self._client

    stub_client = StubClient()
    provider = AwsSecretsManagerProvider(
        secret_prefix="prod", region_name="af-south-1", session=StubSession(stub_client)
    )
    assert provider.get("TOKEN") == "resolved"
    assert stub_client.calls == ["prod/TOKEN"]


def test_aws_secrets_manager_provider_handles_binary_payload():
    class StubClient:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def get_secret_value(self, SecretId: str) -> dict[str, object]:
            self.calls.append(SecretId)
            return {"SecretString": None, "SecretBinary": b"payload"}

    class StubSession:
        def __init__(self, client: StubClient) -> None:
            self._client = client

        def client(self, *_: object, **__: object) -> StubClient:
            return self._client

    stub_client = StubClient()
    provider = AwsSecretsManagerProvider(session=StubSession(stub_client))
    assert provider.get("TOKEN") == "payload"
    assert stub_client.calls == ["TOKEN"]

    class NonBytesClient(StubClient):
        def get_secret_value(self, SecretId: str) -> dict[str, object]:
            self.calls.append(SecretId)
            return {"SecretString": None, "SecretBinary": {"value": "data"}}

    other_client = NonBytesClient()
    provider = AwsSecretsManagerProvider(session=StubSession(other_client))
    assert provider.get("TOKEN") == "{'value': 'data'}"


def test_aws_secrets_manager_provider_returns_none_for_empty_payload():
    class StubClient:
        def get_secret_value(self, SecretId: str) -> dict[str, object]:
            return {}

    class StubSession:
        def __init__(self, client: StubClient) -> None:
            self._client = client

        def client(self, *_: object, **__: object) -> StubClient:
            return self._client

    provider = AwsSecretsManagerProvider(session=StubSession(StubClient()))
    assert provider.get("TOKEN") is None


def test_aws_secrets_manager_provider_handles_missing_secret():
    class FailingClient:
        def __init__(self, code: str) -> None:
            self.code = code

        def get_secret_value(self, SecretId: str) -> dict[str, Any]:
            raise ClientError({"Error": {"Code": self.code}}, "GetSecretValue")

    class StubSession:
        def __init__(self, client: FailingClient) -> None:
            self._client = client

        def client(self, *_: object, **__: object) -> FailingClient:
            return self._client

    missing_provider = AwsSecretsManagerProvider(
        session=StubSession(FailingClient("ResourceNotFoundException"))
    )
    assert missing_provider.get("TOKEN") is None

    provider = AwsSecretsManagerProvider(
        session=StubSession(FailingClient("InternalServiceError"))
    )
    with pytest.raises(SecretsProviderError):
        provider.get("TOKEN")


def test_azure_key_vault_provider_returns_secret(monkeypatch):
    class StubSecret:
        def __init__(self, value: str) -> None:
            self.value = value

    class StubClient:
        def __init__(self, *, vault_url: str, credential: object) -> None:
            self.vault_url = vault_url
            self.credential = credential
            self.calls: list[str] = []

        def get_secret(self, name: str) -> StubSecret:
            self.calls.append(name)
            return StubSecret("fetched")

    class StubCredential:
        pass

    _install_azure_stubs(monkeypatch, StubClient, StubCredential)

    provider = AzureKeyVaultProvider(
        vault_url="https://vault.example", secret_prefix="team/"
    )
    assert provider.get("TOKEN") == "fetched"


def test_azure_key_vault_provider_handles_missing_secret(monkeypatch):
    class StubClient:
        def __init__(self, *, vault_url: str, credential: object) -> None:
            self.vault_url = vault_url
            self.credential = credential

        def get_secret(self, name: str) -> None:
            error = Exception("missing")
            setattr(error, "status_code", 404)
            raise error

    class StubCredential:
        pass

    _install_azure_stubs(monkeypatch, StubClient, StubCredential)

    provider = AzureKeyVaultProvider(vault_url="https://vault.example")
    assert provider.get("TOKEN") is None


def test_azure_key_vault_provider_wraps_other_errors(monkeypatch):
    class StubClient:
        def __init__(self, *, vault_url: str, credential: object) -> None:
            self.vault_url = vault_url
            self.credential = credential

        def get_secret(self, name: str) -> None:
            raise RuntimeError("boom")

    class StubCredential:
        pass

    _install_azure_stubs(monkeypatch, StubClient, StubCredential)

    provider = AzureKeyVaultProvider(vault_url="https://vault.example")
    with pytest.raises(SecretsProviderError):
        provider.get("TOKEN")


def test_build_provider_from_environment_defaults_to_env():
    provider = build_provider_from_environment({"SAMPLE": "value"})
    assert isinstance(provider, EnvSecretsProvider)
    assert provider.get("SAMPLE") == "value"


def test_build_provider_from_environment_includes_aws(monkeypatch):
    class StubProvider:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs
            self.values = {"SECRET": "aws"}

        def get(self, name: str) -> str | None:
            return self.values.get(name)

    monkeypatch.setattr(secrets, "AwsSecretsManagerProvider", StubProvider)

    provider = build_provider_from_environment(
        {
            "SECRETS_BACKEND": "aws",
            "AWS_REGION": "af-south-1",
            "AWS_SECRETS_PREFIX": "prod/",
            "SECRET": "env",
        }
    )

    value = provider.get("SECRET")
    assert value == "aws"


def test_build_provider_from_environment_handles_aws_errors(monkeypatch):
    def raising_provider(**_: object) -> None:
        raise SecretsProviderError("boom")

    monkeypatch.setattr(secrets, "AwsSecretsManagerProvider", raising_provider)

    provider = build_provider_from_environment(
        {"SECRETS_BACKEND": "aws", "SECRET": "env"}
    )
    assert isinstance(provider, EnvSecretsProvider)
    assert provider.get("SECRET") == "env"


def test_build_provider_from_environment_includes_azure(monkeypatch):
    class StubProvider:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs
            self.values = {"SECRET": "azure"}

        def get(self, name: str) -> str | None:
            return self.values.get(name)

    monkeypatch.setattr(secrets, "AzureKeyVaultProvider", StubProvider)

    provider = build_provider_from_environment(
        {
            "SECRETS_BACKEND": "azure",
            "AZURE_KEY_VAULT_URL": "https://vault.example",
            "AZURE_SECRETS_PREFIX": "team/",
            "SECRET": "env",
        }
    )

    assert provider.get("SECRET") == "azure"


def test_build_provider_from_environment_handles_azure_errors(monkeypatch):
    def raising_provider(**_: object) -> None:
        raise SecretsProviderError("boom")

    monkeypatch.setattr(secrets, "AzureKeyVaultProvider", raising_provider)

    provider = build_provider_from_environment(
        {
            "SECRETS_BACKEND": "azure",
            "AZURE_KEY_VAULT_URL": "https://vault.example",
            "SECRET": "env",
        }
    )
    assert isinstance(provider, EnvSecretsProvider)
    assert provider.get("SECRET") == "env"


def test_configure_uses_supplied_provider() -> None:
    provider = DummyProvider(
        {
            "FIRECRAWL_API_KEY": "test-key",
            "FIRECRAWL_API_URL": "https://api.example.com",
            "FEATURE_ENABLE_FIRECRAWL_SDK": "true",
            "FEATURE_ENABLE_PRESS_RESEARCH": "0",
            "FEATURE_ENABLE_REGULATOR_LOOKUP": "yes",
            "FEATURE_INVESTIGATE_REBRANDS": "false",
            "ALLOW_NETWORK_RESEARCH": "1",
            "FIRECRAWL_SEARCH_LIMIT": "9",
            "FIRECRAWL_MAP_LIMIT": "4",
            "FIRECRAWL_TIMEOUT_SECONDS": "12.5",
            "FIRECRAWL_PROXY_MODE": "advanced",
            "FIRECRAWL_ONLY_MAIN_CONTENT": "false",
            "FIRECRAWL_SCRAPE_FORMATS": json.dumps(["markdown"]),
            "FIRECRAWL_PARSERS": json.dumps(["html"]),
            "FIRECRAWL_RETRY_MAX_ATTEMPTS": "7",
            "FIRECRAWL_RETRY_INITIAL_DELAY": "0.5",
            "FIRECRAWL_RETRY_MAX_DELAY": "5",
            "FIRECRAWL_RETRY_BACKOFF_FACTOR": "1.5",
            "FIRECRAWL_MAX_CONCURRENCY": "6",
            "FIRECRAWL_MIN_INTERVAL_SECONDS": "0.1",
            "FIRECRAWL_CACHE_TTL_HOURS": "6",
            "FIRECRAWL_MX_LOOKUP_TIMEOUT": "1.5",
            "FIRECRAWL_BATCH_SIZE": "11",
            "FIRECRAWL_REQUEST_DELAY_SECONDS": "0.3",
            "CRAWLER_FRONTIER_BACKEND": "stormcrawler",
            "CRAWLER_SCHEDULER_MODE": "bandit",
            "CRAWLER_POLITENESS_DELAY_SECONDS": "2.0",
            "CRAWLER_MAX_DEPTH": "8",
            "CRAWLER_MAX_PAGES": "7000",
            "CRAWLER_USER_AGENT": "ACESBot/1.1",
            "CRAWLER_ROBOTS_CACHE_HOURS": "9",
            "OBSERVABILITY_PORT": "7070",
            "OBSERVABILITY_LIVENESS_PATH": "/health/live",
            "OBSERVABILITY_READINESS_PATH": "/health/ready",
            "OBSERVABILITY_STARTUP_PATH": "/health/start",
            "OBSERVABILITY_ALERT_ROUTES": "slack,pagerduty",
            "SLO_AVAILABILITY_TARGET": "99.8",
            "SLO_LATENCY_P95_MS": "350",
            "SLO_ERROR_BUDGET_PERCENT": "1.5",
            "OPA_DECISION_PATH": "copilot/allow",
            "OPA_ENFORCEMENT_MODE": "dry-run",
            "OPA_CACHE_SECONDS": "45",
            "PLAN_COMMIT_REQUIRED": "0",
            "PLAN_COMMIT_DIFF_FORMAT": "json",
            "PLAN_COMMIT_AUDIT_TOPIC": "audit.plan-commit.test",
            "PLAN_COMMIT_ALLOW_FORCE": "1",
        }
    )

    config.configure(provider)
    try:
        assert config.settings.FIRECRAWL_API_KEY == "test-key"
        assert config.settings.FIRECRAWL_API_URL == "https://api.example.com"
        assert config.FEATURE_FLAGS.enable_firecrawl_sdk is True
        assert config.FEATURE_FLAGS.enable_press_research is False
        assert config.FEATURE_FLAGS.enable_regulator_lookup is True
        assert config.FEATURE_FLAGS.investigate_rebrands is False
        assert config.ALLOW_NETWORK_RESEARCH is True
        assert config.FIRECRAWL.api_key == "test-key"
        assert config.FIRECRAWL.api_url == "https://api.example.com"
        assert config.FIRECRAWL.behaviour.search_limit == 9
        assert config.FIRECRAWL.behaviour.map_limit == 4
        assert config.FIRECRAWL.behaviour.timeout_seconds == 12.5
        assert config.FIRECRAWL.behaviour.proxy_mode == "advanced"
        assert config.FIRECRAWL.behaviour.only_main_content is False
        assert config.FIRECRAWL.behaviour.scrape_formats == ["markdown"]
        assert config.FIRECRAWL.behaviour.parsers == ["html"]
        assert config.RETRY.max_attempts == 7
        assert config.RETRY.initial_delay == 0.5
        assert config.RETRY.max_delay == 5.0
        assert config.RETRY.backoff_factor == 1.5
        assert config.THROTTLE.max_concurrency == 6
        assert config.THROTTLE.min_interval == 0.1
        assert config.CACHE_TTL_HOURS == 6.0
        assert config.MX_LOOKUP_TIMEOUT == 1.5
        assert config.BATCH_SIZE == 11
        assert config.REQUEST_DELAY_SECONDS == 0.3
        assert config.CRAWLER_INFRASTRUCTURE.frontier_backend == "stormcrawler"
        assert config.CRAWLER_INFRASTRUCTURE.scheduler_mode == "bandit"
        assert config.CRAWLER_INFRASTRUCTURE.politeness_delay_seconds == 2.0
        assert config.CRAWLER_INFRASTRUCTURE.max_depth == 8
        assert config.CRAWLER_INFRASTRUCTURE.max_pages == 7000
        assert config.CRAWLER_INFRASTRUCTURE.user_agent == "ACESBot/1.1"
        assert config.CRAWLER_INFRASTRUCTURE.robots_cache_hours == 9.0
        assert config.OBSERVABILITY.probes.port == 7070
        assert config.OBSERVABILITY.probes.liveness_path == "/health/live"
        assert config.OBSERVABILITY.probes.readiness_path == "/health/ready"
        assert config.OBSERVABILITY.probes.startup_path == "/health/start"
        assert config.OBSERVABILITY.alert_routes == ("slack", "pagerduty")
        assert config.OBSERVABILITY.slos.availability_target == 99.8
        assert config.OBSERVABILITY.slos.latency_p95_ms == 350.0
        assert config.OBSERVABILITY.slos.error_budget_percent == 1.5
        assert config.POLICY_GUARDS.decision_path == "copilot/allow"
        assert config.POLICY_GUARDS.enforcement_mode == "dry-run"
        assert config.POLICY_GUARDS.cache_seconds == 45
        assert config.PLAN_COMMIT.require_plan is False
        assert config.PLAN_COMMIT.diff_format == "json"
        assert config.PLAN_COMMIT.audit_topic == "audit.plan-commit.test"
        assert config.PLAN_COMMIT.allow_force_commit is True
    finally:
        config.configure()
