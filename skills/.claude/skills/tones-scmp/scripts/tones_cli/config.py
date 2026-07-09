# -*- coding: utf-8 -*-
"""内置服务端点配置（不再依赖外部 config.yaml / 手工 token）。"""

from __future__ import annotations

import copy
from typing import Any

from tones_cli.uac_login import ensure_auth

DEFAULTS = {
    "user_agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
    ),
}

# HAR 派生的服务端点，auth 由 UAC 自动登录注入
SERVICES: dict[str, dict[str, Any]] = {
    "tones-build-platform": {
        "base_url": "https://api-tones.transsion.com",
        "path_prefix": "/tones-build-platform",
    },
    "tones-spd": {
        "base_url": "https://api-tones.transsion.com",
        "path_prefix": "/tones-spd",
    },
}


def get_service_config(service_name: str, *, force_refresh: bool = False) -> dict[str, Any]:
    if service_name not in SERVICES:
        raise KeyError(
            f"Service '{service_name}' not defined. "
            f"Available: {', '.join(sorted(SERVICES))}"
        )
    service = copy.deepcopy(SERVICES[service_name])
    service["auth"] = copy.deepcopy(ensure_auth(force_refresh=force_refresh))
    service["defaults"] = copy.deepcopy(DEFAULTS)
    return service
