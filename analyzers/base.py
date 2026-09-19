from abc import ABC, abstractmethod

from models.analysis import AnalysisRequest, AnalysisResult
from models.transcript import VideoTranscript


class BaseAnalyzer(ABC):
    model_type: str = ""

    @abstractmethod
    async def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        ...

    @abstractmethod
    async def chunk_transcripts(
        self, transcripts: list[VideoTranscript], max_chunk_size: int = 5
    ) -> list[list[VideoTranscript]]:
        ...

    def _build_file_prompt(self, request: AnalysisRequest) -> str:
        parts = []
        if request.user_query:
            parts.append(f"User Question: {request.user_query}\n")

        if request.transcript_files:
            parts.append("\nTranscript files to analyze:\n")
            for fp in request.transcript_files:
                parts.append(f"  - {fp}\n")
            parts.append(
                "\nPlease read each file above and provide your analysis.\n"
            )

        if request.extra_context:
            parts.append("Extra Context:\n")
            for k, v in request.extra_context.items():
                parts.append(f"{k}: {v}\n")

        return "".join(parts)