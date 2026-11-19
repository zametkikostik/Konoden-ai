from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from .config import Settings
from .core.schema import Timeline
from .export.edl import save_edl
from .llm.base import LLMError
from .llm.factory import make_backend
from .planner import plan_timeline
from .render.assemble import AssembleError, assemble
from .sources.base import SourceError
from .sources.resolver import make_providers, resolve_timeline, sidecar_path, swap_candidate
from .stt.openrouter_stt import STTError, save_transcript, transcribe


def _cmd_plan(a, s: Settings) -> None:
    brief = Path(a.brief).read_text(encoding="utf-8") if Path(a.brief).is_file() else a.brief
    tl = plan_timeline(
        make_backend(s), brief,
        target_seconds=a.seconds, width=a.width, height=a.height, fps=a.fps,
    )
    tl.save(a.out)
    print(f"OK: {len(tl.clips)} клипов, ~{tl.total_duration:.0f} сек -> {a.out}")


def _cmd_transcribe(a, s: Settings) -> None:
    data = transcribe(
        a.media, api_key=s.openrouter_api_key, base_url=s.openrouter_base_url,
        model=a.model or s.stt_model, language=a.language, chunk_seconds=a.chunk,
    )
    save_transcript(data, a.out)
    print(f"OK: {len(data['segments'])} кусков, {len(data['text'])} символов -> {a.out}")


def _cmd_resolve(a, s: Settings) -> None:
    tl = Timeline.load(a.timeline)
    report = resolve_timeline(
        tl, make_providers(s), s.cache_dir, alternatives=a.alternatives, force=a.force
    )
    tl.save(a.timeline)
    side = sidecar_path(a.timeline)
    report.save(side)
    for cid, cands in report.candidates.items():
        top = cands[0]
        print(f"  {cid}: {top.ref} ({top.width}x{top.height}, {top.duration:.0f}с), альтернатив: {len(cands) - 1}")
    for w in report.warnings:
        print(f"  ! {w}")
    print(f"OK: подобрано {len(report.candidates)} клипов -> {a.timeline}; кандидаты -> {side}")


def _cmd_swap(a, s: Settings) -> None:
    tl = Timeline.load(a.timeline)
    chosen = swap_candidate(tl, a.clip_id, sidecar_path(a.timeline), a.pick, s.cache_dir)
    tl.save(a.timeline)
    print(f"OK: {a.clip_id} -> {chosen.ref} ({chosen.page_url})")


def _cmd_assemble(a, s: Settings) -> None:
    out = assemble(Timeline.load(a.timeline), a.out, audio=a.audio)
    print(f"OK: {out}")


def _cmd_edl(a, s: Settings) -> None:
    save_edl(Timeline.load(a.timeline), a.out)
    print(f"OK: {a.out}")


def _cmd_doctor(a, s: Settings) -> None:
    yes = lambda v: "задан" if v else "НЕ ЗАДАН"  # noqa: E731
    print(f"{s.brand['product_name']} — проверка окружения")
    print(f"  ffmpeg:         {'OK' if shutil.which('ffmpeg') else 'НЕ НАЙДЕН'}")
    print(f"  LLM-бэкенд:     {s.llm_backend}")
    if s.llm_backend == "ollama":
        import requests
        try:
            tags = requests.get(f"{s.ollama_host}/api/tags", timeout=5).json()
            names = {m["name"] for m in tags.get("models", [])}
            have = s.ollama_model in names or f"{s.ollama_model}:latest" in names
            print(f"  Ollama:         OK, модель {s.ollama_model}: {'есть' if have else 'НЕ СКАЧАНА (ollama pull)'}")
        except Exception as e:  # noqa: BLE001
            print(f"  Ollama:         недоступна ({e.__class__.__name__})")
    print(f"  OpenRouter key: {yes(s.openrouter_api_key)} (транскрипция)")
    print(f"  STT модель:     {s.stt_model}")
    print(f"  Pexels key:     {yes(s.pexels_api_key)}")
    print(f"  Pixabay key:    {yes(s.pixabay_api_key)}")
    print(f"  Кэш:            {s.cache_dir}")


def main(argv: list[str] | None = None) -> int:
    s = Settings.load()
    p = argparse.ArgumentParser(prog=s.brand["cli_name"], description=f"{s.brand['product_name']} — {s.brand['tagline']}")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("plan", help="бриф -> timeline.json")
    sp.add_argument("brief", help="текст брифа или путь к .txt")
    sp.add_argument("--out", default="timeline.json")
    sp.add_argument("--seconds", type=int, default=60)
    sp.add_argument("--width", type=int, default=1920)
    sp.add_argument("--height", type=int, default=1080)
    sp.add_argument("--fps", type=int, default=30)
    sp.set_defaults(fn=_cmd_plan)

    sp = sub.add_parser("transcribe", help="видео/аудио -> transcript.json (облако, OpenRouter)")
    sp.add_argument("media")
    sp.add_argument("--out", default="transcript.json")
    sp.add_argument("--model", default=None)
    sp.add_argument("--language", default=None, help="подсказка языка, напр. ru")
    sp.add_argument("--chunk", type=int, default=600, help="длина куска, сек")
    sp.set_defaults(fn=_cmd_transcribe)

    sp = sub.add_parser("resolve", help="подобрать и скачать сток-видео для footage-клипов")
    sp.add_argument("timeline")
    sp.add_argument("--alternatives", type=int, default=5, help="сколько кандидатов хранить на клип")
    sp.add_argument("--force", action="store_true", help="перезаписать уже заданные src")
    sp.set_defaults(fn=_cmd_resolve)

    sp = sub.add_parser("swap", help="заменить материал клипа на альтернативу")
    sp.add_argument("timeline")
    sp.add_argument("clip_id")
    sp.add_argument("--pick", type=int, required=True, help="номер кандидата, с 1")
    sp.set_defaults(fn=_cmd_swap)

    sp = sub.add_parser("assemble", help="timeline.json -> mp4 (черновая сборка)")
    sp.add_argument("timeline")
    sp.add_argument("--out", default="draft.mp4")
    sp.add_argument("--audio", default=None, help="дорожка озвучки/музыки")
    sp.set_defaults(fn=_cmd_assemble)

    sp = sub.add_parser("edl", help="timeline.json -> .edl для Premiere Pro")
    sp.add_argument("timeline")
    sp.add_argument("--out", default="cut.edl")
    sp.set_defaults(fn=_cmd_edl)

    sp = sub.add_parser("doctor", help="проверка окружения")
    sp.set_defaults(fn=_cmd_doctor)

    a = p.parse_args(argv)
    try:
        a.fn(a, s)
    except (LLMError, STTError, AssembleError, SourceError) as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        return 1
    return 0
