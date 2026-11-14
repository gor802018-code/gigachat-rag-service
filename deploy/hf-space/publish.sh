#!/usr/bin/env bash
# Публикация демо в Hugging Face Space.
#
# Что делает: собирает в отдельной папке содержимое будущего Space-репозитория
# (код проекта + Dockerfile и entrypoint из этой папки + README с фронтматтером)
# и отправляет его в Space.
#
# Использование:
#   ./deploy/hf-space/publish.sh /tmp/rag-space-demo
#   cd /tmp/rag-space-demo && git remote add space https://huggingface.co/spaces/<user>/rag-demo && git push space main

set -euo pipefail

TARGET="${1:-}"
if [ -z "$TARGET" ]; then
  echo "Укажите пустую папку для Space: $0 /tmp/rag-space-demo" >&2
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
mkdir -p "$TARGET"

# Код и конфиги, нужные контейнеру
cp -r "$ROOT/src" "$ROOT/alembic" "$TARGET/"
cp "$ROOT/alembic.ini" "$ROOT/app.py" "$ROOT/pyproject.toml" "$ROOT/poetry.lock" "$TARGET/"

# Файлы самого Space
cp "$ROOT/deploy/hf-space/Dockerfile" "$ROOT/deploy/hf-space/entrypoint.sh" "$TARGET/"
cp "$ROOT/deploy/hf-space/README.md" "$TARGET/README.md"
chmod +x "$TARGET/entrypoint.sh"

cat > "$TARGET/.gitignore" <<'EOF'
__pycache__/
.venv/
data/
*.db
EOF

cd "$TARGET"
git init -q -b main
git add -A
git commit -q -m "feat: демо RAG-сервиса для Hugging Face Space"

echo "Готово: $TARGET"
echo "Дальше:"
echo "  cd $TARGET"
echo "  git remote add space https://huggingface.co/spaces/<user>/<space-name>"
echo "  git push --force space main"
