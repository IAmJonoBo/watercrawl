import asyncio
from pathlib import Path

import pytest

pytest.importorskip("yaml")

import yaml

from watercrawl.core import config


def _clone_profile(tmp_path: Path, identifier: str) -> Path:
    payload = yaml.safe_load(config.PROFILE_PATH.read_text(encoding="utf-8"))
    payload["id"] = identifier
    payload["name"] = f"Profile {identifier}"
    payload["description"] = "Fixture profile for context tests"
    destination = tmp_path / f"{identifier}.yaml"
    destination.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return destination


def test_profile_context_restores_previous_state(tmp_path: Path) -> None:
    original_id = config.PROFILE.identifier
    profile_path = _clone_profile(tmp_path, "context-restored")

    with config.profile_context(profile_path=profile_path):
        assert config.PROFILE.identifier == "context-restored"
        assert config.PROFILE_PATH == profile_path

    assert config.PROFILE.identifier == original_id


@pytest.mark.asyncio()
async def test_profile_context_isolation_across_tasks(tmp_path: Path) -> None:
    original_id = config.PROFILE.identifier
    first_path = _clone_profile(tmp_path, "context-first")
    second_path = _clone_profile(tmp_path, "context-second")

    async def _use(path: Path, expected: str) -> str:
        with config.profile_context(profile_path=path):
            await asyncio.sleep(0)
            return config.PROFILE.identifier

    first_result, second_result = await asyncio.gather(
        _use(first_path, "context-first"),
        _use(second_path, "context-second"),
    )

    assert first_result == "context-first"
    assert second_result == "context-second"
    assert config.PROFILE.identifier == original_id


def test_switch_profile_updates_default_state(tmp_path: Path) -> None:
    original_path = config.PROFILE_PATH
    profile_path = _clone_profile(tmp_path, "context-switch")
    try:
        config.switch_profile(profile_path=profile_path)
        assert config.PROFILE.identifier == "context-switch"
        assert config.PROFILE_PATH == profile_path
    finally:
        config.switch_profile(profile_path=original_path)
