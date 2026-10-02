from pathlib import Path

import pytest

from mcp_server.frames import FrameExtractor


def test_extract_frames_uses_transcript_timestamps(tmp_path: Path, monkeypatch):
    root = tmp_path / "data"
    source = root / "youtube" / "video.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"video")
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        Path(command[-1]).write_bytes(b"jpg")

    monkeypatch.setattr("mcp_server.frames.subprocess.run", fake_run)
    result = FrameExtractor(root, root / "artifacts").extract("youtube/video.mp4", [12.5])
    assert result["status"] == "ok"
    assert result["frames"][0]["timestamp"] == 12.5
    assert Path(result["frames"][0]["file"]).read_bytes() == b"jpg"
    assert "12.500" in " ".join(calls[0])


def test_extract_frames_rejects_files_outside_data_root(tmp_path: Path):
    root = tmp_path / "data"
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"video")
    with pytest.raises(ValueError, match="inside"):
        FrameExtractor(root, root / "artifacts").extract(str(outside), [1])


def test_extract_frames_limits_timestamp_count(tmp_path: Path):
    root = tmp_path / "data"
    source = root / "video.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"video")
    with pytest.raises(ValueError, match="1-20"):
        FrameExtractor(root, root / "artifacts").extract("video.mp4", list(range(21)))
