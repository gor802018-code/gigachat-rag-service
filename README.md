# RAG Service

Production-ready сервис Retrieval-Augmented Generation: загружаете свои документы — задаёте вопросы
и получаете ответы **только по этим документам**, со ссылками на конкретные фрагменты.

FastAPI + FAISS + GigaChat, layered architecture, JWT, PostgreSQL, Streamlit, Docker Compose, CI.

## Возможности

- **Ingestion**: PDF, DOCX, TXT, MD → чанки с перекрытием → эмбеддинги → FAISS.
- **Ответы со ссылками**: каждый ответ содержит источники (`file_name`, номер фрагмента, `score`).
- **Anti-hallucination**: жёсткий системный промпт «отвечай только по контексту»; если релевантных
  фрагментов нет — LLM **не вызывается**, возвращается фиксированный отказ.
- **JWT-аутентификация**: регистрация, логин, защищённые эндпоинты, изоляция истории по пользователю.
- **Смена LLM-провайдера через env**: `gigachat` (по умолчанию), `openai`, `deepseek` — без правок кода.
- **Наблюдаемость**: structlog (JSON в production), health-эндпоинт, типизированные ошибки.
- **Качество**: 151 тест, Ruff, миграции Alembic, CI с сборкой Docker-образов.

## Архитектура

```mermaid
flowchart LR
    UI["Streamlit UI"] -->|JWT| API["FastAPI /api/v1"]
    API --> AUTH["AuthService"]
    API --> RAG["RAGService"]
    AUTH --> UREPO["UserRepository"]
    RAG --> ING["Ingestion<br/>loader + splitter"]
    RAG --> RETR["Retriever"]
    RAG --> LLM["LLMClient<br/>GigaChat / OpenAI / DeepSeek"]
    ING --> VEC[("FAISS index<br/>+ records.json")]
    RETR --> VEC
    UREPO --> DB[("PostgreSQL")]
    API --> DB
```

Строгое направление зависимостей: `api → services → repositories → core`.
Слой `rag` подключается только через сервисы и DI-провайдеры; ни один роутер не знает про FAISS или SDK GigaChat.

## Стек

| Слой | Технологии |
| --- | --- |
| API | FastAPI, Uvicorn, Pydantic v2, pydantic-settings |
| Бизнес-логика | Service layer, Dependency Injection |
| RAG | LangChain (loaders, splitter), sentence-transformers, FAISS |
| LLM | GigaChat (`langchain-gigachat`), OpenAI/DeepSeek через `langchain-openai` |
| Метаданные и история | PostgreSQL, SQLAlchemy 2 (async), Alembic |
| Auth | JWT (python-jose), passlib + bcrypt |
| Frontend | Streamlit |
| Качество | pytest, pytest-asyncio, httpx, Ruff, coverage |
| Инфраструктура | Docker (multi-stage, non-root), Docker Compose, GitHub Actions |

## Структура проекта

```
.
├── src/
│   ├── api/
│   │   ├── routers/          # auth.py, chat.py — только эндпоинты
│   │   ├── schemas.py        # Pydantic-схемы
│   │   └── dependencies.py   # DI: get_db, get_current_user, get_rag_service
│   ├── services/             # AuthService, RAGService
│   ├── repositories/         # SQLAlchemy-репозитории, FAISS, ORM-модели
│   ├── core/                 # config, logging, security, database
│   ├── ingestion/            # loader.py, splitter.py
│   ├── rag/                  # embeddings, retriever, prompt_builder, llm_client
│   └── main.py               # точка входа ASGI
├── tests/                    # 151 тест: unit + API
├── alembic/                  # env.py + миграции
├── app.py                    # Streamlit-клиент
├── Dockerfile                # API (multi-stage, non-root)
├── Dockerfile.streamlit      # UI (лёгкий образ)
├── docker-compose.yml        # api + db + frontend
└── .github/workflows/ci.yml  # lint + tests + docker build
```

## Быстрый старт

### 1. Требования

