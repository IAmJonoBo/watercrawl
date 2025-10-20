FROM python:3.14-slim

# Create a non-root user and switch to it
RUN useradd --create-home appuser

WORKDIR /app
COPY . /app

# Install dependencies as appuser
USER appuser
RUN python -m pip install --no-cache-dir "poetry==1.8.4" \
  && poetry install --no-root --sync

# Verify bundled linter binaries are available
RUN echo "Verifying bundled linter binaries..." && \
    test -x tools/bin/hadolint-linux-x86_64 && echo "✓ hadolint available" || echo "✗ hadolint missing" && \
    test -x tools/bin/actionlint-linux-x86_64 && echo "✓ actionlint available" || echo "✗ actionlint missing"

# Add a basic healthcheck (checks if python responds)
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python -c "print('healthcheck')" || exit 1

CMD ["poetry", "run", "python", "main.py"]
