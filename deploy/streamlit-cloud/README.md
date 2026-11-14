# Демо на Streamlit Community Cloud

Один процесс без FastAPI и PostgreSQL: документы индексируются в память сессии, векторы — FAISS, эмбеддинги — `intfloat/multilingual-e5-small` (118M, чтобы уложиться в 1 ГБ памяти бесплатного инстанса), ответы — GigaChat.

## Что задеплоить

- **Репозиторий:** этот же, `gigachat-rag-service` (публичный).
- **Main file path:** `deploy/streamlit-cloud/app.py`
- **Python:** 3.11 (`runtime.txt` рядом).

Зависимости ставятся из `deploy/streamlit-cloud/requirements.txt`.

## Секреты

В дашборде Cloud: **App → Settings → Secrets**, формат TOML:

```toml
GIGACHAT_CREDENTIALS = "client_id:client_secret"
GIGACHAT_SCOPE = "GIGACHAT_API_PERS"
GIGACHAT_MODEL = "GigaChat-2"
LLM_PROVIDER = "gigachat"
JWT_SECRET_KEY = "не используется, но пусть будет"
EMBEDDING_MODEL_NAME = "intfloat/multilingual-e5-small"
RETRIEVER_MIN_SCORE = "0.78"
```

Секреты приложение само переносит в переменные окружения до импорта модулей `src`.

## Как это работает

1. Пользователь загружает PDF/DOCX/TXT/MD в сайдбаре.
2. `DocumentLoader` читает текст, `DocumentSplitter` режет на чанки 1000/200.
3. `VectorRepository` считает эмбеддинги e5-small и кладёт в FAISS (косинус).
4. Вопрос → эмбеддинг → поиск top-k с порогом сходства → `PromptBuilder` → GigaChat.
5. Если релевантных фрагментов нет, модель не вызывается — возвращается честное «в документах нет ответа».

## Ограничения

- Индекс и загруженные файлы живут в памяти: перезапуск приложения (или простой) очищает данные.
- Первый запуск грузит модель ~470 МБ, это 1–2 минуты; дальше — из кэша инстанса.
- 1 ГБ RAM: не загружайте десятки больших PDF за раз, лучше по 2–3 документа.
- Только тестовые документы: персональные данные и коммерческую тайну в публичное демо не кладём.
- Для реальной работы — VPS по `DEPLOY.md`: там PostgreSQL, персистентный индекс, HTTPS и бэкапы.

## Локальный запуск

```bash
pip install -r deploy/streamlit-cloud/requirements.txt
export GIGACHAT_CREDENTIALS="client_id:client_secret"
streamlit run deploy/streamlit-cloud/app.py
```
