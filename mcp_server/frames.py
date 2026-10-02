"""Extract evidence frames from downloaded video files."""

from __future__ import annotations

import subprocess
import uuid
from pathlib import Path
from typing import Any


class FrameExtractor:
    """Use ffmpeg with argument lists so timestamps never become shell code."""

    def __init__(self, root: Path, artifacts: Path) -> None:
        self.root = root.resolve()
        self.artifacts = artifacts.resolve()

    def _source(self, media_file: str) -> Path:
        candidate = Path(media_file).expanduser()
        if not candidate.is_absolute():
            candidate = self.root / candidate
        candidate = candidate.resolve()
        if not candidate.is_relative_to(self.root) or not candidate.is_file():
            raise ValueError("media_file must be an existing file inside the configured data directory")
        return candidate

    def extract(self, media_file: str, timestamps: list[float]) -> dict[str, Any]:
        if not timestamps or len(timestamps) > 20:
            raise ValueError("provide 1-20 timestamps")
        if any(not isinstance(value, (int, float)) or value < 0 or value > 24 * 60 * 60 for value in timestamps):
            raise ValueError("timestamps must be between 0 and 86400 seconds")
        source = self._source(media_file)
        output_dir = self.artifacts / "frames" / uuid.uuid4().hex
        output_dir.mkdir(parents=True, exist_ok=True)
        frames = []
        for index, timestamp in enumerate(timestamps):
            target = output_dir / f"frame-{index:02d}-{timestamp:.3f}.jpg"
            command = [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-ss", f"{float(timestamp):.3f}", "-i", str(source),
                "-frames:v", "1", "-q:v", "2", str(target),
            ]
            try:
                subprocess.run(command, check=True, capture_output=True, timeout=120)
            except FileNotFoundError as exc:
                raise RuntimeError("ffmpeg is required for frame extraction") from exc
            except subprocess.CalledProcessError as exc:
                raise RuntimeError("ffmpeg could not extract the requested frame") from exc
            if not target.is_file() or target.stat().st_size == 0:
                raise RuntimeError("ffmpeg produced an empty frame")
            frames.append({"timestamp": float(timestamp), "file": str(target)})
        return {"status": "ok", "source": str(source), "frames": frames}
