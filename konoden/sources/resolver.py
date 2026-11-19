"""Подбор материала: запросы из таймлайна -> кандидаты -> скачивание -> clip.src.

Полуавтомат: берём лучшего кандидата, остальные сохраняем в sidecar-файл,
чтобы можно было заменить командой `swap`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import requests

from ..config import Settings
from ..core.schema import Clip, Timeline
from .base import Candidate, SourceError, SourceProvider
from .pexels import PexelsProvider
from .pixabay import PixabayProvider


def make_providers(s: Settings) -> list[SourceProvider]:
    providers: list[SourceProvider] = []
    if s.pexels_api_key:
        providers.append(PexelsProvider(s.pexels_api_key))
    if s.pixabay_api_key:
        providers.append(PixabayProvider(s.pixabay_api_key))
    if not providers:
        raise SourceError("Не задан ни PEXELS_API_KEY, ни PIXABAY_API_KEY")
    return providers


def rank(cands: list[Candidate], clip: Clip, tl: Timeline) -> list[Candidate]:
    """Отсеять короткие исходники и отсортировать: сначала достаточное разрешение,
    потом ближайшая к нужной длительность."""
    need = clip.start + clip.duration
    seen: set[str] = set()
    ok: list[Candidate] = []
    for c in cands:
        if c.duration >= need and c.ref not in seen:
            seen.add(c.ref)
            ok.append(c)
    return sorted(ok, key=lambda c: (0 if c.width >= tl.width else 1, abs(c.duration - clip.duration)))


def download(c: Candidate, cache_dir: Path) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{c.provider}_{c.id}.mp4"
    if path.exists() and path.stat().st_size > 0:
        return path
    tmp = path.with_suffix(".part")
    with requests.get(c.download_url, stream=True, timeout=60) as r:
        if r.status_code != 200:
            raise SourceError(f"Скачивание {c.ref}: HTTP {r.status_code}")
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    tmp.replace(path)
    return path


def sidecar_path(timeline_path: str | Path) -> Path:
    p = Path(timeline_path)
    return p.with_suffix(".candidates.json")


@dataclass
class ResolveReport:
    candidates: dict[str, list[Candidate]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def save(self, path: str | Path) -> None:
        data = {cid: [c.to_dict() for c in cs] for cid, cs in self.candidates.items()}
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _apply(clip: Clip, c: Candidate, path: Path) -> None:
    clip.src = str(path)
    clip.source_ref = c.ref
    clip.attribution = c.attribution


def resolve_timeline(
    tl: Timeline,
    providers: list[SourceProvider],
    cache_dir: str | Path,
    *,
    alternatives: int = 5,
    force: bool = False,
    downloader: Callable[[Candidate, Path], Path] = download,
) -> ResolveReport:
    cache = Path(cache_dir)
    report = ResolveReport()
    for clip in tl.clips:
        if clip.kind != "footage" or not clip.query:
            continue
        if clip.src and not force:
            continue
        found: list[Candidate] = []
        for p in providers:
            try:
                found += p.search(clip.query, min_width=tl.width, limit=10)
            except SourceError as e:
                report.warnings.append(f"{clip.id}: {p.name}: {e}")
        ranked = rank(found, clip, tl)[:alternatives]
        if not ranked:
            report.warnings.append(f"{clip.id}: ничего не найдено по запросу {clip.query!r}")
            continue
        try:
            _apply(clip, ranked[0], downloader(ranked[0], cache))
        except (SourceError, requests.RequestException, OSError) as e:
            report.warnings.append(f"{clip.id}: не скачалось: {e}")
            continue
        report.candidates[clip.id] = ranked
    return report


def swap_candidate(
    tl: Timeline,
    clip_id: str,
    candidates_file: str | Path,
    pick: int,
    cache_dir: str | Path,
    *,
    downloader: Callable[[Candidate, Path], Path] = download,
) -> Candidate:
    """Заменить материал клипа на альтернативу №pick (нумерация с 1)."""
    data = json.loads(Path(candidates_file).read_text(encoding="utf-8"))
    options = [Candidate(**d) for d in data.get(clip_id, [])]
    if not options:
        raise SourceError(f"Для {clip_id} нет сохранённых кандидатов")
    if not 1 <= pick <= len(options):
        raise SourceError(f"pick должен быть от 1 до {len(options)}")
    chosen = options[pick - 1]
    _apply(tl.clip(clip_id), chosen, downloader(chosen, Path(cache_dir)))
    return chosen
