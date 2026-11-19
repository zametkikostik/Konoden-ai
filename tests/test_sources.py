import json
from pathlib import Path

import pytest

from konoden.core.schema import Timeline
from konoden.sources.base import Candidate, SourceError, SourceProvider
from konoden.sources.resolver import rank, resolve_timeline, sidecar_path, swap_candidate


def cand(i, w=1920, dur=10.0, provider="pexels"):
    return Candidate(provider, str(i), f"http://x/{i}.mp4", f"http://p/{i}", w, 1080, dur, "Author")


class Stub(SourceProvider):
    name = "stub"

    def __init__(self, cands=None, fail=False):
        self.cands, self.fail = cands or [], fail

    def search(self, query, *, min_width, limit=10):
        if self.fail:
            raise SourceError("boom")
        return self.cands


def fake_dl(c, cache):
    p = Path(cache) / f"{c.provider}_{c.id}.mp4"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x")
    return p


def make_tl():
    return Timeline.model_validate({"title": "T", "clips": [
        {"id": "c1", "kind": "footage", "query": "city", "duration": 5},
        {"id": "c2", "kind": "title", "duration": 2},
    ]})


def test_rank_drops_short_and_prefers_resolution():
    tl = make_tl()
    ranked = rank([cand(1, dur=3), cand(2, w=1280, dur=5), cand(3, w=1920, dur=30), cand(4, w=1920, dur=6)], tl.clips[0], tl)
    assert [c.id for c in ranked] == ["4", "3", "2"]


def test_rank_dedupes():
    tl = make_tl()
    assert len(rank([cand(1), cand(1)], tl.clips[0], tl)) == 1


def test_resolve_sets_src_and_skips_non_footage(tmp_path):
    tl = make_tl()
    rep = resolve_timeline(tl, [Stub([cand(7), cand(8, dur=12)])], tmp_path, downloader=fake_dl)
    c1 = tl.clip("c1")
    assert c1.src and Path(c1.src).exists() and c1.source_ref == "pexels:7"
    assert c1.attribution == "Author / Pexels"
    assert tl.clip("c2").src is None
    assert len(rep.candidates["c1"]) == 2 and not rep.warnings


def test_resolve_survives_provider_failure(tmp_path):
    tl = make_tl()
    rep = resolve_timeline(tl, [Stub(fail=True), Stub([cand(1)])], tmp_path, downloader=fake_dl)
    assert tl.clip("c1").src and any("boom" in w for w in rep.warnings)


def test_resolve_warns_when_nothing_found(tmp_path):
    tl = make_tl()
    rep = resolve_timeline(tl, [Stub([])], tmp_path, downloader=fake_dl)
    assert tl.clip("c1").src is None and rep.warnings


def test_resolve_does_not_overwrite_without_force(tmp_path):
    tl = make_tl()
    tl.clip("c1").src = "mine.mp4"
    resolve_timeline(tl, [Stub([cand(1)])], tmp_path, downloader=fake_dl)
    assert tl.clip("c1").src == "mine.mp4"


def test_swap(tmp_path):
    tl = make_tl()
    rep = resolve_timeline(tl, [Stub([cand(1), cand(2, dur=11)])], tmp_path / "cache", downloader=fake_dl)
    tl_path = tmp_path / "timeline.json"
    rep.save(sidecar_path(tl_path))
    chosen = swap_candidate(tl, "c1", sidecar_path(tl_path), 2, tmp_path / "cache", downloader=fake_dl)
    assert tl.clip("c1").source_ref == chosen.ref
    with pytest.raises(SourceError):
        swap_candidate(tl, "c1", sidecar_path(tl_path), 9, tmp_path / "cache", downloader=fake_dl)
