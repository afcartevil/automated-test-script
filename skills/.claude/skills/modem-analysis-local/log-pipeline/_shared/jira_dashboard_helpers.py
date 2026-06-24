"""Jira → 飞书看板字段辅助（状态英文、经办人、工单内日志路径）。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# 常见 Jira 中文状态 → 英文（Transsion 实例）
STATUS_ZH_TO_EN: Dict[str, str] = {
    "开放": "Open",
    "待办": "To Do",
    "进行中": "In Progress",
    "处理中": "In Progress",
    "审核中": "In Review",
    "已解决": "Resolved",
    "解决": "Resolved",
    "已关闭": "Closed",
    "关闭": "Closed",
    "重新打开": "Reopened",
    "完成": "Done",
    "未解决": "Unresolved",
    "挂起": "On Hold",
    "等待": "Waiting",
}

STATUS_CATEGORY_KEY_TO_EN: Dict[str, str] = {
    "new": "Open",
    "indeterminate": "In Progress",
    "done": "Done",
}


def normalize_jira_status_en(status: Any) -> str:
    """将 Jira status 对象或中文 name 转为英文展示名。"""
    if status is None:
        return ""
    if isinstance(status, str):
        name = status.strip()
        if not name:
            return ""
        if name in STATUS_ZH_TO_EN:
            return STATUS_ZH_TO_EN[name]
        # 已是英文或未知：原样返回
        return name

    if isinstance(status, dict):
        name = (status.get("name") or "").strip()
        if name in STATUS_ZH_TO_EN:
            return STATUS_ZH_TO_EN[name]
        category = status.get("statusCategory") or {}
        if isinstance(category, dict):
            key = (category.get("key") or "").strip().lower()
            if key in STATUS_CATEGORY_KEY_TO_EN:
                return STATUS_CATEGORY_KEY_TO_EN[key]
        if name and name.isascii():
            return name
        return STATUS_ZH_TO_EN.get(name, name)

    name = str(getattr(status, "name", "") or "").strip()
    if name in STATUS_ZH_TO_EN:
        return STATUS_ZH_TO_EN[name]
    category = getattr(status, "statusCategory", None)
    if category is not None:
        key = (getattr(category, "key", None) or "").strip().lower()
        if key in STATUS_CATEGORY_KEY_TO_EN:
            return STATUS_CATEGORY_KEY_TO_EN[key]
    return name


def collect_log_paths_from_urls_by_type(urls_by_type: Any) -> List[str]:
    """从 manifest.jira.urls_by_type 收集工单上的日志路径/链接（保持优先级顺序、去重）。"""
    if not isinstance(urls_by_type, dict):
        return []
    order = ("network_share", "box", "http_direct", "feishu_file")
    seen = set()
    paths: List[str] = []
    for key in order:
        for item in urls_by_type.get(key) or []:
            text = (item or "").strip()
            if text and text not in seen:
                seen.add(text)
                paths.append(text)
    return paths


def primary_log_path_from_urls_by_type(urls_by_type: Any) -> str:
    """看板「日志路径」：优先 network_share，否则取第一条可用路径。"""
    paths = collect_log_paths_from_urls_by_type(urls_by_type)
    if not paths:
        return ""
    for p in paths:
        if p.startswith("\\\\"):
            return p
    return paths[0]


def format_log_paths_for_dashboard(paths: List[str]) -> str:
    """多条路径时用换行拼接（飞书文本单元格）。"""
    return "\n".join(p for p in paths if p)
