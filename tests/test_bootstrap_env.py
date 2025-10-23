from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import bootstrap_env


def _seed_poetry_lock(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch | None = None
) -> None:
    (repo_root / "poetry.lock").write_text("", encoding="utf-8")
    if monkeypatch is not None:
        monkeypatch.setattr(
            bootstrap_env.subprocess,
            "run",
            lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="", stderr=""),
        )


def test_lock_sync_guard_requires_lockfile(tmp_path: Path) -> None:
    with pytest.raises(bootstrap_env.BootstrapError) as excinfo:
        bootstrap_env._ensure_poetry_lock_in_sync(tmp_path)

    assert "Missing 'poetry.lock'" in str(excinfo.value)


def test_lock_sync_guard_passes_when_poetry_check_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "poetry.lock").write_text("", encoding="utf-8")

    def fake_run(*args: object, **kwargs: object) -> SimpleNamespace:
        assert args[0] == ("poetry", "check", "--lock")
        assert kwargs["cwd"] == tmp_path
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(bootstrap_env.subprocess, "run", fake_run)

    # Should not raise.
    bootstrap_env._ensure_poetry_lock_in_sync(tmp_path)


def test_lock_sync_guard_surfaces_poetry_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "poetry.lock").write_text("", encoding="utf-8")

    def fake_run(*args: object, **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(
            returncode=1,
            stdout="lock mismatch",
            stderr="update required",
        )

    monkeypatch.setattr(bootstrap_env.subprocess, "run", fake_run)

    with pytest.raises(bootstrap_env.BootstrapError) as excinfo:
        bootstrap_env._ensure_poetry_lock_in_sync(tmp_path)

    message = str(excinfo.value)
    assert "out of sync" in message
    assert "lock mismatch" in message
    assert "update required" in message


def test_lock_sync_guard_runs_during_plan_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    invoked: list[Path] = []

    def fake_check(path: Path) -> None:
        invoked.append(path)

    monkeypatch.setattr(bootstrap_env, "_ensure_poetry_lock_in_sync", fake_check)

    bootstrap_env.build_bootstrap_plan(
        repo_root=tmp_path,
        enable_python=True,
        enable_node=False,
        enable_docs=False,
        offline=False,
    )

    assert invoked == [tmp_path]


def test_discover_node_projects(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("{}\n", encoding="utf-8")
    docs_dir = tmp_path / "docs-starlight"
    docs_dir.mkdir()
    (docs_dir / "package.json").write_text("{}\n", encoding="utf-8")
    (docs_dir / "package-lock.json").write_text("{}\n", encoding="utf-8")

    projects = bootstrap_env.discover_node_projects(tmp_path)

    assert [p.relative_to(tmp_path) for p in projects] == [
        Path("package.json").parent,
        Path("docs-starlight"),
    ]


def test_build_node_command_prefers_ci_with_lock(tmp_path: Path) -> None:
    project = tmp_path / "docs"
    project.mkdir()
    (project / "package.json").write_text("{}\n", encoding="utf-8")
    (project / "package-lock.json").write_text("{}\n", encoding="utf-8")

    command = bootstrap_env.build_node_install_command(project)

    assert command == ("npm", "ci")


@pytest.mark.parametrize(
    "lock_file,expected",
    [
        ("pnpm-lock.yaml", ("pnpm", "install", "--frozen-lockfile")),
        ("yarn.lock", ("yarn", "install", "--frozen-lockfile")),
        (None, ("npm", "install")),
    ],
)
def test_build_node_command_variants(
    tmp_path: Path, lock_file: str | None, expected: tuple[str, ...]
) -> None:
    project = tmp_path / "web"
    project.mkdir()
    (project / "package.json").write_text("{}\n", encoding="utf-8")
    if lock_file:
        (project / lock_file).write_text("lock\n", encoding="utf-8")

    command = bootstrap_env.build_node_install_command(project)

    assert command == expected


def test_plan_includes_python_and_node(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_poetry_lock(tmp_path, monkeypatch)
    (tmp_path / "package.json").write_text("{}\n", encoding="utf-8")
    docs_dir = tmp_path / "docs-starlight"
    docs_dir.mkdir()
    (docs_dir / "package.json").write_text("{}\n", encoding="utf-8")

    plan = bootstrap_env.build_bootstrap_plan(
        repo_root=tmp_path,
        enable_python=True,
        enable_node=True,
        enable_docs=True,
        offline=False,
    )

    step_descriptions = [step.description for step in plan]

    assert any(
        "Install Poetry environment" in description for description in step_descriptions
    )
    assert any("docs-starlight" in step.description for step in plan)


def test_offline_plan_requires_cached_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_poetry_lock(tmp_path, monkeypatch)
    with pytest.raises(bootstrap_env.BootstrapError) as excinfo:
        bootstrap_env.build_bootstrap_plan(
            repo_root=tmp_path,
            enable_python=True,
            enable_node=True,
            enable_docs=False,
            offline=True,
        )

    message = str(excinfo.value)
    assert "pip wheel cache" in message
    assert "Playwright" in message
    assert "tldextract" in message
    assert "Node.js tarball" in message


def test_offline_plan_uses_cached_resources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_poetry_lock(tmp_path, monkeypatch)
    (tmp_path / "package.json").write_text("{}\n", encoding="utf-8")
    docs_dir = tmp_path / "docs-starlight"
    docs_dir.mkdir()
    (docs_dir / "package.json").write_text("{}\n", encoding="utf-8")
    (docs_dir / "pnpm-lock.yaml").write_text("{}\n", encoding="utf-8")

    playwright_cache = tmp_path / "artifacts" / "cache" / "playwright"
    for browser in bootstrap_env.PLAYWRIGHT_BROWSERS:
        (playwright_cache / f"{browser}-123").mkdir(parents=True, exist_ok=True)

    tld_cache = (
        tmp_path / "artifacts" / "cache" / "tldextract" / "publicsuffix.org-tlds"
    )
    tld_cache.mkdir(parents=True, exist_ok=True)
    (tld_cache / "snapshot.tldextract.json").write_text("{}", encoding="utf-8")

    node_cache = tmp_path / "artifacts" / "cache" / "node"
    node_cache.mkdir(parents=True, exist_ok=True)
    tarball = node_cache / "node-v20.0.0-linux-x64.tar.gz"
    tarball.write_bytes(b"cache")
    checksum = hashlib.sha256(b"cache").hexdigest()
    (node_cache / "SHASUMS256.txt").write_text(
        f"{checksum}  {tarball.name}\n", encoding="utf-8"
    )

    pip_cache = tmp_path / "artifacts" / "cache" / "pip"
    pip_cache.mkdir(parents=True, exist_ok=True)
    (pip_cache / "mirror_state.json").write_text("{}\n", encoding="utf-8")

    plan = bootstrap_env.build_bootstrap_plan(
        repo_root=tmp_path,
        enable_python=True,
        enable_node=True,
        enable_docs=True,
        offline=True,
    )

    commands = [step.command for step in plan]

    assert ("uv", "venv", str(tmp_path / ".venv")) in commands
    assert any(cmd[:3] == ("uv", "pip", "sync") for cmd in commands)
    assert not any("playwright" in " ".join(cmd) for cmd in commands)
    assert any(cmd[0] in {"pnpm", "npm", "yarn"} for cmd in commands)


def test_collect_cache_status_respects_optional_node(tmp_path: Path) -> None:
    pip_cache = tmp_path / "artifacts" / "cache" / "pip"
    pip_cache.mkdir(parents=True, exist_ok=True)
    (pip_cache / "mirror_state.json").write_text("{}\n", encoding="utf-8")

    playwright_cache = tmp_path / "artifacts" / "cache" / "playwright"
    for browser in bootstrap_env.PLAYWRIGHT_BROWSERS:
        (playwright_cache / f"{browser}-seed").mkdir(parents=True, exist_ok=True)

    suffix_cache = (
        tmp_path / "artifacts" / "cache" / "tldextract" / "publicsuffix.org-tlds"
    )
    suffix_cache.mkdir(parents=True, exist_ok=True)
    (suffix_cache / "seed.tldextract.json").write_text("{}", encoding="utf-8")

    status = bootstrap_env._collect_cache_status(
        tmp_path, require_python=True, require_node=False
    )

    assert status["missing"] == []


def test_preflight_report_writes_plan_artifact(tmp_path: Path) -> None:
    pip_cache = tmp_path / "artifacts" / "cache" / "pip"
    pip_cache.mkdir(parents=True, exist_ok=True)
    (pip_cache / "mirror_state.json").write_text("{}\n", encoding="utf-8")

    playwright_cache = tmp_path / "artifacts" / "cache" / "playwright"
    for browser in bootstrap_env.PLAYWRIGHT_BROWSERS:
        (playwright_cache / f"{browser}-seed").mkdir(parents=True, exist_ok=True)

    suffix_cache = (
        tmp_path / "artifacts" / "cache" / "tldextract" / "publicsuffix.org-tlds"
    )
    suffix_cache.mkdir(parents=True, exist_ok=True)
    (suffix_cache / "seed.tldextract.json").write_text("{}", encoding="utf-8")

    report = bootstrap_env._build_preflight_report(
        repo_root=tmp_path,
        offline=True,
        error=None,
        require_python=True,
        require_node=False,
    )

    assert report["status"] == "pass"
    assert report["missing_caches"] == []
    assert "report_path" in report
    report_path = tmp_path / report["report_path"]
    assert report_path.exists()
    saved = json.loads(report_path.read_text(encoding="utf-8"))
    assert saved["offline"] is True


def test_validate_node_tarball_checksum_success(tmp_path: Path) -> None:
    """Test checksum validation succeeds with valid tarball and checksum."""
    tarball_path = tmp_path / "node-v20.0.0-linux-x64.tar.gz"
    checksum_path = tmp_path / "SHASUMS256.txt"

    # Create a dummy tarball
    tarball_path.write_bytes(b"fake tarball content")

    # Calculate the actual checksum
    import hashlib

    sha256 = hashlib.sha256(b"fake tarball content")
    expected_checksum = sha256.hexdigest()

    # Create checksum file
    checksum_path.write_text(
        f"{expected_checksum}  node-v20.0.0-linux-x64.tar.gz\n",
        encoding="utf-8",
    )

    result = bootstrap_env._validate_node_tarball_checksum(tarball_path)
    assert result is True


def test_validate_node_tarball_checksum_failure(tmp_path: Path) -> None:
    """Test checksum validation fails with mismatched checksum."""
    tarball_path = tmp_path / "node-v20.0.0-linux-x64.tar.gz"
    checksum_path = tmp_path / "SHASUMS256.txt"

    tarball_path.write_bytes(b"fake tarball content")

    # Create checksum file with wrong checksum
    checksum_path.write_text(
        "deadbeef00000000000000000000000000000000000000000000000000000000  node-v20.0.0-linux-x64.tar.gz\n",
        encoding="utf-8",
    )

    result = bootstrap_env._validate_node_tarball_checksum(tarball_path)
    assert result is False


def test_validate_node_tarball_checksum_missing_file(tmp_path: Path) -> None:
    """Test checksum validation fails when SHASUMS256.txt is missing."""
    tarball_path = tmp_path / "node-v20.0.0-linux-x64.tar.gz"
    tarball_path.write_bytes(b"fake tarball content")

    result = bootstrap_env._validate_node_tarball_checksum(tarball_path)
    assert result is False


def test_validate_node_tarball_cache_with_valid_tarball(tmp_path: Path) -> None:
    """Test cache validation succeeds when tarball and checksum are valid."""
    cache_dir = tmp_path / "artifacts" / "cache" / "node"
    cache_dir.mkdir(parents=True)

    tarball_path = cache_dir / "node-v20.0.0-linux-x64.tar.gz"
    checksum_path = cache_dir / "SHASUMS256.txt"

    tarball_path.write_bytes(b"fake tarball content")

    import hashlib

    sha256 = hashlib.sha256(b"fake tarball content")
    expected_checksum = sha256.hexdigest()

    checksum_path.write_text(
        f"{expected_checksum}  node-v20.0.0-linux-x64.tar.gz\n",
        encoding="utf-8",
    )

    result = bootstrap_env._validate_node_tarball_cache(tmp_path)
    assert result is True


def test_validate_node_tarball_cache_missing_directory(tmp_path: Path) -> None:
    """Test cache validation fails when cache directory doesn't exist."""
    result = bootstrap_env._validate_node_tarball_cache(tmp_path)
    assert result is False


def test_validate_node_tarball_cache_no_tarballs(tmp_path: Path) -> None:
    """Test cache validation fails when no tarballs are found."""
    cache_dir = tmp_path / "artifacts" / "cache" / "node"
    cache_dir.mkdir(parents=True)

    result = bootstrap_env._validate_node_tarball_cache(tmp_path)
    assert result is False


def test_offline_bootstrap_requires_validated_cache(tmp_path: Path) -> None:
    """Test offline bootstrap raises error when Node cache validation fails."""
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")

    with pytest.raises(
        bootstrap_env.BootstrapError,
        match=r"Node\.js tarball cache missing or unverified",
    ):
        bootstrap_env.build_bootstrap_plan(
            repo_root=tmp_path,
            enable_python=False,
            enable_node=True,
            enable_docs=False,
            offline=True,
        )


def _seed_offline_caches(repo_root: Path) -> None:
    pip_cache = repo_root / "artifacts" / "cache" / "pip"
    pip_cache.mkdir(parents=True, exist_ok=True)
    (pip_cache / "sample-0.0.0-py3-none-any.whl").write_bytes(b"wheel")

    playwright_cache = repo_root / "artifacts" / "cache" / "playwright"
    for browser in bootstrap_env.PLAYWRIGHT_BROWSERS:
        (playwright_cache / f"{browser}-cached").mkdir(parents=True, exist_ok=True)

    suffix_cache = (
        repo_root / "artifacts" / "cache" / "tldextract" / "publicsuffix.org-tlds"
    )
    suffix_cache.mkdir(parents=True, exist_ok=True)
    (suffix_cache / "snapshot.tldextract.json").write_text("{}", encoding="utf-8")

    cache_dir = repo_root / "artifacts" / "cache" / bootstrap_env.NODE_CACHE_DIRNAME
    cache_dir.mkdir(parents=True, exist_ok=True)
    tarball = cache_dir / "node-v20.0.0-linux-x64.tar.gz"
    tarball.write_bytes(b"node")
    checksum = cache_dir / "SHASUMS256.txt"

    import hashlib

    digest = hashlib.sha256(b"node").hexdigest()
    checksum.write_text(
        f"{digest}  node-v20.0.0-linux-x64.tar.gz\n",
        encoding="utf-8",
    )


def test_dry_run_preflight_reports_success(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dry-run preflight emits JSON and writes a chaos artefact when caches are ready."""

    _seed_poetry_lock(tmp_path, monkeypatch)
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    _seed_offline_caches(tmp_path)
    pip_cache = tmp_path / "artifacts" / "cache" / "pip"
    monkeypatch.setenv("UV_CACHE_DIR", str(pip_cache))

    exit_code = bootstrap_env.main(
        ["--repo-root", str(tmp_path), "--offline", "--dry-run"]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out.strip().splitlines()[-1])

    assert exit_code == 0
    assert payload["status"] == "pass"
    assert payload["missing_caches"] == []
    assert payload["offline"] is True
    artefact_path = tmp_path / payload["report_path"]
    assert artefact_path.exists()


def test_dry_run_preflight_reports_missing_cache(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dry-run preflight fails fast and records missing caches when offline requirements are absent."""

    _seed_poetry_lock(tmp_path, monkeypatch)
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("UV_CACHE_DIR", str(tmp_path / "artifacts" / "cache" / "pip"))

    exit_code = bootstrap_env.main(
        ["--repo-root", str(tmp_path), "--offline", "--dry-run"]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out.strip().splitlines()[-1])

    assert exit_code == 1
    assert payload["status"] == "fail"
    assert "playwright" in payload["missing_caches"]
    assert "pip_cache" in payload["missing_caches"]
    artefact_path = tmp_path / payload["report_path"]
    assert artefact_path.exists()
