# syntax=docker/dockerfile:1.7
# Docker Space для Hugging Face: API + Streamlit в одном контейнере.
# Наружу смотрит только 7860 (его открывает HF), API слушает localhost внутри.

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_VERSION=2.5.1 \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1 \
    PYTHONPATH=/app \
    PATH="/app/.venv/bin:${PATH}"

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install "poetry==${POETRY_VERSION}"

WORKDIR /app

# Зависимости отдельным слоем: пересборка при правках кода не тянет их заново
COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-ansi

# Для демо база — SQLite, поэтому нужен драйвер; Streamlit — интерфейс
RUN pip install "aiosqlite>=0.22" "streamlit>=1.39"

COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./
COPY app.py ./
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=5 \
    CMD curl -fsS http://127.0.0.1:7860/_stcore/health || exit 1

ENTRYPOINT ["/entrypoint.sh"]
