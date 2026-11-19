"""Единая точка конфигурации. Бренд (white-label) живёт в branding/brand.json."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_DEFAULT_BRAND = {
    "product_name": "Konoden AI",
    "tagline": "AI video editor",
    "cli_name": "konoden",
    "accent_color": "#6C5CE7",
    "logo_path": None,
    "company": "Konoden",
}


def _load_dotenv() -> None:
    path = ROOT / ".env"
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _load_brand() -> dict:
    brand = dict(_DEFAULT_BRAND)
    path = ROOT / "branding" / "brand.json"
    if path.exists():
        brand.update(json.loads(path.read_text(encoding="utf-8")))
    return brand


@dataclass(frozen=True)
class Settings:
    llm_backend: str = "ollama"
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b-instruct"
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_chat_model: str = "qwen/qwen-2.5-72b-instruct"
    stt_model: str = "openai/whisper-large-v3"
    brand: dict = field(default_factory=lambda: dict(_DEFAULT_BRAND))

    @classmethod
    def load(cls) -> "Settings":
        _load_dotenv()
        env = os.environ.get
        return cls(
            llm_backend=env("KONODEN_LLM_BACKEND", "ollama").lower(),
            ollama_host=env("OLLAMA_HOST", "http://localhost:11434").rstrip("/"),
            ollama_model=env("OLLAMA_MODEL", "qwen2.5:7b-instruct"),
            openrouter_api_key=env("OPENROUTER_API_KEY", ""),
            openrouter_base_url=env("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/"),
            openrouter_chat_model=env("OPENROUTER_CHAT_MODEL", "qwen/qwen-2.5-72b-instruct"),
            stt_model=env("KONODEN_STT_MODEL", "openai/whisper-large-v3"),
            brand=_load_brand(),
        )
