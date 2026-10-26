# Seeker engine — single-stage build on Python 3.12 slim.
# Tailscale and backups are sidecars (see docker-compose.yml at repo root);
# Ollama runs on the host — the engine reaches it at host.docker.internal:11434.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install the package first so dependency layers cache across source edits.
COPY pyproject.toml README.md* ./
COPY src/ ./src/
RUN pip install --no-cache-dir .

# Non-root: the engine reads mounted sources and writes ./data only.
RUN useradd --create-home seeker
USER seeker

EXPOSE 8420

# /v1/health is the one anonymous route (docs/build_docs/03-api-design.md);
# probe it with stdlib — slim images ship no curl.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8420/v1/health', timeout=5).status == 200 else 1)"

CMD ["python", "-m", "seeker"]
