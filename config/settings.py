from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class PromptTemplatesConfig(BaseModel):
    analysis: str = ""
    summary: str = ""


class CacheConfig(BaseModel):
    storage_dir: str = "cache/storage"
    video_ttl_hours: int = 72
    query_ttl_hours: int = 24


class ScraperConfig(BaseModel):
    max_concurrency: int = 3
    request_delay_seconds: float = 1.0
    user_agent: str = ""


class TranscriberConfig(BaseModel):
    whisper_model: str = "base"
    device: str = "cpu"
    language: str = "zh"


class AnalyzerConfig(BaseModel):
    claude_api_key: str = ""
    codex_api_key: str = ""
    default_model: str = "claude"
    max_tokens: int = 4096
    temperature: float = 0.3


class DataConfig(BaseModel):
    data_dir: str = "data"
    transcript_subdir: str = "transcripts"
    result_subdir: str = "results"


class Settings(BaseModel):
    cache: CacheConfig = CacheConfig()
    scraper: ScraperConfig = ScraperConfig()
    transcriber: TranscriberConfig = TranscriberConfig()
    analyzer: AnalyzerConfig = AnalyzerConfig()
    data: DataConfig = DataConfig()
    prompt_templates: PromptTemplatesConfig = PromptTemplatesConfig()
    config_dir: str = "config"

    @classmethod
    def load(cls, path: str | Path = "config/settings.yaml") -> "Settings":
        p = Path(path)
        if not p.exists():
            return cls()
        with open(p, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls(**data) if data else cls()
