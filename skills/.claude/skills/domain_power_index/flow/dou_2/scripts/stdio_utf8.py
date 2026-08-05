"""CLI 脚本 UTF-8 stdio 初始化（Windows 中文输出）。"""
from __future__ import annotations

import sys


def _setup_utf8_stdio() -> None:
    for name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
