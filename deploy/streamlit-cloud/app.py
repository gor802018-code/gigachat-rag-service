"""RAG-демо для Streamlit Community Cloud.

Один процесс: без FastAPI и без PostgreSQL. Документы живут в памяти сессии,
векторы — в FAISS, ответы — через GigaChat. Модель по умолчанию e5-small,
чтобы уложиться в 1 ГБ памяти бесплатного инстанса.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path

import streamlit as st

# --- секреты Streamlit Cloud -> переменные окружения (до импорта src) ---
_SECRET_KEYS = (
    "GIGACHAT_CREDENTIALS",
    "GIGACHAT_SCOPE",
    "GIGACHAT_MODEL",
    "LLM_PROVIDER",
    "LLM_API_KEY",
    "LLM_BASE_URL",
    "JWT_SECRET_KEY",
    "EMBEDDING_MODEL_NAME",
    "RETRIEVER_TOP_K",
    "RETRIEVER_MIN_SCORE",
    "CHUNK_SIZE",
    "CHUNK_OVERLAP",
    "GIGACHAT_VERIFY_SSL_CERTS",
)
try:
    _raw_secrets = dict(st.secrets)
except Exception:  # локально файла secrets.toml может не быть
    _raw_secrets = {}

# Секреты можно писать и плоско, и секциями ([gigachat] CREDENTIALS = ...),
# регистр ключа не важен — собираем плоский словарь.
_secrets: dict[str, object] = {}
for _name, _value in _raw_secrets.items():
    if isinstance(_value, Mapping):
        _secrets.update({str(k).upper(): v for k, v in _value.items()})
    else:
        _secrets[str(_name).upper()] = _value

for _key in _SECRET_KEYS:
    _value = _secrets.get(_key)
    if _value is None:
        continue
    _text = str(_value).strip().strip("\"'").strip()
    if _text and not os.getenv(_key):
        os.environ[_key] = _text

GIGACHAT_READY = bool(os.environ.get("GIGACHAT_CREDENTIALS", "").strip())

os.environ.setdefault("EMBEDDING_MODEL_NAME", "intfloat/multilingual-e5-small")
os.environ.setdefault("RETRIEVER_MIN_SCORE", "0.78")
os.environ.setdefault("APP_ENV", "production")
# JWT в этом демо не используется (входа нет), но валидатор настроек требует
# недефолтное значение в production — задаём демо-значение, если секрет не добавлен.
os.environ.setdefault("JWT_SECRET_KEY", "streamlit-demo-jwt-unused-local-only")

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.core.config import get_settings  # noqa: E402
from src.ingestion.loader import DocumentLoader, DocumentLoadError  # noqa: E402
from src.ingestion.splitter import DocumentSplitter  # noqa: E402
from src.rag.embeddings import SentenceTransformerEmbedder  # noqa: E402
from src.rag.llm_client import LLMConfigurationError, LLMGenerationError, create_lazy_llm_client  # noqa: E402
from src.rag.prompt_builder import PromptBuilder  # noqa: E402
from src.rag.retriever import Retriever  # noqa: E402
from src.repositories.vector_repository import VectorRepository  # noqa: E402

st.set_page_config(page_title="RAG-демо: вопросы по документам", page_icon="🔎", layout="centered")
st.title("RAG-демо")
st.caption("Загрузите документы — и задавайте вопросы. Ответ строится только по ним.")


@st.cache_resource(show_spinner="Загружаю модель эмбеддингов (первый раз ~1 минута)…")
def get_pipeline() -> tuple[Retriever, PromptBuilder, SentenceTransformerEmbedder]:
    embedder = SentenceTransformerEmbedder.from_settings()
    index_dir = Path(tempfile.mkdtemp(prefix="faiss-"))
    repository = VectorRepository(embedder, index_dir)
    retriever = Retriever.from_settings(repository)
    return retriever, PromptBuilder(), embedder


retriever, prompt_builder, _embedder = get_pipeline()
repository = retriever._repository

# Настройки кэшируются (lru_cache) при первом обращении, поэтому ключ,
# добавленный в Secrets после старта приложения, иначе не подхватится.
get_settings.cache_clear()
llm_client = create_lazy_llm_client()

if "chunks" not in st.session_state:
    st.session_state.chunks = 0
if "history" not in st.session_state:
    st.session_state.history = []
if "indexed_files" not in st.session_state:
    st.session_state.indexed_files = []

with st.sidebar:
    st.subheader("Документы")
    uploaded = st.file_uploader(
        "PDF, DOCX, TXT или MD",
        type=["pdf", "docx", "txt", "md"],
        accept_multiple_files=True,
    )
    if st.button("Проиндексировать", type="primary", disabled=not uploaded):
        loader = DocumentLoader()
        splitter = DocumentSplitter.from_settings()
        added = 0
        with st.spinner("Читаю и разбиваю на фрагменты…"):
            for file in uploaded or []:
                suffix = Path(file.name).suffix.lower()
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp.write(file.getbuffer())
                    tmp_path = Path(tmp.name)
                try:
                    documents = loader.load(tmp_path)
                    chunks = splitter.split(documents)
                    for chunk in chunks:
                        chunk.metadata["source"] = file.name
                    repository.add_documents(chunks, user_id="demo")
                    added += len(chunks)
                    if file.name not in st.session_state.indexed_files:
                        st.session_state.indexed_files.append(file.name)
                except (DocumentLoadError, ValueError) as exc:
                    st.error(f"{file.name}: {exc}")
                finally:
                    tmp_path.unlink(missing_ok=True)
        st.session_state.chunks = repository.count
        st.success(f"Добавлено фрагментов: {added}. Всего в индексе: {repository.count}")

    st.divider()
    st.metric("Фрагментов в индексе", repository.count)
    if st.session_state.indexed_files:
        st.caption("Файлы: " + ", ".join(st.session_state.indexed_files))
    if st.button("Очистить индекс"):
        repository.reset()
        st.session_state.chunks = 0
        st.session_state.indexed_files = []
        st.session_state.history = []
        st.rerun()

    st.divider()
    if GIGACHAT_READY:
        st.caption("Ключ GigaChat: задан")
    else:
        st.error("Ключ GigaChat не найден: добавьте GIGACHAT_CREDENTIALS в Secrets приложения.")
    st.caption(
        "Демо: данные живут в памяти и пропадают при перезапуске. "
        "Загружайте только тестовые документы."
    )

question = st.chat_input("Спросите что-нибудь по документам")

for entry in st.session_state.history:
    with st.chat_message(entry["role"]):
        st.markdown(entry["content"])
        for hit in entry.get("sources", []):
            st.caption(f"[{hit['n']}] {hit['source']} · сходство {hit['score']:.2f}")

if question:
    st.session_state.history.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        if repository.count == 0:
            answer = "Сначала загрузите документы в левой панели и нажмите «Проиндексировать»."
            st.markdown(answer)
            st.session_state.history.append({"role": "assistant", "content": answer})
        else:
            hits = retriever.retrieve(question, user_id="demo")
            if not hits:
                answer = "В загруженных документах нет ответа на этот вопрос."
                st.markdown(answer)
                st.session_state.history.append({"role": "assistant", "content": answer})
            else:
                messages = prompt_builder.build(question, hits)
                try:
                    with st.spinner("Думаю…"):
                        response = asyncio.run(llm_client.agenerate(messages))
                    answer = response.content
                except (LLMConfigurationError, LLMGenerationError) as exc:
                    answer = f"Ошибка модели: {exc}"
                st.markdown(answer)

                sources = []
                for number, hit in enumerate(hits, start=1):
                    metadata = hit.metadata
                    source = metadata.get("source") or metadata.get("file_name") or "документ"
                    st.caption(f"[{number}] {source} · сходство {hit.score:.2f}")
                    sources.append({"n": number, "source": source, "score": hit.score})

                st.session_state.history.append(
                    {"role": "assistant", "content": answer, "sources": sources}
                )
