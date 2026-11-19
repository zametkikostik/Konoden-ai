"""Планировщик: бриф -> валидный Timeline. LLM только думает, не монтирует."""
from __future__ import annotations

import json

from pydantic import ValidationError

from .core.schema import Timeline, timeline_json_schema
from .llm.base import LLMBackend, LLMError

SYSTEM = """Ты — монтажёр-планировщик. По брифу составь таймлайн видео в виде JSON.
Правила:
- Каждый клип — одна сцена, 2-12 секунд.
- kind: footage (стоковое видео), screencast (запись экрана сайта/приложения),
  infographic (анимированная графика/диаграмма), title (титр).
- query: для footage — английский поисковый запрос 2-5 слов; для screencast —
  что именно показать; для infographic — какие данные визуализировать.
- voiceover: короткий текст озвучки сцены, на языке брифа.
- src оставляй null: файлы подбирает система.
- Отвечай ТОЛЬКО JSON по схеме, без пояснений."""


def plan_timeline(
    backend: LLMBackend,
    brief: str,
    *,
    target_seconds: int = 60,
    width: int = 1920,
    height: int = 1080,
    fps: int = 30,
    retries: int = 3,
) -> Timeline:
    schema = timeline_json_schema()
    user = (
        f"Бриф: {brief}\n"
        f"Целевая длительность: ~{target_seconds} сек. "
        f"Формат: {width}x{height}, {fps} fps."
    )
    last_error = ""
    for attempt in range(1, retries + 1):
        prompt = user if not last_error else f"{user}\n\nПрошлый ответ невалиден: {last_error}\nИсправь."
        raw = backend.generate_json(SYSTEM, prompt, schema)
        try:
            data = json.loads(raw)
            data.update({"width": width, "height": height, "fps": fps})
            return Timeline.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as e:
            last_error = str(e)[:600]
    raise LLMError(f"Не удалось получить валидный таймлайн за {retries} попыток: {last_error}")
