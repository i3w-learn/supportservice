# Build stage — uv resolves from the committed lockfile, never the network's latest.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Dependencies first, so a source-only change does not re-resolve them.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# README.md is not documentation here — pyproject declares it as the package
# readme, so the build backend fails without it.
COPY README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev

# Runtime stage — no uv, no build tools.
FROM python:3.12-slim-bookworm

WORKDIR /app
COPY --from=builder /app /app
ENV PATH="/app/.venv/bin:$PATH"

# Cloud Run injects PORT; 8080 is the local default.
EXPOSE 8080
CMD ["sh", "-c", "uvicorn support_service.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
