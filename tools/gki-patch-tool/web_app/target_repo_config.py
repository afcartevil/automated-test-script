"""Upgrade workflow defaults (apply mode). Build settings are per-task only."""
import sys
from pathlib import Path
from typing import Any, Dict, Optional

PROJECT_ROOT = Path(__file__).parent.parent
DB_APPLY_MODE_KEY = "upgrade_apply_mode"


def _path_is_usable(p: Path) -> bool:
    return (p / ".git").exists() or p.is_dir()


def normalize_linux_path(path_str: str) -> str:
    """Normalize a Linux absolute path; safe against Windows Path backslash mangling."""
    s = (path_str or "").strip().replace("\\", "/")
    while "//" in s:
        s = s.replace("//", "/")
    return s.rstrip("/") or s


def resolve_target_repo_path(path_str: str) -> Optional[Path]:
    """Resolve a per-task vendor kernel path (must be explicitly provided)."""
    raw = (path_str or "").strip()
    if not raw:
        return None
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = (PROJECT_ROOT / p).resolve()
    else:
        p = p.resolve()
    if _path_is_usable(p):
        return p
    return None


def resolve_build_workdir(path_str: str) -> Optional[Path]:
    """Resolve per-task build working directory."""
    raw = (path_str or "").strip()
    if not raw:
        return None
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = (PROJECT_ROOT / p).resolve()
    else:
        p = p.resolve()
    return p if p.is_dir() else None


def _yaml_settings() -> Dict[str, Any]:
    try:
        sys.path.insert(0, str(PROJECT_ROOT / "tools"))
        from cli_config import load_settings

        settings, _ = load_settings()
        return settings
    except Exception:
        return {}


def _yaml_section(key: str) -> Dict[str, Any]:
    section = _yaml_settings().get(key, {})
    return section if isinstance(section, dict) else {}


def _db_value(key: str) -> str:
    try:
        from web_app.database import get_config_value

        return get_config_value(key) or ""
    except Exception:
        return ""


def get_apply_mode() -> str:
    db_mode = _db_value(DB_APPLY_MODE_KEY).strip()
    if db_mode in ("format-patch", "squash"):
        return db_mode
    yaml_mode = str(_yaml_section("upgrade").get("apply_mode") or "squash").strip()
    return yaml_mode if yaml_mode in ("format-patch", "squash") else "squash"


def get_build_timeout() -> int:
    try:
        return int(_yaml_section("build").get("timeout_seconds") or 3600)
    except (TypeError, ValueError):
        return 3600


def get_upgrade_defaults_config() -> Dict[str, Any]:
    return {
        "apply_mode": get_apply_mode(),
        "build_timeout_seconds": get_build_timeout(),
    }


def save_upgrade_defaults_config(apply_mode: str = "") -> None:
    from web_app.database import set_config_value

    if apply_mode in ("format-patch", "squash"):
        set_config_value(DB_APPLY_MODE_KEY, apply_mode)


get_target_repo_config = get_upgrade_defaults_config
save_target_repo_config = save_upgrade_defaults_config
