"""LLM -> спецификация инфографики для клипов kind=infographic.

Данные в инфографике должны браться только из брифа/озвучки: LLM легко «придумывает» цифры,
поэтому промпт это запрещает, а результат всё равно нужно сверять человеку.
"""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from .core.schema import Clip, Timeline
from .llm.base import LLMBackend, LLMError
from .render.infographic import InfographicSpec

SYSTEM = """Ты проектируешь инфографику для видео. Выбери тип:
- bar_chart: сравнение величин; donut: доли целого; counter: одно ключевое число; steps: последовательность этапов.
Правила:
- Используй ТОЛЬКО числа, которые явно есть в описании сцены или тексте озвучки. Ничего не выдумывай и не округляй «для красоты».
- Если чисел нет, выбирай steps (значения не нужны).
- Тексты короткие, на языке озвучки. Не больше 6 элементов.
- Отвечай только JSON по схеме."""


def plan_infographic(
    backend: LLMBackend, clip: Clip, video_title: str, *, retries: int = 3
) -> InfographicSpec:
    schema = InfographicSpec.model_json_schema()
    user = (
        f"Видео: {video_title}\nОписание сцены: {clip.query or '-'}\nОзвучка сцены: {clip.voiceover or '-'}\n"
        f"Длительность сцены: {clip.duration} сек."
    )
    last = ""
    for _ in range(retries):
        prompt = user if not last else f"{user}\n\nПрошлый ответ невалиден: {last}\nИсправь."
        raw = backend.generate_json(SYSTEM, prompt, schema)
        try:
            return InfographicSpec.model_validate(json.loads(raw))
        except (json.JSONDecodeError, ValidationError) as e:
            last = str(e)[:500]
    raise LLMError(f"Не удалось получить валидную спецификацию для {clip.id}: {last}")


def plan_specs(
    backend: LLMBackend, tl: Timeline, base_dir: str | Path, out_dir: str = "specs", *, force: bool = False
) -> list[str]:
    """Создать specs/<clip>.json для infographic-клипов без спецификации. Возвращает предупреждения."""
    warnings: list[str] = []
    target = Path(base_dir) / out_dir
    for clip in tl.clips:
        if clip.kind != "infographic" or (clip.spec and not force):
            continue
        try:
            spec = plan_infographic(backend, clip, tl.title)
        except LLMError as e:
            warnings.append(str(e))
            continue
        target.mkdir(parents=True, exist_ok=True)
        (target / f"{clip.id}.json").write_text(spec.model_dump_json(indent=2), encoding="utf-8")
        clip.spec = f"{out_dir}/{clip.id}.json"
        if spec.type != "steps":
            warnings.append(f"{clip.id}: {spec.type} с числами от LLM — сверь данные с источником")
    return warnings
