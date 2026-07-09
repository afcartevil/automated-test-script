"""HTTP client with UAC auth header injection and one-shot token refresh."""

from __future__ import annotations

import json
from typing import Any

import httpx

from tones_cli.config import get_service_config
from tones_cli.uac_login import ensure_auth


class TonesApiError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class TonesHttpClient:
    SERVICE_NAME = "tones-build-platform"

    def __init__(self, service_name: str | None = None, timeout: float = 60.0):
        self.service_name = service_name or self.SERVICE_NAME
        self._timeout = timeout
        self._cfg: dict[str, Any] | None = None

    def _ensure_cfg(self, *, force_refresh: bool = False) -> dict[str, Any]:
        if self._cfg is None or force_refresh:
            self._cfg = get_service_config(self.service_name, force_refresh=force_refresh)
        return self._cfg

    def reload_auth(self, *, force_refresh: bool = False) -> None:
        self._cfg = get_service_config(self.service_name, force_refresh=force_refresh)

    @property
    def base_url(self) -> str:
        return self._ensure_cfg()["base_url"].rstrip("/")

    @property
    def path_prefix(self) -> str:
        prefix = self._ensure_cfg().get("path_prefix", "")
        return prefix if prefix.startswith("/") else f"/{prefix}"

    def _build_headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        cfg = self._ensure_cfg()
        auth = cfg.get("auth") or {}
        defaults = cfg.get("defaults") or {}

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

    @staticmethod
    def _is_auth_failure(status_code: int, payload: Any) -> bool:
        if status_code in (401, 403):
            return True
        if isinstance(payload, dict):
            code = payload.get("code")
            msg = str(payload.get("msg") or payload.get("message") or "").lower()
            if code in ("401", "403", 401, 403):
                return True
            if any(token in msg for token in ("unauth", "token", "登录", "过期", "expire")):
                return True
        return False

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | list[Any] | None = None,
        params: dict[str, Any] | None = None,
        empty_body: bool = False,
        _retried: bool = False,
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

        if response.status_code >= 400 or (
            isinstance(payload, dict) and payload.get("code") not in (None, "0000", 0)
        ):
            if not _retried and self._is_auth_failure(response.status_code, payload):
                ensure_auth(force_refresh=True)
                self.reload_auth(force_refresh=False)
                return self.request(
                    method,
                    path,
                    json_body=json_body,
                    params=params,
                    empty_body=empty_body,
                    _retried=True,
                )

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
