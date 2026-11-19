"""Сборка черновика через FFmpeg: нормализация каждого клипа + склейка."""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from ..core.schema import Clip, Timeline

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


class AssembleError(RuntimeError):
    pass


def _run(cmd: list[str]) -> None:
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise AssembleError(f"{' '.join(cmd[:3])}...: {res.stderr.strip()[-600:]}")


def _normalize(clip: Clip, tl: Timeline, out: Path) -> None:
    src = Path(clip.src or "")
    if not src.exists():
        raise AssembleError(f"Клип {clip.id}: исходник не найден ({clip.src!r})")
    w, h = tl.width, tl.height
    vf = (
        f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={tl.fps},format=yuv420p"
    )
    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    if src.suffix.lower() in IMAGE_EXT:
        cmd += ["-loop", "1", "-t", f"{clip.duration}", "-i", str(src)]
    else:
        cmd += ["-ss", f"{clip.start}", "-t", f"{clip.duration}", "-i", str(src)]
    cmd += ["-an", "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", str(out)]
    _run(cmd)


def assemble(tl: Timeline, out_path: str | Path, audio: str | Path | None = None) -> Path:
    out_path = Path(out_path)
    with tempfile.TemporaryDirectory(prefix="konoden_asm_") as tmp:
        tmp_dir = Path(tmp)
        parts = []
        for i, clip in enumerate(tl.clips):
            part = tmp_dir / f"part_{i:03d}.mp4"
            _normalize(clip, tl, part)
            parts.append(part)
        listing = tmp_dir / "list.txt"
        listing.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")

        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listing)]
        if audio:
            cmd += ["-i", str(audio), "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "192k", "-shortest"]
        else:
            cmd += ["-c", "copy"]
        cmd += [str(out_path)]
        _run(cmd)
    return out_path
