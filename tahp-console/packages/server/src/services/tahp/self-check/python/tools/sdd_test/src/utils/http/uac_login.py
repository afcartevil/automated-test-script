# -*- coding: utf-8 -*-
from __future__ import annotations

import base64
import logging
import json

from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_der_public_key

from src.utils.http.http_client import get, post
from src.utils.fileloader.toml_loader import read_toml

TOKEN_TEMP_FILE = "temp_token.tmp"

class UacLogin:
    """UAC 登录客户端，从 pyproject.toml 读取 SPD 配置并完成登录。"""

    LOGIN_URL = "/uac-auth-service/v2/api/uac-auth/login/account"
    RSA_KEY_URL = "/uac-auth-service/v2/api/uac-auth/crypto/rsaKeyPair"

    def __init__(self, config_path: str = "pyproject.toml"):
        cfg = read_toml(config_path, "tool.spd.config")
        if cfg is None:
            raise ValueError(f"无法从 {config_path} 读取 tool.spd.config 配置")
        self.gateway = "https://pfgatewaysz.transsion.com:9199"
        # 简单加解密，正式版本需替换，请勿解密后使用信息！！！
        self.appid = self.decode("Y19Nall3TlRFME1EQXlkZw==")
        self.appsecret = self.decode("QVoySGxyRFZlMnpoWDhUcTM5VXR5ajdRQ3lWTlRpQU8=")
        self.username = self.decode("U0lTTUswMQ==")
        self.password = self.decode("U0lTTUswMQ==")

    def _url(self, path: str) -> str:
        # 拼接 gateway 和 path，确保路径以斜杠开头，避免重复斜杠问题
        return f"{self.gateway.rstrip('/')}/{path.lstrip('/')}"

    def decode(self, v: str) -> str:
        return base64.b64decode(v.encode("utf-8")).decode("utf-8")

    def get_public_key(self, debug: bool = False) -> dict[str, str]:
        """调接口拿公钥与 verifyKey（须与加密使用同一组）。"""
        resp = get(
            self._url(self.RSA_KEY_URL),
            debug=debug,
        )
        return {
            "publicKey": resp.body["data"]["publicKey"],
            "verifyKey": resp.body["data"]["verifyKey"],
        }

    @staticmethod
    def encrypt_password(public_key: str, password: str) -> str:
        """使用 RSA 公钥加密密码，返回 BASE64 密文。"""
        public_key_bytes = base64.b64decode(public_key)
        rsa_public_key = load_der_public_key(public_key_bytes)
        encrypted_bytes = rsa_public_key.encrypt(
            password.encode("utf-8"),
            padding.PKCS1v15(),
        )
        return base64.b64encode(encrypted_bytes).decode("utf-8")

    def login(self, debug: bool = False) -> dict[str, str]:
        """
        执行登录，返回登录接口的响应
        
        缓存模式： 把获取到的token缓存起来，后续先使用缓存的token, 如果缓存的token过期, 则重新获取token。
        """
        key_pair = self.get_public_key(debug=debug)
        cipher_password = self.encrypt_password(key_pair["publicKey"], self.password)
        body = {
            "appId": self.appid,
            "pwd": cipher_password,
            "source": "MGT",
            "username": self.username,
            "verifyKey": key_pair["verifyKey"],
        }
        logging.info(f"尝试登录，获取用户token")
        resp = post(
            self._url(self.LOGIN_URL),
            body_json=body,
            debug=debug,
        )
        if "succeed" in resp.body["message"]:
            token = resp.body["data"]["token"]
            utoken = resp.body["data"]["utoken"]
            # 保存为json字符串
            with open(TOKEN_TEMP_FILE, "w", encoding="utf-8") as f:
                f.write(json.dumps(
                    {
                        "P-Auth": token,
                        "P-Rtoken": utoken,
                    },
                    ensure_ascii=False,
                    indent=2,
                ))
            logging.info(f"登录到用户中心成功成功")
            return {"P-Auth": token, "P-Rtoken": utoken}
        else:
            logging.error(f"登录到用户中心失败，错误信息：{resp.body}")
            return None


