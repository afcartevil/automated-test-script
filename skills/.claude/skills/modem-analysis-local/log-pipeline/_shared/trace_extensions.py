"""Modem trace 文件后缀约定（MTK / QCOM 分列，互不改对方逻辑）。"""

from __future__ import annotations

import os
from typing import Iterable, List, Set, Tuple

# MTK — 仅供既有 export_traces / mddb 路径使用，本模块不改动其调用方逻辑
MUX_EXTENSIONS = (".mux", ".muxz", ".muxraw")

# QCOM
QCOM_TRACE_EXTENSIONS = (".qmdl2", ".qdss")

# 与 export_traces.EXPORT_ROOTS 对齐，扫描时跳过工具输出目录
_TOOL_OUTPUT_DIR_NAMES = frozenset({"elt_export_txt", "nlt_export_txt", "qcom_export"})


def is_qcom_trace_filename(name: str) -> bool:
    return (name or "").lower().endswith(QCOM_TRACE_EXTENSIONS)


def discover_qcom_trace_dirs(base_dir: str) -> List[str]:
    """
    返回 base_dir 下「直接含有 .qmdl2 或 .qdss 文件」的目录绝对路径列表（去重排序）。
    """
    base_dir = os.path.abspath(base_dir)
    if not os.path.isdir(base_dir):
        return []

    found: Set[str] = set()
    for root, dirs, files in os.walk(base_dir):
        dirs[:] = [d for d in dirs if d.lower() not in _TOOL_OUTPUT_DIR_NAMES]
        if any(is_qcom_trace_filename(name) for name in files):
            found.add(os.path.abspath(root))
    return sorted(found)


def iter_qcom_trace_groups(input_path: str) -> List[Tuple[str, List[str]]]:
    """
    按目录分组 QCOM trace 文件，格式与 iter_trace_groups（MTK）类似。
    返回 [(group_dir, [file paths]), ...]
    """
    input_path = os.path.abspath(input_path)
    if os.path.isfile(input_path):
        if is_qcom_trace_filename(os.path.basename(input_path)):
            return [(os.path.dirname(input_path), [input_path])]
        return []

    if not os.path.isdir(input_path):
        return []

    grouped: dict = {}
    for root, dirs, files in os.walk(input_path):
        dirs[:] = [d for d in dirs if d.lower() not in _TOOL_OUTPUT_DIR_NAMES]
        paths = sorted(
            os.path.join(root, name)
            for name in files
            if is_qcom_trace_filename(name)
        )
        if paths:
            grouped[root] = paths

    return sorted(grouped.items(), key=lambda item: item[0])
