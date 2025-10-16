"""Secrets provider abstractions for configuration resolution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, Sequence, runtime_checkable


class SecretsProviderError(RuntimeError):
    """Raised when a provider cannot service a secret request."""


@runtime_checkable
class SecretsProvider(Protocol):
    """Protocol for retrieving named secrets or configuration values."""

    def get(self, name: str) -> str | None:
        """Return the secret identified by *name*, or ``None`` when missing."""


@dataclass
class EnvSecretsProvider:
    """Provider that reads values directly from an environment mapping."""

    environ: dict[str, str]

    def __init__(self, environ: dict[str, str] | None = None) -> None:
        if environ is None:
            import os

            environ = dict(os.environ)
        self.environ = environ

    def get(self, name: str) -> str | None:
        return self.environ.get(name)


@dataclass
class ChainedSecretsProvider:
    """Provider that queries a sequence of providers until one returns a value."""

    providers: Sequence[SecretsProvider]

    def get(self, name: str) -> str | None:
        for provider in self.providers:
            value = provider.get(name)
            if value is not None:
                return value
        return None


class AwsSecretsManagerProvider:
    """Secrets provider backed by AWS Secrets Manager."""

    def __init__(
        self,
        *,
        secret_prefix: str | None = None,
        region_name: str | None = None,
        session: Any | None = None,
    ) -> None:
        try:  # pragma: no cover - optional dependency
            import boto3  # type: ignore[import-not-found]
            from botocore.exceptions import ClientError  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - import-time guard
            raise SecretsProviderError(
                "boto3 is required for AwsSecretsManagerProvider"
            ) from exc

        client_factory: Any = session or boto3
        self._client = client_factory.client("secretsmanager", region_name=region_name)
        self._client_error: Any = ClientError
        self._prefix = secret_prefix.rstrip("/") + "/" if secret_prefix else ""

    def get(self, name: str) -> str | None:
        secret_id = f"{self._prefix}{name}"
        try:
            response = self._client.get_secret_value(SecretId=secret_id)
        except self._client_error as exc:  # pragma: no cover - network path
            error_code = getattr(exc, "response", {}).get("Error", {}).get("Code")
            if error_code in {
                "ResourceNotFoundException",
                "DecryptionFailureException",
            }:
                return None
            raise SecretsProviderError(
                f"Unable to fetch secret '{secret_id}' from AWS Secrets Manager"
            ) from exc

        secret_string = response.get("SecretString")
        if secret_string is not None:
            return secret_string
        binary = response.get("SecretBinary")
        if binary is not None:  # pragma: no cover - binary seldom used in tests
            if isinstance(binary, (bytes, bytearray)):
                return binary.decode()
            return str(binary)
        return None


class AzureKeyVaultProvider:
    """Secrets provider backed by Azure Key Vault."""

    def __init__(
        self,
        *,
        vault_url: str,
        credential: Any | None = None,
        secret_prefix: str | None = None,
    ) -> None:
        try:  # pragma: no cover - optional dependency
            from azure.identity import DefaultAzureCredential  # type: ignore[import-not-found]
            from azure.keyvault.secrets import SecretClient  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - import-time guard
            raise SecretsProviderError(
                "azure-identity and azure-keyvault-secrets are required for AzureKeyVaultProvider"
            ) from exc

        if credential is None:
            credential = DefaultAzureCredential()
        self._client = SecretClient(vault_url=vault_url, credential=credential)
        self._prefix = secret_prefix.rstrip("/") + "/" if secret_prefix else ""

    def get(self, name: str) -> str | None:
        secret_name = f"{self._prefix}{name}"
        try:
            secret = self._client.get_secret(secret_name)
        except Exception as exc:  # pragma: no cover - SDK specific exceptions
            if getattr(exc, "status_code", None) == 404:
                return None
            raise SecretsProviderError(
                f"Unable to fetch secret '{secret_name}' from Azure Key Vault"
            ) from exc
        value = getattr(secret, "value", None)
        return value if value else None


def build_provider_from_environment(
    environ: dict[str, str] | None = None,
) -> SecretsProvider:
    """Create a provider chain from environment hints."""

    env_provider = EnvSecretsProvider(environ)
    backend = (env_provider.get("SECRETS_BACKEND") or "env").strip().lower()

    providers: list[SecretsProvider] = []

    if backend == "aws":
        region = env_provider.get("AWS_REGION") or env_provider.get(
            "AWS_DEFAULT_REGION"
        )
        prefix = env_provider.get("AWS_SECRETS_PREFIX")
        try:
            providers.append(
                AwsSecretsManagerProvider(secret_prefix=prefix, region_name=region)
            )
        except SecretsProviderError:
            # When boto3 is absent locally we continue with env provider only.
            providers.clear()
    elif backend == "azure":
        vault_url = env_provider.get("AZURE_KEY_VAULT_URL")
        if vault_url:
            prefix = env_provider.get("AZURE_SECRETS_PREFIX")
            try:
                providers.append(
                    AzureKeyVaultProvider(vault_url=vault_url, secret_prefix=prefix)
                )
            except SecretsProviderError:
                providers.clear()

    providers.append(env_provider)

    if len(providers) == 1:
        return providers[0]
    return ChainedSecretsProvider(tuple(providers))


__all__ = [
    "AzureKeyVaultProvider",
    "AwsSecretsManagerProvider",
    "ChainedSecretsProvider",
    "EnvSecretsProvider",
    "SecretsProvider",
    "SecretsProviderError",
    "build_provider_from_environment",
]
