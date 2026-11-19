import json
import subprocess

import pytest
from pydantic import ValidationError

from konoden.core.schema import Timeline
from konoden.llm.base import LLMBackend, LLMError
from konoden.render.infographic import InfographicSpec, build_html, render_infographic, render_infographics
from konoden.spec_planner import plan_infographic, plan_specs
from tests.test_screencast import _browser_ok


def spec(**kw):
    base = {"type": "bar_chart", "title": "T", "items": [{"label": "a", "value": 1}, {"label": "b", "value": 3}]}
    base.update(kw)
    return InfographicSpec.model_validate(base)


def test_validation_per_type():
    with pytest.raises(ValidationError):
        spec(items=[{"label": "a", "value": 1}])                      # bar: мало элементов
    with pytest.raises(ValidationError):
        spec(items=[{"label": "a", "value": 1}, {"label": "b"}])      # bar: нет value
    with pytest.raises(ValidationError):
        spec(type="counter")                                          # counter: 2 элемента
    spec(type="counter", items=[{"label": "x", "value": 5}])
    with pytest.raises(ValidationError):
        spec(type="donut", items=[{"label": "a", "value": 0}, {"label": "b", "value": 0}])
    spec(type="steps", items=[{"label": "a"}, {"label": "b"}])
    with pytest.raises(ValidationError):
        spec(accent="red")
    with pytest.raises(ValidationError):
        spec(items=[{"label": str(i), "value": 1} for i in range(9)])  # >8


def test_html_escapes_everything():
    evil = '<script>alert(1)</script>"&'
    html = build_html(spec(title=evil, subtitle=evil, unit="<b>",
                           items=[{"label": evil, "value": 1}, {"label": "b", "value": 2}]))
    assert "<script>alert(1)" not in html
    assert "&lt;script&gt;" in html


def test_bar_widths_relative_to_max():
    html = build_html(spec())
    assert "--w:33.33%" in html and "--w:100.00%" in html


def test_donut_segments_cover_whole_circle():
    html = build_html(spec(type="donut", items=[{"label": "a", "value": 1}, {"label": "b", "value": 3}]))
    assert 'stroke-dashoffset="-0.0000"' in html and 'stroke-dashoffset="-25.0000"' in html


class Stub(LLMBackend):
    def __init__(self, answers):
        self.answers = list(answers)

    def generate_json(self, system, user, schema):
        return self.answers.pop(0)


def clip(**kw):
    return Timeline.model_validate({"title": "V", "clips": [
        {"id": "c1", "kind": "infographic", "query": "доли трафика", "duration": 3, **kw}]}).clips[0]


GOOD = json.dumps({"type": "steps", "title": "Шаги", "items": [{"label": "a"}, {"label": "b"}]})


def test_spec_planner_retries_and_fails():
    assert plan_infographic(Stub(['{"type":"counter"}', GOOD]), clip(), "V").type == "steps"
    with pytest.raises(LLMError):
        plan_infographic(Stub(["bad"] * 3), clip(), "V")


def test_plan_specs_writes_files_and_warns_on_numbers(tmp_path):
    tl = Timeline.model_validate({"title": "V", "clips": [
        {"id": "c1", "kind": "infographic", "query": "x", "duration": 3},
        {"id": "c2", "kind": "infographic", "query": "y", "duration": 3},
        {"id": "c3", "kind": "footage", "query": "z", "duration": 3}]})
    nums = json.dumps({"type": "counter", "title": "N", "items": [{"label": "l", "value": 7}]})
    warns = plan_specs(Stub([GOOD, nums]), tl, tmp_path)
    assert (tmp_path / "specs" / "c1.json").exists() and tl.clip("c1").spec == "specs/c1.json"
    assert tl.clip("c3").spec is None
    assert len(warns) == 1 and "сверь" in warns[0]


pytestmark_browser = pytest.mark.skipif(not _browser_ok(), reason="Chromium недоступен")


@pytestmark_browser
@pytest.mark.parametrize("kind", ["bar_chart", "donut", "counter", "steps"])
def test_render_each_type(tmp_path, kind):
    items = {"bar_chart": [{"label": "a", "value": 5}, {"label": "b", "value": 9}],
             "donut": [{"label": "a", "value": 5}, {"label": "b", "value": 9}],
             "counter": [{"label": "a", "value": 1234.5}],
             "steps": [{"label": "a", "detail": "d"}, {"label": "b"}]}[kind]
    out = tmp_path / "o.mp4"
    dur = render_infographic(spec(type=kind, items=items), out, width=640, height=360, fps=25, seconds=1.5)
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=width,height", "-of", "default=nw=1", str(out)],
                           capture_output=True, text=True, check=True).stdout
    assert dur > 1.4 and "width=640" in probe and "height=360" in probe


@pytestmark_browser
def test_timeline_render_sets_src(tmp_path):
    (tmp_path / "s.json").write_text(spec().model_dump_json(), encoding="utf-8")
    tl = Timeline.model_validate({"title": "V", "width": 640, "height": 360, "fps": 25,
                                  "clips": [{"id": "c1", "kind": "infographic", "spec": "s.json", "duration": 1.5}]})
    warns = render_infographics(tl, tmp_path, tmp_path / "r")
    assert tl.clip("c1").src and not warns
