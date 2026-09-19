"""通用错误页面."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from litestar import get
from litestar.response import Template
from litestar.status_codes import HTTP_500_INTERNAL_SERVER_ERROR
from litestar.exceptions import NoRouteMatchFoundException


@get("/404")
async def page_not_found() -> Template:
    return Template(
        template_name="error.html",
        context={"title": "页面未找到", "code": 404, "message": "页面未找到，请检查 URL"},
    )


@get("/500")
async def server_error() -> Template:
    return Template(
        template_name="error.html",
        context={"title": "服务器错误", "code": 500, "message": "服务器内部错误，请稍后再试"},
    )


def create_error_handler() -> dict:
    """创建 Litestar 异常处理器."""

    async def error_handler(request: Any, exception: Exception) -> Template:
        if isinstance(exception, NoRouteMatchFoundException):
            return Template(
                template_name="error.html",
                context={
                    "title": "404 - 页面未找到",
                    "code": 404,
                    "message": f"找不到路径: {request.url.path}",
                },
            )
        return Template(
            template_name="error.html",
            context={
                "title": "500 - 服务器错误",
                "code": 500,
                "message": str(exception),
            },
        )

    return {
        HTTP_500_INTERNAL_SERVER_ERROR: error_handler,
    }
