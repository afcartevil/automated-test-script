"""HTTP client with shared auth header injection."""

from __future__ import annotations

import json
from typing import Any

import httpx

from tones_cli.config import get_service_config


class TonesApiError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class TonesHttpClient:
    SERVICE_NAME = "tones-build-platform"

    def __init__(self, service_name: str | None = None, timeout: float = 60.0):
        self.service_name = service_name or self.SERVICE_NAME
        self._cfg = get_service_config(self.service_name)
        self._timeout = timeout

    @property
    def base_url(self) -> str:
        return self._cfg["base_url"].rstrip("/")

    @property
    def path_prefix(self) -> str:
        prefix = self._cfg.get("path_prefix", "")
        return prefix if prefix.startswith("/") else f"/{prefix}"

    def _build_headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        auth = self._cfg.get("auth") or {}
        defaults = self._cfg.get("defaults") or {}

        authorization = auth.get("authorization") or auth.get("p_auth") or ""
        p_auth = auth.get("p_auth") or authorization

        headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "zh-CN,zh;q=0.9",
            "content-type": "application/json",
            "origin": auth.get("origin", ""),
            "referer": auth.get("referer", ""),
            "user-agent": defaults.get("user_agent", "tones-cli"),
        }
        if auth.get("p_appid"):
            headers["p-appid"] = str(auth["p_appid"])
        if authorization:
            headers["authorization"] = authorization
        if p_auth:
            headers["p-auth"] = p_auth
        if auth.get("p_rtoken"):
            headers["p-rtoken"] = auth["p_rtoken"]
        if extra:
            headers.update(extra)
        return headers

    def _url(self, path: str) -> str:
        if not path.startswith("/"):
            path = f"/{path}"
        return f"{self.base_url}{self.path_prefix}{path}"

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | list[Any] | None = None,
        params: dict[str, Any] | None = None,
        empty_body: bool = False,
    ) -> dict[str, Any]:
        url = self._url(path)
        headers = self._build_headers()

        if empty_body:
            headers.pop("content-type", None)

        with httpx.Client(timeout=self._timeout) as client:
            if empty_body:
                response = client.request(method.upper(), url, headers=headers, params=params)
            else:
                response = client.request(
                    method.upper(),
                    url,
                    headers=headers,
                    json=json_body,
                    params=params,
                )

        try:
            payload = response.json()
        except json.JSONDecodeError:
            payload = {"raw": response.text}

        if response.status_code >= 400:
            raise TonesApiError(
                f"HTTP {response.status_code} for {method.upper()} {url}",
                status_code=response.status_code,
                body=payload,
            )

        if isinstance(payload, dict) and payload.get("code") not in (None, "0000", 0):
            raise TonesApiError(
                f"API error: {payload.get('msg', payload.get('code'))}",
                status_code=response.status_code,
                body=payload,
            )

        return payload if isinstance(payload, dict) else {"data": payload}

    def get(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.request("GET", path, params=params)

    def post(
        self,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        empty_body: bool = False,
    ) -> dict[str, Any]:
        if empty_body:
            return self.request("POST", path, empty_body=True)
        return self.request("POST", path, json_body=json_body or {})
