FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (layer cache friendly).
COPY engine/pyproject.toml engine/src/ /app/
COPY seeker/ /app/src/seeker/

RUN pip install --no-cache-dir -e /app

EXPOSE 8420

# Engine reads config from env: SEEKER_TOKEN (required), SEEKER_DB_PATH (default /data/seeker.db).
# Host-gateway resolves host.docker.internal on Linux.
CMD ["uvicorn", "seeker.api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8420"]