"""Shared configuration loader for all TONES CLI modules."""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

import yaml

CONFIG_ENV_VAR = "TONES_CLI_CONFIG"
PACKAGE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PACKAGE_ROOT / "config.yaml"
EXAMPLE_CONFIG_PATH = PACKAGE_ROOT / "config.example.yaml"


def config_dir() -> Path:
    explicit = os.environ.get(CONFIG_ENV_VAR)
    if explicit:
        path = Path(explicit)
        return path if path.is_dir() else path.parent
    return PACKAGE_ROOT


def config_path() -> Path:
    explicit = os.environ.get(CONFIG_ENV_VAR)
    if explicit:
        path = Path(explicit)
        return path if path.suffix else path / "config.yaml"
    return DEFAULT_CONFIG_PATH


def ensure_config_exists() -> Path:
    path = config_path()
    if path.is_file():
        return path

    path.parent.mkdir(parents=True, exist_ok=True)
    if EXAMPLE_CONFIG_PATH.is_file():
        path.write_text(EXAMPLE_CONFIG_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        path.write_text(
            "defaults:\n  user_agent: Mozilla/5.0\n"
            "auth_profiles:\n  hk-intra-paas:\n    origin: ''\n"
            "    referer: ''\n    p_appid: ''\n    authorization: ''\n"
            "    p_auth: ''\n    p_rtoken: ''\n"
            "services:\n  tones-build-platform:\n"
            "    base_url: https://api-tones.transsion.com\n"
            "    path_prefix: /tones-build-platform\n"
            "    auth_profile: hk-intra-paas\n",
            encoding="utf-8",
        )
    return path


def load_config() -> dict[str, Any]:
    path = ensure_config_exists()
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data


def get_service_config(service_name: str) -> dict[str, Any]:
    cfg = load_config()
    services = cfg.get("services") or {}
    if service_name not in services:
        raise KeyError(
            f"Service '{service_name}' not defined in {config_path()}. "
            f"Available: {', '.join(sorted(services)) or '(none)'}"
        )

    service = copy.deepcopy(services[service_name])
    profile_name = service.get("auth_profile")
    profiles = cfg.get("auth_profiles") or {}
    if not profile_name or profile_name not in profiles:
        raise KeyError(
            f"Auth profile '{profile_name}' for service '{service_name}' "
            f"not found in config."
        )

    service["auth"] = copy.deepcopy(profiles[profile_name])
    service["defaults"] = copy.deepcopy(cfg.get("defaults") or {})
    return service


def set_config_value(dotted_key: str, value: str) -> None:
    """Set a nested config value, e.g. auth_profiles.hk-intra-paas.p_auth."""
    path = ensure_config_exists()
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}

    parts = dotted_key.split(".")
    node: Any = data
    for part in parts[:-1]:
        if part not in node or not isinstance(node[part], dict):
            node[part] = {}
        node = node[part]
    node[parts[-1]] = value

    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, allow_unicode=True, sort_keys=False)


def mask_secret(value: str, visible: int = 4) -> str:
    if not value:
        return "(empty)"
    if len(value) <= visible * 2:
        return "*" * len(value)
    return f"{value[:visible]}...{value[-visible:]}"
