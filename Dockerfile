FROM python:3.14-slim

# Create a non-root user and switch to it
RUN useradd --create-home appuser
USER appuser

WORKDIR /app
COPY . /app
RUN python -m pip install --no-cache-dir "poetry==1.8.4" \
  && poetry install --no-root --sync

# Add a basic healthcheck (checks if python responds)
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python -c "print('healthcheck')" || exit 1

CMD ["poetry", "run", "python", "main.py"]
