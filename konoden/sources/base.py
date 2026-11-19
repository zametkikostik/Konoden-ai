from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass


class SourceError(RuntimeError):
    pass


@dataclass
class Candidate:
    provider: str
    id: str
    download_url: str
    page_url: str
    width: int
    height: int
    duration: float
    author: str = ""

    @property
    def ref(self) -> str:
        return f"{self.provider}:{self.id}"

    @property
    def attribution(self) -> str:
        who = f"{self.author} / " if self.author else ""
        return f"{who}{self.provider.capitalize()}"

    def to_dict(self) -> dict:
        return asdict(self)


class SourceProvider(ABC):
    name = "base"

    @abstractmethod
    def search(self, query: str, *, min_width: int, limit: int = 10) -> list[Candidate]:
        """Найти видео-кандидатов по запросу."""