- Python 3.11+
- [Poetry 2.x](https://python-poetry.org/)
- PostgreSQL 14+ (или Docker)
- Аккаунт GigaChat Studio с ключами приложения

### 2. Установка

```bash
git clone <repo-url>
cd project_llm_rag
poetry install
cp .env.example .env
```

### 3. Ключи GigaChat

1. Зарегистрируйтесь в **GigaChat Studio** (портал для разработчиков Сбера) и создайте проект.
2. Получите **Client ID** и **Client Secret** в настройках проекта.
3. Соберите строку `client_id:client_secret` и закодируйте её в Base64:

```bash
# Linux / macOS / Git Bash
echo -n "$CLIENT_ID:$CLIENT_SECRET" | base64 -w 0
```

```powershell
# Windows PowerShell
[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes("$clientId:$clientSecret"))
```

4. Положите результат в `.env`:

```dotenv
GIGACHAT_CREDENTIALS=<base64-строка>
GIGACHAT_SCOPE=GIGACHAT_API_PERS
```

`GIGACHAT_SCOPE` должен соответствовать типу аккаунта: `GIGACHAT_API_PERS` для физлиц,
`GIGACHAT_API_B2B` / `GIGACHAT_API_CORP` для юридических лиц.

> `GIGACHAT_VERIFY_SSL_CERTS=false` стоит по умолчанию, потому что API Сбера использует сертификаты
> НУЦ Минцифры, которых нет в стандартном хранилище. Для строгой проверки установите корневой
> сертификат и выставьте `GIGACHAT_VERIFY_SSL_CERTS=true`.

### 4. База данных

```bash
# поднять только Postgres из compose
docker compose up -d db

# применить миграции
poetry run alembic upgrade head
```

### 5. Запуск

```bash
# API (http://127.0.0.1:8000/docs)
poetry run uvicorn src.main:app --reload

# UI (http://127.0.0.1:8501) — во втором терминале
poetry run streamlit run app.py
```

При первом запросе скачивается модель эмбеддингов (~470 МБ) — это разовая операция.

## Docker Compose

```bash
cp .env.example .env      # вписать GIGACHAT_CREDENTIALS
docker compose up --build
```

| Сервис | Адрес | Что внутри |
| --- | --- | --- |
| `api` | http://localhost:8000/docs | FastAPI, миграции применяются на старте |
| `frontend` | http://localhost:8501 | Streamlit-чат |
| `db` | `localhost:5432` | PostgreSQL 16 + volume |

FAISS-индекс лежит в volume `faiss_data` (`/app/data/faiss_index`), база — в `postgres_data`.

## API

Все прикладные эндпоинты — под `/api/v1`. Интерактивная документация: `/docs`, схема: `/openapi.json`.

| Метод | Путь | Доступ | Назначение |
| --- | --- | --- | --- |
| `GET` | `/health` | публичный | liveness-проба |
| `POST` | `/api/v1/auth/register` | публичный | регистрация |
| `POST` | `/api/v1/auth/login` | публичный | выдача JWT |
| `POST` | `/api/v1/chat/upload` | JWT | загрузка и индексация документа |
| `POST` | `/api/v1/chat/ask` | JWT | вопрос по документам |
| `GET` | `/api/v1/chat/history` | JWT | история вопросов |

### Регистрация и логин

```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "strong-password"}'
```

```json
{
  "id": "9f1c2c4f7a8b4d1e9a0b5c6d7e8f9012",
  "email": "user@example.com",
  "is_active": true,
  "created_at": "2026-10-31T18:00:00Z"
}
```

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "strong-password"}'
```

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 3600,
  "user_id": "9f1c2c4f7a8b4d1e9a0b5c6d7e8f9012"
}
```

### Загрузка документа

```bash
curl -X POST http://localhost:8000/api/v1/chat/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@contract.pdf"
```

```json
{
  "document_id": "3b7e1d9c4a5f6b8c0d1e2f3a4b5c6d7e",
  "file_name": "contract.pdf",
  "chunks": 24
}
```

Ограничения: расширения `.pdf`, `.docx`, `.txt`, `.md`; размер — `MAX_UPLOAD_SIZE_MB` (по умолчанию 20 МБ).

### Вопрос

```bash
curl -X POST http://localhost:8000/api/v1/chat/ask \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question": "Какой срок оплаты по договору?", "top_k": 4}'
```

```json
{
  "answer": "Срок оплаты — 30 календарных дней с момента поставки [1].",
  "sources": [
    {
      "file_name": "contract.pdf",
      "chunk_index": 3,
      "chunk_id": "3b7e1d9c4a5f6b8c:3",
      "score": 0.87
    }
  ],
  "model": "GigaChat",
  "usage": {"input_tokens": 812, "output_tokens": 96, "total_tokens": 908}
}
```

`top_k` необязателен (по умолчанию `RETRIEVER_TOP_K`, максимум 20).
Поле `usage` может быть `null`, если провайдер не вернул статистику токенов.

### История

```bash
curl "http://localhost:8000/api/v1/chat/history?limit=10" \
  -H "Authorization: Bearer $TOKEN"
```

Возвращает последние вопросы пользователя с ответами и источниками (изоляция по `user_id`).

### Коды ошибок

| Код | Когда |
| --- | --- |
| `401` | нет токена, токен истёк или подписан чужим ключом |
| `403` | аккаунт деактивирован |
| `409` | email уже занят |
| `413` | файл больше лимита |
| `415` | расширение файла не поддерживается |
| `422` | невалидное тело запроса / файл не читается / пустой документ |

## Конфигурация

Все параметры читаются из env или `.env` (см. `.env.example`).

