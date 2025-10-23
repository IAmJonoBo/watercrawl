from __future__ import annotations

from pathlib import Path

import certifi
import pytest

from scripts import provision_wheelhouse as wheelhouse


class DummyResult:
    def __init__(
        self, *, returncode: int = 0, stdout: str = "", stderr: str = ""
    ) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_ensure_export_plugin_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the plugin is already installed we avoid running `poetry self add`."""

    def fake_subprocess_run(*_args, **_kwargs) -> DummyResult:
        return DummyResult(stdout=f"some\n{wheelhouse.EXPORT_PLUGIN}\nlist")

    monkeypatch.setattr(wheelhouse.subprocess, "run", fake_subprocess_run)

    invoked = False

    def fail_run(*_args, **_kwargs) -> None:  # pragma: no cover - safety
        nonlocal invoked
        invoked = True

    monkeypatch.setattr(wheelhouse, "run", fail_run)

    wheelhouse.ensure_export_plugin()
    assert not invoked


def test_ensure_export_plugin_installs_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []

    def fake_subprocess_run(*_args, **_kwargs) -> DummyResult:
        return DummyResult(stdout="other-plugin")

    def record_run(cmd: list[str], *, env: dict[str, str] | None = None) -> None:
        commands.append(cmd)

    monkeypatch.setattr(wheelhouse.subprocess, "run", fake_subprocess_run)
    monkeypatch.setattr(wheelhouse, "run", record_run)

    wheelhouse.ensure_export_plugin()
    assert commands == [["poetry", "self", "add", wheelhouse.EXPORT_PLUGIN]]


def test_export_requirements_filters_blockers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    req_file = tmp_path / "reqs.txt"
    monkeypatch.setattr(wheelhouse, "REQUIREMENTS_FILE", req_file)
    monkeypatch.setattr(wheelhouse, "ensure_export_plugin", lambda: None)

    def fake_run(cmd: list[str], *, env: dict[str, str] | None = None) -> None:
        req_file.write_text("duckdb==1.0.0\nrequests==2.0.0\n")

    monkeypatch.setattr(wheelhouse, "run", fake_run)

    wheelhouse.export_requirements(include_dev=False, blocker_names={"duckdb"})

    assert req_file.read_text().strip().splitlines() == ["requests==2.0.0"]


def test_download_wheels_sets_cert_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: dict[str, str] = {}

    def capture(cmd: list[str], *, env: dict[str, str] | None = None) -> None:
        assert env is not None
        recorded.update(env)
        assert cmd[0:4] == [wheelhouse.sys.executable, "-m", "pip", "download"]

    monkeypatch.setattr(wheelhouse, "run", capture)
    for var in ("PIP_CERT", "REQUESTS_CA_BUNDLE", "SSL_CERT_FILE"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(wheelhouse.certifi, "where", lambda: "/tmp/cert.pem")

    wheelhouse.download_wheels(Path("/tmp/out"), "3.13")

    assert recorded["PIP_CERT"] == "/tmp/cert.pem"
    assert recorded["REQUESTS_CA_BUNDLE"] == "/tmp/cert.pem"
    assert recorded["SSL_CERT_FILE"] == "/tmp/cert.pem"


def test_download_wheels_defaults_to_certifi(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def capture_env(cmd: list[str], *, env: dict[str, str] | None = None) -> None:
        captured.update(env or {})

    monkeypatch.setattr(wheelhouse, "run", capture_env)
    for var in ("PIP_CERT", "REQUESTS_CA_BUNDLE", "SSL_CERT_FILE"):
        monkeypatch.delenv(var, raising=False)

    wheelhouse.download_wheels(Path("/tmp/out"), "3.13")

    ca_path = certifi.where()
    assert captured["PIP_CERT"] == ca_path
    assert captured["REQUESTS_CA_BUNDLE"] == ca_path
    assert captured["SSL_CERT_FILE"] == ca_path


def test_download_wheels_merges_existing_ca(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    existing = tmp_path / "existing.pem"
    existing.write_text("EXISTING\n")
    cert_path = tmp_path / "certifi.pem"
    cert_path.write_text("CERTIFI\n")

    created: list[str] = []
    contents: list[str] = []

    def capture_env(cmd: list[str], *, env: dict[str, str] | None = None) -> None:
        assert env is not None
        created.append(env["PIP_CERT"])
        contents.append(Path(env["PIP_CERT"]).read_text())

    monkeypatch.setattr(wheelhouse, "run", capture_env)
    monkeypatch.setattr(wheelhouse.certifi, "where", lambda: str(cert_path))
    monkeypatch.setenv("SSL_CERT_FILE", str(existing))
    monkeypatch.delenv("PIP_CERT", raising=False)
    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)

    wheelhouse.download_wheels(Path("/tmp/out"), "3.13")

    assert created, "Expected pip to run"
    bundle_path = Path(created[0])
    assert str(bundle_path) != str(existing)
    assert str(bundle_path) != str(cert_path)
    assert "EXISTING" in contents[0] and "CERTIFI" in contents[0]
    assert not bundle_path.exists()
