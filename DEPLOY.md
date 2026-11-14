# Деплой RAG-сервиса на VPS

Инструкция для одного сервера: Docker Compose, nginx с TLS, PostgreSQL, автоматический бэкап.

## 1. Требования

| Что | Минимум | Комфортно |
|---|---|---|
| CPU | 2 vCPU | 4 vCPU |
| RAM | 4 ГБ | 8 ГБ |
| Диск | 20 ГБ SSD | 40 ГБ SSD |
| ОС | Ubuntu 22.04 / Debian 12 | — |

GPU не нужен: `multilingual-e5-base` работает на CPU, полный индекс FAISS грузится в память при первом запросе.

Если через сервис пойдут документы клиентов с персональными данными — сервер должен быть в России (152-ФЗ).

## 2. Что открыто наружу

Только nginx: `80` и `443`. `api:8000`, `frontend:8501` и `db:5432` живут во внутренней docker-сети и портов на хост не публикуют — это отличие от dev-схемы в `docker-compose.yml`.

```
Интернет ──▶ nginx :443 ──▶ /        frontend:8501 (Streamlit)
                         └─ /api/    api:8000     (FastAPI)
```

## 3. Подготовка сервера

```bash
# Docker + Compose
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER"   # перелогиниться после этого

# Файрвол
sudo ufw allow OpenSSH
sudo ufw allow 80,443/tcp
sudo ufw enable
```

DNS: A-запись домена на IP сервера, до выпуска сертификата. Проверка:

```bash
dig +short rag.example.com
```

## 4. Код и окружение

```bash
git clone https://github.com/gor802018-code/gigachat-rag-service.git /opt/llm-rag
cd /opt/llm-rag

cp .env.prod.example .env.prod
chmod 600 .env.prod
nano .env.prod
```

Заполнить обязательно:

- `DOMAIN` и `LETSENCRYPT_EMAIL`;
- `POSTGRES_PASSWORD` — `openssl rand -base64 24`;
- `JWT_SECRET_KEY` — `openssl rand -hex 32`;
- `GIGACHAT_CREDENTIALS` — client_id:client_secret из личного кабинета GigaChat.

`.env.prod` в git не попадает (см. `.gitignore`), ключи не уходят в образ: секреты передаются через `env_file` в рантайме.

## 5. Первый запуск

```bash
# сборка и старт (сертификата ещё нет — nginx поднимется с заглушкой)
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build

# выпуск TLS-сертификата и перезагрузка nginx
chmod +x deploy/init-letsencrypt.sh deploy/backup.sh
sudo ./deploy/init-letsencrypt.sh
```

Проверка:

```bash
curl -fsS https://rag.example.com/healthz     # ok
curl -fsS https://rag.example.com/api/health  # {"status":"ok"}
docker compose --env-file .env.prod -f docker-compose.prod.yml ps
```

Интерфейс: `https://rag.example.com`. API: `https://rag.example.com/api`, документация — `https://rag.example.com/api/docs`.

## 6. Миграции

Схема обновляется автоматически при старте контейнера (`alembic upgrade head` в команде сервиса). Принудительно:

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml run --rm api alembic upgrade head
```

## 7. Индекс FAISS и документы

Индекс лежит в томе `faiss_data` (`/app/data/faiss_index`), кэш модели — в `hf_cache`. При пересборке контейнера данные сохраняются.

Важно: демо-индекс из репозитория в прод не тянем — загружайте свои документы через интерфейс, индекс пересоберётся под них.

Первая загрузка модели занимает 1–3 минуты (скачивание ~470 МБ в `hf_cache`), дальше старт мгновенный.

## 8. Обновление версии

```bash
cd /opt/llm-rag
git pull
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build
```

Простой на время пересборки — 30–90 секунд. Миграции применяются при старте `api`.

## 9. Бэкапы

```bash
./deploy/backup.sh     # backups/rag_YYYY-MM-DD_HHMM.sql.gz, хранение 14 дней
```

Cron:

```cron
15 3 * * * cd /opt/llm-rag && ./deploy/backup.sh >> /var/log/rag-backup.log 2>&1
```

Восстановление:

```bash
gunzip -c backups/rag_2026-01-01_0315.sql.gz | \
  docker compose --env-file .env.prod -f docker-compose.prod.yml exec -T db \
  psql -U rag -d rag
```

Бэкапятся только метаданные и документы в PostgreSQL. Индекс FAISS восстановится пересборкой, поэтому отдельно его копировать не нужно.

## 10. Логи и диагностика

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml logs -f api
docker compose --env-file .env.prod -f docker-compose.prod.yml logs -f nginx
docker stats --no-stream
```

Логи пишутся в json-file с ротацией 10 МБ × 3 файла на сервис.

## 11. Частые проблемы

| Симптом | Причина | Что делать |
|---|---|---|
| `502` от nginx | `api` не поднялся | `logs api`, чаще всего неверный `GIGACHAT_CREDENTIALS` или база не готова |
| `nginx: [emerg] cannot load certificate` | нет файлов сертификата | запустить `deploy/init-letsencrypt.sh` |
| Certbot: `Timeout during connect` | домен не указывает на сервер или закрыт 80 | проверить A-запись и `ufw` |
| Пустые ответы агента | в индексе нет документов или `RETRIEVER_MIN_SCORE` слишком высок | загрузить документы, при необходимости снизить порог до 0.75 |
| OOM на 4 ГБ RAM | модель + индекс + Postgres | поднять до 8 ГБ или ограничить `RETRIEVER_TOP_K` |
| Медленный первый запрос | скачивание e5-base | дождаться прогрева, кэш останется в `hf_cache` |

## 12. Откат

```bash
git log --oneline -5
git checkout <предыдущий-коммит>
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build
```

Если миграция несовместима — восстановить базу из бэкапа (раздел 9) и вернуться на прошлый коммит.
