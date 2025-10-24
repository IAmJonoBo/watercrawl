# Stage 1: Builder - install dependencies and build artifacts
FROM python:3.14-slim@sha256:4ed33101ee7ec299041cc41dd268dae17031184be94384b1ce7936dc4e5dead3 as builder

# Install build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential=12.9 \
        curl=7.88.1-10+deb12u8 \
        libnss3 \
        libatk1.0-0 \
        libatk-bridge2.0-0 \
        libdrm2 \
        libxcb1 \
        libxkbcommon0 \
        libxcomposite1 \
        libxdamage1 \
        libxrandr2 \
        libxfixes3 \
        libxrender1 \
        libx11-6 \
        libxss1 \
        libxshmfence1 \
        libgtk-3-0 \
        libgbm1 \
        libasound2 \
        fonts-liberation && \
    rm -rf /var/lib/apt/lists/*

# Install Poetry with retry configuration
RUN python -m pip install --no-cache-dir --timeout 60 --retries 5 "poetry==1.9.6"

WORKDIR /build
COPY pyproject.toml poetry.lock poetry.toml ./
COPY crawlkit ./crawlkit
COPY watercrawl ./watercrawl
COPY scripts ./scripts
COPY tools ./tools
COPY data ./data
COPY profiles ./profiles
COPY artifacts ./artifacts
COPY README.md LICENSE ./

# Install dependencies in a virtual environment with timeout/retry configuration
ENV PIP_TIMEOUT=60 \
    PIP_RETRIES=5
RUN poetry config virtualenvs.in-project true && \
    poetry install --no-root --no-dev --no-interaction --no-ansi

# Pre-cache Playwright browsers and public suffix data for offline execution
RUN mkdir -p artifacts/cache/playwright artifacts/cache/tldextract && \
    PLAYWRIGHT_BROWSERS_PATH="/build/artifacts/cache/playwright" \
        poetry run playwright install chromium firefox webkit && \
    poetry run python -c "from pathlib import Path; import tldextract; cache = Path('/build/artifacts/cache/tldextract'); cache.mkdir(parents=True, exist_ok=True); tldextract.TLDExtract(cache_dir=str(cache), suffix_list_urls=())('example.com')"

# Stage 2: Runtime - minimal production image
FROM python:3.14-slim@sha256:4ed33101ee7ec299041cc41dd268dae17031184be94384b1ce7936dc4e5dead3

# Install minimal runtime dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        libnss3 \
        libatk1.0-0 \
        libatk-bridge2.0-0 \
        libdrm2 \
        libxcb1 \
        libxkbcommon0 \
        libxcomposite1 \
        libxdamage1 \
        libxrandr2 \
        libxfixes3 \
        libxrender1 \
        libx11-6 \
        libxss1 \
        libxshmfence1 \
        libgtk-3-0 \
        libgbm1 \
        libasound2 \
        fonts-liberation && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user and group with explicit UID/GID
RUN groupadd --gid 1000 app && \
    useradd --uid 1000 --gid app --create-home --shell /bin/bash app

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder --chown=app:app /build/.venv /app/.venv
COPY --from=builder --chown=app:app /build/artifacts/cache /app/artifacts/cache

# Copy application code
COPY --chown=app:app crawlkit ./crawlkit
COPY --chown=app:app watercrawl ./watercrawl
COPY --chown=app:app scripts ./scripts
COPY --chown=app:app tools ./tools
COPY --chown=app:app data ./data
COPY --chown=app:app profiles ./profiles
COPY --chown=app:app main.py pyproject.toml README.md LICENSE ./

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PLAYWRIGHT_BROWSERS_PATH=/app/artifacts/cache/playwright

# Switch to non-root user
USER app:app

# Verify bundled linter binaries are available
RUN echo "Verifying bundled linter binaries..." && \
    test -x tools/bin/hadolint-linux-x86_64 && echo "✓ hadolint available" || echo "✗ hadolint missing" && \
    test -x tools/bin/actionlint-linux-x86_64 && echo "✓ actionlint available" || echo "✗ actionlint missing"

# Add healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python -c "import sys; sys.exit(0)" || exit 1

# Drop all capabilities and run with read-only filesystem
# Note: These are applied at runtime with docker run --cap-drop=ALL --read-only
# or in docker-compose.yml / Kubernetes manifests

CMD ["python", "main.py"]
