"""Streamlit chat frontend for the RAG service."""

import os
from typing import Any

import httpx
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
API_PREFIX = "/api/v1"
REQUEST_TIMEOUT = 600.0
ALLOWED_EXTENSIONS = ["pdf", "txt", "md", "docx"]

st.set_page_config(page_title="RAG Chat", page_icon="📚", layout="centered")


def _api_url(path: str) -> str:
    return f"{API_BASE_URL}{API_PREFIX}{path}"


def _headers() -> dict[str, str]:
    token = st.session_state.get("token")
    return {"Authorization": f"Bearer {token}"} if token else {}


def _error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return f"HTTP {response.status_code}"
    if isinstance(payload, dict) and "detail" in payload:
        detail = payload["detail"]
        if isinstance(detail, list):
            return "; ".join(str(item.get("msg", item)) for item in detail)
        return str(detail)
    return f"HTTP {response.status_code}"


def _init_state() -> None:
    st.session_state.setdefault("token", None)
    st.session_state.setdefault("email", None)
    st.session_state.setdefault("messages", [])
    st.session_state.setdefault("documents", [])


def _request(method: str, path: str, **kwargs: Any) -> httpx.Response:
    with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
        return client.request(method, _api_url(path), **kwargs)


def login(email: str, password: str) -> bool:
    """Authenticate and store the access token in the session."""
    try:
        response = _request("POST", "/auth/login", json={"email": email, "password": password})
    except httpx.RequestError as exc:
        st.error(f"API недоступен: {exc}")
        return False

    if response.status_code != 200:
        st.error(_error_detail(response))
        return False

    payload = response.json()
    st.session_state["token"] = payload["access_token"]
    st.session_state["email"] = email
    return True


def register(email: str, password: str) -> bool:
    """Create an account and log in right away."""
    try:
        response = _request(
            "POST",
            "/auth/register",
            json={"email": email, "password": password},
        )
    except httpx.RequestError as exc:
        st.error(f"API недоступен: {exc}")
        return False

    if response.status_code != 201:
        st.error(_error_detail(response))
        return False

    st.success("Аккаунт создан")
    return login(email, password)


def upload_document(file_name: str, payload: bytes, content_type: str) -> bool:
    """Send a document to the ingestion endpoint."""
    try:
        response = _request(
            "POST",
            "/chat/upload",
            headers=_headers(),
            files={"file": (file_name, payload, content_type)},
        )
    except httpx.RequestError as exc:
        st.error(f"API недоступен: {exc}")
        return False

    if response.status_code != 201:
        st.error(_error_detail(response))
        return False

    result = response.json()
    st.session_state["documents"].append(
        {
            "file_name": result["file_name"],
            "chunks": result["chunks"],
            "document_id": result["document_id"],
        }
    )
    st.success(f"{result['file_name']}: {result['chunks']} фрагментов")
    return True


def ask_question(question: str) -> None:
    """Ask a question and append the grounded answer to the chat."""
    st.session_state["messages"].append({"role": "user", "content": question})

    try:
        with st.spinner("Думаю над ответом…"):
            response = _request(
                "POST",
                "/chat/ask",
                headers=_headers(),
                json={"question": question},
            )
    except httpx.RequestError as exc:
        st.session_state["messages"].append(
            {"role": "assistant", "content": f"API недоступен: {exc}", "sources": []}
        )
        return

    if response.status_code != 200:
        st.session_state["messages"].append(
            {"role": "assistant", "content": _error_detail(response), "sources": []}
        )
        return

    payload = response.json()
    st.session_state["messages"].append(
        {
            "role": "assistant",
            "content": payload["answer"],
            "sources": payload.get("sources", []),
        }
    )


def load_history() -> None:
    """Replace the local chat with the server-side history."""
    try:
        response = _request("GET", "/chat/history", headers=_headers())
    except httpx.RequestError as exc:
        st.error(f"API недоступен: {exc}")
        return

    if response.status_code != 200:
        st.error(_error_detail(response))
        return

    messages: list[dict[str, Any]] = []
    for item in reversed(response.json()):
        messages.append({"role": "user", "content": item["question"]})
        messages.append(
            {
                "role": "assistant",
                "content": item["answer"],
                "sources": item.get("sources", []),
            }
        )
    st.session_state["messages"] = messages


def logout() -> None:
    st.session_state["token"] = None
    st.session_state["email"] = None
    st.session_state["messages"] = []
    st.session_state["documents"] = []


def _render_auth() -> None:
    st.title("📚 RAG Chat")
    st.caption("Вопросы по вашим документам: FAISS + GigaChat")

    login_tab, register_tab = st.tabs(["Вход", "Регистрация"])

    with login_tab, st.form("login_form"):
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Пароль", type="password", key="login_password")
        if st.form_submit_button("Войти", use_container_width=True) and login(email, password):
            st.rerun()

    with register_tab, st.form("register_form"):
        email = st.text_input("Email", key="register_email")
        password = st.text_input(
            "Пароль (минимум 8 символов)",
            type="password",
            key="register_password",
        )
        if st.form_submit_button("Зарегистрироваться", use_container_width=True) and register(
            email, password
        ):
            st.rerun()


def _render_sidebar() -> None:
    with st.sidebar:
        st.header("Документы")
        uploaded = st.file_uploader("PDF, TXT, MD или DOCX", type=ALLOWED_EXTENSIONS)
        if uploaded is not None and st.button("Загрузить", use_container_width=True):
            upload_document(
                uploaded.name,
                uploaded.getvalue(),
                uploaded.type or "application/octet-stream",
            )

        if st.session_state["documents"]:
            st.subheader("В индексе")
            for document in st.session_state["documents"]:
                st.caption(f"• {document['file_name']} — {document['chunks']} фрагм.")

        st.divider()
        if st.button("Загрузить историю", use_container_width=True):
            load_history()

        st.divider()
        st.caption(f"Вы вошли как {st.session_state['email']}")
        if st.button("Выйти", use_container_width=True):
            logout()
            st.rerun()


def _render_chat() -> None:
    st.title("📚 RAG Chat")

    if not st.session_state["messages"]:
        st.info("Загрузите документ в панели слева и задайте вопрос.")

    for message in st.session_state["messages"]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            for source in message.get("sources", []):
                page = source.get("page")
                page_part = f", стр. {page}" if page is not None else ""
                st.caption(
                    f"Источник: {source.get('file_name', '—')}"
                    f"{page_part}, фрагмент {source.get('chunk_index', '?')}, "
                    f"score {source.get('score', 0):.2f}"
                )

    with st.form("ask_form", clear_on_submit=True):
        question = st.text_area(
            "Вопрос",
            height=160,
            placeholder="Спросите что-нибудь по документам…",
            label_visibility="collapsed",
        )
        submitted = st.form_submit_button("Отправить", use_container_width=True)

    if submitted and question.strip():
        ask_question(question.strip())
        st.rerun()


def main() -> None:
    _init_state()
    if not st.session_state["token"]:
        _render_auth()
        return
    _render_sidebar()
    _render_chat()


if __name__ == "__main__":
    main()
