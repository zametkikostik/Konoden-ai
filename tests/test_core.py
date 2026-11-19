import json

import pytest
from pydantic import ValidationError

from konoden.core.schema import Timeline
from konoden.export.edl import _tc, to_edl
from konoden.llm.base import LLMBackend, LLMError
from konoden.planner import plan_timeline


def make_tl(**kw):
    clips = kw.pop("clips", [
        {"id": "c1", "kind": "footage", "query": "city", "src": "a.mp4", "start": 1, "duration": 3},
        {"id": "c2", "kind": "title", "duration": 2.5},
    ])
    return Timeline.model_validate({"title": "T", "clips": clips, **kw})


def test_duplicate_ids_rejected():
    with pytest.raises(ValidationError):
        make_tl(clips=[{"id": "x", "kind": "title", "duration": 1}, {"id": "x", "kind": "title", "duration": 1}])


def test_total_duration():
    assert make_tl().total_duration == 5.5


def test_timecode():
    assert _tc(2.5, 30) == "00:00:02:15"
    assert _tc(3661, 25) == "01:01:01:00"


def test_edl_record_timeline_is_contiguous():
    edl = to_edl(make_tl())
    assert "001  AX       V     C        00:00:01:00 00:00:04:00 00:00:00:00 00:00:03:00" in edl
    assert "00:00:03:00 00:00:05:15" in edl


class Flaky(LLMBackend):
    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = 0

    def generate_json(self, system, user, schema):
        self.calls += 1
        return self.answers.pop(0)


GOOD = json.dumps({"title": "ok", "clips": [{"id": "c1", "kind": "title", "duration": 2}]})


def test_planner_retries_on_invalid():
    b = Flaky(['{"title": "x", "clips": []}', "не json", GOOD])
    tl = plan_timeline(b, "brief")
    assert b.calls == 3 and tl.title == "ok"


def test_planner_gives_up():
    with pytest.raises(LLMError):
        plan_timeline(Flaky(["bad"] * 3), "brief", retries=3)
