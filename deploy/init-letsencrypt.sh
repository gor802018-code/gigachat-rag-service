#!/usr/bin/env bash
# Первый выпуск TLS-сертификата Let's Encrypt.
#
# Зачем скрипт: nginx не стартует, если файлов сертификата нет. Поэтому сначала
# кладём самоподписанный «заглушечный» сертификат, поднимаем nginx, а затем
# получаем настоящий через ACME-челлендж и перезагружаем nginx.
#
# Запуск: ./deploy/init-letsencrypt.sh  (из корня проекта, права root/sudo)

set -euo pipefail
cd "$(dirname "$0")/.."

COMPOSE_FILE="docker-compose.prod.yml"
ENV_FILE=".env.prod"
PROJECT="llm-rag-prod"

if [ ! -f "$ENV_FILE" ]; then
  echo "Нет $ENV_FILE. Скопируйте .env.prod.example и заполните." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
. "./$ENV_FILE"
set +a

: "${DOMAIN:?Задайте DOMAIN в .env.prod}"
: "${LETSENCRYPT_EMAIL:?Задайте LETSENCRYPT_EMAIL в .env.prod}"

COMPOSE=(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE")
CERT_VOLUME="${PROJECT}_certbot_conf"

has_cert() {
  docker run --rm -v "${CERT_VOLUME}:/etc/letsencrypt" alpine \
    sh -c "[ -s /etc/letsencrypt/live/${DOMAIN}/fullchain.pem ]" >/dev/null 2>&1
}

if has_cert; then
  echo "Сертификат для ${DOMAIN} уже есть — пропускаю выпуск."
else
  echo "1/3 Создаю временный самоподписанный сертификат для ${DOMAIN}..."
  docker run --rm -v "${CERT_VOLUME}:/etc/letsencrypt" alpine sh -c "
    set -e
    apk add --no-cache openssl >/dev/null
    mkdir -p /etc/letsencrypt/live/${DOMAIN}
    openssl req -x509 -nodes -newkey rsa:2048 -days 1 \
      -keyout /etc/letsencrypt/live/${DOMAIN}/privkey.pem \
      -out /etc/letsencrypt/live/${DOMAIN}/fullchain.pem \
      -subj '/CN=${DOMAIN}' >/dev/null 2>&1
  "

  echo "2/3 Поднимаю nginx для прохождения ACME-челленджа..."
  "${COMPOSE[@]}" up -d nginx
  sleep 5

  echo "3/3 Запрашиваю сертификат у Let's Encrypt..."
  "${COMPOSE[@]}" run --rm --entrypoint certbot certbot certonly \
    --webroot -w /var/www/certbot \
    -d "${DOMAIN}" \
    --email "${LETSENCRYPT_EMAIL}" \
    --agree-tos --no-eff-email \
    --force-renewal

  "${COMPOSE[@]}" exec nginx nginx -s reload
  echo "Готово: https://${DOMAIN}"
fi
