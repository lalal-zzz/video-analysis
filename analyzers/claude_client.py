import subprocess
import sys
import asyncio
from pathlib import Path

from analyzers.base import BaseAnalyzer
from exceptions import AnalyzerError
from models.analysis import AnalysisInsight, AnalysisRequest, AnalysisResult
from models.transcript import VideoTranscript


# 项目根目录（cli/main.py 的 parent = cli/, parent parent = project root）
# analyzers/claude_client.py 的 parent = analyzers/, parent parent = project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_PROJECT_SKILLS_DIR = _PROJECT_ROOT / "config" / "skills"


def resolve_skill_path(skill_name_or_path: str) -> str:
    """
    解析 skill 路径：
    - 如果是以 . 开头的相对路径，返回原样
    - 如果是绝对路径，返回原样
    - 如果是 skill 名称，从 config/skills/<name>/SKILL.md 解析
    """
    p = Path(skill_name_or_path)
    if p.is_absolute():
        return str(p)
    if p.exists() or (p.parent / "SKILL.md").exists():
        # 可能是目录或文件
        if p.is_dir():
            skill_md = p / "SKILL.md"
        else:
            skill_md = p
        return str(skill_md)

    # 尝试从 config/skills/<name>/SKILL.md 解析
    candidate = _PROJECT_SKILLS_DIR / skill_name_or_path / "SKILL.md"
    if candidate.exists():
        return str(candidate)

    raise FileNotFoundError(
        f"Skill '{skill_name_or_path}' not found. "
        f"Available skills: {[d.name for d in _PROJECT_SKILLS_DIR.iterdir() if d.is_dir()]}"
    )


class ClaudeAnalyzer(BaseAnalyzer):
    model_type = "claude"

    def __init__(
        self,
        cli_path: str = "claude",
        skill: str | None = None,
        model: str | None = None,
    ) -> None:
        self._cli = cli_path
        self._skill = skill  # 可以是名称或路径
        self._model = model

    async def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        if request.transcript_files:
            prompt = self._build_file_prompt(request)
        else:
            prompt = self._build_prompt(request)
        raw_output = await self._run_claude(prompt)
        return AnalysisResult(
            request=request,
            summary=raw_output,
            raw_response=raw_output,
        )

    async def chunk_transcripts(
        self,
        transcripts: list[VideoTranscript],
        max_chunk_size: int = 5,
    ) -> list[list[VideoTranscript]]:
        chunks: list[list[VideoTranscript]] = []
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

    async def _run_claude(self, prompt: str) -> str:
        cmd = [self._cli]

        if self._skill:
            skill_path = resolve_skill_path(self._skill)
            cmd.extend(["--skill", skill_path])

        if self._model:
            cmd.extend(["-m", self._model])

        cmd.extend(["-p", prompt])

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
        except FileNotFoundError as e:
            raise AnalyzerError(
                f"CLI '{self._cli}' not found. "
                "Install it first, or pass a different --cli-path."
            ) from e

        if proc.returncode != 0:
            err_text = stderr.decode().strip() if stderr else "unknown error"
            raise AnalyzerError(
                f"{self._cli} exited with code {proc.returncode}: {err_text}"
            )

        return stdout.decode().strip()

    @staticmethod
    async def interactive(
        skill: str | None = None,
        model: str | None = None,
        cli_path: str = "claude",
    ) -> int:
        cmd = [cli_path]
        if skill:
            try:
                skill_path = resolve_skill_path(skill)
                cmd.extend(["--skill", skill_path])
            except FileNotFoundError as e:
                print(f"Warning: {e}", file=sys.stderr)
        if model:
            cmd.extend(["-m", model])
        return subprocess.call(cmd)
