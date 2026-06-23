"""Persist and inspect jira-ops/.env configuration."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ENV_PATH_NAME = ".env"
SECRET_KEY_SUBSTRINGS = ("password", "secret", "token", "credential")

KNOWN_ENV_KEYS = (
    "JIRA_SERVER",
    "JIRA_USERNAME",
    "JIRA_PASSWORD",
    "FEISHU_APP_ID",
    "FEISHU_APP_SECRET",
    "NETWORK_SERVERS",
    "SEVEN_ZIP_EXE",
    "CHROME_BINARY",
    "WORKSPACE_ROOT",
)


def env_file_path(skill_root: Path) -> Path:
    return skill_root / ENV_PATH_NAME


def _is_secret_key(key: str) -> bool:
    lower = key.lower()
    return any(s in lower for s in SECRET_KEY_SUBSTRINGS)


def _mask_value(key: str, value: str) -> str:
    if not value:
        return ""
    if _is_secret_key(key):
        if len(value) <= 4:
            return "****"
        return value[:2] + "****" + value[-2:]
    if key == "NETWORK_SERVERS" and len(value) > 80:
        return value[:40] + "...(truncated)"
    return value


def parse_env_file(path: Path) -> Dict[str, str]:
    if not path.is_file():
        return {}
    out: Dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        key, _, val = stripped.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        out[key] = val
    return out


def write_env_file(path: Path, values: Dict[str, str]) -> None:
    existing = parse_env_file(path) if path.is_file() else {}
    existing.update({k: v for k, v in values.items() if v is not None})
    lines: List[str] = [
        "# jira-ops runtime configuration (auto-managed; do not commit secrets)",
        "",
    ]
    for key in KNOWN_ENV_KEYS:
        if key in existing and existing[key] != "":
            lines.append(f"{key}={existing[key]}")
    extra_keys = sorted(k for k in existing if k not in KNOWN_ENV_KEYS)
    if extra_keys:
        lines.append("")
        lines.append("# additional keys")
        for key in extra_keys:
            lines.append(f"{key}={existing[key]}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def show_env(skill_root: Path) -> Dict[str, Any]:
    path = env_file_path(skill_root)
    raw = parse_env_file(path)
    masked = {k: _mask_value(k, v) for k, v in raw.items()}
    return {
        "env_path": str(path.resolve()),
        "exists": path.is_file(),
        "keys": masked,
        "missing_recommended": [k for k in ("FEISHU_APP_ID", "FEISHU_APP_SECRET") if not raw.get(k)],
    }


def set_env_pairs(skill_root: Path, pairs: Dict[str, str]) -> Dict[str, Any]:
    path = env_file_path(skill_root)
    write_env_file(path, pairs)
    return show_env(skill_root)


def validate_network_servers_json(raw: str) -> Tuple[bool, str]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return False, f"NETWORK_SERVERS 不是合法 JSON: {exc}"
    if not isinstance(data, list):
        return False, "NETWORK_SERVERS 必须是 JSON 数组"
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            return False, f"NETWORK_SERVERS[{i}] 必须是对象"
        if not item.get("server"):
            return False, f"NETWORK_SERVERS[{i}] 缺少 server"
    return True, ""


def run_setup_check(skill_root: Path, jira_config: Dict[str, str]) -> Dict[str, Any]:
    checks: List[Dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str, required: bool = False) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail, "required": required})

    # Python packages
    for pkg, import_name in (("jira", "jira"), ("requests", "requests"), ("python-dotenv", "dotenv")):
        try:
            __import__(import_name)
            add(f"pip:{pkg}", True, "已安装")
        except ImportError:
            add(f"pip:{pkg}", False, f"缺失，请 pip install {pkg}", required=(pkg == "jira"))

    try:
        import playwright  # noqa: F401

        add("pip:playwright", True, "已安装（Box 浏览器兜底可选）")
    except ImportError:
        add("pip:playwright", False, "未安装（Box HTTP 失败时需 playwright + chromium）")

    # Jira config
    jira_ok = all(jira_config.get(k) for k in ("server", "user", "password"))
    add("jira_credentials", jira_ok, "bugtool 或 api_jira.py config set 已配置" if jira_ok else "缺少 server/user/password", required=True)

    env_raw = parse_env_file(env_file_path(skill_root))
    feishu_ok = bool(env_raw.get("FEISHU_APP_ID") and env_raw.get("FEISHU_APP_SECRET"))
    add("feishu_openapi", feishu_ok, "FEISHU_APP_ID/SECRET 已写入 .env" if feishu_ok else "飞书文件分享下载需要配置")

    net_raw = env_raw.get("NETWORK_SERVERS", "")
    if net_raw:
        net_ok, net_msg = validate_network_servers_json(net_raw)
        add("network_servers", net_ok, net_msg or f"已配置 {len(json.loads(net_raw))} 条服务器")
    else:
        add("network_servers", False, "未配置 NETWORK_SERVERS（UNC 下载在 Windows 上可能需要）")

    seven = os.environ.get("SEVEN_ZIP_EXE") or ""
    from .recursive_extract import find_7z

    z = find_7z()
    add("seven_zip", bool(z), (z or "未找到 7z（.rar/.7z 解压需要 7-Zip 或 SEVEN_ZIP_EXE）"))

    all_required_ok = all(c["ok"] for c in checks if c.get("required"))
    return {
        "ready": all_required_ok,
        "checks": checks,
        "env_path": str(env_file_path(skill_root).resolve()),
    }
