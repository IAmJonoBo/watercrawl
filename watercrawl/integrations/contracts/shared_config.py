"""Canonical configuration shared across data contract toolchains."""

from __future__ import annotations

import json
import os
from typing import Any, Final

_CANONICAL_CONTRACTS: Final[dict[str, Any]] = {
    "provinces": [
        "Eastern Cape",
        "Free State",
        "Gauteng",
        "KwaZulu-Natal",
        "Limpopo",
        "Mpumalanga",
        "Northern Cape",
        "North West",
        "Western Cape",
        "Unknown",
    ],
    "statuses": [
        "Verified",
        "Candidate",
        "Needs Review",
        "Duplicate",
        "Do Not Contact (Compliance)",
    ],
    "evidence": {
        "minimum_confidence": 70,
        "maximum_confidence": 100,
    },
}

_CANONICAL_ENV_VAR: Final[str] = "CONTRACTS_CANONICAL_JSON"


def canonical_contracts_config() -> dict[str, Any]:
    """Return a copy of the canonical contracts configuration."""

    return json.loads(json.dumps(_CANONICAL_CONTRACTS, sort_keys=True))


def environment_payload() -> dict[str, str]:
    """Serialise the canonical configuration for environment seeding."""

    return {_CANONICAL_ENV_VAR: json.dumps(_CANONICAL_CONTRACTS, sort_keys=True)}


def seed_environment(env: dict[str, str] | None = None) -> dict[str, str | None]:
    """Seed *env* (defaults to :data:`os.environ`) with canonical payload.

    Returns a mapping of previous values so callers can restore overrides
    after running external processes such as dbt.
    """

    target = env if env is not None else os.environ
    previous: dict[str, str | None] = {}
    for key, value in environment_payload().items():
        previous[key] = target.get(key)
        target[key] = value
    return previous


def restore_environment(
    previous: dict[str, str | None], env: dict[str, str] | None = None
) -> None:
    """Restore *env* to a state recorded by :func:`seed_environment`."""

    target = env if env is not None else os.environ
    for key, value in environment_payload().items():
        if key not in previous:
            target.pop(key, None)
            continue
        old = previous[key]
        if old is None:
            target.pop(key, None)
        else:
            target[key] = old
