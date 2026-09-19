from datetime import datetime

from pydantic import BaseModel, Field

from .transcript import VideoTranscript


class AnalysisRequest(BaseModel):
    transcripts: list[VideoTranscript] = Field(default_factory=list)
    transcript_files: list[str] = Field(default_factory=list)
    user_query: str = ""
    model_type: str = ""  # "claude" | "codex"
    prompt_template: str | None = None
    extra_context: dict[str, str] = Field(default_factory=dict)


class AnalysisInsight(BaseModel):
    summary: str = ""
    video_titles: list[str] = Field(default_factory=list)
    confidence: float = 1.0


class AnalysisResult(BaseModel):
    request: AnalysisRequest
    summary: str = ""
    insights: list[AnalysisInsight] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    conclusion: str = ""
    raw_response: str = ""
    analyzed_at: datetime = Field(default_factory=datetime.now)
    error: str | None = None