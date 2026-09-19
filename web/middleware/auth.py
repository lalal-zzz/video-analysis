"""Auth 中间件 — 基础 Bearer Token 认证."""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# 从环境变量读取 API Key（可选）
API_TOKEN = os.getenv("API_TOKEN", "")


def check_api_token(token: str | None) -> bool:
    """验证 API Token.

    未设置 API_TOKEN 时不鉴权，允许公开访问。
    """
    if not API_TOKEN:
        return True
    if not token:
        return False
    return token == API_TOKEN
