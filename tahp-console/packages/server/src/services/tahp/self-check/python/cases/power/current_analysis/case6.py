from __future__ import annotations

import sys
from pathlib import Path

_DIR = Path(__file__).resolve().parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))

from power_scene_runner import run_scene


def run(case_ids=None, **context):
    return run_scene(scene="基础体验场景", case_ids=case_ids, **context)
