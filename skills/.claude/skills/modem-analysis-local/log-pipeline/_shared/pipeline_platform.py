"""Watcher / Phase1 平台参数：Affects Version 前缀、Jira export-flag、评论模板。"""

from __future__ import annotations

import os
from typing import Tuple

VALID_PLATFORMS = frozenset({"mtk", "qcom", "sprd"})

_EXPORT_FLAG_BY_PLATFORM = {
    "mtk": "ModemLogPipelineExportFlag",
    "qcom": "QcomModemLogPipelineExportFlag",
    "sprd": "SprdModemLogPipelineExportFlag",
}


def normalize_platform(raw: str) -> str:
    """空或未传视为 mtk（沿用 JIRA_EXPORT_WATCHER_AFFECTS_VERSION_PREFIXES）。"""
    p = (raw or "").strip().lower()
    if not p or p == "mtk":
        return "mtk"
    if p in VALID_PLATFORMS:
        return p
    raise ValueError(f"不支持的平台 {raw!r}，可选: mtk, qcom, sprd")


def prefixes_env_var(platform: str) -> str:
    if platform == "qcom":
        return "JIRA_EXPORT_WATCHER_PREFIXES_QCOM"
    if platform == "sprd":
        return "JIRA_EXPORT_WATCHER_PREFIXES_SPRD"
    return "JIRA_EXPORT_WATCHER_AFFECTS_VERSION_PREFIXES"


def export_flag(platform: str) -> str:
    return _EXPORT_FLAG_BY_PLATFORM[normalize_platform(platform)]


def resolve_comment_template(platform: str) -> Tuple[str, str]:
    """
    返回 (template_path, source_env_name)。
    优先平台专用变量，否则回落 JIRA_PUBLISH_COMMENT_TEMPLATE。
    """
    p = normalize_platform(platform)
    if p == "qcom":
        names = ("JIRA_PUBLISH_COMMENT_TEMPLATE_QCOM", "JIRA_PUBLISH_COMMENT_TEMPLATE")
    elif p == "sprd":
        names = ("JIRA_PUBLISH_COMMENT_TEMPLATE_SPRD", "JIRA_PUBLISH_COMMENT_TEMPLATE")
    else:
        names = ("JIRA_PUBLISH_COMMENT_TEMPLATE_MTK", "JIRA_PUBLISH_COMMENT_TEMPLATE")
    for name in names:
        val = (os.getenv(name) or "").strip()
        if val:
            return val, name
    return "", names[0]
