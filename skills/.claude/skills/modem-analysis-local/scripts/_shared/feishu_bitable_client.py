"""飞书多维表格 API 封装模块

用于 ModemEE 记录的查询和写入。

飞书多维表格链接: https://transsioner.feishu.cn/base/JzmgbczwraPHQ1s2Fz9cmHh7nov?table=tblANV8zkvN8llAf&view=vewLvx6K3h

API 文档: https://open.feishu.cn/document/server-docs/docs/bitable-v1/bitable-overview
"""

from __future__ import annotations

import hashlib
import os
import sys
from typing import Any, Dict, List, Optional

import requests


FEISHU_API_BASE = "https://open.feishu.cn/open-apis"

MODEMEE_BITABLE_APP_TOKEN = "JzmgbczwraPHQ1s2Fz9cmHh7nov"
MODEMEE_TABLE_ID = "tblANV8zkvN8llAf"

def default_feishu_app_id() -> str:
    """读取 FEISHU_APP_ID（须在 load_skill_env() 之后调用）。"""
    return (os.getenv("FEISHU_APP_ID") or "").strip()


def default_feishu_app_secret() -> str:
    """读取 FEISHU_APP_SECRET（须在 load_skill_env() 之后调用）。"""
    return (os.getenv("FEISHU_APP_SECRET") or "").strip()


# 兼容旧 import；勿在模块 import 时缓存，否则 load_skill_env 之前为空
DEFAULT_FEISHU_APP_ID = ""
DEFAULT_FEISHU_APP_SECRET = ""

REQUEST_TIMEOUT_SECONDS = 30


def _feishu_debug_enabled() -> bool:
    v = (os.getenv("FEISHU_DEBUG") or "").strip().lower()
    return v in ("1", "true", "yes", "y", "on")


def _mask_credential(label: str, value: str) -> str:
    """脱敏：仅长度 + 首尾少量字符，便于排查空格/截断，不打印完整 secret。"""
    if not value:
        return f"{label}=(empty,len=0)"
    raw_len = len(value)
    stripped = value.strip()
    extra_ws = raw_len - len(stripped)
    head, tail = 4, 4
    if len(stripped) <= head + tail:
        mid = "*" * min(len(stripped), 12)
    else:
        mid = f"{stripped[:head]}...{stripped[-tail:]}"
    ws_hint = f", leading/trailing_ws={extra_ws}" if extra_ws else ""
    return f"{label}: len={raw_len}{ws_hint}, preview={mid!r}"


