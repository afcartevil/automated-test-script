#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("PYTHONUNBUFFERED", "1")
os.environ.setdefault("PYTHONUTF8", "1")

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from checklist_scmp_sync.cli import main

if __name__ == "__main__":
    sys.exit(main())
