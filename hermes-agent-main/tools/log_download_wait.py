"""Detect jira-ops log-download CLI so Hermes can wait until the process exits.

SGBOX/FRBOX downloads routinely outlast the generic sequential tool deadline
(420s) and terminal foreground cap (600s). HTTP stall handling stays in the
Skill script; this module only identifies those CLI invocations.
"""

from __future__ import annotations

import re
from typing import Any

# Subcommands of scripts/api_jira.py (and wrappers) that stream log archives.
_LOG_DOWNLOAD_TOKEN = re.compile(
    r"(?:^|[\s\"'=])(prepare-logs|download-logs|download-box)(?:$|[\s\"'])",
    re.IGNORECASE,
)


def is_log_download_command(command: str | None) -> bool:
    if not command or not isinstance(command, str):
        return False
    return _LOG_DOWNLOAD_TOKEN.search(command) is not None


def is_log_download_tool_call(function_name: str | None, function_args: Any) -> bool:
    if (function_name or "") != "terminal":
        return False
    if not isinstance(function_args, dict):
        return False
    cmd = function_args.get("command") or function_args.get("cmd") or ""
    return is_log_download_command(str(cmd) if cmd is not None else "")


# stdout last-line hints from jira-ops aliyun_pds_downloader / extract.
_PROGRESS_HINTS = (
    "下载进度",
    "开始流式下载",
    "下载中",
    "解压",
    "获取share_token",
    "合并分块",
    "检测服务器能力",
    "线程分块下载",
    "[文件]",
    "[文件夹]",
    "下载完成",
    "下载失败",
)


def is_log_download_progress_line(line: str | None) -> bool:
    if not line or not isinstance(line, str):
        return False
    text = line.strip()
    if not text:
        return False
    return any(hint in text for hint in _PROGRESS_HINTS)
