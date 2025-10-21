# Dependency Resilience and Download Configuration

## Overview

This document describes the configuration improvements made to ensure reliable access to dependency resources across all environments, including scenarios with network timeouts, slow connections, or transient failures.

## Problem Statement

The original setup experienced timeouts when downloading dependencies from:
- PyPI (Python packages via pip and Poetry)
- npm registry (Node packages via pnpm)
- GitHub releases (for bundled binaries)

These issues could cause CI/CD failures and make local development difficult in environments with poor network connectivity.

## Solutions Implemented

### 1. Pip Configuration (`.config/pip/pip.conf`)

Created a global pip configuration file with:
- **Timeout**: Increased to 60 seconds (from default 15s)
- **Retries**: Set to 5 attempts for failed downloads
- **Binary packages**: Prefer pre-built wheels to reduce build time
- **Progress bar**: Enabled for better visibility

This file is automatically picked up by pip when present in the repository.

### 2. Poetry Configuration (`poetry.toml`)

Enhanced Poetry settings with:
- **Max workers**: Set to 10 for parallel downloads
- **Virtual environments**: In-project for consistency

Environment variables are used in CI workflows:
- `POETRY_INSTALLER_MAX_WORKERS=10`
- `PIP_TIMEOUT=60`
- `PIP_RETRIES=5`

### 3. pnpm Configuration (`.npmrc`)

Added network resilience settings:
- **Network timeout**: 60 seconds
- **Fetch retries**: 5 attempts
- **Retry timing**: Exponential backoff (10-60 seconds)

Settings:
```ini
network-timeout=60000
fetch-retries=5
fetch-retry-factor=10
fetch-retry-mintimeout=10000
fetch-retry-maxtimeout=60000
```

### 4. GitHub Actions Workflow Updates

Updated all workflows to use:

#### Pip Installation
```yaml
run: |
  python -m pip install --upgrade pip --timeout 60 --retries 5
  python -m pip install poetry --timeout 60 --retries 5
```

#### Poetry Installation
```yaml
run: poetry install --no-root
env:
  POETRY_INSTALLER_MAX_WORKERS: 10
  PIP_TIMEOUT: 60
  PIP_RETRIES: 5
```

#### pnpm Installation
```yaml
run: pnpm install --frozen-lockfile
env:
  PNPM_NETWORK_TIMEOUT: 60000
  PNPM_FETCH_RETRIES: 5
  PNPM_FETCH_RETRY_MINTIMEOUT: 10000
  PNPM_FETCH_RETRY_MAXTIMEOUT: 60000
```

### 5. Caching Improvements

Added or enhanced caching in workflows:

#### Poetry Cache
```yaml
- uses: actions/cache@v4
  with:
    path: |
      ~/.cache/pypoetry/virtualenvs
      ~/.cache/pip
    key: ${{ runner.os }}-poetry-${{ matrix.python-version }}-${{ hashFiles('poetry.lock') }}
```

#### pnpm Cache
```yaml
- uses: actions/setup-node@v6
  with:
    cache: 'pnpm'
```

### 6. Docker Build Optimization

Updated `Dockerfile` with:
- Timeout and retry flags for pip commands
- Environment variables for Poetry's pip usage
- Optimized layer caching

### 7. Reusable GitHub Action

Created `.github/actions/setup-python-deps/action.yml` for consistent Python dependency setup across workflows.

## Benefits

1. **Resilience**: Automatic retries handle transient network failures
2. **Speed**: Parallel downloads and caching reduce installation time
3. **Consistency**: Standardized configuration across all environments
4. **Visibility**: Better logging helps debug issues
5. **Offline Support**: Bundled binaries in `tools/bin/` reduce external dependencies

## Testing

To test these improvements locally:

```bash
# Test pip configuration
python -m pip install --timeout 60 --retries 5 some-package

# Test Poetry installation
poetry install --no-root

# Test pnpm installation
pnpm install --frozen-lockfile
```

## Monitoring

Monitor dependency installation in CI:
1. Check GitHub Actions logs for retry attempts
2. Review cache hit rates in workflow runs
3. Track installation time trends

## Troubleshooting

### Slow Downloads
- Check `pip.conf` timeout settings
- Verify cache is being used
- Consider using a PyPI mirror for corporate networks

### Cache Misses
- Ensure `poetry.lock` and `pnpm-lock.yaml` haven't changed
- Check cache key configuration in workflows

### Network Failures
- Retry the workflow run
- Check for PyPI/npm registry outages
- Verify firewall/proxy settings

## Future Enhancements

Potential improvements:
1. Add PyPI mirror fallback for additional resilience
2. Pre-download frequently used packages
3. Implement local package cache in CI runners
4. Add metrics for dependency installation performance

## References

- [pip Configuration](https://pip.pypa.io/en/stable/topics/configuration/)
- [Poetry Configuration](https://python-poetry.org/docs/configuration/)
- [pnpm Configuration](https://pnpm.io/npmrc)
- [GitHub Actions Caching](https://docs.github.com/en/actions/using-workflows/caching-dependencies-to-speed-up-workflows)
