"""Per-task remote temp directory on target host (158)."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

from web_app.target_repo_config import normalize_linux_path

PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_REMOTE_TEMP_DIR = "/tmp"


def _yaml_remote_temp() -> str:
    try:
        sys.path.insert(0, str(PROJECT_ROOT / "tools"))
        from cli_config import load_settings

        settings, _ = load_settings()
        upgrade = settings.get("upgrade") or {}
        if isinstance(upgrade, dict):
            return str(upgrade.get("remote_temp_dir") or "").strip()
    except Exception:
        pass
    return ""


def resolve_remote_temp_dir(raw: str = "") -> str:
    """Priority: task field > gki-patch-tool.yaml > /tmp."""
    if (raw or "").strip():
        return normalize_linux_path(raw.strip())
    yaml_val = _yaml_remote_temp()
    if yaml_val:
        return normalize_linux_path(yaml_val)
    return DEFAULT_REMOTE_TEMP_DIR


def resolve_job_remote_temp_dir(job: Dict[str, Any]) -> str:
    return resolve_remote_temp_dir(str(job.get("remote_temp_dir") or ""))


def job_remote_temp_join(job: Dict[str, Any], *parts: str) -> str:
    base = resolve_job_remote_temp_dir(job)
    tail = "/".join(p.strip("/").replace("\\", "/") for p in parts if p)
    if not tail:
        return base
    return f"{base}/{tail}"
