"""Tests for the provider-agnostic LLM client."""

import sys
import types
from collections.abc import Callable, Sequence
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from src.core.config import Settings
from src.rag.llm_client import (
    GigaChatClient,
    LangChainChatClient,
    LLMClient,
    LLMConfigurationError,
    LLMGenerationError,
    LLMResponse,
    create_llm_client,
)

USAGE = {"input_tokens": 12, "output_tokens": 8, "total_tokens": 20}


class FakeChatModel:
    """Minimal async chat model double."""

    def __init__(
        self,
        content: Any = "Ответ по контексту [1].",
        usage: dict[str, int] | None = USAGE,
        error: Exception | None = None,
    ) -> None:
        self._content = content
        self._usage = usage
        self._error = error
        self.calls: list[list[BaseMessage]] = []

    async def ainvoke(self, messages: Sequence[BaseMessage]) -> AIMessage:
        self.calls.append(list(messages))
        if self._error is not None:
            raise self._error
        return AIMessage(content=self._content, usage_metadata=self._usage)


async def test_agenerate_returns_provider_independent_response() -> None:
    model = FakeChatModel()
    client = LangChainChatClient(model, model_name="GigaChat")

    response = await client.agenerate([HumanMessage(content="Какой срок оплаты?")])

    assert response == LLMResponse(content="Ответ по контексту [1].", model="GigaChat", usage=USAGE)
    assert len(model.calls) == 1


async def test_agenerate_joins_content_blocks() -> None:
    model = FakeChatModel(content=[{"type": "text", "text": "Ответ "}, "целиком"])
    client = LangChainChatClient(model, model_name="GigaChat")

    response = await client.agenerate([HumanMessage(content="Вопрос")])

    assert response.content == "Ответ целиком"


async def test_empty_messages_are_rejected() -> None:
    client = LangChainChatClient(FakeChatModel(), model_name="GigaChat")

    with pytest.raises(ValueError, match="messages"):
        await client.agenerate([])


async def test_provider_error_is_wrapped() -> None:
    client = LangChainChatClient(
        FakeChatModel(error=RuntimeError("timeout")), model_name="GigaChat"
    )

    with pytest.raises(LLMGenerationError, match="timeout"):
        await client.agenerate([HumanMessage(content="Вопрос")])


async def test_empty_response_is_rejected() -> None:
    client = LangChainChatClient(FakeChatModel(content="   "), model_name="GigaChat")

    with pytest.raises(LLMGenerationError, match="empty"):
        await client.agenerate([HumanMessage(content="Вопрос")])


def test_missing_credentials_raise_configuration_error(
    make_settings: Callable[..., Settings],
) -> None:
    with pytest.raises(LLMConfigurationError, match="GIGACHAT_CREDENTIALS"):
        GigaChatClient.from_settings(make_settings())


def test_blank_credentials_raise_configuration_error(
    make_settings: Callable[..., Settings],
) -> None:
    with pytest.raises(LLMConfigurationError, match="GIGACHAT_CREDENTIALS"):
        GigaChatClient.from_settings(make_settings(gigachat_credentials="   "))


def test_gigachat_client_is_built_from_settings(
    make_settings: Callable[..., Settings],
) -> None:
    settings = make_settings(
        gigachat_credentials="client-id:client-secret",
        gigachat_scope="GIGACHAT_API_CORP",
        llm_temperature=0.3,
        llm_timeout_seconds=15,
    )

    with patch("src.rag.llm_client.GigaChat") as giga_chat:
        client = GigaChatClient.from_settings(settings)

    giga_chat.assert_called_once_with(
        credentials="client-id:client-secret",
        scope="GIGACHAT_API_CORP",
        model="GigaChat",
        temperature=0.3,
        timeout=15,
        verify_ssl_certs=False,
    )
    assert client.model_name == "GigaChat"


def test_factory_builds_gigachat_by_default(make_settings: Callable[..., Settings]) -> None:
    settings = make_settings(gigachat_credentials="client-id:client-secret")

    with patch("src.rag.llm_client.GigaChat"):
        client = create_llm_client(settings)

    assert isinstance(client, GigaChatClient)


def test_factory_switches_provider_to_deepseek(
    make_settings: Callable[..., Settings],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: dict[str, Any] = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs: Any) -> None:
            created.update(kwargs)

    fake_module = types.ModuleType("langchain_openai")
    fake_module.ChatOpenAI = FakeChatOpenAI  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "langchain_openai", fake_module)

    settings = make_settings(llm_provider="deepseek", llm_api_key="sk-test")
    client = create_llm_client(settings)

    assert isinstance(client, LangChainChatClient)
    assert client.model_name == "deepseek-chat"
    assert created["base_url"] == "https://api.deepseek.com/v1"
    assert created["api_key"] == "sk-test"


def test_factory_requires_api_key_for_openai_providers(
    make_settings: Callable[..., Settings],
) -> None:
    with pytest.raises(LLMConfigurationError, match=r"langchain-openai|LLM_API_KEY"):
        create_llm_client(make_settings(llm_provider="openai"))


def test_llm_client_protocol_is_implemented() -> None:
    assert isinstance(GigaChatClient(MagicMock(), model_name="GigaChat"), LLMClient)
