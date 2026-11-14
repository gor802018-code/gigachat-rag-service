#!/usr/bin/env bash
# Запуск демо на Hugging Face Spaces: SQLite + API + Streamlit в одном контейнере.
set -euo pipefail

DATA_DIR="${DATA_DIR:-/data}"
mkdir -p "${DATA_DIR}/faiss_index" "${DATA_DIR}/hf"

# Демо-база: файл в /data (на бесплатном Space не сохраняется между рестартами,
# это нормально — при старте база создаётся заново)
export DATABASE_URL="${DATABASE_URL:-sqlite+aiosqlite:////data/app.db}"
export FAISS_INDEX_PATH="${DATA_DIR}/faiss_index"
export HF_HOME="${DATA_DIR}/hf"
export APP_ENV="${APP_ENV:-production}"

cd /app

echo "[entrypoint] миграции..."
if ! alembic upgrade head; then
  echo "[entrypoint] alembic не применился — продолжаю, схема создастся при первом запросе"
fi

echo "[entrypoint] запускаю API на 127.0.0.1:8000"
uvicorn src.main:app --host 127.0.0.1 --port 8000 --workers 1 &
API_PID=$!

for _ in $(seq 1 90); do
  if curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
    echo "[entrypoint] API готов"
    break
  fi
  if ! kill -0 "$API_PID" 2>/dev/null; then
    echo "[entrypoint] API упал, смотрите логи выше" >&2
    exit 1
  fi
  sleep 2
done

export API_BASE_URL="http://127.0.0.1:8000"

echo "[entrypoint] запускаю Streamlit на 0.0.0.0:7860"
exec streamlit run app.py \
  --server.address 0.0.0.0 \
  --server.port 7860 \
  --server.headless true \
  --browser.gatherUsageStats false
