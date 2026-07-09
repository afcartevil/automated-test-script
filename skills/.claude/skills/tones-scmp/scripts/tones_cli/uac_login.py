# -*- coding: utf-8 -*-
"""UAC 自动登录：账号写死在脚本内，token 缓存到本地文件。"""

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Any

import httpx
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_der_public_key

logger = logging.getLogger(__name__)

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
TOKEN_CACHE_FILE = PACKAGE_ROOT / ".token_cache.json"

# 与 sdd_test UacLogin 一致：简易 Base64，请勿明文传播
_GATEWAY = "https://pfgatewaysz.transsion.com:9199"
_LOGIN_PATH = "/uac-auth-service/v2/api/uac-auth/login/account"
_RSA_KEY_PATH = "/uac-auth-service/v2/api/uac-auth/crypto/rsaKeyPair"
_P_APPID = "220713001"
_ORIGIN = "https://hk-intra-paas.transsion.com"
_REFERER = "https://hk-intra-paas.transsion.com/"


def _b64_decode(value: str) -> str:
    return base64.b64decode(value.encode("utf-8")).decode("utf-8")


class UacLogin:
    """硬编码账号的 UAC 登录客户端。"""

    def __init__(self, timeout: float = 30.0):
        self.gateway = _GATEWAY
        self.appid = _b64_decode("Y19Nall3TlRFME1EQXlkZw==")
        self.appsecret = _b64_decode("QVoySGxyRFZlMnpoWDhUcTM5VXR5ajdRQ3lWTlRpQU8=")
        self.username = _b64_decode("U0lTTUswMQ==")
        self.password = _b64_decode("U0lTTUswMQ==")
        self.timeout = timeout

    def _url(self, path: str) -> str:
        return f"{self.gateway.rstrip('/')}/{path.lstrip('/')}"

    def get_public_key(self) -> dict[str, str]:
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.get(self._url(_RSA_KEY_PATH))
            resp.raise_for_status()
            data = resp.json()["data"]
        return {
            "publicKey": data["publicKey"],
            "verifyKey": data["verifyKey"],
        }

    @staticmethod
    def encrypt_password(public_key: str, password: str) -> str:
        public_key_bytes = base64.b64decode(public_key)
        rsa_public_key = load_der_public_key(public_key_bytes)
        encrypted_bytes = rsa_public_key.encrypt(
            password.encode("utf-8"),
            padding.PKCS1v15(),
        )
        return base64.b64encode(encrypted_bytes).decode("utf-8")

    def login(self) -> dict[str, str]:
        key_pair = self.get_public_key()
        cipher_password = self.encrypt_password(key_pair["publicKey"], self.password)
        body = {
            "appId": self.appid,
            "pwd": cipher_password,
            "source": "MGT",
            "username": self.username,
            "verifyKey": key_pair["verifyKey"],
        }
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(self._url(_LOGIN_PATH), json=body)
            resp.raise_for_status()
            payload = resp.json()

        message = str(payload.get("message") or "")
        if "succeed" not in message.lower() and payload.get("code") not in (None, "0000", 0):
            raise RuntimeError(f"UAC 登录失败: {payload}")

        data = payload.get("data") or {}
        token = data.get("token")
        utoken = data.get("utoken")
        if not token or not utoken:
            raise RuntimeError(f"UAC 登录响应缺少 token: {payload}")

        auth = {
            "p_auth": token,
            "authorization": token,
            "p_rtoken": utoken,
            "p_appid": _P_APPID,
            "origin": _ORIGIN,
            "referer": _REFERER,
        }
        save_auth(auth)
        logger.info("UAC 登录成功，token 已缓存")
        return auth


def save_auth(auth: dict[str, str]) -> None:
    TOKEN_CACHE_FILE.write_text(
        json.dumps(auth, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_cached_auth() -> dict[str, str] | None:
    if not TOKEN_CACHE_FILE.is_file():
        return None
    try:
        data = json.loads(TOKEN_CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    if not data.get("p_auth") and not data.get("authorization"):
        return None
    # 补齐固定字段
    data.setdefault("p_appid", _P_APPID)
    data.setdefault("origin", _ORIGIN)
    data.setdefault("referer", _REFERER)
    if data.get("p_auth") and not data.get("authorization"):
        data["authorization"] = data["p_auth"]
    if data.get("authorization") and not data.get("p_auth"):
        data["p_auth"] = data["authorization"]
    return data


def ensure_auth(*, force_refresh: bool = False) -> dict[str, str]:
    """返回可用 auth；无缓存或强制刷新时自动 UAC 登录。"""
    if not force_refresh:
        cached = load_cached_auth()
        if cached:
            return cached
    return UacLogin().login()


def auth_status() -> dict[str, Any]:
    cached = load_cached_auth()
    return {
        "code": "0000",
        "msg": "success",
        "data": {
            "cached": bool(cached),
            "token_file": str(TOKEN_CACHE_FILE),
            "p_auth_present": bool(cached and (cached.get("p_auth") or cached.get("authorization"))),
            "p_rtoken_present": bool(cached and cached.get("p_rtoken")),
        },
    }
