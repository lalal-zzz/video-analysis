import asyncio
import subprocess

from analyzers.base import BaseAnalyzer
from exceptions import AnalyzerError
from models.analysis import AnalysisInsight, AnalysisRequest, AnalysisResult
from models.transcript import VideoTranscript


class CodexAnalyzer(BaseAnalyzer):
    model_type = "codex"

    def __init__(self, cli_path: str = "codex") -> None:
        self._cli = cli_path

    async def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        if request.transcript_files:
            prompt = self._build_file_prompt(request)
        else:
            prompt = self._build_prompt(request)
        raw_output = await self._run_codex(prompt)
        return AnalysisResult(
            request=request,
            summary=raw_output,
            raw_response=raw_output,
        )

    async def chunk_transcripts(
        self, transcripts: list[VideoTranscript], max_chunk_size: int = 5
    ) -> list[list[VideoTranscript]]:
        chunks = []
        for i in range(0, len(transcripts), max_chunk_size):
            chunks.append(transcripts[i : i + max_chunk_size])
        return chunks

    def _build_prompt(self, request: AnalysisRequest) -> str:
        parts = []
        if request.user_query:
            parts.append(f"User Question: {request.user_query}\n")

        for t in request.transcripts:
            v = t.video
            parts.append(
                f"--- Video: {v.title} (by {v.author}) ---\n"
                f"URL: {v.url}\n"
                f"{t.full_text}\n"
            )

        if request.extra_context:
            parts.append("Extra Context:\n")
            for k, v in request.extra_context.items():
                parts.append(f"{k}: {v}\n")

        return "\n".join(parts)

    async def _run_codex(self, prompt: str) -> str:
        cmd = [self._cli, "-p", prompt]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
        except FileNotFoundError as e:
            raise AnalyzerError(
                f"CLI '{self._cli}' not found. Install it first, or set a different path."
            ) from e

        if proc.returncode != 0:
            err_text = stderr.decode().strip() if stderr else "unknown error"
            raise AnalyzerError(f"{self._cli} exited with code {proc.returncode}: {err_text}")

        return stdout.decode().strip()