| Переменная | По умолчанию | Описание |
| --- | --- | --- |
| `APP_ENV` | `development` | `development` / `staging` / `production` / `test` |
| `LOG_LEVEL` | `INFO` | уровень structlog и stdlib |
| `DATABASE_URL` | `postgresql+asyncpg://rag:rag@localhost:5432/rag` | DSN async-драйвера |
| `JWT_SECRET_KEY` | dev-значение | в production обязателен свой (валидируется) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | TTL access-токена |
| `LLM_PROVIDER` | `gigachat` | `gigachat` / `openai` / `deepseek` |
| `LLM_MODEL` | по провайдеру | переопределяет имя модели |
| `LLM_API_KEY` | — | ключ для OpenAI/DeepSeek |
| `LLM_BASE_URL` | `https://api.deepseek.com/v1` для deepseek | кастомный endpoint |
| `GIGACHAT_CREDENTIALS` | — | Base64 `client_id:client_secret` |
| `GIGACHAT_SCOPE` | `GIGACHAT_API_PERS` | scope приложения |
| `GIGACHAT_MODEL` | `GigaChat` | модель GigaChat |
| `LLM_TEMPERATURE` | `0.1` | температура генерации |
| `EMBEDDING_MODEL_NAME` | `paraphrase-multilingual-MiniLM-L12-v2` | модель эмбеддингов |
| `FAISS_INDEX_PATH` | `./data/faiss_index` | каталог индекса и `records.json` |
| `RETRIEVER_TOP_K` | `4` | сколько чанков подавать в контекст |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `1000` / `200` | параметры чанкинга |
| `MAX_UPLOAD_SIZE_MB` | `20` | лимит размера файла |

Смена провайдера — только env:

```dotenv
LLM_PROVIDER=deepseek
LLM_API_KEY=sk-...
```

Для `openai`/`deepseek` нужен пакет `langchain-openai` (`poetry add langchain-openai`);
фабрика сообщит об этом понятной ошибкой `LLMConfigurationError`.

## Тесты и качество

```bash
poetry run ruff check .          # линтер
poetry run ruff format --check . # форматирование
poetry run pytest                # 151 тест, ~20 с
poetry run pytest --cov=src --cov-report=term-missing
```

Тесты не обращаются к GigaChat и не скачивают модель эмбеддингов: LLM и эмбеддер замоканы,
API-тесты используют SQLite и подменяют `get_db` / `get_rag_service`.
Покрыто: конфиг и валидаторы, безопасность (bcrypt, JWT, истечение, подмена подписи), загрузка
и чанкинг (включая cp1251 и BOM), FAISS (персистентность, битый индекс, размерность), RAG-логика,
сервисы, все роутеры и коды ошибок, compose и CI.

## CI

`.github/workflows/ci.yml` — три джоба:

1. **lint** — `ruff check` + `ruff format --check`;
2. **tests** — `pytest` с coverage, отчёт в артефактах;
3. **docker** — валидация compose и сборка обоих образов с кэшем слоёв (`type=gha`).

## Как это работает

**Ingestion**: файл → `DocumentLoader` (LangChain) → `DocumentSplitter` (1000/200, русская пунктуация)
→ `SentenceTransformerEmbedder` → нормализованные векторы в `IndexFlatIP` (+ JSON с текстами чанков).
Всё блокирующее выполняется в `asyncio.to_thread`, event loop не встаёт.

**Ответ**: вопрос → эмбеддинг → cosine top-k в FAISS → нумерованный контекст с источниками →
системный промпт «только по контексту» → LLM → ответ + `sources`. Пустая выдача обрывает цепочку
до вызова LLM.

## Обучение модели

Модель в проекте **не обучается** — это inference-only RAG:

- эмбеддинги и LLM берутся предобученными, веса не меняются;
- «знания» живут в индексе: добавили документ — дописали векторы, обновили документ — переиндексировали.

Если качество поиска окажется недостаточным, порядок действий такой:

1. Замерить `recall@k` / MRR на golden-set из 50–100 пар «вопрос → правильный фрагмент».
2. Улучшить retrieval без обучения: chunking, `top_k`, гибридный поиск (BM25 + векторы), reranker.
3. Только потом — fine-tune эмбеддера на доменных парах (contrastive loss) и переиндексация.
4. LoRA для LLM — крайняя мера и только на open-source модели: GigaChat API файнтюнинг не предоставляет,
   а для «отвечай по документам» RAG обычно эффективнее.

## Ограничения

- FAISS-индекс живёт в памяти процесса: запускайте API с одним воркером либо переходите на внешнюю
  векторную БД (Qdrant/pgvector) при горизонтальном масштабировании.
- Индекс общий для всех пользователей: разграничение доступа к документам — следующий шаг.
- Нет OCR: сканы PDF без текстового слоя не индексируются.
- Ответы не стримятся (нет SSE/WebSocket).

## Лицензия

MIT.
