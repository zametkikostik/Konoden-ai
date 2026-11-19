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


def _cmd_assemble(a, s: Settings) -> None:
    out = assemble(Timeline.load(a.timeline), a.out, audio=a.audio)
    print(f"OK: {out}")


def _cmd_edl(a, s: Settings) -> None:
    save_edl(Timeline.load(a.timeline), a.out)
    print(f"OK: {a.out}")


def _cmd_doctor(a, s: Settings) -> None:
    print(f"{s.brand['product_name']} — проверка окружения")
    print(f"  ffmpeg:        {'OK' if shutil.which('ffmpeg') else 'НЕ НАЙДЕН'}")
    print(f"  LLM-бэкенд:    {s.llm_backend}")
    if s.llm_backend == "ollama":
        import requests
        try:
            tags = requests.get(f"{s.ollama_host}/api/tags", timeout=5).json()
            names = [m["name"] for m in tags.get("models", [])]
            ok = any(n.split(":")[0] == s.ollama_model.split(":")[0] and n == s.ollama_model for n in names) or s.ollama_model in names
            print(f"  Ollama:        OK, модель {s.ollama_model}: {'есть' if ok else 'НЕ СКАЧАНА (ollama pull ...)'}")
        except Exception as e:  # noqa: BLE001
            print(f"  Ollama:        недоступна ({e.__class__.__name__})")
    print(f"  OpenRouter key:{' задан' if s.openrouter_api_key else ' НЕ ЗАДАН (нужен для транскрипции)'}")
    print(f"  STT модель:    {s.stt_model}")


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
    except (LLMError, STTError, AssembleError) as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        return 1
    return 0
