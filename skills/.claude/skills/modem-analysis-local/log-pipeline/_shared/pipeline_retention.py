"""Pipeline 本地文件保留策略（下载、解压、过滤阶段是否删除源文件）。"""

from __future__ import annotations

import os

_TRUTHY = frozenset({"1", "true", "yes", "y", "on"})
_FALSY = frozenset({"0", "false", "no", "n", "off"})


def _parse_env_bool(name: str) -> bool | None:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return None
    if raw in _TRUTHY:
        return True
    if raw in _FALSY:
        return False
    return None


def should_preserve_local_files() -> bool:
    """
    是否保留下载/解压后的本地文件（默认保留，便于继续分析调试）。

    优先级（高 → 低）：
    1. DELETE_LOCAL_FILES_AFTER_PIPELINE=1 → 不保留（Step 8 删 downloads，Step 4 执行精简删除）
    2. PIPELINE_KEEP_LOCAL_FILES=0/1
    3. 兼容旧变量 SKIP_DOWNLOAD_CLEANUP（仅影响 downloads 清理语义时由 should_skip_download_cleanup 读取）
    4. 默认 True（保留）
    """
    if _parse_env_bool("DELETE_LOCAL_FILES_AFTER_PIPELINE") is True:
        return False
    keep = _parse_env_bool("PIPELINE_KEEP_LOCAL_FILES")
    if keep is not None:
        return keep
    return True


def should_skip_download_cleanup() -> bool:
    """Step 8 完成后是否跳过删除 downloads/。"""
    legacy = _parse_env_bool("SKIP_DOWNLOAD_CLEANUP")
    if legacy is not None:
        return legacy
    return should_preserve_local_files()


def should_skip_log_filter_deletion() -> bool:
    """
    Step 4 是否跳过「删非 modem 目录 / 精简 APLog」等破坏性过滤。

    默认与 should_preserve_local_files 一致；可单独用 SKIP_LOG_FILTER_DELETION 覆盖。
    """
    explicit = _parse_env_bool("SKIP_LOG_FILTER_DELETION")
    if explicit is not None:
        return explicit
    return should_preserve_local_files()
