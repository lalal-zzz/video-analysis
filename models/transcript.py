from pydantic import BaseModel, Field

from .video import VideoMetadata


class TranscriptSegment(BaseModel):
    start: float
    end: float
    text: str = ""


class VideoTranscript(BaseModel):
    video: VideoMetadata
    segments: list[TranscriptSegment] = Field(default_factory=list)
    full_text: str = ""
    source: str = ""  # "subtitle" | "whisper"

    def build_full_text(self) -> str:
        self.full_text = " ".join(seg.text for seg in self.segments)
        return self.full_text