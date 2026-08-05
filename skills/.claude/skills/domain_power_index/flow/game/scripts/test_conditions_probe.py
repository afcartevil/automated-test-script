"""兼容 shim：转发至 game_precondition/precondition_probe。"""
from __future__ import annotations

import sys
from pathlib import Path

_GP_SCRIPTS = Path(__file__).resolve().parent.parent / "game_precondition" / "scripts"
if str(_GP_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_GP_SCRIPTS))

from precondition_probe import probe_test_conditions, probe_volume_stats  # noqa: F401

__all__ = ["probe_test_conditions", "probe_volume_stats"]
