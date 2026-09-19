from __future__ import annotations

import httpx
import pytest

from mcp_server.auth import CookieStore
from mcp_server.service import VideoService
from mcp_server.storage import Paths


def _cookie(name, value="value", domain=".bilibili.com"):
    return {"name": name, "value": value, "domain": domain, "path": "/", "expires": -1}


@pytest.mark.asyncio
async def test_missing_cookie_is_auth_required(tmp_path):
    service = VideoService(Paths(tmp_path / "data", tmp_path / "state"))
    try:
        result = await service.auth.validate("bilibili")
        assert result["status"] == "auth_required"
        assert result["verification"] == "local_cookie_missing"
        assert "value" not in str(result)
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_bilibili_cookie_remote_validation_is_boolean_and_redacted(tmp_path, monkeypatch):
    service = VideoService(Paths(tmp_path / "data", tmp_path / "state"))
    service.cookies.save("bilibili", [_cookie("SESSDATA", "do-not-return")])
    seen = {}
    def handler(request):
        seen["cookie"] = request.headers.get("cookie", "")
        return httpx.Response(200, json={"code": 0, "data": {"isLogin": True, "mid": 1}})
    original_client = httpx.AsyncClient
    def client(**kwargs):
        return original_client(transport=httpx.MockTransport(handler), **kwargs)
    monkeypatch.setattr(httpx, "AsyncClient", client)
    try:
        result = await service.auth.validate("bilibili")
        assert result["status"] == "ok"
        assert result["verification"] == "remote_endpoint"
        assert "do-not-return" not in str(result)
        assert "SESSDATA" in seen["cookie"]
    finally:
        await service.close()
