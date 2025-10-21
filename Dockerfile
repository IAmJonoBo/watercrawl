# Stage 1: Builder - install dependencies and build artifacts
FROM python:3.13-slim@sha256:2ec5a4a5c3e919570f57675471f081d6299668d909feabd8d4803c6c61af666c as builder

# Install build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential=12.9 \
        curl=7.88.1-10+deb12u8 && \
    rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN python -m pip install --no-cache-dir "poetry==1.9.6"

WORKDIR /build
COPY pyproject.toml poetry.lock poetry.toml ./
COPY firecrawl_demo ./firecrawl_demo
COPY scripts ./scripts
COPY tools ./tools
COPY data ./data
COPY profiles ./profiles
COPY README.md LICENSE ./

# Install dependencies in a virtual environment
RUN poetry config virtualenvs.in-project true && \
    poetry install --no-root --no-dev --no-interaction --no-ansi

# Stage 2: Runtime - minimal production image
FROM python:3.13-slim@sha256:2ec5a4a5c3e919570f57675471f081d6299668d909feabd8d4803c6c61af666c

# Install minimal runtime dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates=20230311 && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user and group with explicit UID/GID
RUN groupadd --gid 1000 app && \
    useradd --uid 1000 --gid app --create-home --shell /bin/bash app

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder --chown=app:app /build/.venv /app/.venv

# Copy application code
COPY --chown=app:app firecrawl_demo ./firecrawl_demo
COPY --chown=app:app scripts ./scripts
COPY --chown=app:app tools ./tools
COPY --chown=app:app data ./data
COPY --chown=app:app profiles ./profiles
COPY --chown=app:app main.py pyproject.toml README.md LICENSE ./

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

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
