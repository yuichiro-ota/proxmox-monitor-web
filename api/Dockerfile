FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_SYSTEM_PYTHON=1

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev

COPY api/ ./api/

CMD ["/app/.venv/bin/uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000"]
