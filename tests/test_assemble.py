import shutil
import subprocess

import pytest

from konoden.core.schema import Timeline
from konoden.render.assemble import AssembleError, assemble

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg не установлен")


def lavfi(path, src, size, rate, dur=4):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    f"{src}=duration={dur}:size={size}:rate={rate}", str(path)], check=True)


def test_assemble_normalizes_to_timeline_format(tmp_path):
    lavfi(tmp_path / "a.mp4", "testsrc", "1280x720", 25)
    lavfi(tmp_path / "b.mp4", "testsrc2", "640x480", 24)
    tl = Timeline.model_validate({"title": "T", "width": 1280, "height": 720, "fps": 30, "clips": [
        {"id": "c1", "kind": "footage", "src": str(tmp_path / "a.mp4"), "duration": 2},
        {"id": "c2", "kind": "footage", "src": str(tmp_path / "b.mp4"), "duration": 1.5},
    ]})
    out = assemble(tl, tmp_path / "out.mp4")
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=width,height,r_frame_rate:format=duration", "-of", "default=nw=1", str(out)],
                           capture_output=True, text=True, check=True).stdout
    assert "width=1280" in probe and "height=720" in probe and "r_frame_rate=30/1" in probe
    assert abs(float(probe.split("duration=")[1]) - 3.5) < 0.2


def test_missing_source_raises(tmp_path):
    tl = Timeline.model_validate({"title": "T", "clips": [{"id": "c1", "kind": "footage", "duration": 1}]})
    with pytest.raises(AssembleError):
        assemble(tl, tmp_path / "o.mp4")
