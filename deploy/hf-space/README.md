---
title: RAG Demo — документы и GigaChat
emoji: 🔎
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: RAG-сервис: загрузка документов и ответы по ним
---

# RAG-демо на Hugging Face Spaces

Демонстрация сервиса Retrieval-Augmented Generation: загружаете документы (PDF, DOCX, TXT, MD) — задаёте вопросы, получаете ответ только по этим документам, с указанием фрагментов-источников.

Внутри контейнера работают три части:

- **FastAPI** (`127.0.0.1:8000`) — загрузка, нарезка на чанки, эмбеддинги `multilingual-e5-base`, поиск FAISS, вызов GigaChat;
- **SQLite** — пользователи, документы и история диалогов (в демо файл в `/data`);
- **Streamlit** (`0.0.0.0:7860`) — интерфейс, который открывает Hugging Face.

Наружу смотрит только `7860`. Регистрация и вход — прямо в интерфейсе, аккаунт создаётся на лету.

## Как получить доступ

1. Создайте Space: **New Space → Docker → Blank**.
2. В **Settings → Variables and secrets** добавьте секреты:

| Имя | Значение |
|---|---|
| `GIGACHAT_CREDENTIALS` | `client_id:client_secret` из личного кабинета GigaChat |
| `GIGACHAT_SCOPE` | `GIGACHAT_API_PERS` |
| `GIGACHAT_MODEL` | `GigaChat-2` |
| `JWT_SECRET_KEY` | любая длинная случайная строка |
| `LLM_PROVIDER` | `gigachat` |

3. Загрузите в Space репозиторий с кодом (`deploy/hf-space/publish.sh` собирает его в отдельной папке).
4. Дождитесь сборки: первый билд 8–15 минут (ставится torch CPU и sentence-transformers).

## Ограничения демо

- База в `/data` не переживает перезапуск Space без платного persistent storage — после рестарта документы придётся загрузить заново.
- CPU-инстанс: первый запрос к модели прогревается 1–3 минуты, дальше ответы за секунды.
- Это демонстрация, а не продакшн: нет HTTPS-политики на уровне приложения, бэкапов и ротации ключей. Для реальной работы — развёртывание на VPS по инструкции `DEPLOY.md`.
- Загружайте только тестовые документы. Не отправляйте персональные данные и коммерческую тайну: бесплатный Space не предназначен для конфиденциальной информации.

## Стек

Python 3.11 · FastAPI · SQLAlchemy (async) · FAISS · sentence-transformers `intfloat/multilingual-e5-base` · GigaChat API · Streamlit
