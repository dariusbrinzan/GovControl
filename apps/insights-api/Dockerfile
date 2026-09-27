FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app
RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY alembic.ini ./
COPY alembic ./alembic
COPY insights_app ./insights_app

RUN useradd --create-home --uid 10001 govinsights && chown -R govinsights:govinsights /app
USER govinsights

EXPOSE 8040
CMD ["uvicorn", "insights_app.main:app", "--host", "0.0.0.0", "--port", "8040"]

