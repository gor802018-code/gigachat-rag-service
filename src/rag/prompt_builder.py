"""Prompt construction for the RAG chain."""

from collections.abc import Sequence

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from src.repositories.vector_repository import SearchHit

SYSTEM_PROMPT = """Ты — ассистент по внутренним документам.
Отвечай только на основе фрагментов контекста, которые передаёт пользователь.

Правила:
1. Не используй внешние знания и ничего не додумывай.
2. Если в контексте нет ответа, ответь: "В загруженных документах нет ответа на этот вопрос."
3. Ставь ссылки на источники в формате [1], [2] — номера соответствуют фрагментам контекста.
4. Отвечай на языке вопроса, кратко и по существу.
"""

NO_CONTEXT_PLACEHOLDER = "Контекст отсутствует: подходящих фрагментов не найдено."


class PromptBuilder:
    """Builds chat messages containing retrieved context and the question."""

    def __init__(self, system_prompt: str = SYSTEM_PROMPT) -> None:
        if not system_prompt.strip():
            msg = "system_prompt must not be empty"
            raise ValueError(msg)
        self._system_prompt = system_prompt.strip()

    @property
    def system_prompt(self) -> str:
        return self._system_prompt

    def build(self, question: str, hits: Sequence[SearchHit]) -> list[BaseMessage]:
        """Return ``[SystemMessage, HumanMessage]`` ready for a chat model."""
        cleaned = question.strip()
        if not cleaned:
            msg = "Question must not be empty"
            raise ValueError(msg)

        context = self.format_context(hits)
        human_message = (
            f"Контекст:\n{context}\n\n"
            f"Вопрос: {cleaned}\n\n"
            "Ответь только по контексту выше и укажи номера источников."
        )
        return [SystemMessage(content=self._system_prompt), HumanMessage(content=human_message)]

    def format_context(self, hits: Sequence[SearchHit]) -> str:
        """Render retrieved chunks as numbered, citable blocks."""
        if not hits:
            return NO_CONTEXT_PLACEHOLDER

        blocks: list[str] = []
        for number, hit in enumerate(hits, start=1):
            file_name = hit.metadata.get("file_name", "неизвестный источник")
            chunk_index = hit.metadata.get("chunk_index", "?")
            blocks.append(
                f"[{number}] Источник: {file_name}, фрагмент {chunk_index}\n{hit.content}"
            )
        return "\n\n".join(blocks)
