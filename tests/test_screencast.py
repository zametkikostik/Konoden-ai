import json
import subprocess

import pytest
from pydantic import ValidationError

from konoden.render.screencast import Scenario, ScreencastError, Step, capture, check_url_allowed


def test_step_requires_fields():
    with pytest.raises(ValidationError):
        Step(action="click")
    with pytest.raises(ValidationError):
        Step(action="type", selector="#a")
    Step(action="wait")
    Step(action="zoom")  # сброс масштаба


def test_scenario_needs_steps():
    with pytest.raises(ValidationError):
        Scenario(steps=[])


def test_allowed_hosts():
    check_url_allowed("https://anything.com", [])
    check_url_allowed("https://example.com/x", ["example.com"])
    with pytest.raises(ScreencastError):
        check_url_allowed("https://evil.com", ["example.com"])
    with pytest.raises(ScreencastError):
        check_url_allowed("file:///etc/passwd", ["example.com"])


HTML = """<!doctype html><html><body style="margin:0;font:32px sans-serif;background:#fafafa">
<h1 id="t">Konoden demo</h1>
<input id="i" style="font-size:28px;margin:20px" placeholder="type here">
<button id="b" style="font-size:28px;margin:20px" onclick="document.getElementById('t').textContent='Clicked'">Go</button>
<div style="height:2000px"></div></body></html>"""


def _browser_ok():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.chromium.launch().close()
        return True
    except Exception:  # noqa: BLE001
        return False


@pytest.mark.skipif(not _browser_ok(), reason="Chromium недоступен")
def test_capture_end_to_end(tmp_path):
    page = tmp_path / "p.html"
    page.write_text(HTML, encoding="utf-8")
    sc = Scenario.model_validate({
        "width": 960, "height": 540, "fps": 25, "tail_seconds": 0.5,
        "steps": [
            {"action": "goto", "url": page.as_uri()},
            {"action": "click", "selector": "#b"},
            {"action": "type", "selector": "#i", "text": "hello"},
            {"action": "zoom", "selector": "#t", "scale": 1.5},
            {"action": "scroll", "y": 300},
            {"action": "wait", "seconds": 0.5},
        ],
    })
    out = tmp_path / "o.mp4"
    dur = capture(sc, out)
    assert out.exists() and dur > 3
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=width,height,r_frame_rate", "-of", "default=nw=1", str(out)],
                           capture_output=True, text=True, check=True).stdout
    assert "width=960" in probe and "height=540" in probe and "r_frame_rate=25/1" in probe


@pytest.mark.skipif(not _browser_ok(), reason="Chromium недоступен")
def test_bad_selector_reports_step(tmp_path):
    page = tmp_path / "p.html"
    page.write_text(HTML, encoding="utf-8")
    sc = Scenario.model_validate({"width": 640, "height": 360, "steps": [
        {"action": "goto", "url": page.as_uri()}, {"action": "click", "selector": "#nope"}]})
    with pytest.raises(ScreencastError, match="Шаг 2"):
        capture(sc, tmp_path / "o.mp4")
