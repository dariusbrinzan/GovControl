FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:0.8.22 /uv /uvx /bin/
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY alembic.ini ./
COPY alembic ./alembic
COPY notifications_app ./notifications_app

RUN useradd --create-home --uid 10001 govcontrol && chown -R govcontrol:govcontrol /app
USER govcontrol
EXPOSE 8030
CMD ["uv", "run", "--no-sync", "uvicorn", "notifications_app.main:app", "--host", "0.0.0.0", "--port", "8030"]
