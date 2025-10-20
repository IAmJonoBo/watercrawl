# Offline Linter Support

## Overview

This document describes how `hadolint` and `actionlint` binaries are bundled in the repository to support ephemeral runners and offline environments without internet access.

## Problem Statement

Previously, the repository relied on downloading linter binaries at runtime:
- CI workflows downloaded binaries during each run
- Pre-commit hooks downloaded binaries on first use
- This approach failed in environments without internet access (air-gapped environments, restricted networks, ephemeral runners)

## Solution

Linter binaries are now bundled directly in the repository under `tools/bin/`:

### Bundled Binaries

**hadolint v2.14.0** (Dockerfile linter)
- `hadolint-linux-x86_64` (53MB)
- `hadolint-linux-arm64` (57MB)
- `hadolint-macos-x86_64` (22MB)
- `hadolint-macos-arm64` (97MB)

**actionlint v1.7.1** (GitHub Actions workflow linter)
- `actionlint-linux-x86_64` (4.9MB)
- `actionlint-linux-arm64` (4.8MB)
- `actionlint-macos-x86_64` (5.0MB)
- `actionlint-macos-arm64` (4.8MB)

Total size: ~247MB across all platforms

## How It Works

### Bootstrap Priority

The `tools/hooks/bootstrap.py` module follows this priority when locating binaries:

1. **Environment variable override** (`HADOLINT_PATH` or `ACTIONLINT_PATH`)
2. **Bundled binary** (in `tools/bin/`)
3. **Cached download** (in `~/.cache/watercrawl/bin/`)
4. **Fresh download** (from GitHub releases)

### Environment Variables

- `HADOLINT_PATH` - Override path to hadolint binary
- `ACTIONLINT_PATH` - Override path to actionlint binary
- `WATERCRAWL_BOOTSTRAP_SKIP_BUNDLED` - Skip checking for bundled binaries
- `WATERCRAWL_BOOTSTRAP_SKIP_SSL` - Allow SSL verification bypass (use with caution)

## Usage

### Pre-commit Hooks

The pre-commit hooks in `.pre-commit-config.yaml` automatically use the bundled binaries:

```yaml
- repo: local
  hooks:
    - id: hadolint
      name: hadolint
      entry: poetry run python -m tools.hooks.run_hadolint
      language: system
      types: [dockerfile]
    - id: actionlint
      name: actionlint
      entry: poetry run python -m tools.hooks.run_actionlint
      language: system
      types_or: [yaml]
      files: ^\.github/workflows/.*\.ya?ml$
```

### CI Workflows

The CI workflow (`.github/workflows/ci.yml`) checks for bundled binaries first:

```bash
# Use bundled hadolint binary for offline environments
HADOLINT_BIN="tools/bin/hadolint-linux-x86_64"
if [ -x "$HADOLINT_BIN" ]; then
  "$HADOLINT_BIN" Dockerfile || true
else
  # Fallback to downloading if bundled binary not available
  # ...
fi
```

### Docker Builds

The Dockerfile verifies bundled binaries are available during the build:

```dockerfile
RUN echo "Verifying bundled linter binaries..." && \
    test -x tools/bin/hadolint-linux-x86_64 && echo "✓ hadolint available" || echo "✗ hadolint missing" && \
    test -x tools/bin/actionlint-linux-x86_64 && echo "✓ actionlint available" || echo "✗ actionlint missing"
```

## Maintenance

### Updating Binaries

To update to a newer version:

1. Download new binaries for all platforms from official GitHub releases
2. Replace files in `tools/bin/` with the naming convention: `{tool}-{platform}-{arch}`
3. Update version numbers in `tools/hooks/bootstrap.py`
4. Update `tools/bin/README.md` with new version numbers
5. Test on all platforms
6. Commit changes

### Verifying Checksums

Always verify checksums when updating binaries:

```bash
# For hadolint
wget https://github.com/hadolint/hadolint/releases/download/v2.14.0/hadolint-Linux-x86_64.sha256
sha256sum -c hadolint-Linux-x86_64.sha256

# For actionlint (checksums in release notes)
sha256sum tools/bin/actionlint-linux-x86_64
```

## Benefits

1. **Offline Support** - Works in air-gapped environments and ephemeral runners without internet
2. **Reliability** - No dependency on external downloads during CI runs
3. **Speed** - Faster execution without download time
4. **Consistency** - Same binary version across all environments
5. **Security** - Binaries are committed and tracked in version control

## Trade-offs

1. **Repository Size** - Adds ~247MB to repository size
2. **Maintenance** - Manual updates required when new versions are released
3. **Git LFS Consideration** - Large binaries trigger GitHub warnings (but work without LFS)

## Related Documentation

- [Tools README](../tools/README.md)
- [Bundled Binaries README](../tools/bin/README.md)
- [Pre-commit Configuration](../.pre-commit-config.yaml)
- [CI Workflow](../.github/workflows/ci.yml)

## References

- hadolint: https://github.com/hadolint/hadolint
- actionlint: https://github.com/rhysd/actionlint
- Next Steps tracking: [Next_Steps.md](../Next_Steps.md)
