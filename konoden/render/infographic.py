"""Инфографика: JSON-спецификация -> анимированный HTML/CSS -> mp4 (запись через Playwright).

Без внешних зависимостей и лицензионных рисков: чистые HTML/CSS/JS, системные шрифты.
Типы: bar_chart, donut, counter, steps. Весь текст экранируется.
"""
from __future__ import annotations

import html
import re
import tempfile
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from ..core.schema import Timeline
from .screencast import Scenario, capture

InfoType = Literal["bar_chart", "donut", "counter", "steps"]
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
_PALETTE = ["{accent}", "#00B894", "#FDCB6E", "#E17055", "#74B9FF", "#A29BFE", "#FD79A8", "#55EFC4"]


class Item(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    value: Optional[float] = Field(default=None, ge=0)
    detail: Optional[str] = Field(default=None, max_length=140, description="Пояснение (для steps)")


class InfographicSpec(BaseModel):
    type: InfoType = Field(description="bar_chart — сравнение величин; donut — доли; counter — одно число; steps — этапы")
    title: str = Field(min_length=1, max_length=100)
    subtitle: Optional[str] = Field(default=None, max_length=140)
    items: list[Item] = Field(min_length=1, max_length=8)
    unit: str = Field(default="", max_length=8, description="Суффикс значений: %, $, млн...")
    duration: float = Field(default=6.0, gt=0, le=60, description="Длительность записи для отдельного рендера, сек")
    theme: Literal["dark", "light"] = "dark"
    accent: Optional[str] = Field(default=None, description="HEX-цвет #RRGGBB; по умолчанию берётся из бренда")

    @field_validator("accent")
    @classmethod
    def _accent(cls, v):
        if v is not None and not _HEX.match(v):
            raise ValueError("accent должен быть в формате #RRGGBB")
        return v

    @model_validator(mode="after")
    def _per_type(self) -> "InfographicSpec":
        n = len(self.items)
        if self.type in ("bar_chart", "donut"):
            if n < 2:
                raise ValueError(f"{self.type} требует минимум 2 элемента")
            if any(i.value is None for i in self.items):
                raise ValueError(f"{self.type}: у каждого элемента должно быть value")
            if self.type == "donut" and sum(i.value for i in self.items) <= 0:
                raise ValueError("donut: сумма значений должна быть > 0")
        elif self.type == "counter":
            if n != 1 or self.items[0].value is None:
                raise ValueError("counter требует ровно 1 элемент со value")
        elif self.type == "steps" and n < 2:
            raise ValueError("steps требует минимум 2 элемента")
        return self

    @classmethod
    def load(cls, path: str | Path) -> "InfographicSpec":
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))


_e = lambda t: html.escape(str(t), quote=True)  # noqa: E731


def _fmt_js_num(v: float) -> str:
    return repr(float(v))


