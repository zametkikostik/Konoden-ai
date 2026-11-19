"""Схема таймлайна — контракт между LLM-планировщиком, рендером и экспортом."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

ClipKind = Literal["footage", "screencast", "infographic", "title"]


class Clip(BaseModel):
    id: str = Field(description="Короткий уникальный id клипа, например c01")
    kind: ClipKind = Field(description="Тип сцены")
    query: Optional[str] = Field(
        default=None,
        description="Поисковый запрос для стока (на английском, 2-5 слов) или описание сцены",
    )
    src: Optional[str] = Field(
        default=None, description="Путь к файлу. Заполняется системой, а не LLM"
    )
    source_ref: Optional[str] = Field(
        default=None, description="Откуда взят материал, напр. pexels:12345. Заполняется системой"
    )
    attribution: Optional[str] = Field(
        default=None, description="Автор/провайдер для титров. Заполняется системой"
    )
    scenario: Optional[str] = Field(
        default=None, description="Путь к JSON-сценарию скринкаста (для kind=screencast). Заполняется системой"
    )
    spec: Optional[str] = Field(
        default=None, description="Путь к JSON-спецификации инфографики (для kind=infographic). Заполняется системой"
    )
    start: float = Field(default=0.0, ge=0, description="Смещение внутри исходника, сек")
    duration: float = Field(gt=0, le=120, description="Длительность клипа на таймлайне, сек")
    voiceover: Optional[str] = Field(default=None, description="Текст озвучки для этой сцены")
    caption: Optional[str] = Field(default=None, description="Короткая подпись на экране")


class Timeline(BaseModel):
    title: str
    fps: int = Field(default=30, ge=1, le=120)
    width: int = Field(default=1920, ge=16)
    height: int = Field(default=1080, ge=16)
    clips: list[Clip] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_ids(self) -> "Timeline":
        ids = [c.id for c in self.clips]
        if len(ids) != len(set(ids)):
            raise ValueError("id клипов должны быть уникальны")
        return self

    @property
    def total_duration(self) -> float:
        return sum(c.duration for c in self.clips)

    def clip(self, clip_id: str) -> Clip:
        for c in self.clips:
            if c.id == clip_id:
                return c
        raise KeyError(f"Нет клипа {clip_id!r}")

    def save(self, path: str | Path) -> None:
        Path(path).write_text(self.model_dump_json(indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "Timeline":
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))


def timeline_json_schema() -> dict:
    return Timeline.model_json_schema()


if __name__ == "__main__":
    print(json.dumps(timeline_json_schema(), ensure_ascii=False, indent=2))
