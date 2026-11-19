"""Экспорт в CMX3600 EDL — Premiere Pro импортирует его как секвенцию с нарезкой.

Ограничения v1: одна видеодорожка, только склейки (без графики/эффектов).
"""
from __future__ import annotations

from pathlib import Path

from ..core.schema import Timeline


def _tc(seconds: float, fps: int) -> str:
    frames = round(seconds * fps)
    f = frames % fps
    s_total = frames // fps
    return f"{s_total // 3600:02d}:{(s_total // 60) % 60:02d}:{s_total % 60:02d}:{f:02d}"


def to_edl(tl: Timeline) -> str:
    lines = [f"TITLE: {tl.title}", "FCM: NON-DROP FRAME", ""]
    cursor = 0.0
    for i, c in enumerate(tl.clips, start=1):
        src_in, src_out = c.start, c.start + c.duration
        rec_in, rec_out = cursor, cursor + c.duration
        lines.append(
            f"{i:03d}  AX       V     C        "
            f"{_tc(src_in, tl.fps)} {_tc(src_out, tl.fps)} "
            f"{_tc(rec_in, tl.fps)} {_tc(rec_out, tl.fps)}"
        )
        name = Path(c.src).name if c.src else f"{c.id}.mp4"
        lines.append(f"* FROM CLIP NAME: {name}")
        lines.append("")
        cursor = rec_out
    return "\n".join(lines)


def save_edl(tl: Timeline, path: str | Path) -> None:
    Path(path).write_text(to_edl(tl), encoding="utf-8")
