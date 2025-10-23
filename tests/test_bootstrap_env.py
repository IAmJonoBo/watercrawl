from __future__ import annotations

from pathlib import Path

import pytest

from scripts import bootstrap_env


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


def test_plan_includes_python_and_node(tmp_path: Path) -> None:
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

    assert "Install Poetry environment" in step_descriptions
    assert any("docs-starlight" in step.description for step in plan)


def test_offline_plan_requires_cached_artifacts(tmp_path: Path) -> None:
    with pytest.raises(bootstrap_env.BootstrapError) as excinfo:
        bootstrap_env.build_bootstrap_plan(
            repo_root=tmp_path,
            enable_python=True,
            enable_node=True,
            enable_docs=False,
            offline=True,
        )

    assert "Playwright" in str(excinfo.value)


def test_offline_plan_uses_cached_resources(tmp_path: Path) -> None:
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
    (node_cache / "package-1.0.0.tgz").write_bytes(b"cache")

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
        match="Offline bootstrap requires validated Node package tarballs",
    ):
        bootstrap_env.build_bootstrap_plan(
            repo_root=tmp_path,
            enable_python=False,
            enable_node=True,
            enable_docs=False,
            offline=True,
        )
