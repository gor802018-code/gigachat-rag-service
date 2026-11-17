---
title: RAG Demo — документы и GigaChat
emoji: 🔎
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: RAG-сервис — загрузка документов и ответы по ним
---

# RAG-демо

Демонстрация RAG-сервиса: загружаете документы (PDF, DOCX, TXT, MD), задаёте вопросы и получаете ответ только по ним, со ссылками на фрагменты.

Внутри контейнера: FastAPI (`127.0.0.1:8000`), SQLite в `/data`, Streamlit на `7860` (его и открывает Hugging Face).

## Секреты

Задаются в **Settings → Variables and secrets**:

| Имя | Значение |
|---|---|
| `GIGACHAT_CREDENTIALS` | `client_id:client_secret` из кабинета GigaChat |
| `GIGACHAT_SCOPE` | `GIGACHAT_API_PERS` |
| `GIGACHAT_MODEL` | `GigaChat-2` |
| `JWT_SECRET_KEY` | случайная длинная строка |
| `LLM_PROVIDER` | `gigachat` |

## Ограничения

- База в `/data` не переживает рестарт без платного persistent storage.
- CPU-инстанс: первый ответ после прогрева модели — 1–3 минуты.
- Только тестовые документы: персональные данные и коммерческую тайну не загружать.
- Для реальной работы — деплой на VPS по `DEPLOY.md` в основном репозитории.
