"""Skill 根目录 .env 加载（不依赖 python-dotenv）。

供 scripts/*.py 共用：dotenv 已安装则优先用；否则用内置解析器。
"""

from __future__ import annotations

import os
from pathlib import Path

# scripts/_shared/skill_env.py → skill 根 = scripts 的上一级（modem-analysis-unified）
SKILL_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_PATH = SKILL_ROOT / ".env"

_DOTENV_SOURCE = "none"


def _builtin_load_env(path: Path) -> int:
    """无依赖 .env 解析。返回写入 os.environ 的键数（仅当 key 尚未在 os.environ 中）。"""
    if not path.is_file():
        return 0
    count = 0
    with open(path, "r", encoding="utf-8-sig") as fp:
        for raw in fp:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.lower().startswith("export "):
                line = line[7:].lstrip()
            if "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip()
            if not key:
                continue
            if len(val) >= 2 and (
                (val[0] == val[-1] == '"') or (val[0] == val[-1] == "'")
            ):
                val = val[1:-1]
            if key not in os.environ:
                os.environ[key] = val
                count += 1
    return count


def load_skill_env() -> str:
    """加载 SKILL_ROOT/.env，返回人类可读的加载来源说明（用于日志）。"""
    global _DOTENV_SOURCE
    if not ENV_PATH.exists():
        _DOTENV_SOURCE = f"NOT FOUND: {ENV_PATH}"
        return _DOTENV_SOURCE
    try:
        from dotenv import load_dotenv  # type: ignore

        load_dotenv(ENV_PATH)
        _DOTENV_SOURCE = f"python-dotenv ({ENV_PATH})"
    except ImportError:
        n = _builtin_load_env(ENV_PATH)
        _DOTENV_SOURCE = f"builtin parser, {n} keys ({ENV_PATH})"
    return _DOTENV_SOURCE


def dotenv_source() -> str:
    return _DOTENV_SOURCE
