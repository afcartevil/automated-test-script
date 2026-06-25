#!/usr/bin/env python3
"""刷机包路径选择（tkinter，与 autotest device_update_interface 同源）。"""
from __future__ import annotations

import json
import os
import sys


def _configure_stdio_utf8() -> None:
    """Node 通过 pipe 读取 stdout；Windows 默认 cp936 会导致中文路径乱码。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8")
            except (OSError, ValueError):
                pass


def _has_display() -> bool:
    if sys.platform == "win32":
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def pick_file() -> dict:
    if not _has_display():
        return {"canceled": True, "error": "无图形界面，请手动输入路径"}

    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        return {"canceled": True, "error": "Python 无 tkinter（Linux: apt install python3-tk）"}

    root = tk.Tk()
    root.withdraw()
    try:
        root.attributes("-topmost", True)
    except tk.TclError:
        pass
    root.update_idletasks()
    try:
        selected = filedialog.askopenfilename(
            parent=root,
            title="选择版本包（zip / scatter xml）",
            filetypes=[
                ("刷机包", "*.zip *.xml"),
                ("ZIP", "*.zip"),
                ("Scatter XML", "*.xml"),
                ("所有文件", "*.*"),
            ],
        )
        if selected:
            return {"canceled": False, "path": selected}
        return {"canceled": True}
    finally:
        root.destroy()


if __name__ == "__main__":
    _configure_stdio_utf8()
    if "--probe" in sys.argv:
        if not _has_display():
            sys.exit(2)
        try:
            import tkinter  # noqa: F401
        except ImportError:
            sys.exit(1)
        sys.exit(0)
    if "--pick" in sys.argv:
        print(json.dumps(pick_file(), ensure_ascii=False), flush=True)
        sys.exit(0)
    sys.exit(2)