class FeishuBitableClient:
    """飞书多维表格客户端"""

    def __init__(self, app_id: str = "", app_secret: str = "", app_token: str = "", table_id: str = ""):
        # strip：避免 .env 行尾空格/换行导致飞书 10003 invalid param
        self.app_id = (app_id or default_feishu_app_id()).strip()
        self.app_secret = (app_secret or default_feishu_app_secret()).strip()
        if not self.app_id or not self.app_secret:
            raise ValueError(
                "FEISHU_APP_ID / FEISHU_APP_SECRET 未配置或为空；"
                "请检查 skill 根目录 .env，并确保在 import 飞书客户端前已 load_skill_env()"
            )
        self.app_token = app_token or MODEMEE_BITABLE_APP_TOKEN
        self.table_id = table_id or MODEMEE_TABLE_ID
        self._tenant_access_token: Optional[str] = None

    def _get_tenant_access_token(self) -> str:
        """获取 tenant_access_token"""
        if self._tenant_access_token:
            return self._tenant_access_token

        url = f"{FEISHU_API_BASE}/auth/v3/tenant_access_token/internal"
        payload = {
            "app_id": self.app_id,
            "app_secret": self.app_secret,
        }
        headers = {"Content-Type": "application/json; charset=utf-8"}

        if _feishu_debug_enabled():
            print(
                "[feishu] POST tenant_access_token/internal "
                + _mask_credential("app_id", self.app_id)
                + " | "
                + _mask_credential("app_secret", self.app_secret),
                file=sys.stderr,
            )

        response = requests.post(url, json=payload, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        data = response.json()

        if data.get("code") != 0:
            print(
                f"[feishu] tenant_access_token failed code={data.get('code')} msg={data.get('msg')!r}",
                file=sys.stderr,
            )
            if _feishu_debug_enabled():
                print(f"[feishu] token response body={data!r}", file=sys.stderr)
            raise RuntimeError(f"获取 tenant_access_token 失败: {data}")

        self._tenant_access_token = data.get("tenant_access_token")
        if _feishu_debug_enabled():
            print(
                f"[feishu] tenant_access_token OK, expire_sec={data.get('expire')!r}",
                file=sys.stderr,
            )
        return self._tenant_access_token

    def _get_headers(self) -> Dict[str, str]:
        """获取请求头"""
        token = self._get_tenant_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def list_records(
        self,
        view_id: str = "",
        field_names: Optional[List[str]] = None,
        filter_condition: Optional[str] = None,
        sort_condition: Optional[List[Dict[str, Any]]] = None,
        page_size: int = 100,
        page_token: str = "",
    ) -> Dict[str, Any]:
        """查询记录

        Args:
            view_id: 视图 ID
            field_names: 返回字段列表
            filter_condition: 过滤条件
            sort_condition: 排序条件
            page_size: 每页记录数
            page_token: 分页 token

        Returns:
            查询结果
        """
        url = f"{FEISHU_API_BASE}/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records"
        params = {"page_size": page_size}
        if view_id:
            params["view_id"] = view_id
        if field_names:
            params["field_names"] = ",".join(field_names)
        if filter_condition:
            params["filter"] = filter_condition
        if sort_condition:
            params["sort"] = sort_condition
        if page_token:
            params["page_token"] = page_token

        response = requests.get(url, headers=self._get_headers(), params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json()

    def create_record(self, fields: Dict[str, Any], position: str = "first") -> Dict[str, Any]:
        """创建记录

        Args:
            fields: 字段值字典
            position: 插入位置，"first" 表示开头，"last" 表示末尾

        Returns:
            创建结果
        """
        url = f"{FEISHU_API_BASE}/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records"
        payload = {"fields": fields, "position": position}

        response = requests.post(url, headers=self._get_headers(), json=payload, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json()

    def update_record(self, record_id: str, fields: Dict[str, Any]) -> Dict[str, Any]:
        """更新记录

        Args:
            record_id: 记录 ID
            fields: 字段值字典

        Returns:
            更新结果
        """
        url = f"{FEISHU_API_BASE}/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records/{record_id}"
        payload = {"fields": fields}

        response = requests.put(url, headers=self._get_headers(), json=payload, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json()

    def search_records(self, filter_condition: str, page_size: int = 100) -> Dict[str, Any]:
        """搜索记录（公式 filter，GET list records）

        Args:
            filter_condition: 过滤条件，如 'CurrentValue.[ee_hash] = "abc123"'
            page_size: 每页记录数

        Returns:
            搜索结果
        """
        return self.list_records(filter_condition=filter_condition, page_size=page_size)

    def search_records_by_field(
        self,
        field_name: str,
        value: str,
        operator: str = "is",
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """按字段精确搜索记录（POST records/search）

        Args:
            field_name: 字段名（与多维表格列名一致）
            value: 匹配值
            operator: 比较符，文本主键常用 ``is``
            page_size: 返回条数上限

        Returns:
            飞书 API 原始响应 JSON
        """
        url = (
            f"{FEISHU_API_BASE}/bitable/v1/apps/{self.app_token}"
            f"/tables/{self.table_id}/records/search"
        )
        payload = {
            "filter": {
                "conjunction": "and",
                "conditions": [
                    {
                        "field_name": field_name,
                        "operator": operator,
                        "value": [value],
                    }
                ],
            },
            "page_size": page_size,
        }
        response = requests.post(
            url, headers=self._get_headers(), json=payload, timeout=REQUEST_TIMEOUT_SECONDS
        )
        response.raise_for_status()
        return response.json()


def generate_ee_hash(ee_type: str, err_code: str, exception_source: str) -> str:
    """生成 EE 唯一标识 Hash

    Args:
        ee_type: 异常类型
        err_code: 异常代码
        exception_source: 异常源

    Returns:
        32位 MD5 Hash 字符串
    """
    content = f"{ee_type}|{err_code}|{exception_source}"
    return hashlib.md5(content.encode()).hexdigest()


def query_modemee_from_feishu(
    ee_hash: str,
    client: Optional[FeishuBitableClient] = None,
) -> Dict[str, Any]:
    """从飞书表格查询 ModemEE 记录

    Args:
        ee_hash: EE 唯一标识 Hash
        client: 飞书客户端

    Returns:
        查询结果，包含 root_cause 和 solution（如果存在）
    """
    if client is None:
        client = FeishuBitableClient()

    filter_condition = f'CurrentValue.[HASH值] = "{ee_hash}"'

    try:
        result = client.search_records(filter_condition=filter_condition)
        if result.get("code") != 0:
            return {
                "success": False,
                "error": result.get("msg", "查询失败"),
                "response": result,
            }

        items = result.get("data", {}).get("items", [])
        if not items:
            return {
                "success": True,
                "exists": False,
                "record": None,
            }

        record = items[0]
        fields = record.get("fields", {})
        
        return {
            "success": True,
            "exists": True,
            "record_id": record.get("record_id"),
            "record": fields,
            "root_cause": fields.get("结论信息", ""),
            "solution": fields.get("结论信息", ""),
            "status": fields.get("解决状态", ""),
            "bug单": fields.get("bug单", ""),
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


def write_modemee_to_feishu(
    ee_data: Dict[str, Any],
    client: Optional[FeishuBitableClient] = None,
) -> Dict[str, Any]:
    """写入 ModemEE 记录到飞书表格

    Args:
        ee_data: EE 数据字典（飞书表格字段格式）
        client: 飞书客户端

    Returns:
        写入结果
    """
    if client is None:
        client = FeishuBitableClient()

    ee_hash = ee_data.get("HASH值", "")
    if not ee_hash:
        return {
            "success": False,
            "error": "缺少 HASH值 字段",
        }

    query_result = query_modemee_from_feishu(ee_hash, client)
    if query_result.get("success") and query_result.get("exists"):
        return {
            "success": True,
            "action": "skipped_already_exists",
            "record_id": query_result.get("record_id"),
            "record": query_result.get("record"),
            "root_cause": query_result.get("root_cause"),
            "solution": query_result.get("solution"),
        }

    try:
        result = client.create_record(ee_data)
        if result.get("code") != 0:
            return {
                "success": False,
                "error": result.get("msg", "写入失败"),
                "response": result,
            }

        return {
            "success": True,
            "action": "created",
            "record_id": result.get("data", {}).get("record", {}).get("record_id"),
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


def build_modemee_record(
    jira_key: str,
    ee_type: str,
    err_code: str,
    exception_source: str,
    platform: str = "",
    chip_vendor: str = "",
    chip_model: str = "",
    sw_version: str = "",
    title: str = "",
    description: str = "",
    call_stack: str = "",
    root_cause: str = "",
    solution: str = "",
    status: str = "待分析",
    first_occurrence: str = "",
    occurrence_count: int = 1,
) -> Dict[str, Any]:
    """构建 ModemEE 记录（飞书表格字段格式）

    Args:
        jira_key: Jira 单号
        ee_type: 异常类型
        err_code: 异常代码
        exception_source: 异常源
        platform: 平台代号
        chip_vendor: 芯片厂商
        chip_model: 芯片型号
        sw_version: 软件版本
        title: 标题
        description: 描述
        call_stack: 调用栈
        root_cause: 根因
        solution: 解决方案
        status: 状态
        first_occurrence: 首次发生时间
        occurrence_count: 发生次数

    Returns:
        记录字典（飞书表格字段格式）
    """
    ee_hash = generate_ee_hash(ee_type, err_code, exception_source)
    
    ee_detail = f"""EE Type: {ee_type}
Error Code: {err_code}
Exception Source: {exception_source}
Jira Key: {jira_key}
Title: {title}
Occurrence Count: {occurrence_count}
First Occurrence: {first_occurrence}"""
    
    platform_info = f"Chip Model: {chip_model}"
    
    conclusion_info = f"""Root Cause: {root_cause if root_cause else 'Pending analysis'}
Solution: {solution if solution else 'Pending'}"""

    return {
        "EE详细信息": ee_detail,
        "平台信息": platform_info,
        "结论信息": conclusion_info,
        "解决状态": status,
        "HASH值": ee_hash,
        "bug单": jira_key,
    }
