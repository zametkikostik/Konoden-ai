"""Транскрипция через OpenRouter (/audio/transcriptions) — локальная машина не нагружается.

Аудио извлекается ffmpeg в лёгкий моно-mp3, режется на куски и уходит в облако.
Эндпоинт возвращает текст без таймкодов, поэтому тайминг у нас на уровне куска.
"""
from __future__ import annotations

import base64
import json
import subprocess
import tempfile
import time
from pathlib import Path

import requests


class STTError(RuntimeError):
    pass


def extract_audio_chunks(media: Path, workdir: Path, chunk_seconds: int = 600) -> list[Path]:
    workdir.mkdir(parents=True, exist_ok=True)
    pattern = workdir / "chunk_%03d.mp3"
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(media),
        "-vn", "-ac", "1", "-ar", "16000", "-c:a", "libmp3lame", "-b:a", "48k",
        "-f", "segment", "-segment_time", str(chunk_seconds), "-reset_timestamps", "1",
        str(pattern),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise STTError(f"ffmpeg: {res.stderr.strip()[:500]}")
    chunks = sorted(workdir.glob("chunk_*.mp3"))
    if not chunks:
        raise STTError("В файле нет аудиодорожки")
    return chunks


def _transcribe_chunk(
    path: Path, *, api_key: str, base_url: str, model: str, language: str | None, retries: int = 4
) -> str:
    body = {
        "model": model,
        "input_audio": {"data": base64.b64encode(path.read_bytes()).decode("ascii"), "format": "mp3"},
    }
    if language:
        body["language"] = language
    delay = 2.0
    for attempt in range(1, retries + 1):
        r = requests.post(
            f"{base_url}/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=body,
            timeout=300,
        )
        if r.status_code == 200:
            return r.json()["text"]
        if r.status_code in (429, 500, 502, 503, 504, 529) and attempt < retries:
            time.sleep(delay)
            delay *= 2
            continue
        raise STTError(f"OpenRouter STT {r.status_code}: {r.text[:500]}")
    raise STTError("unreachable")


def transcribe(
    media: str | Path,
    *,
    api_key: str,
    base_url: str = "https://openrouter.ai/api/v1",
    model: str = "openai/whisper-large-v3",
    language: str | None = None,
    chunk_seconds: int = 600,
) -> dict:
    if not api_key:
        raise STTError("OPENROUTER_API_KEY не задан")
    media = Path(media)
    if not media.exists():
        raise STTError(f"Файл не найден: {media}")
    segments = []
    with tempfile.TemporaryDirectory(prefix="konoden_stt_") as tmp:
        for i, chunk in enumerate(extract_audio_chunks(media, Path(tmp), chunk_seconds)):
            text = _transcribe_chunk(
                chunk, api_key=api_key, base_url=base_url.rstrip("/"), model=model, language=language
            )
            segments.append({"start": i * chunk_seconds, "text": text.strip()})
    return {
        "model": model,
        "source": media.name,
        "text": " ".join(s["text"] for s in segments),
        "segments": segments,
    }


def save_transcript(data: dict, path: str | Path) -> None:
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
