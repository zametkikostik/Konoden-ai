from __future__ import annotations

import requests

from .base import LLMBackend, LLMError


class OllamaBackend(LLMBackend):
    name = "ollama"

    def __init__(self, host: str, model: str, timeout: int = 600):
        self.host = host.rstrip("/")
        self.model = model
        self.timeout = timeout

    def generate_json(self, system: str, user: str, schema: dict) -> str:
        payload = {
            "model": self.model,
            "stream": False,
            "format": schema,  # structured outputs: Ollama жёстко держит JSON-схему
            "options": {"temperature": 0.2},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        try:
            r = requests.post(f"{self.host}/api/chat", json=payload, timeout=self.timeout)
        except requests.ConnectionError as e:
            raise LLMError(f"Ollama недоступна на {self.host}. Запущена ли она? ({e})") from e
        if r.status_code != 200:
            raise LLMError(f"Ollama {r.status_code}: {r.text[:500]}")
        return r.json()["message"]["content"]
