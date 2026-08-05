#!/usr/bin/env python3
"""兼容层：请使用 game_precondition/scripts/game_precondition.py"""
from __future__ import annotations

import sys
from pathlib import Path

def _setup_utf8_stdio() -> None:
    for name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS = _ROOT / "game_precondition" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from game_precondition import main  # noqa: E402

if __name__ == "__main__":
    _setup_utf8_stdio()
    raise SystemExit(main())