_CSS = """
:root{--u:calc(min(100vw,100vh*1.7778)/100);--accent:%ACCENT%;%THEME%}
*{box-sizing:border-box;margin:0;padding:0}
html,body{width:100%;height:100%;overflow:hidden;background:var(--bg);color:var(--fg);
  font-family:Inter,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif}
.wrap{height:100%;padding:calc(var(--u)*5.5) calc(var(--u)*7);display:flex;flex-direction:column}
h1{font-size:calc(var(--u)*4.6);font-weight:800;letter-spacing:-.02em;line-height:1.1;opacity:0;animation:rise .7s .1s ease-out forwards}
.sub{font-size:calc(var(--u)*2.1);color:var(--muted);margin-top:calc(var(--u)*.9);opacity:0;animation:rise .7s .25s ease-out forwards}
.body{flex:1;display:flex;align-items:center;justify-content:center;min-height:0}
@keyframes rise{from{opacity:0;transform:translateY(calc(var(--u)*1.6))}to{opacity:1;transform:none}}
.tab{font-variant-numeric:tabular-nums}
/* bar_chart */
.bars{width:100%;display:flex;flex-direction:column;gap:calc(var(--u)*2.2)}
.row{display:grid;grid-template-columns:calc(var(--u)*21) 1fr calc(var(--u)*12);align-items:center;gap:calc(var(--u)*2)}
.lab{font-size:calc(var(--u)*2.5);font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.track{height:calc(var(--u)*3.4);background:var(--track);border-radius:999px;overflow:hidden}
.bar{height:100%;width:0;border-radius:999px;background:linear-gradient(90deg,var(--accent),color-mix(in srgb,var(--accent) 55%,#fff));
  animation:grow 1.3s var(--d) cubic-bezier(.2,.8,.2,1) forwards}
@keyframes grow{to{width:var(--w)}}
.val{font-size:calc(var(--u)*2.7);font-weight:800;text-align:right}
/* donut */
.dwrap{display:flex;align-items:center;gap:calc(var(--u)*8);width:100%;justify-content:center}
.donut{width:calc(var(--u)*34);height:calc(var(--u)*34);flex:none}
.seg{animation:seg .9s var(--d) ease-out forwards}
@keyframes seg{to{stroke-dasharray:var(--p) calc(100 - var(--p))}}
.legend{display:flex;flex-direction:column;gap:calc(var(--u)*1.8)}
.li{display:flex;align-items:center;gap:calc(var(--u)*1.6);opacity:0;animation:rise .6s var(--d) ease-out forwards}
.sw{width:calc(var(--u)*2.4);height:calc(var(--u)*2.4);border-radius:calc(var(--u)*.6);flex:none}
.li .lab{font-size:calc(var(--u)*2.5)}
.li .val{font-size:calc(var(--u)*2.5);margin-left:calc(var(--u)*2);color:var(--muted)}
/* counter */
.cnt{text-align:center}
.big{font-size:calc(var(--u)*17);font-weight:900;letter-spacing:-.03em;line-height:1;
  background:linear-gradient(135deg,var(--accent),color-mix(in srgb,var(--accent) 50%,#fff));-webkit-background-clip:text;background-clip:text;color:transparent;
  opacity:0;animation:rise .6s .3s ease-out forwards}
.cap{font-size:calc(var(--u)*3);color:var(--muted);margin-top:calc(var(--u)*2.2);opacity:0;animation:rise .6s .6s ease-out forwards}
/* steps */
.steps{position:relative;display:flex;flex-direction:column;gap:calc(var(--u)*3);width:100%}
.steps::before{content:"";position:absolute;left:calc(var(--u)*2.9);top:calc(var(--u)*3);bottom:calc(var(--u)*3);width:calc(var(--u)*.35);background:var(--track);border-radius:9px}
.step{position:relative;display:flex;align-items:center;gap:calc(var(--u)*2.8);opacity:0;animation:rise .6s var(--d) ease-out forwards}
.n{width:calc(var(--u)*6);height:calc(var(--u)*6);border-radius:50%;background:var(--accent);color:#fff;font-size:calc(var(--u)*3);font-weight:800;
  display:flex;align-items:center;justify-content:center;flex:none;box-shadow:0 0 0 calc(var(--u)*.8) var(--bg)}
.t{font-size:calc(var(--u)*3.1);font-weight:700}
.d{font-size:calc(var(--u)*2.1);color:var(--muted);margin-top:calc(var(--u)*.4)}
"""

_THEMES = {
    "dark": "--bg:#0F1220;--fg:#F4F5FA;--muted:#9AA0B8;--track:#23283F;",
    "light": "--bg:#F7F8FC;--fg:#14172B;--muted:#5B6180;--track:#E3E6F2;",
}

_JS = """
const fmt=(v,dec)=>{const s=v.toFixed(dec).split('.');s[0]=s[0].replace(/\\B(?=(\\d{3})+(?!\\d))/g,'\\u202f');return s.join('.')};
document.querySelectorAll('[data-v]').forEach(el=>{
  const target=+el.dataset.v,delay=(+el.dataset.d||0)*1000,dur=+(el.dataset.dur||1300),dec=+(el.dataset.dec||0),unit=el.dataset.unit||'';
  const t0=performance.now();
  const tick=now=>{const p=Math.min(1,Math.max(0,(now-t0-delay)/dur));const e=1-Math.pow(1-p,3);
    el.textContent=fmt(target*e,dec)+unit;if(p<1)requestAnimationFrame(tick)};
  el.textContent=fmt(0,dec)+unit;requestAnimationFrame(tick);
});
"""


def _decimals(values: list[float]) -> int:
    return 0 if all(abs(v - round(v)) < 1e-9 for v in values) else 1


