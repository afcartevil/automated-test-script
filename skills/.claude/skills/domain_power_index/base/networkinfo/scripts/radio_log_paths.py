"""radio_log 路径解析：工作区 converted/APLog 优先（base_networkinfo 专用）。"""
from __future__ import annotations

import os
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)
_BASE_LIB = os.path.abspath(
    os.path.join(_SCRIPT_DIR, "..", "..", "..", "..", "..", "base", "lib")
)
if _BASE_LIB not in sys.path:
    sys.path.insert(0, _BASE_LIB)

from repo_paths import find_repo_root, resolve_workspace_dir  # noqa: E402

_RADIO_PREFIX = "radio_log_"


def _walk_radio_log_files(root: str) -> list[str]:
    found: list[str] = []
    if not os.path.isdir(root):
        return found
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            if name.startswith(_RADIO_PREFIX):
                found.append(os.path.join(dirpath, name))
    return found


def _workspace_from_input(input_path: str, repo_root: str | None) -> str | None:
    norm = os.path.normpath(input_path.strip())
    if os.path.isfile(norm):
        norm = os.path.dirname(norm)
    try:
        base = os.path.basename(norm).lower()
        if base == "downloads":
            return os.path.dirname(norm)
        if base == "converted":
            return os.path.dirname(norm)
        if base in ("aplog", "ntlog", "bugreports"):
            return os.path.dirname(os.path.dirname(norm))
        ws = resolve_workspace_dir(norm, repo_root)
        if os.path.isdir(ws):
            return ws
    except Exception:
        pass
    return None


def resolve_radio_log_scan_dir(input_path: str, repo_root: str | None = None) -> str:
    """
    解析用于扫描 radio_log_* 的目录。

    优先级：
    1. 输入为 radio_log 文件 → 其所在目录
    2. 工作区 converted/APLog/ 且含 radio_log_*
    3. 工作区 converted/ 且含 radio_log_*
    4. 输入目录本身（递归）含 radio_log_*
    5. 回退为规范化后的输入路径
    """
    repo = repo_root or find_repo_root(input_path)
    raw = os.path.normpath(input_path.strip())
    if os.path.isfile(raw) and os.path.basename(raw).startswith(_RADIO_PREFIX):
        return os.path.dirname(raw)

    workspace = _workspace_from_input(raw, repo)
    if workspace:
        for sub in ("APLog", ""):
            candidate = (
                os.path.join(workspace, "converted", sub)
                if sub
                else os.path.join(workspace, "converted")
            )
            if os.path.isdir(candidate) and _walk_radio_log_files(candidate):
                return candidate

    if os.path.isdir(raw) and _walk_radio_log_files(raw):
        return raw

    if workspace:
        flat = os.path.join(workspace, "converted", "APLog")
        if os.path.isdir(flat):
            return flat
        converted = os.path.join(workspace, "converted")
        if os.path.isdir(converted):
            return converted

    return raw


def discover_radio_log_files(
    input_path: str, repo_root: str | None = None
) -> tuple[str, list[str]]:
    """返回 (scan_dir, radio_log_paths)。"""
    scan_dir = resolve_radio_log_scan_dir(input_path, repo_root)
    files = sorted(_walk_radio_log_files(scan_dir), key=lambda p: os.path.basename(p).lower())
    return scan_dir, files


def resolve_radio_log(input_path: str, repo_root: str | None = None) -> dict:
    """探测 radio_log 是否就绪及扫描目录。"""
    scan_dir, files = discover_radio_log_files(input_path, repo_root)
    return {
        "scan_dir": scan_dir,
        "radio_log_count": len(files),
        "radio_log_files": [os.path.basename(p) for p in files],
        "ready": bool(files),
    }
