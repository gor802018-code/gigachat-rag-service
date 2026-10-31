"""LLM clients behind a provider-agnostic interface."""

from collections.abc import Sequence
from dataclasses import dataclass
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


class GigaChatClient(LangChainChatClient):
    """GigaChat wrapper configured from application settings."""

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "GigaChatClient":
        settings = settings or get_settings()
        credentials = settings.gigachat_credentials
        if credentials is None or not credentials.get_secret_value().strip():
            msg = (
                "GIGACHAT_CREDENTIALS is not set. "
                "Pass the Base64 'client_id:client_secret' pair from GigaChat Studio."
            )
            raise LLMConfigurationError(msg)

        chat_model = GigaChat(
            credentials=credentials.get_secret_value(),
            scope=settings.gigachat_scope,
            model=settings.active_llm_model,
            temperature=settings.llm_temperature,
            timeout=settings.llm_timeout_seconds,
            verify_ssl_certs=settings.gigachat_verify_ssl_certs,
        )
        return cls(chat_model, model_name=settings.active_llm_model)


def create_llm_client(settings: Settings | None = None) -> LLMClient:
    """Build the client for ``LLM_PROVIDER`` from configuration."""
    settings = settings or get_settings()

    if settings.llm_provider == "gigachat":
        return GigaChatClient.from_settings(settings)

    if settings.llm_provider in {"openai", "deepseek"}:
        return _create_openai_compatible_client(settings)

    msg = f"Unsupported LLM provider: {settings.llm_provider}"
    raise LLMConfigurationError(msg)


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
