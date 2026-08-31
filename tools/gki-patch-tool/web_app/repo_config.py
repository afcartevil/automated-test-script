"""Local kernel repository path configuration."""
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from web_app.app_paths import install_root, setup_sys_path, tools_dir

setup_sys_path()

ENV_KEY = "GKI_REPO_DIR"
DEFAULT_RELATIVE_REPO = install_root() / "code" / "common"


def _path_is_usable(p: Path) -> bool:
    return (p / ".git").exists() or p.is_dir()


def _resolve_path(path_str: str) -> Optional[Path]:
    raw = path_str.strip()
    if not raw:
        return None
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = (install_root() / p).resolve()
    else:
        p = p.resolve()
    if _path_is_usable(p):
        return p
    return None


def get_local_repo_dir() -> Optional[Path]:
    """Resolve effective local repo directory.

    Priority: DB config > GKI_REPO_DIR env > gki-patch-tool.yaml > code/common fallback.
    """
    try:
        from web_app.database import get_db_repo_dir

        db_path = get_db_repo_dir()
    except Exception:
        db_path = ""
    if db_path:
        resolved = _resolve_path(db_path)
        if resolved:
            return resolved

    env_path = os.environ.get(ENV_KEY, "").strip()
    if env_path:
        resolved = _resolve_path(env_path)
        if resolved:
            return resolved

    try:
        sys.path.insert(0, str(tools_dir()))
        from cli_config import get_yaml_repo_dir, load_settings

        settings, _ = load_settings()
        yaml_repo = get_yaml_repo_dir(settings)
        if yaml_repo:
            return yaml_repo
    except Exception:
        pass

    if _path_is_usable(DEFAULT_RELATIVE_REPO):
        return DEFAULT_RELATIVE_REPO.resolve()
    return None


def _detect_source(
    effective: Optional[Path],
    db_path: str,
    env_path: str,
    yaml_effective: Optional[Path] = None,
) -> str:
    if effective is None:
        return "none"
    eff_str = str(effective)
    if db_path:
        db_resolved = _resolve_path(db_path)
        if db_resolved and str(db_resolved) == eff_str:
            return "db"
    if env_path:
        env_resolved = _resolve_path(env_path)
        if env_resolved and str(env_resolved) == eff_str:
            return "env"
    if yaml_effective and str(yaml_effective) == eff_str:
        return "yaml"
    if _path_is_usable(DEFAULT_RELATIVE_REPO):
        if str(DEFAULT_RELATIVE_REPO.resolve()) == eff_str:
            return "default"
    return "unknown"


def get_repo_config() -> Dict[str, Any]:
    """Return config info for API/display."""
    try:
        from web_app.database import get_db_repo_dir

        db_path = get_db_repo_dir()
    except Exception:
        db_path = ""
    env_path = os.environ.get(ENV_KEY, "").strip()
    yaml_path = ""
    yaml_settings_file = ""
    yaml_effective: Optional[Path] = None
    try:
        sys.path.insert(0, str(tools_dir()))
        from cli_config import _section, get_yaml_repo_dir, load_settings

        settings, settings_file = load_settings()
        yaml_path = str(_section(settings, "repo").get("dir") or "")
        yaml_settings_file = str(settings_file) if settings_file else ""
        yaml_effective = get_yaml_repo_dir(settings)
    except Exception:
        pass
    effective = get_local_repo_dir()
    return {
        "configured": effective is not None,
        "repo_dir": db_path or "",
        "effective_dir": str(effective) if effective else "",
        "source": _detect_source(effective, db_path, env_path, yaml_effective),
        "env_dir": env_path,
        "yaml_dir": yaml_path,
        "yaml_settings_file": yaml_settings_file,
        "default_dir": str(DEFAULT_RELATIVE_REPO),
    }


def save_repo_config(repo_dir: str) -> None:
    from web_app.database import save_db_repo_dir

    save_db_repo_dir(repo_dir.strip())
