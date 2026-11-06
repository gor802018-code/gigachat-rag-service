"""LLM clients behind a provider-agnostic interface."""

import base64
import binascii
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from threading import Lock
from typing import Any, Protocol, runtime_checkable

from langchain_core.messages import BaseMessage
from langchain_gigachat.chat_models import GigaChat

from src.core.config import Settings, get_settings


class LLMConfigurationError(RuntimeError):
    """Raised when the selected provider is not configured properly."""


class LLMGenerationError(RuntimeError):
    """Raised when the provider call fails."""


@dataclass(frozen=True, slots=True)
class LLMResponse:
    """Provider-independent answer."""

    content: str
    model: str
    usage: dict[str, Any] | None = None


@runtime_checkable
class LLMClient(Protocol):
    """Interface implemented by every LLM provider wrapper."""

    async def agenerate(self, messages: Sequence[BaseMessage]) -> LLMResponse:
        """Send chat messages and return the model answer."""
        ...


class LangChainChatClient:
    """Adapter around any LangChain chat model (GigaChat, OpenAI, DeepSeek)."""

    def __init__(self, chat_model: Any, model_name: str) -> None:
        self._chat_model = chat_model
        self._model_name = model_name

    @property
    def model_name(self) -> str:
        return self._model_name

    async def agenerate(self, messages: Sequence[BaseMessage]) -> LLMResponse:
        if not messages:
            msg = "messages must not be empty"
            raise ValueError(msg)

        try:
            response = await self._chat_model.ainvoke(list(messages))
        except Exception as exc:
            msg = f"LLM request to {self._model_name} failed: {exc}"
            raise LLMGenerationError(msg) from exc

        content = _extract_text(getattr(response, "content", ""))
        if not content:
            msg = "LLM returned an empty response"
            raise LLMGenerationError(msg)

        usage = getattr(response, "usage_metadata", None)
        return LLMResponse(content=content, model=self._model_name, usage=usage)


def _is_ready_authorization_key(value: str, client_id: str) -> bool:
    """True when ``value`` is already ``base64(client_id:secret)``."""
    try:
        decoded = base64.b64decode(value, validate=True).decode("utf-8")
    except (ValueError, binascii.Error, UnicodeDecodeError):
        return False
    return decoded.startswith(f"{client_id}:")


def normalize_gigachat_credentials(raw: str) -> str:
    """Accept ``client_id:client_secret``, ``client_id:<Authorization key>`` or Base64.

    GigaChat Studio shows an "Authorization key" that is already
    ``base64(client_id:client_secret)``; users often copy it next to the
    client id. GigaChat SDK puts the value into ``Authorization: Basic <value>``
    verbatim, so a raw pair has to be encoded and a ready key left untouched.
    """
    value = raw.strip()
    if value.lower().startswith("basic "):
        value = value[6:].strip()

    if ":" not in value:
        try:
            base64.b64decode(value, validate=True)
        except (ValueError, binascii.Error) as exc:
            msg = (
                "GIGACHAT_CREDENTIALS must be 'client_id:client_secret', "
                "its Base64 form or the Authorization key"
            )
            raise LLMConfigurationError(msg) from exc
        return value

    client_id, rest = value.split(":", 1)
    if _is_ready_authorization_key(rest, client_id):
        return rest
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


class GigaChatClient(LangChainChatClient):
    """GigaChat wrapper configured from application settings."""

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "GigaChatClient":
        settings = settings or get_settings()
        credentials = settings.gigachat_credentials
        if credentials is None or not credentials.get_secret_value().strip():
            msg = (
                "GIGACHAT_CREDENTIALS is not set. "
                "Pass 'client_id:client_secret' or its Base64 form from GigaChat Studio."
            )
            raise LLMConfigurationError(msg)

        chat_model = GigaChat(
            credentials=normalize_gigachat_credentials(credentials.get_secret_value()),
            scope=settings.gigachat_scope,
            model=settings.active_llm_model,
            temperature=settings.llm_temperature,
            timeout=settings.llm_timeout_seconds,
            verify_ssl_certs=settings.gigachat_verify_ssl_certs,
        )
        return cls(chat_model, model_name=settings.active_llm_model)


class LazyLLMClient:
    """Defers provider construction until the first generation call.

    Ingestion does not need an LLM, so a missing credential must not make
    ``/chat/upload`` fail; the error has to surface on ``/chat/ask``.
    """

    def __init__(self, factory: Callable[[], LLMClient], model_name: str) -> None:
        self._factory = factory
        self._model_name = model_name
        self._client: LLMClient | None = None
        self._lock = Lock()

    @property
    def model_name(self) -> str:
        return self._model_name

    def _resolve(self) -> LLMClient:
        if self._client is None:
            with self._lock:
                if self._client is None:
                    self._client = self._factory()
        return self._client

    async def agenerate(self, messages: Sequence[BaseMessage]) -> LLMResponse:
        return await self._resolve().agenerate(messages)


def create_llm_client(settings: Settings | None = None) -> LLMClient:
    """Build the client for ``LLM_PROVIDER`` from configuration."""
    settings = settings or get_settings()

    if settings.llm_provider == "gigachat":
        return GigaChatClient.from_settings(settings)

    if settings.llm_provider in {"openai", "deepseek"}:
        return _create_openai_compatible_client(settings)

    msg = f"Unsupported LLM provider: {settings.llm_provider}"
    raise LLMConfigurationError(msg)


def create_lazy_llm_client(settings: Settings | None = None) -> LLMClient:
    """Return a client that validates the provider only when it is actually used."""
    settings = settings or get_settings()
    return LazyLLMClient(
        lambda: create_llm_client(settings),
        model_name=settings.active_llm_model,
    )


def _create_openai_compatible_client(settings: Settings) -> LangChainChatClient:
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:
        msg = (
            f"LLM_PROVIDER={settings.llm_provider} requires the 'langchain-openai' package. "
            "Install it with: poetry add langchain-openai"
        )
        raise LLMConfigurationError(msg) from exc

    api_key = settings.llm_api_key
    if api_key is None or not api_key.get_secret_value().strip():
        msg = f"LLM_API_KEY is required for provider {settings.llm_provider}"
        raise LLMConfigurationError(msg)

    base_url = settings.llm_base_url or (
        "https://api.deepseek.com/v1" if settings.llm_provider == "deepseek" else None
    )
    chat_model = ChatOpenAI(
        model=settings.active_llm_model,
        api_key=api_key.get_secret_value(),
        base_url=base_url,
        temperature=settings.llm_temperature,
        timeout=settings.llm_timeout_seconds,
    )
    return LangChainChatClient(chat_model, model_name=settings.active_llm_model)


def _extract_text(content: Any) -> str:
    """Normalise text content returned by different LangChain providers."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "".join(parts).strip()
    return ""
