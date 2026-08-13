"""flow/game 子 skill 脚本路径辅助。"""

from __future__ import annotations

import sys
from pathlib import Path


def game_scripts_dir(from_file: str | Path) -> Path:
    p = Path(from_file).resolve()
    for parent in p.parents:
        if parent.name == "game" and (parent / "scripts" / "skill_references.py").is_file():
            return parent / "scripts"
    raise RuntimeError("未找到 flow/game/scripts")


def ensure_game_scripts_on_path(from_file: str | Path) -> Path:
    scripts = game_scripts_dir(from_file)
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    return scripts
