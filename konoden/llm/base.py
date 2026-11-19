from __future__ import annotations

from abc import ABC, abstractmethod


class LLMError(RuntimeError):
    pass


class LLMBackend(ABC):
    """Единый интерфейс: Ollama и OpenRouter взаимозаменяемы."""

    name: str = "base"

    @abstractmethod
    def generate_json(self, system: str, user: str, schema: dict) -> str:
        """Вернуть сырой JSON-текст, соответствующий schema."""
