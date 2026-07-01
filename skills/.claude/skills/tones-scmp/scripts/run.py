#!/usr/bin/env python3
"""Portable entry point — run from any skill install location."""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from tones_cli.main import main

if __name__ == "__main__":
    sys.exit(main())
