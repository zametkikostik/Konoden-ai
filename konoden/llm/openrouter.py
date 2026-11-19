from __future__ import annotations

import requests

from .base import LLMBackend, LLMError


class OpenRouterBackend(LLMBackend):
    """Опциональный облачный бэкенд для планирования (для клиентов без GPU)."""

    name = "openrouter"

    def __init__(self, api_key: str, model: str, base_url: str, timeout: int = 180):
        if not api_key:
            raise LLMError("OPENROUTER_API_KEY не задан")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def generate_json(self, system: str, user: str, schema: dict) -> str:
        payload = {
            "model": self.model,
            "temperature": 0.2,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "timeline", "strict": False, "schema": schema},
            },
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        r = requests.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=payload,
            timeout=self.timeout,
        )
        if r.status_code != 200:
            raise LLMError(f"OpenRouter {r.status_code}: {r.text[:500]}")
        return r.json()["choices"][0]["message"]["content"]
