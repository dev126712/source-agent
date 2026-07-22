# syntax=docker/dockerfile:1

# uv-based image (CLAUDE.md: uv replaces pip in Dockerfiles).
# Pinned to 3.12 to match `requires-python = ">=3.12"`.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# - bytecode compile for faster cold starts
# - copy link mode (bind-mounted cache isn't on the same fs as the venv)
# - venv OUTSIDE the workdir so a dev bind-mount of ./app doesn't shadow it
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# 1) Dependency layer — cached until pyproject/uv.lock change.
#    --no-install-project so app code changes don't bust this layer.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --frozen --no-install-project --no-dev

# 2) Project layer.
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

EXPOSE 8000

# Production default. Compose overrides this with --reload for local dev.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
