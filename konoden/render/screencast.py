"""Скринкасты: JSON-сценарий -> mp4 через Playwright.

Playwright не рисует курсор в записи, поэтому в страницу внедряется оверлей:
подсвеченная точка, следующая за мышью, и «рябь» при клике. Движения плавные.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Literal, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field, model_validator

from ..core.schema import Timeline

Action = Literal["goto", "click", "type", "press", "hover", "scroll", "zoom", "wait"]

_REQUIRED: dict[str, tuple[str, ...]] = {
    "goto": ("url",),
    "click": ("selector",),
    "type": ("selector", "text"),
    "press": ("key",),
    "hover": ("selector",),
    "scroll": ("y",),
    "zoom": (),  # selector опционален: без него — сброс масштаба
    "wait": (),
}


class ScreencastError(RuntimeError):
    pass


class Step(BaseModel):
    action: Action
    url: Optional[str] = None
    selector: Optional[str] = None
    text: Optional[str] = None
    key: Optional[str] = None
    y: Optional[int] = None
    scale: float = Field(default=1.0, ge=1.0, le=4.0)
    seconds: float = Field(default=1.0, ge=0, le=30)

    @model_validator(mode="after")
    def _check_required(self) -> "Step":
        for f in _REQUIRED[self.action]:
            if getattr(self, f) in (None, ""):
                raise ValueError(f"action={self.action!r} требует поле {f!r}")
        return self


class Scenario(BaseModel):
    width: int = Field(default=1920, ge=320)
    height: int = Field(default=1080, ge=240)
    fps: int = Field(default=30, ge=1, le=60)
    allowed_hosts: list[str] = Field(
        default_factory=list,
        description="Если задан — goto разрешён только на эти хосты (защита от сценариев, сгенерированных LLM)",
    )
    tail_seconds: float = Field(default=1.0, ge=0, le=10, description="Пауза в конце записи")
    steps: list[Step] = Field(min_length=1)

    @classmethod
    def load(cls, path: str | Path) -> "Scenario":
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))


def check_url_allowed(url: str, allowed_hosts: list[str]) -> None:
    if not allowed_hosts:
        return
    u = urlparse(url)
    if u.scheme not in ("http", "https") or (u.hostname or "").lower() not in {h.lower() for h in allowed_hosts}:
        raise ScreencastError(f"URL вне allowed_hosts: {url}")


_CURSOR_JS = """
(() => {
  const ACCENT = '%ACCENT%';
  const add = () => {
    if (document.getElementById('__kc')) return;
    const c = document.createElement('div');
    c.id = '__kc';
    c.style.cssText = 'position:fixed;z-index:2147483647;width:22px;height:22px;margin:-11px 0 0 -11px;' +
      'border-radius:50%;background:' + ACCENT + ';border:2px solid #fff;box-shadow:0 2px 8px rgba(0,0,0,.45);' +
      'pointer-events:none;left:-60px;top:-60px;';
    document.documentElement.appendChild(c);
    addEventListener('mousemove', e => { c.style.left = e.clientX + 'px'; c.style.top = e.clientY + 'px'; }, true);
    addEventListener('mousedown', e => {
      const r = document.createElement('div');
      r.style.cssText = 'position:fixed;z-index:2147483646;pointer-events:none;border-radius:50%;' +
        'border:3px solid ' + ACCENT + ';width:20px;height:20px;margin:-10px 0 0 -10px;left:' + e.clientX + 'px;top:' + e.clientY + 'px;';
      document.documentElement.appendChild(r);
      r.animate([{transform:'scale(1)',opacity:.9},{transform:'scale(3.2)',opacity:0}], {duration:550, easing:'ease-out'})
        .onfinish = () => r.remove();
    }, true);
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', add); else add();
})();
"""

_ZOOM_JS = """
([sel, scale]) => {
  const b = document.body;
  b.style.transition = 'transform 0.9s ease';
  if (!sel || scale <= 1) { b.style.transform = 'scale(1)'; return; }
  const el = document.querySelector(sel);
  if (!el) return;
  const r = el.getBoundingClientRect();
  b.style.transformOrigin = (r.left + r.width / 2 + scrollX) + 'px ' + (r.top + r.height / 2 + scrollY) + 'px';
  b.style.transform = 'scale(' + scale + ')';
}
"""


def _probe_duration(path: Path) -> float:
    res = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(res.stdout.strip())
    except ValueError:
        return 0.0


def _to_mp4(webm: Path, out: Path, fps: int, trim: float) -> None:
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{trim:.3f}", "-i", str(webm),
           "-vf", f"fps={fps},format=yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", str(out)]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise ScreencastError(f"ffmpeg: {res.stderr.strip()[-500:]}")


def _center(page, selector: str) -> tuple[float, float]:
    loc = page.locator(selector).first
    loc.scroll_into_view_if_needed(timeout=10_000)
    box = loc.bounding_box()
    if not box:
        raise ScreencastError(f"Элемент не виден: {selector}")
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


def capture(scenario: Scenario, out_path: str | Path, *, accent: str = "#6C5CE7") -> float:
    """Выполнить сценарий и записать mp4. Возвращает длительность результата, сек."""
    try:
        from playwright.sync_api import Error as PWError
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise ScreencastError("Нужен Playwright: pip install playwright && playwright install chromium") from e

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    size = {"width": scenario.width, "height": scenario.height}
    last = [scenario.width / 2, scenario.height / 2]

    def move(page, x: float, y: float) -> None:
        page.mouse.move(x, y, steps=28)
        last[0], last[1] = x, y

    with tempfile.TemporaryDirectory(prefix="konoden_sc_") as tmp, sync_playwright() as pw:
        try:
            browser = pw.chromium.launch()
        except PWError as e:
            raise ScreencastError(f"Не удалось запустить Chromium (playwright install chromium?): {e}") from e
        ctx = browser.new_context(viewport=size, record_video_dir=tmp, record_video_size=size)
        ctx.add_init_script(_CURSOR_JS.replace("%ACCENT%", accent))
        page = ctx.new_page()
        t0 = time.monotonic()
        trim = 0.0
        first_goto = True
        try:
            for i, st in enumerate(scenario.steps, start=1):
                try:
                    if st.action == "goto":
                        check_url_allowed(st.url, scenario.allowed_hosts)
                        page.goto(st.url, wait_until="load", timeout=30_000)
                        page.mouse.move(*last)  # синхронизировать оверлей после навигации
                        if first_goto:
                            trim, first_goto = time.monotonic() - t0, False
                    elif st.action in ("click", "hover"):
                        x, y = _center(page, st.selector)
                        move(page, x, y)
                        if st.action == "click":
                            page.wait_for_timeout(120)
                            page.mouse.click(x, y)
                    elif st.action == "type":
                        x, y = _center(page, st.selector)
                        move(page, x, y)
                        page.mouse.click(x, y)
                        page.keyboard.type(st.text, delay=65)
                    elif st.action == "press":
                        page.keyboard.press(st.key)
                    elif st.action == "scroll":
                        page.evaluate(
                            "y => window.scrollBy({top: y, behavior: 'smooth'})", st.y
                        )
                        page.wait_for_timeout(700)
                    elif st.action == "zoom":
                        page.evaluate(_ZOOM_JS, [st.selector, st.scale])
                        page.wait_for_timeout(950)
                    elif st.action == "wait":
                        pass
                    page.wait_for_timeout(int(st.seconds * 1000) if st.action == "wait" else 250)
                except PWError as e:
                    raise ScreencastError(f"Шаг {i} ({st.action}): {str(e).splitlines()[0]}") from e
            page.wait_for_timeout(int(scenario.tail_seconds * 1000))
        finally:
            ctx.close()  # без закрытия контекста видео не сбрасывается на диск
            browser.close()
        webms = sorted(Path(tmp).glob("*.webm"))
        if not webms:
            raise ScreencastError("Playwright не создал видео")
        _to_mp4(webms[0], out_path, scenario.fps, trim)
    return _probe_duration(out_path)


def render_screencasts(
    tl: Timeline, base_dir: str | Path, out_dir: str | Path, *, force: bool = False, accent: str = "#6C5CE7"
) -> list[str]:
    """Для всех screencast-клипов со сценарием записать видео и проставить src.
    Возвращает предупреждения (например, запись короче, чем clip.duration)."""
    warnings: list[str] = []
    out_dir = Path(out_dir)
    for clip in tl.clips:
        if clip.kind != "screencast" or not clip.scenario:
            continue
        if clip.src and not force:
            continue
        sc_path = Path(clip.scenario)
        if not sc_path.is_absolute():
            sc_path = Path(base_dir) / sc_path
        scenario = Scenario.load(sc_path)
        scenario = scenario.model_copy(update={"width": tl.width, "height": tl.height, "fps": tl.fps})
        out = out_dir / f"{clip.id}.mp4"
        dur = capture(scenario, out, accent=accent)
        clip.src = str(out)
        if dur + 0.05 < clip.duration:
            warnings.append(f"{clip.id}: запись {dur:.1f}с короче клипа {clip.duration:.1f}с — добавь wait/tail_seconds")
    return warnings


def save_scenario_schema(path: str | Path) -> None:
    Path(path).write_text(json.dumps(Scenario.model_json_schema(), ensure_ascii=False, indent=2), encoding="utf-8")
