"""Web 配置."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class WebSettings(BaseSettings):
    host: str = "127.0.0.1"
    port: int = 8080
    project_root: str = "."
