# Dependency Download Troubleshooting Guide

## Quick Diagnosis

If you're experiencing issues with dependency downloads, run the configuration test:

```bash
./scripts/test_dependency_config.sh
```

This will verify all timeout and retry settings are correctly configured.

## Common Issues and Solutions

### Issue: pip install times out

**Symptoms:**
- `ReadTimeoutError: HTTPSConnectionPool(host='pypi.org', port=443): Read timed out`
- Installation hangs for extended periods

**Solutions:**

1. **Use the configured timeout/retry settings:**
   ```bash
   python -m pip install --timeout 60 --retries 5 <package>
   ```

2. **Set environment variables for Poetry:**
   ```bash
   export PIP_TIMEOUT=60
   export PIP_RETRIES=5
   poetry install --no-root
   ```

3. **Check pip configuration:**
   ```bash
   python -m pip config list
   ```
   Should show `global.timeout=60` and `global.retries=5`

### Issue: Poetry install fails with network errors

**Symptoms:**
- Poetry hangs during dependency resolution
- `HTTP Error 503` or timeout errors
- Slow installation progress

**Solutions:**

1. **Use environment variables:**
   ```bash
   export POETRY_INSTALLER_MAX_WORKERS=10
   export PIP_TIMEOUT=60
   export PIP_RETRIES=5
   poetry install --no-root
   ```

2. **Use the justfile recipe** (automatically sets environment):
   ```bash
   just install-dev
   ```

3. **Clear Poetry cache if corrupt:**
   ```bash
   poetry cache clear pypi --all
   poetry install --no-root
   ```

### Issue: pnpm install fails or is slow

**Symptoms:**
- `ERR_PNPM_FETCH_*` errors
- Network timeout errors
- Very slow package downloads

**Solutions:**

1. **Verify .npmrc configuration:**
   ```bash
   cat .npmrc | grep -E "(timeout|retries)"
   ```
   Should show:
   ```
   network-timeout=60000
   fetch-retries=5
   fetch-retry-factor=10
   fetch-retry-mintimeout=10000
   fetch-retry-maxtimeout=60000
   ```

2. **Set environment variables explicitly:**
   ```bash
   export PNPM_NETWORK_TIMEOUT=60000
   export PNPM_FETCH_RETRIES=5
   pnpm install --frozen-lockfile
   ```

3. **Clear pnpm cache if needed:**
   ```bash
   pnpm store prune
   pnpm install --frozen-lockfile
   ```

### Issue: Docker build fails during dependency installation

**Symptoms:**
- Docker build fails at `RUN poetry install` step
- Timeout errors in Docker build logs

**Solutions:**

1. **Increase Docker build timeout:**
   ```bash
   docker build --network=host --build-arg BUILDKIT_INLINE_CACHE=1 -t watercrawl:latest .
   ```

2. **Use BuildKit with increased timeouts:**
   ```bash
   DOCKER_BUILDKIT=1 docker build -t watercrawl:latest .
   ```

3. **Check Dockerfile environment variables:**
   The Dockerfile should have:
   ```dockerfile
   ENV PIP_TIMEOUT=60 \
       PIP_RETRIES=5
   ```

### Issue: GitHub Actions workflow fails with timeout

**Symptoms:**
- CI workflow fails at dependency installation step
- "The operation was canceled" errors
- Network-related errors in Actions logs

**Solutions:**

1. **Re-run the workflow** - Transient network issues often resolve on retry

2. **Check workflow environment variables:**
   Ensure the workflow step has:
   ```yaml
   env:
     PIP_TIMEOUT: 60
     PIP_RETRIES: 5
     POETRY_INSTALLER_MAX_WORKERS: 10
   ```

3. **For pnpm steps, verify:**
   ```yaml
   env:
     PNPM_NETWORK_TIMEOUT: 60000
     PNPM_FETCH_RETRIES: 5
   ```

### Issue: Offline/air-gapped environment installation

**Symptoms:**
- No internet connectivity
- Need to install without external network access

**Solutions:**

1. **Use bundled binaries** (hadolint, actionlint):
   ```bash
   ls tools/bin/
   ```
   These are automatically used when available.

2. **Pre-download wheel files:**
   ```bash
   # On a machine with internet:
   pip download -r requirements-dev.txt -d ./wheels/
   
   # On offline machine:
   pip install --no-index --find-links=./wheels/ -r requirements-dev.txt
   ```

3. **Use vendored dependencies if available:**
   ```bash
   poetry config virtualenvs.in-project true
   # Copy the entire .venv directory from a machine with internet
   ```

## Environment Verification

### Check all configurations:

```bash
# Run the comprehensive test
./scripts/test_dependency_config.sh

# Or check individually:

# Pip config
python -m pip config list

# Poetry config
poetry config --list

# pnpm config
cat .npmrc

# Environment variables
env | grep -E "(PIP_|POETRY_|PNPM_)"
```

### Verify network connectivity:

```bash
# Test PyPI connectivity
curl -I https://pypi.org/simple/

# Test npm registry
curl -I https://registry.npmjs.org/

# Test with timeout
curl --max-time 10 https://pypi.org/simple/
```

## Performance Tips

### Speed up installation with caching:

1. **Use Poetry cache:**
   ```bash
   # Cache is automatic, but you can check size:
   du -sh ~/.cache/pypoetry/
   ```

2. **Use pnpm store:**
   ```bash
   # pnpm automatically uses content-addressable storage
   pnpm store status
   ```

3. **In GitHub Actions**, ensure cache actions are configured (already done in workflows)

### Parallel downloads:

```bash
# Poetry (set in poetry.toml and environment)
export POETRY_INSTALLER_MAX_WORKERS=10

# pip (use parallel option if available)
pip install --use-feature=fast-deps <package>
```

## Getting Help

If issues persist after trying these solutions:

1. Run the diagnostics:
   ```bash
   ./scripts/test_dependency_config.sh
   just test-deps  # Alternative using justfile
   ```

2. Check the detailed documentation:
   - [docs/dependency-resilience.md](dependency-resilience.md) - Complete configuration guide
   - [docs/offline-linters.md](offline-linters.md) - Bundled binary usage

3. Review recent changes:
   ```bash
   git log --oneline docs/dependency-resilience.md
   ```

4. Create an issue with:
   - Output of `./scripts/test_dependency_config.sh`
   - Relevant error messages
   - Environment details (OS, Python version, network setup)
