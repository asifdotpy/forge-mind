# ForgeMind control-plane container image (Cloud Run ready).
#
# Build:  docker build -t forgemind .
# Run:    docker run -p 8080:8080 forgemind
#
# Dependencies install with `uv` from the committed uv.lock (--frozen),
# matching local development and giving fast, reproducible builds.  The
# dependency layer caches independently of application source: it only
# rebuilds when pyproject.toml / uv.lock change.
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1

# uv for fast, lock-frozen dependency installation (matches local dev).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# curl is required by the HEALTHCHECK below (absent from slim images).
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# ------------------------------------------------------------------
# Dependency layer (cached until pyproject.toml / uv.lock change).
# docs/PROJECT.md is copied because pyproject declares it as `readme`;
# the wheel build fails without it.
# ------------------------------------------------------------------
COPY pyproject.toml uv.lock ./
COPY docs/PROJECT.md docs/PROJECT.md
# Cache mount persists downloaded wheels across build attempts: on rebuilds
# (or flaky networks) uv resumes from its cache instead of refetching.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# ----------------------------------------------------------
# Application source.  specs/ and fixtures/ ship in the image
# because forgemind resolves contract paths relative to the
# repository root (forgemind/_paths.py).
# ----------------------------------------------------------
COPY src/ ./src/
COPY specs/ ./specs/
COPY fixtures/ ./fixtures/
COPY scripts/ ./scripts/

# Install the forge-mind package itself into the project venv.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Run unprivileged (Cloud Run-compatible arbitrary UID).
RUN useradd --uid 10001 --user-group --shell /usr/sbin/nologin appuser
USER appuser

ENV PATH="/app/.venv/bin:$PATH"

# Cloud Run injects $PORT; default to 8080 for local parity.
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -fsS "http://localhost:${PORT:-8080}/api/v1/health" || exit 1

CMD ["sh", "-c", "exec uvicorn forgemind.api:create_api --host 0.0.0.0 --port ${PORT:-8080} --factory"]
