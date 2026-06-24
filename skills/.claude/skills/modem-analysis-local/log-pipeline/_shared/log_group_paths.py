"""打包分组路径：相对 normalized_root 保留完整目录层级（POSIX 相对路径）。"""

from __future__ import annotations

import os

_TOOL_OUTPUT_DIR_NAMES = frozenset(
    {"elt_export_txt", "nlt_export_txt", "qcom_export", "elt_export_txt2", "nlt_export_txt2"}
)


def sanitize_path_component(name: str) -> str:
    name = "" if name is None else str(name)
    name = name.strip()
    if not name:
        return "unknown"
    for ch in '<>:"/\\|?*':
        name = name.replace(ch, "_")
    return name.strip("._") or "unknown"


def resolve_group_rel_path(path: str, base_dir: str) -> str:
    """
    计算 path 相对 base_dir（normalized_log_root）的目录层级，用作 group_key / 打包子路径。

    示例：downloads/REF/CASE1/REF-1/mdlog1 -> REF/CASE1/REF-1/mdlog1
    """
    path = os.path.abspath(path)
    base_dir = os.path.abspath(base_dir) if base_dir else ""

    if base_dir:
        try:
            rel = os.path.relpath(path, base_dir)
        except ValueError:
            rel = path
    else:
        rel = path

    parts = []
    for part in os.path.normpath(rel).split(os.sep):
        if not part or part == ".":
            continue
        if part.lower() in _TOOL_OUTPUT_DIR_NAMES:
            continue
        parts.append(sanitize_path_component(part))

    return "/".join(parts) if parts else "root"


def resolve_pack_dest_dir(final_root: str, normalized_root: str, group_rel_path: str) -> str:
    """final_root + 多级相对路径（每段 sanitize）。"""
    final_root = os.path.abspath(final_root)
    group_rel_path = (group_rel_path or "root").replace("\\", "/").strip("/")
    parts = [sanitize_path_component(p) for p in group_rel_path.split("/") if p]
    if not parts:
        parts = ["root"]
    return os.path.join(final_root, *parts)


def resolve_aplog_group_rel_path(path: str, base_dir: str) -> str:
    """
    MTK mobilelog/APLog 打包分组：相对路径截断到 APLog_* 目录一层。

    例：.../mobilelog/APLog_xxx/kernel_log_6__... -> .../mobilelog/APLog_xxx
    """
    full = resolve_group_rel_path(path, base_dir)
    if not full or full == "root":
        return full or "root"
    parts = full.replace("\\", "/").split("/")
    for i, part in enumerate(parts):
        if part.lower().startswith("aplog"):
            return "/".join(parts[: i + 1])
    return full


def resolve_mobilelog_group_rel_path(path: str, base_dir: str) -> str:
    """
    QCOM debuglogger mobilelog 打包分组：相对路径截断到 mobilelog 目录。

    例：.../debuglogger/mobilelog/mainlogcat-log.* -> .../debuglogger/mobilelog
    """
    full = resolve_group_rel_path(path, base_dir)
    if not full or full == "root":
        return full or "root"
    parts = full.replace("\\", "/").split("/")
    for i, part in enumerate(parts):
        if part.lower() == "mobilelog":
            return "/".join(parts[: i + 1])
    return full
