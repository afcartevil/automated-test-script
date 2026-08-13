"""
flow_power_dou 技能内运行时路径：CPU 磁盘缓存、Flask Session 落盘目录均固定在技能目录下，
不依赖进程当前工作目录（cwd）。工作区根解析见 analysis/base/lib/repo_paths.py。
"""
from __future__ import annotations

from pathlib import Path

# .../dou_2/scripts/paths.py -> 技能根目录 dou_2
DOU_SKILL_ROOT: Path = Path(__file__).resolve().parent.parent

CPU_CACHE_DIR: Path = DOU_SKILL_ROOT / "cpu_cache"
FLASK_SESSION_DIR: Path = DOU_SKILL_ROOT / "flask_session"
IGNORABLE_SCENES_JSON: Path = DOU_SKILL_ROOT / "ignorable_scenes.json"
KNOWN_ISSUES_MD: Path = DOU_SKILL_ROOT / "known_issues.md"


def ensure_cpu_cache_dir() -> Path:
    CPU_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CPU_CACHE_DIR


def ensure_flask_session_dir() -> Path:
    FLASK_SESSION_DIR.mkdir(parents=True, exist_ok=True)
    return FLASK_SESSION_DIR


def ensure_dou_runtime_dirs() -> None:
    """创建 CPU 缓存与 Flask Session 目录（幂等）。"""
    ensure_cpu_cache_dir()
    ensure_flask_session_dir()


def flask_session_config() -> dict:
    """供 Flask 应用合并到 app.config，例如：app.config.update(flask_session_config())"""
    ensure_flask_session_dir()
    return {"SESSION_FILE_DIR": str(FLASK_SESSION_DIR)}


# 导入本模块时即确保目录存在，避免首次写缓存失败
ensure_dou_runtime_dirs()