def _body(spec: InfographicSpec, accent: str) -> str:
    items, unit = spec.items, spec.unit
    if spec.type == "bar_chart":
        vmax = max(i.value for i in items) or 1.0
        dec = _decimals([i.value for i in items])
        rows = "".join(
            f'<div class="row" style="--w:{i.value / vmax * 100:.2f}%;--d:{0.5 + k * 0.22:.2f}s">'
            f'<div class="lab">{_e(i.label)}</div><div class="track"><div class="bar"></div></div>'
            f'<div class="val tab" data-v="{_fmt_js_num(i.value)}" data-d="{0.5 + k * 0.22:.2f}" '
            f'data-dec="{dec}" data-unit="{_e(unit)}"></div></div>'
            for k, i in enumerate(items)
        )
        return f'<div class="bars">{rows}</div>'

    if spec.type == "donut":
        total = sum(i.value for i in items)
        pcts = [i.value / total * 100 for i in items]
        dec = _decimals(pcts)
        colors = [c.replace("{accent}", accent) for c in _PALETTE]
        segs, legend, offset = [], [], 0.0
        for k, (i, p) in enumerate(zip(items, pcts)):
            color = colors[k % len(colors)]
            d = 0.5 + k * 0.25
            dash = max(p - 0.6, 0.1)
            segs.append(
                f'<circle class="seg" cx="21" cy="21" r="15.9155" fill="none" stroke="{color}" stroke-width="5" '
                f'stroke-dasharray="0 100" stroke-dashoffset="{-offset:.4f}" transform="rotate(-90 21 21)" '
                f'style="--p:{dash:.3f};--d:{d:.2f}s"/>'
            )
            legend.append(
                f'<div class="li" style="--d:{d:.2f}s"><div class="sw" style="background:{color}"></div>'
                f'<div class="lab">{_e(i.label)}</div>'
                f'<div class="val tab" data-v="{p:.4f}" data-d="{d:.2f}" data-dec="{dec}" data-unit="%"></div></div>'
            )
            offset += p
        return (
            '<div class="dwrap"><svg class="donut" viewBox="0 0 42 42">'
            '<circle cx="21" cy="21" r="15.9155" fill="none" stroke="var(--track)" stroke-width="5"/>'
            + "".join(segs) + '</svg><div class="legend">' + "".join(legend) + "</div></div>"
        )

    if spec.type == "counter":
        it = items[0]
        dec = _decimals([it.value])
        return (
            f'<div class="cnt"><div class="big tab" data-v="{_fmt_js_num(it.value)}" data-d="0.3" data-dur="2200" '
            f'data-dec="{dec}" data-unit="{_e(unit)}"></div><div class="cap">{_e(it.label)}</div></div>'
        )

    steps = "".join(
        f'<div class="step" style="--d:{0.6 + k * 0.7:.2f}s"><div class="n">{k + 1}</div><div>'
        f'<div class="t">{_e(i.label)}</div>'
        + (f'<div class="d">{_e(i.detail)}</div>' if i.detail else "")
        + "</div></div>"
        for k, i in enumerate(items)
    )
    return f'<div class="steps">{steps}</div>'


def build_html(spec: InfographicSpec, accent: str = "#6C5CE7") -> str:
    accent = spec.accent or accent
    if not _HEX.match(accent):
        accent = "#6C5CE7"
    css = _CSS.replace("%ACCENT%", accent).replace("%THEME%", _THEMES[spec.theme])
    sub = f'<div class="sub">{_e(spec.subtitle)}</div>' if spec.subtitle else ""
    return (
        '<!doctype html><html><head><meta charset="utf-8"><title>infographic</title>'
        f"<style>{css}</style></head><body><div class=\"wrap\"><h1>{_e(spec.title)}</h1>{sub}"
        f'<div class="body">{_body(spec, accent)}</div></div><script>{_JS}</script></body></html>'
    )


def render_infographic(
    spec: InfographicSpec,
    out_path: str | Path,
    *,
    width: int = 1920,
    height: int = 1080,
    fps: int = 30,
    seconds: float | None = None,
    accent: str = "#6C5CE7",
) -> float:
    """Записать инфографику в mp4. После окончания анимации финальный кадр удерживается."""
    seconds = seconds if seconds is not None else spec.duration
    steps: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="konoden_ig_") as tmp:
        page = Path(tmp) / "index.html"
        page.write_text(build_html(spec, accent), encoding="utf-8")
        steps.append({"action": "goto", "url": page.as_uri()})
        left = seconds
        while left > 0:
            chunk = min(left, 30.0)
            steps.append({"action": "wait", "seconds": chunk})
            left -= chunk
        sc = Scenario.model_validate(
            {"width": width, "height": height, "fps": fps, "tail_seconds": 0.2, "steps": steps}
        )
        return capture(sc, out_path, cursor=False)


def render_infographics(
    tl: Timeline, base_dir: str | Path, out_dir: str | Path, *, force: bool = False, accent: str = "#6C5CE7"
) -> list[str]:
    warnings: list[str] = []
    out_dir = Path(out_dir)
    for clip in tl.clips:
        if clip.kind != "infographic" or not clip.spec:
            continue
        if clip.src and not force:
            continue
        spec_path = Path(clip.spec)
        if not spec_path.is_absolute():
            spec_path = Path(base_dir) / spec_path
        spec = InfographicSpec.load(spec_path)
        out = out_dir / f"{clip.id}.mp4"
        dur = render_infographic(
            spec, out, width=tl.width, height=tl.height, fps=tl.fps, seconds=clip.duration + 0.5, accent=accent
        )
        clip.src = str(out)
        if dur + 0.05 < clip.duration:
            warnings.append(f"{clip.id}: запись {dur:.1f}с короче клипа {clip.duration:.1f}с")
    return warnings
