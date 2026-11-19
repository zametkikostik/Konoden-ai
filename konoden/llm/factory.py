from __future__ import annotations

from ..config import Settings
from .base import LLMBackend, LLMError
from .ollama import OllamaBackend
from .openrouter import OpenRouterBackend


def make_backend(s: Settings) -> LLMBackend:
    if s.llm_backend == "ollama":
        return OllamaBackend(s.ollama_host, s.ollama_model)
    if s.llm_backend == "openrouter":
        return OpenRouterBackend(s.openrouter_api_key, s.openrouter_chat_model, s.openrouter_base_url)
    raise LLMError(f"Неизвестный бэкенд: {s.llm_backend!r} (ожидалось ollama|openrouter)")
