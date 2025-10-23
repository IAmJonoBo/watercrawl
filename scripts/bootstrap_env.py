from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from os import environ
from pathlib import Path

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
                    description="Install Poetry environment",
                    command=("poetry", "install", "--no-root", "--sync"),
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
        if offline and not _has_node_tarball_cache(repo_root):
            raise BootstrapError(
                "Offline bootstrap requires cached Node package tarballs under "
                "'artifacts/cache/node'. Seed the cache or disable Node setup."
            )
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


def _has_node_tarball_cache(repo_root: Path) -> bool:
    """Return True when a local Node package tarball cache is available."""

    cache_root = repo_root / "artifacts" / "cache" / NODE_CACHE_DIRNAME
    if not cache_root.exists():
        return False
    for suffixes in (".tgz", ".tar", ".tar.gz", ".tar.xz"):
        if any(cache_root.rglob(f"*{suffixes}")):
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
    plan = build_bootstrap_plan(
        repo_root=args.repo_root,
        enable_python=args.enable_python,
        enable_node=args.enable_node,
        enable_docs=args.enable_docs,
        offline=args.offline,
    )
    try:
        execute_plan(plan, dry_run=args.dry_run)
    except BootstrapError as exc:  # pragma: no cover - CLI error handling
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
