from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from os import environ
from pathlib import Path
from typing import Any

PLAYWRIGHT_BROWSERS: tuple[str, ...] = ("chromium", "firefox", "webkit")
NODE_CACHE_DIRNAME = "node"


class BootstrapError(RuntimeError):
    """Raised when one of the bootstrap steps fails."""


@dataclass(frozen=True)
class BootstrapStep:
    """Represents an executable step in the environment bootstrap plan."""

    description: str
    command: tuple[str, ...]
    cwd: Path | None = None
    env: dict[str, str] | None = None

    def render(self) -> str:
        location = f" (cwd: {self.cwd})" if self.cwd else ""
        cmd = " ".join(self.command)
        suffix = ""
        if self.env:
            exports = " ".join(f"{key}={value}" for key, value in self.env.items())
            suffix = f" (env: {exports})"
        return f"{self.description}{location}: $ {cmd}{suffix}"


def _ensure_poetry_lock_in_sync(repo_root: Path) -> None:
    """Raise an error when the Poetry lockfile is missing or out of sync."""

    lock_path = repo_root / "poetry.lock"
    if not lock_path.exists():
        raise BootstrapError(
            "Missing 'poetry.lock'. Run 'poetry lock' (or 'poetry lock --no-update' on "
            "older Poetry releases) to generate it before bootstrapping."
        )

    try:
        result = subprocess.run(
            ("poetry", "check", "--lock"),
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:  # pragma: no cover - defensive guard
        raise BootstrapError(
            "Poetry CLI is required to validate the lockfile but was not found in PATH. "
            "Install Poetry and retry the bootstrap command."
        ) from exc

    if result.returncode == 0:
        return

    details = "\n".join(
        part for part in (result.stdout.strip(), result.stderr.strip()) if part
    )
    message = (
        "'pyproject.toml' and 'poetry.lock' are out of sync. Regenerate the lockfile "
        "with 'poetry lock' (or 'poetry lock --no-update' when supported) and commit "
        "the changes before rerunning the bootstrap command."
    )
    if details:
        message = f"{message}\nPoetry output:\n{details}"
    raise BootstrapError(message)


def discover_node_projects(repo_root: Path) -> list[Path]:
    """Return known Node.js project directories within the repository."""

    candidates = [repo_root, repo_root / "docs-starlight"]
    projects: list[Path] = []
    for candidate in candidates:
        if (candidate / "package.json").exists():
            projects.append(candidate)
    projects.sort(key=lambda path: path.relative_to(repo_root).as_posix())
    return projects


def build_node_install_command(project_dir: Path) -> tuple[str, ...]:
    """Build the install command for a Node.js project based on its lock file."""

    if (project_dir / "package-lock.json").exists():
        return ("npm", "ci")
    if (project_dir / "pnpm-lock.yaml").exists():
        return ("pnpm", "install", "--frozen-lockfile")
    if (project_dir / "yarn.lock").exists():
        return ("yarn", "install", "--frozen-lockfile")
    return ("npm", "install")


def build_bootstrap_plan(
    *,
    repo_root: Path,
    enable_python: bool,
    enable_node: bool,
    enable_docs: bool,
    offline: bool,
) -> list[BootstrapStep]:
    """Assemble the ordered bootstrap steps for the repository."""

    if enable_python:
        _ensure_poetry_lock_in_sync(repo_root)

    if offline:
        _ensure_offline_caches(
            repo_root,
            require_python=enable_python,
            require_node=enable_node,
        )

    steps: list[BootstrapStep] = []

    if enable_python:
        steps.append(
            BootstrapStep(
                description="Provision Python toolchain with uv",
                command=(
                    sys.executable,
                    "-m",
                    "scripts.bootstrap_python",
                    "--install-uv",
                    "--poetry",
                ),
            )
        )
        if offline:
            steps.append(
                BootstrapStep(
                    description="Create project virtualenv with uv",
                    command=(
                        "uv",
                        "venv",
                        str(repo_root / ".venv"),
                    ),
                )
            )
            steps.append(
                BootstrapStep(
                    description="Sync Python dependencies with uv (requirements-dev)",
                    command=(
                        "uv",
                        "pip",
                        "sync",
                        "--python",
                        str(repo_root / ".venv"),
                        str(repo_root / "requirements-dev.txt"),
                    ),
                )
            )
            steps.append(
                BootstrapStep(
                    description="Sync runtime Python dependencies with uv",
                    command=(
                        "uv",
                        "pip",
                        "sync",
                        "--python",
                        str(repo_root / ".venv"),
                        str(repo_root / "requirements.txt"),
                    ),
                )
            )
        else:
            steps.append(
                BootstrapStep(
                    description="Install Poetry environment (with dev dependencies)",
                    command=(
                        "poetry",
                        "install",
                        "--no-root",
                        "--with",
                        "dev",
                        "--sync",
                    ),
                    env={"PYO3_USE_ABI3_FORWARD_COMPATIBILITY": "1"},
                )
            )
        steps.append(
            BootstrapStep(
                description="Verify Poetry dependency graph",
                command=("poetry", "check"),
            )
        )
        steps.append(
            BootstrapStep(
                description="Install pre-commit hooks",
                command=("poetry", "run", "pre-commit", "install"),
            )
        )
        steps.append(
            BootstrapStep(
                description="Verify vendored type stubs",
                command=("poetry", "run", "python", "-m", "scripts.sync_type_stubs"),
            )
        )
        steps.extend(_build_artifact_cache_steps(repo_root, offline=offline))

    if enable_node:
        root_package = repo_root / "package.json"
        if root_package.exists():
            steps.append(
                BootstrapStep(
                    description="Install Node.js tooling for repository root",
                    command=build_node_install_command(repo_root),
                    cwd=repo_root,
                )
            )

    if enable_docs:
        docs_project = repo_root / "docs-starlight"
        if (docs_project / "package.json").exists():
            steps.append(
                BootstrapStep(
                    description="Install docs-starlight dependencies",
                    command=build_node_install_command(docs_project),
                    cwd=docs_project,
                )
            )

    return steps


def _build_artifact_cache_steps(
    repo_root: Path, *, offline: bool
) -> list[BootstrapStep]:
    """Return bootstrap steps that seed heavyweight runtime caches."""

    steps: list[BootstrapStep] = []
    steps.extend(_playwright_cache_steps(repo_root, offline=offline))
    steps.extend(_tldextract_cache_steps(repo_root, offline=offline))
    return steps


def _playwright_cache_steps(repo_root: Path, *, offline: bool) -> list[BootstrapStep]:
    """Pre-download Playwright browsers when they are not already cached."""

    cache_dir = repo_root / "artifacts" / "cache" / "playwright"
    missing = [
        browser
        for browser in PLAYWRIGHT_BROWSERS
        if not _playwright_browser_cached(cache_dir, browser)
    ]
    if not missing:
        return []
    if offline:
        raise BootstrapError(
            "Offline bootstrap requires cached Playwright archives under 'artifacts/cache/playwright'. "
            f"Missing browsers: {', '.join(sorted(missing))}."
        )
    return [
        BootstrapStep(
            description="Seed Playwright browser cache (chromium/firefox/webkit)",
            command=("poetry", "run", "playwright", "install", *PLAYWRIGHT_BROWSERS),
            env={"PLAYWRIGHT_BROWSERS_PATH": str(cache_dir)},
        )
    ]


def _playwright_browser_cached(cache_dir: Path, browser: str) -> bool:
    """Return True if the requested browser artifact is already cached."""

    search_roots = [cache_dir, cache_dir / "ms-playwright"]
    pattern = f"{browser}-*"
    for root in search_roots:
        if not root.exists():
            continue
        if any(root.glob(pattern)):
            return True
    return False


def _tldextract_cache_steps(repo_root: Path, *, offline: bool) -> list[BootstrapStep]:
    """Create steps that pre-populate the public suffix cache for offline runs."""

    cache_dir = repo_root / "artifacts" / "cache" / "tldextract"
    has_cache = cache_dir.exists() and any(
        cache_dir.glob("publicsuffix.org-tlds/*.tldextract.json")
    )
    if has_cache:
        return []
    if offline:
        raise BootstrapError(
            "Offline bootstrap requires a pre-seeded tldextract cache under 'artifacts/cache/tldextract'."
        )

    script = (
        "from pathlib import Path; import tldextract; "
        f'cache = Path(r"{cache_dir.as_posix()}"); '
        "cache.mkdir(parents=True, exist_ok=True); "
        "tldextract.TLDExtract(cache_dir=str(cache), suffix_list_urls=())('example.com')"
    )

    return [
        BootstrapStep(
            description="Seed tldextract public suffix cache",
            command=("poetry", "run", "python", "-c", script),
        )
    ]


def _validate_node_tarball_checksum(tarball_path: Path) -> bool:
    """Validate the checksum of a Node.js tarball against SHASUMS256.txt.

    Returns True if checksum is valid, False otherwise.
    """
    import hashlib

    checksum_file = tarball_path.parent / "SHASUMS256.txt"
    if not checksum_file.exists():
        return False

    # Find expected checksum
    checksum_text = checksum_file.read_text(encoding="utf-8")
    tarball_name = tarball_path.name
    expected_checksum = None
    for line in checksum_text.splitlines():
        if tarball_name in line:
            parts = line.strip().split()
            if len(parts) >= 2:
                expected_checksum = parts[0]
                break

    if not expected_checksum:
        return False

    # Calculate actual checksum
    sha256 = hashlib.sha256()
    with tarball_path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            sha256.update(chunk)
    actual_checksum = sha256.hexdigest()

    return actual_checksum == expected_checksum


def _has_node_tarball_cache(repo_root: Path) -> bool:
    """Return True when a local Node package tarball cache is available."""

    cache_root = repo_root / "artifacts" / "cache" / NODE_CACHE_DIRNAME
    if not cache_root.exists():
        return False
    for suffixes in (".tgz", ".tar", ".tar.gz", ".tar.xz"):
        if any(cache_root.rglob(f"*{suffixes}")):
            return True
    return False


def _validate_node_tarball_cache(repo_root: Path) -> bool:
    """Return True when cached Node tarballs exist and pass checksum validation."""
    cache_root = repo_root / "artifacts" / "cache" / NODE_CACHE_DIRNAME
    if not cache_root.exists():
        return False

    # Find Node.js tarballs
    tarballs: list[Path] = []
    for suffix in (".tgz", ".tar.gz", ".tar.xz"):
        tarballs.extend(cache_root.glob(f"node-*{suffix}"))

    if not tarballs:
        return False

    # Validate at least one tarball
    for tarball in tarballs:
        if _validate_node_tarball_checksum(tarball):
            return True

    return False


def execute_plan(steps: Iterable[BootstrapStep], *, dry_run: bool) -> None:
    """Execute each bootstrap step sequentially."""

    for step in steps:
        print(step.render())
        if dry_run:
            continue
        env = environ.copy()
        if step.env:
            env.update(step.env)
        result = subprocess.run(step.command, cwd=step.cwd, check=False, env=env)
        if result.returncode != 0:
            raise BootstrapError(
                f"Step '{step.description}' failed with exit code {result.returncode}."
            )


def _resolve_pip_cache_dir(repo_root: Path) -> Path:
    """Determine the pip cache directory that should be validated."""

    uv_cache_dir = environ.get("UV_CACHE_DIR")
    if not uv_cache_dir:
        return repo_root / "artifacts" / "cache" / "pip"
    candidate = Path(uv_cache_dir)
    if candidate.is_absolute():
        return candidate
    return (repo_root / candidate).resolve()


def _pip_cache_status(cache_dir: Path) -> dict[str, Any]:
    """Return readiness information for the pip wheel cache."""

    exists = cache_dir.exists()
    mirror_state = (cache_dir / "mirror_state.json").exists() if exists else False
    wheel_sample = None
    if exists:
        wheel_sample = next(cache_dir.rglob("*.whl"), None)
    ready = exists and (mirror_state or wheel_sample is not None)
    status: dict[str, Any] = {
        "path": str(cache_dir),
        "ready": ready,
        "mirror_state": mirror_state,
    }
    if wheel_sample is not None:
        status["sample_wheel"] = wheel_sample.name
    return status


def _collect_cache_status(
    repo_root: Path, *, require_python: bool, require_node: bool
) -> dict[str, Any]:
    """Inspect offline caches and return readiness metadata."""

    pip_cache_dir = _resolve_pip_cache_dir(repo_root)
    pip_status = _pip_cache_status(pip_cache_dir)

    playwright_cache_dir = repo_root / "artifacts" / "cache" / "playwright"
    playwright_missing = [
        browser
        for browser in PLAYWRIGHT_BROWSERS
        if not _playwright_browser_cached(playwright_cache_dir, browser)
    ]
    playwright_status: dict[str, Any] = {
        "path": str(playwright_cache_dir),
        "ready": not playwright_missing,
    }
    if playwright_missing:
        playwright_status["missing_browsers"] = sorted(playwright_missing)

    suffix_cache_root = repo_root / "artifacts" / "cache" / "tldextract"
    suffix_cache_dir = suffix_cache_root / "publicsuffix.org-tlds"
    suffix_ready = suffix_cache_dir.exists() and any(
        suffix_cache_dir.glob("*.tldextract.json")
    )
    tld_status = {
        "path": str(suffix_cache_dir),
        "ready": suffix_ready,
    }

    node_ready = _validate_node_tarball_cache(repo_root)
    node_status = {
        "path": str(repo_root / "artifacts" / "cache" / NODE_CACHE_DIRNAME),
        "ready": node_ready,
        "has_tarballs": _has_node_tarball_cache(repo_root),
    }

    missing: list[str] = []
    if require_python and not pip_status["ready"]:
        missing.append("pip_cache")
    if require_python and not playwright_status["ready"]:
        missing.append("playwright")
    if require_python and not tld_status["ready"]:
        missing.append("tldextract")
    if require_node and not node_status["ready"]:
        missing.append("node_tarballs")

    return {
        "details": {
            "pip": pip_status,
            "playwright": playwright_status,
            "tldextract": tld_status,
            "node": node_status,
        },
        "missing": missing,
    }


def _ensure_offline_caches(
    repo_root: Path, *, require_python: bool, require_node: bool
) -> None:
    """Raise an error when required offline caches are not present."""

    cache_status = _collect_cache_status(
        repo_root, require_python=require_python, require_node=require_node
    )
    if not cache_status["missing"]:
        return

    details = cache_status["details"]
    messages: list[str] = []

    if "pip_cache" in cache_status["missing"]:
        pip_path = details["pip"]["path"]
        messages.append(
            "pip wheel cache not primed at "
            f"{pip_path}. Seed the cache via "
            "'python -m scripts.download_wheelhouse_artifact --seed-pip-cache' "
            "or rerun bootstrap without --offline to populate wheels."
        )
    if "playwright" in cache_status["missing"]:
        playwright_path = details["playwright"]["path"]
        missing_browsers = details["playwright"].get("missing_browsers")
        browser_hint = (
            f" Missing archives: {', '.join(missing_browsers)}." if missing_browsers else ""
        )
        messages.append(
            "Playwright browser cache missing under "
            f"{playwright_path}.{browser_hint} Seed with "
            "'poetry run playwright install --with-deps' before re-running in offline mode."
        )
    if "tldextract" in cache_status["missing"]:
        tld_path = details["tldextract"]["path"]
        messages.append(
            "tldextract suffix cache not found at "
            f"{tld_path}. Run 'python -m scripts.bootstrap_env --dry-run' "
            "without --offline or execute the seeding helper documented in "
            "docs/ephemeral-qa-guide.md to prime the cache."
        )
    if "node_tarballs" in cache_status["missing"]:
        node_path = details["node"]["path"]
        messages.append(
            "Node.js tarball cache missing or unverified at "
            f"{node_path}. Run 'python -m scripts.stage_node_tarball' to "
            "download and validate tarballs for offline bootstrap."
        )

    raise BootstrapError(
        "Offline bootstrap requires pre-seeded caches before running with --offline:\n- "
        + "\n- ".join(messages)
    )


def _write_preflight_report(
    repo_root: Path, report: dict[str, Any], recorded_at: datetime
) -> Path:
    """Persist the preflight report under the chaos artefacts directory."""

    chaos_dir = repo_root / "artifacts" / "chaos" / "preflight"
    chaos_dir.mkdir(parents=True, exist_ok=True)
    filename = f"preflight_{recorded_at.strftime('%Y%m%dT%H%M%SZ')}.json"
    report_path = chaos_dir / filename
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report_path.relative_to(repo_root)


def _build_preflight_report(
    *,
    repo_root: Path,
    offline: bool,
    error: str | None,
    require_python: bool,
    require_node: bool,
) -> dict[str, Any]:
    """Compose the structured JSON payload describing cache readiness."""

    cache_status = _collect_cache_status(
        repo_root, require_python=require_python, require_node=require_node
    )
    recorded_at = datetime.now(UTC)
    status = "pass" if not cache_status["missing"] and error is None else "fail"
    report: dict[str, Any] = {
        "status": status,
        "offline": offline,
        "recorded_at": recorded_at.isoformat(),
        "missing_caches": cache_status["missing"],
        "details": cache_status["details"],
    }
    if error:
        report["error"] = error
    relative_path = _write_preflight_report(repo_root, report, recorded_at)
    report["report_path"] = relative_path.as_posix()
    return report


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bootstrap the Python and Node.js tooling for the repository.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root (defaults to the current working directory).",
    )
    parser.add_argument(
        "--no-python",
        action="store_false",
        dest="enable_python",
        help="Skip Python environment provisioning.",
    )
    parser.add_argument(
        "--no-node",
        action="store_false",
        dest="enable_node",
        help="Skip root Node.js tooling installation.",
    )
    parser.add_argument(
        "--no-docs",
        action="store_false",
        dest="enable_docs",
        help="Skip docs-starlight Node.js dependency installation.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the plan without executing commands.",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Use pre-seeded caches and avoid network downloads.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    plan: list[BootstrapStep] | None = None
    error_message: str | None = None
    try:
        plan = build_bootstrap_plan(
            repo_root=args.repo_root,
            enable_python=args.enable_python,
            enable_node=args.enable_node,
            enable_docs=args.enable_docs,
            offline=args.offline,
        )
    except BootstrapError as exc:
        if args.dry_run:
            error_message = str(exc)
        else:
            print(str(exc), file=sys.stderr)
            return 1
    else:
        try:
            execute_plan(plan, dry_run=args.dry_run)
        except BootstrapError as exc:  # pragma: no cover - CLI error handling
            if args.dry_run:
                error_message = str(exc)
            else:
                print(str(exc), file=sys.stderr)
                return 1

    if args.dry_run:
        report = _build_preflight_report(
            repo_root=args.repo_root,
            offline=args.offline,
            error=error_message,
            require_python=args.enable_python,
            require_node=args.enable_node,
        )
        print(json.dumps(report, sort_keys=True))
        if error_message:
            print(error_message, file=sys.stderr)
        return 0 if report["status"] == "pass" else 1

    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
