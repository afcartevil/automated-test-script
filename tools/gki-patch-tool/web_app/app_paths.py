"""Resolve bundle vs install paths for development and PyInstaller frozen builds."""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Iterable, Union

PathLike = Union[str, Path]


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def bundle_root() -> Path:
    """Read-only packaged resources (_MEIPASS when frozen, repo root in dev)."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def install_root() -> Path:
    """Writable root: directory containing the exe when frozen, repo root in dev."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def project_root() -> Path:
    return install_root()


def tools_dir() -> Path:
    bundled = bundle_root() / "tools"
    if bundled.is_dir():
        return bundled
    return install_root() / "tools"


def _prefer_install_then_bundle(*rel_parts: str) -> Path:
    installed = install_root().joinpath(*rel_parts)
    if installed.exists():
        return installed
    return bundle_root().joinpath(*rel_parts)


def scoring_config_path() -> Path:
    return _prefer_install_then_bundle("config", "scoring-config.yaml")


def dev_modules_path() -> Path:
    return _prefer_install_then_bundle("config", "dev_modules.txt")


def checklist_config_path() -> Path:
    return _prefer_install_then_bundle("config", "checklist_config.yaml")


def frontend_dist_dir() -> Path:
    if is_frozen():
        return bundle_root() / "frontend" / "dist"
    return install_root() / "frontend" / "dist"


def outputs_dir(*parts: PathLike) -> Path:
    base = install_root() / "outputs"
    path = base.joinpath(*map(str, parts)) if parts else base
    path.mkdir(parents=True, exist_ok=True)
    return path


def data_dir() -> Path:
    override = os.environ.get("GKI_DATA_DIR", "").strip()
    if override:
        path = Path(override) / "web_app" / "data"
    elif is_frozen():
        path = install_root() / "data"
    else:
        path = Path(__file__).resolve().parent / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def seed_db_path() -> Path:
    return bundle_root() / "web_app" / "seed" / "gki_patch.db.seed"


def settings_file() -> Path:
    env = os.environ.get("GKI_SETTINGS", "").strip()
    if env:
        return Path(env)
    for name in ("gki-patch-tool.yaml", "gki-patch-tool.yml"):
        candidate = install_root() / name
        if candidate.is_file():
            return candidate
    return install_root() / "gki-patch-tool.yaml"


def overview_html_path() -> Path:
    return _prefer_install_then_bundle("gkiPatchTool_OVERVIEW.html")


def ensure_install_layout() -> None:
    """Create writable dirs and seed default config beside the exe on first run."""
    outputs_dir()
    data_dir()

    settings_dest = install_root() / "gki-patch-tool.yaml"
    if not settings_dest.is_file():
        src = bundle_root() / "gki-patch-tool.yaml"
        if src.is_file():
            shutil.copy2(src, settings_dest)

    config_dest = install_root() / "config"
    if not config_dest.is_dir():
        src_cfg = bundle_root() / "config"
        if src_cfg.is_dir():
            shutil.copytree(src_cfg, config_dest)


def register_tools_aliases() -> None:
    """Expose tools.* as legacy top-level module names in frozen builds."""
    if not is_frozen():
        return
    import importlib

    for name in (
        "patch_analyzer",
        "cli_config",
        "render_report",
        "render_report_llm",
        "render_report_indexed",
        "render_interval_hybrid_overview",
        "merge_llm_analysis",
        "export_patch_analysis_to_excel",
        "extract_patches_for_llm",
        "sample_analyzer",
        "upgrade_runner",
    ):
        full_name = f"tools.{name}"
        if name in sys.modules:
            continue
        try:
            sys.modules[name] = importlib.import_module(full_name)
        except ModuleNotFoundError:
            pass


def setup_sys_path() -> None:
    for entry in (install_root(), tools_dir()):
        entry_s = str(entry)
        if entry_s not in sys.path:
            sys.path.insert(0, entry_s)
    register_tools_aliases()


def resolve_under_root(path: PathLike) -> Path:
    p = Path(path)
    if p.is_absolute():
        return p.resolve()
    return (install_root() / p).resolve()
