FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# The project metadata is copied first so that the dependency layer is
# cached and is only invalidated when the dependencies actually change.
COPY pyproject.toml ./
COPY backend/agent_redteam_framework.egg-info ./backend/agent_redteam_framework.egg-info 2>/dev/null || true

RUN pip install --no-cache-dir uv && \
    uv pip install --system --no-cache -e .

# The application package lives at /app/app so that "uvicorn app.main:app"
# resolves. The previous layout copied it to /app/backend/app, which only
# worked because the compose file mounts the source directory over /app.
COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./alembic.ini
COPY evaluation ./evaluation
COPY scripts ./scripts

FROM base AS development

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

FROM base AS production

RUN useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=5 \
    CMD curl -fsS http://localhost:8000/api/v1/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
