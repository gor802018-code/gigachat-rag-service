# RAG Service

Production-ready Retrieval-Augmented Generation service: FastAPI + FAISS + GigaChat.
Портфолио-проект с layered architecture, DI, JWT-аутентификацией, тестами и CI/CD.

## Стек

| Слой | Технологии |
| --- | --- |
| API | FastAPI, Uvicorn, Pydantic v2, pydantic-settings |
| Бизнес-логика | Service layer, Dependency Injection |
| RAG | LangChain, sentence-transformers, FAISS |
| LLM | GigaChat (`langchain-gigachat`), провайдер меняется через env |
| Хранилище метаданных | PostgreSQL, SQLAlchemy 2 (async), Alembic |
| Auth | JWT (python-jose), passlib/bcrypt |
| Frontend | Streamlit |
| Качество | pytest, pytest-asyncio, httpx, Ruff |
| Инфраструктура | Docker (multi-stage, non-root), docker-compose, GitHub Actions |

## Архитектура

```
src/
├── api/              # HTTP-слой
│   ├── routers/      # auth, chat, ingest — только эндпоинты
│   ├── schemas.py    # Pydantic-схемы запросов/ответов
│   └── dependencies.py  # DI: get_db, get_current_user, get_llm_client
├── services/         # бизнес-логика: AuthService, RAGService
├── repositories/     # доступ к данным: User/Document/Vector
├── core/             # config, logging, security
├── ingestion/        # loader + splitter
├── rag/              # embeddings, retriever, prompt_builder, llm_client
└── main.py           # точка входа ASGI
```

Правило зависимостей: `api → services → repositories → core`.
Слой `rag` подключается только через сервисы и DI-провайдеры.

## Быстрый старт

```bash
poetry install
cp .env.example .env          # заполнить GIGACHAT_CREDENTIALS и DATABASE_URL
poetry run uvicorn src.main:app --reload
```

Проверка: <http://127.0.0.1:8000/health>, документация — <http://127.0.0.1:8000/docs>.

## Качество кода

```bash
poetry run ruff check .
poetry run pytest
```

## Docker

```bash
docker build -t rag-service .
docker run --rm -p 8000:8000 --env-file .env rag-service
```

Образ собирается в два этапа: зависимости ставятся в builder-слое, в runtime попадает только
venv и исходники; процесс работает от непривилегированного пользователя `app`.

## Roadmap

- [x] Шаг 1. Каркас проекта и layered structure
- [ ] Шаг 2. Core: config, logging, security
- [ ] Шаг 3. Ingestion: загрузка и чанкинг документов
- [ ] Шаг 4. Векторное хранилище FAISS
- [ ] Шаг 5. RAG-логика и клиент GigaChat
- [ ] Шаг 6. Service layer
- [ ] Шаг 7. FastAPI роутеры, DI, JWT
- [ ] Шаг 8. Streamlit + docker-compose
- [ ] Шаг 9. CI/CD
- [ ] Шаг 10. Документация
