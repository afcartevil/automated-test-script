from __future__ import annotations

import sys
from pathlib import Path

_DIR = Path(__file__).resolve().parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))

from power_scene_runner import run_scene


def run(**context):
    return run_scene(scene="通用全域测试", **context)
