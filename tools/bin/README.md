# Bundled Linter Binaries

This directory contains pre-downloaded binaries for `hadolint` and `actionlint` to support ephemeral runners and offline environments without internet access.

## Contents

### hadolint v2.14.0

- `hadolint-linux-x86_64` - Linux x86_64 (53MB)
- `hadolint-linux-arm64` - Linux ARM64 (57MB)
- `hadolint-macos-x86_64` - macOS x86_64 (22MB)
- `hadolint-macos-arm64` - macOS ARM64 (97MB)

### actionlint v1.7.1

- `actionlint-linux-x86_64` - Linux x86_64 (4.9MB)
- `actionlint-linux-arm64` - Linux ARM64 (4.8MB)
- `actionlint-macos-x86_64` - macOS x86_64 (5.0MB)
- `actionlint-macos-arm64` - macOS ARM64 (4.8MB)

## Usage

The bootstrap utilities in `tools/hooks/bootstrap.py` will automatically use these bundled binaries when available, falling back to downloading them only if:

1. The bundled binary for the current platform is not found
2. An environment variable override is set (`HADOLINT_PATH` or `ACTIONLINT_PATH`)
3. The `WATERCRAWL_BOOTSTRAP_SKIP_BUNDLED` environment variable is set

## Updating Binaries

To update to a new version:

1. Download the new binaries for all platforms
2. Place them in this directory with the naming convention: `{tool}-{platform}-{arch}`
3. Update the version numbers in `tools/hooks/bootstrap.py`
4. Update this README with the new version numbers

## Security

All binaries are downloaded from official GitHub releases:

- hadolint: <https://github.com/hadolint/hadolint/releases>
- actionlint: <https://github.com/rhysd/actionlint/releases>

Verify checksums against the official releases when updating.
