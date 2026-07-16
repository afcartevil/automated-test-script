"""Shared CLI / runtime settings loader (gki-patch-tool.yaml)."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SETTINGS_ENV = "GKI_SETTINGS"
DEFAULT_SETTINGS_FILES = ("gki-patch-tool.yaml", "gki-patch-tool.yml")
DEFAULT_REPO_URL = "https://android.googlesource.com/kernel/common"
DEFAULT_SCORING_CONFIG = PROJECT_ROOT / "config" / "scoring-config.yaml"
DEFAULT_DEV_MODULES_FILE = PROJECT_ROOT / "config" / "dev_modules.txt"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs"
DEFAULT_OUTPUT_JSON = "patch-analysis-result.json"
ENV_REPO_DIR = "GKI_REPO_DIR"


def strip_settings_from_argv(argv: List[str]) -> Tuple[Optional[str], List[str]]:
    """Extract --settings/-s from argv before main argparse."""
    settings_path: Optional[str] = None
    rest: List[str] = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("--settings", "-s"):
            if i + 1 >= len(argv):
                raise ValueError(f"{arg} 需要指定配置文件路径")
            settings_path = argv[i + 1]
            i += 2
            continue
        if arg.startswith("--settings="):
            settings_path = arg.split("=", 1)[1]
            i += 1
            continue
        rest.append(arg)
        i += 1
    return settings_path, rest


def find_settings_path(explicit: Optional[str] = None) -> Optional[Path]:
    if explicit:
        p = Path(explicit).expanduser()
        if not p.is_absolute():
            p = (Path.cwd() / p).resolve()
        return p if p.exists() else None

    env_path = os.environ.get(SETTINGS_ENV, "").strip()
    if env_path:
        p = Path(env_path).expanduser()
        if not p.is_absolute():
            p = (Path.cwd() / p).resolve()
        if p.exists():
            return p

    for name in DEFAULT_SETTINGS_FILES:
        for base in (Path.cwd(), PROJECT_ROOT):
            p = (base / name).resolve()
            if p.exists():
                return p
    return None


def load_settings(explicit: Optional[str] = None) -> Tuple[Dict[str, Any], Optional[Path]]:
    path = find_settings_path(explicit)
    if not path:
        return {}, None
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"配置文件格式错误（需为 YAML 对象）: {path}")
    return data, path


def resolve_path(value: Optional[str], *, must_exist: bool = False) -> Optional[Path]:
    raw = (value or "").strip()
    if not raw:
        return None
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = (PROJECT_ROOT / p).resolve()
    else:
        p = p.resolve()
    if must_exist and not p.exists():
        return None
    return p


def _section(settings: Dict[str, Any], key: str) -> Dict[str, Any]:
    value = settings.get(key, {})
    return value if isinstance(value, dict) else {}


def get_repo_url(settings: Dict[str, Any]) -> str:
    return str(_section(settings, "repo").get("url") or DEFAULT_REPO_URL).strip()


def get_scoring_config_path(settings: Dict[str, Any]) -> Path:
    raw = _section(settings, "scoring").get("config")
    if raw:
        p = resolve_path(str(raw))
        if p and p.exists():
            return p
    return DEFAULT_SCORING_CONFIG


def get_output_dir(settings: Dict[str, Any]) -> Path:
    raw = _section(settings, "output").get("dir")
    if raw:
        p = resolve_path(str(raw), must_exist=False)
        if p:
            return p
    return DEFAULT_OUTPUT_DIR


def get_default_output_json(settings: Dict[str, Any]) -> str:
    raw = _section(settings, "output").get("json")
    return str(raw).strip() if raw else DEFAULT_OUTPUT_JSON


def resolve_output_path(settings: Dict[str, Any], cli_output: Optional[str]) -> Path:
    if cli_output:
        p = Path(cli_output).expanduser()
        if not p.is_absolute():
            p = (Path.cwd() / p).resolve()
        return p
    out_dir = get_output_dir(settings)
    return (out_dir / get_default_output_json(settings)).resolve()


def get_analysis_options(settings: Dict[str, Any]) -> Dict[str, int]:
    analysis = _section(settings, "analysis")
    return {
        "workers": int(analysis.get("workers", 6)),
        "chunk_size": int(analysis.get("chunk_size", 100)),
        "retry": int(analysis.get("retry", 1)),
        "sample_size": int(analysis.get("sample_size", 100)),
        "sample_seed": int(analysis.get("sample_seed", 42)),
    }


def get_llm_options(settings: Dict[str, Any]) -> Dict[str, Any]:
    llm = _section(settings, "llm")
    return {
        "api_key": str(llm.get("api_key") or os.environ.get("GKI_LLM_API_KEY", "")).strip(),
        "api_base": str(llm.get("api_base") or os.environ.get("GKI_LLM_API_BASE", "https://api.openai.com/v1")).rstrip("/"),
        "model": str(llm.get("model") or os.environ.get("GKI_LLM_MODEL", "gpt-4o")).strip(),
        "concurrency": int(llm.get("concurrency") or os.environ.get("GKI_LLM_CONCURRENCY", 10)),
    }


def get_target_repo_dir_from_settings(
    settings: Dict[str, Any],
    cli_target_dir: Optional[str] = None,
) -> Optional[Path]:
    if cli_target_dir:
        return resolve_path(cli_target_dir, must_exist=False)
    env_path = os.environ.get("GKI_TARGET_REPO_DIR", "").strip()
    if env_path:
        p = resolve_path(env_path, must_exist=False)
        if p and _path_is_usable(p):
            return p
    yaml_dir = _section(settings, "target_repo").get("dir")
    if yaml_dir:
        p = resolve_path(str(yaml_dir), must_exist=False)
        if p and _path_is_usable(p):
            return p
    return None


def get_upgrade_options(settings: Dict[str, Any]) -> Dict[str, Any]:
    upgrade = _section(settings, "upgrade")
    build = _section(settings, "build")
    mode = str(upgrade.get("apply_mode") or "squash").strip()
    if mode not in ("format-patch", "squash"):
        mode = "squash"
    return {
        "apply_mode": mode,
        "build_command": str(build.get("command") or os.environ.get("GKI_BUILD_COMMAND", "")).strip(),
        "build_workdir": str(build.get("workdir") or "").strip(),
        "build_timeout": int(build.get("timeout_seconds") or 3600),
        "target_branch": str(_section(settings, "target_repo").get("branch") or "").strip(),
    }


def get_repo_dir(
    settings: Dict[str, Any],
    cli_repo_dir: Optional[str] = None,
) -> Optional[Path]:
    """Resolve local kernel repo path.

    Priority: CLI --repo-dir > env GKI_REPO_DIR > yaml repo.dir > code/common.
    """
    if cli_repo_dir:
        p = resolve_path(cli_repo_dir, must_exist=False)
        return p

    env_path = os.environ.get(ENV_REPO_DIR, "").strip()
    if env_path:
        p = resolve_path(env_path, must_exist=False)
        if p and _path_is_usable(p):
            return p

    yaml_dir = _section(settings, "repo").get("dir")
    if yaml_dir:
        p = resolve_path(str(yaml_dir), must_exist=False)
        if p and _path_is_usable(p):
            return p

    fallback = PROJECT_ROOT / "code" / "common"
    if _path_is_usable(fallback):
        return fallback.resolve()
    return None


def _path_is_usable(p: Path) -> bool:
    return (p / ".git").exists() or p.is_dir()


def get_yaml_repo_dir(settings: Dict[str, Any]) -> Optional[Path]:
    """Repo dir from yaml only (for web fallback between env and default)."""
    yaml_dir = _section(settings, "repo").get("dir")
    if not yaml_dir:
        return None
    p = resolve_path(str(yaml_dir), must_exist=False)
    if p and _path_is_usable(p):
        return p
    return None


def add_settings_argument(parser: Any) -> None:
    parser.add_argument(
        "-s",
        "--settings",
        help="配置文件路径（默认自动查找 gki-patch-tool.yaml）",
    )


def patch_analyzer_defaults(settings: Dict[str, Any]) -> Dict[str, Any]:
    analysis = get_analysis_options(settings)
    return {
        "repo": get_repo_url(settings),
        "config": str(get_scoring_config_path(settings)),
        "workers": analysis["workers"],
        "chunk_size": analysis["chunk_size"],
        "retry": analysis["retry"],
        "output": str(resolve_output_path(settings, None)),
    }


def sample_analyzer_defaults(settings: Dict[str, Any]) -> Dict[str, Any]:
    base = patch_analyzer_defaults(settings)
    analysis = get_analysis_options(settings)
    out_dir = get_output_dir(settings)
    base["output"] = str((out_dir / "sample-analysis.json").resolve())
    base["sample_size"] = analysis["sample_size"]
    base["seed"] = analysis["sample_seed"]
    return base
