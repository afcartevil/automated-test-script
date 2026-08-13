"""通信 AI 故障分析看板 — 飞书多维表格 upsert

以「JIRA 单号」为唯一键：已存在则更新，否则新建。

表格：https://transsioner.feishu.cn/wiki/YaTFwxUIHiNdXFkget8cXiKTnXg?table=tblODuaS0CR9pzCW
"""

from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from feishu_bitable_client import (
    FeishuBitableClient,
    default_feishu_app_id,
    default_feishu_app_secret,
)

# ----- Base / Table（可用环境变量覆盖） -----
DASHBOARD_BITABLE_APP_TOKEN = (
    os.getenv("FEISHU_DASHBOARD_APP_TOKEN") or "YaTFwxUIHiNdXFkget8cXiKTnXg"
).strip()
DASHBOARD_TABLE_ID = (os.getenv("FEISHU_DASHBOARD_TABLE_ID") or "tblODuaS0CR9pzCW").strip()

# ----- 列名（与飞书多维表格一致，2026-05 快照） -----
class DashboardField:
    JIRA_KEY = "JIRA 单号"
    JIRA_URL = "JIRA 链接"
    JIRA_STATUS = "JIRA 状态"
    JIRA_OWNER = "JIRA Owner"  # 不自动写入；仅人工维护
    LOG_PATH = "日志路径"
    LOG_EXPORT_PATH = "日志导出路径"
    LOG_EXPORT_TIME = "日志导出时间"
    LOG_EXPORT_SCORE = "日志导出评分"
    AI_STATUS = "AI 分析状态"
    AI_FAULT_TYPE = "AI 判定故障类型"
    ACTUAL_FAULT_TYPE = "实际故障类型"
    AI_ANALYSIS_TIME = "AI 分析时间"
    AI_ANALYSIS_SCORE = "AI 分析评分"
    AI_ANALYSIS_SCORE_NOTE = "AI 分析评分说明"
    AI_ANALYSIS_SCORER = "AI 分析评分人"
    CASE_VALIDITY = "问题有效性"
    VALIDITY_NOTE = "有效性说明"
    LAST_UPDATED_AT = "最后更新时间"


AI_STATUS_NOT_STARTED = "未进行"
AI_STATUS_DONE = "已分析"

# L1 primary_domain → 看板「AI 判定故障类型」单选
L1_DOMAIN_TO_AI_FAULT_TYPE = {
    "data": "DATA",
    "call": "CALL",
    "sim": "SIM",
    "ee": "EE",
    "other": "OTHER",
}


DateTimeInput = Union[int, float, datetime, str, None]


class DashboardBitableClient(FeishuBitableClient):
    """看板表专用客户端（与 ModemEE 历史表分离）。"""

    def __init__(
        self,
        app_id: str = "",
        app_secret: str = "",
        app_token: str = "",
        table_id: str = "",
    ):
        super().__init__(
            app_id=app_id,
            app_secret=app_secret,
            app_token=app_token or DASHBOARD_BITABLE_APP_TOKEN,
            table_id=table_id or DASHBOARD_TABLE_ID,
        )


def _strip_none(fields: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in fields.items() if v is not None}


def format_datetime(value: DateTimeInput) -> Optional[int]:
    """转为飞书 DateTime 字段所需的毫秒时间戳。

    支持：毫秒/秒时间戳、datetime、``YYYY-MM-DD`` / ``YYYY-MM-DD HH:MM:SS`` 字符串。
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        ts = int(value)
        if ts < 10_000_000_000:
            ts *= 1000
        return ts
    if isinstance(value, datetime):
        return int(value.timestamp() * 1000)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if "T" in text:
            try:
                iso = text.replace("Z", "+00:00")
                dt = datetime.fromisoformat(iso)
                return int(dt.timestamp() * 1000)
            except ValueError:
                pass
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d"):
            try:
                dt = datetime.strptime(text, fmt)
                return int(dt.timestamp() * 1000)
            except ValueError:
                continue
        raise ValueError(f"无法解析日期时间: {value!r}")
    raise TypeError(f"不支持的日期类型: {type(value)!r}")


def format_url(link: str, text: str = "") -> Dict[str, str]:
    """飞书 Url 字段。"""
    return {"link": link, "text": text or link}


def format_user(user_id: str) -> List[Dict[str, str]]:
    """飞书 User 字段（单人）。``user_id`` 为 open_id 或 user_id。"""
    return [{"id": user_id}]


def map_l1_domain_to_ai_fault_type(primary_domain: str) -> Optional[str]:
    """``analysis.l1_business.primary_domain`` → 看板单选值。"""
    if not primary_domain:
        return None
    return L1_DOMAIN_TO_AI_FAULT_TYPE.get(primary_domain.strip().lower())


def find_dashboard_record_by_jira_key(
    jira_key: str,
    client: Optional[DashboardBitableClient] = None,
) -> Dict[str, Any]:
    """按 JIRA 单号查询是否已有行。

    Returns:
        ``{success, exists, record_id, fields, error?, response?}``
    """
    key = (jira_key or "").strip()
    if not key:
        return {"success": False, "error": "jira_key 为空"}

    if client is None:
        client = DashboardBitableClient()

    try:
        result = client.search_records_by_field(DashboardField.JIRA_KEY, key, operator="is", page_size=5)
        if result.get("code") != 0:
            return {
                "success": False,
                "error": result.get("msg", "查询失败"),
                "response": result,
            }

        items = result.get("data", {}).get("items") or []
        if not items:
            return {"success": True, "exists": False, "record_id": None, "fields": None}

        record = items[0]
        if len(items) > 1:
            return {
                "success": False,
                "error": f"JIRA 单号 {key!r} 匹配到多条记录（{len(items)}），请先在表中去重",
                "response": result,
            }

        return {
            "success": True,
            "exists": True,
            "record_id": record.get("record_id"),
            "fields": record.get("fields") or {},
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def upsert_dashboard_record(
    fields: Dict[str, Any],
    *,
    jira_key: Optional[str] = None,
    client: Optional[DashboardBitableClient] = None,
    touch_updated_at: bool = True,
) -> Dict[str, Any]:
    """插入或更新看板行（以 JIRA 单号为唯一键）。

    Args:
        fields: 要写入的列，键为**飞书列名**（见 ``DashboardField``）。
            未传入的列在更新时**不会**被清空。
        jira_key: 可单独指定主键；默认取 ``fields[DashboardField.JIRA_KEY]``。
        client: 可复用的客户端实例。
        touch_updated_at: 为 True 时自动写入「最后更新时间」为当前时刻。

    Returns:
        ``{success, action: "created"|"updated", record_id, jira_key, error?, response?}``

    Example::

        upsert_dashboard_record({
            DashboardField.JIRA_KEY: "OS162-37733",
            DashboardField.LOG_EXPORT_PATH: r"\\\\10.205.4.20\\sw_temp\\...",
            DashboardField.LOG_EXPORT_TIME: "2026-05-19 14:30:00",
        })
    """
    payload = dict(fields or {})
    key = (jira_key or payload.get(DashboardField.JIRA_KEY) or "").strip()
    if not key:
        return {"success": False, "error": "缺少 JIRA 单号（jira_key 或 fields 中的 JIRA 单号）"}

    payload[DashboardField.JIRA_KEY] = key
    payload = _normalize_dashboard_fields(payload)

    if touch_updated_at and DashboardField.LAST_UPDATED_AT not in payload:
        payload[DashboardField.LAST_UPDATED_AT] = int(time.time() * 1000)

    payload = _strip_none(payload)

    if client is None:
        client = DashboardBitableClient()

    lookup = find_dashboard_record_by_jira_key(key, client=client)
    if not lookup.get("success"):
        return {
            "success": False,
            "action": "failed",
            "jira_key": key,
            "error": lookup.get("error"),
            "response": lookup.get("response"),
        }

    try:
        if lookup.get("exists"):
            record_id = lookup["record_id"]
            result = client.update_record(record_id, payload)
            if result.get("code") != 0:
                return {
                    "success": False,
                    "action": "failed",
                    "jira_key": key,
                    "record_id": record_id,
                    "error": result.get("msg", "更新失败"),
                    "response": result,
                }
            return {
                "success": True,
                "action": "updated",
                "jira_key": key,
                "record_id": record_id,
            }

        result = client.create_record(payload)
        if result.get("code") != 0:
            return {
                "success": False,
                "action": "failed",
                "jira_key": key,
                "error": result.get("msg", "创建失败"),
                "response": result,
            }
        record_id = result.get("data", {}).get("record", {}).get("record_id")
        return {
            "success": True,
            "action": "created",
            "jira_key": key,
            "record_id": record_id,
        }
    except Exception as exc:
        return {
            "success": False,
            "action": "failed",
            "jira_key": key,
            "error": str(exc),
        }


def _normalize_dashboard_fields(fields: Dict[str, Any]) -> Dict[str, Any]:
    """将常见 Python 类型转为飞书单元格格式。"""
    datetime_columns = {
        DashboardField.LOG_EXPORT_TIME,
        DashboardField.AI_ANALYSIS_TIME,
        DashboardField.LAST_UPDATED_AT,
    }
    out: Dict[str, Any] = {}
    for name, value in fields.items():
        if value is None:
            out[name] = None
            continue
        if name in datetime_columns:
            out[name] = format_datetime(value)
            continue
        if name == DashboardField.JIRA_URL and isinstance(value, str):
            out[name] = format_url(value)
            continue
        if name == DashboardField.AI_ANALYSIS_SCORER and isinstance(value, str):
            out[name] = format_user(value)
            continue
        if name == DashboardField.AI_ANALYSIS_SCORER and isinstance(value, list):
            out[name] = value
            continue
        out[name] = value
    return out


def get_dashboard_client(
    app_id: str = "",
    app_secret: str = "",
) -> DashboardBitableClient:
    """使用环境变量 ``FEISHU_APP_ID`` / ``FEISHU_APP_SECRET`` 创建看板客户端。"""
    return DashboardBitableClient(
        app_id=app_id or default_feishu_app_id(),
        app_secret=app_secret or default_feishu_app_secret(),
    )
