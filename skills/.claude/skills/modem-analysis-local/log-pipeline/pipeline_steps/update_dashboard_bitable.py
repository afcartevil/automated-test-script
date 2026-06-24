#!/usr/bin/env python3
"""
Step 10: 将 Phase1 结果 upsert 到飞书分析看板多维表格（一 Jira 一行）。

依赖 _shared/feishu_dashboard_client.py；凭据与表 ID 见 .env。
默认软失败（FEISHU_DASHBOARD_REQUIRED=0），不阻塞 pipeline 主流程。
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

try:
    from dotenv import load_dotenv

    _ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
    if _ENV_PATH.exists():
        load_dotenv(_ENV_PATH)
except ImportError:
    pass

_SHARED_DIR = Path(__file__).resolve().parent.parent / "_shared"
if str(_SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(_SHARED_DIR))

from feishu_dashboard_client import (  # noqa: E402
    AI_STATUS_NOT_STARTED,
    DashboardField,
    upsert_dashboard_record,
)
from pipeline_run_summary import (  # noqa: E402
    EXPORT_STATUS_FAILED,
    EXPORT_STATUS_NOT_STARTED,
    summarize_phase1_steps,
)
from jira_dashboard_helpers import (  # noqa: E402
    collect_log_paths_from_urls_by_type,
    format_log_paths_for_dashboard,
    normalize_jira_status_en,
    primary_log_path_from_urls_by_type,
)
from modem_analysis_runtime import load_manifest, save_manifest  # noqa: E402


def _envbool(name: str, default: bool = False) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    if not v:
        return default
    return v in ("1", "true", "yes", "y", "on")


def _jira_browse_url(issue_key: str) -> str:
    """飞书「JIRA 链接」展示用；与 JIRA_SERVER（API）分离，默认正式站。"""
    base = (os.getenv("JIRA_BROWSE_URL_BASE") or "http://jira.transsion.com").strip().rstrip("/")
    if not base:
        return ""
    return f"{base}/browse/{issue_key}"


def _fetch_jira_status_en(issue_key: str) -> str:
    """manifest 无 issue_status_en 时，从 Jira API 补英文状态。"""
    server = (os.getenv("JIRA_SERVER") or "").strip()
    username = (os.getenv("JIRA_USERNAME") or "").strip()
    password = os.getenv("JIRA_PASSWORD") or ""
    if not (server and issue_key):
        return ""
    try:
        from jira import JIRA

        if username and password:
            client = JIRA(server=server, basic_auth=(username, password))
        else:
            client = JIRA(server=server)
        issue = client.issue(issue_key)
        raw_fields = getattr(issue, "raw", {}).get("fields", {})
        return normalize_jira_status_en(raw_fields.get("status"))
    except Exception as exc:
        print(f"[dashboard] Jira 状态补全跳过: {exc}", file=sys.stderr)
        return ""


def build_dashboard_fields_from_manifest(manifest_path: str) -> Dict[str, Any]:
    """根据 manifest 构造看板 upsert 字段（飞书列名 → 值）。"""
    manifest = load_manifest(manifest_path)
    issue_key = (manifest.get("issue_key") or "").strip()
    if not issue_key:
        raise ValueError("manifest 缺少 issue_key")

    jira = manifest.get("jira") or {}
    meta = manifest.get("_meta") or {}
    smb = meta.get("phase1_smb_publish") or {}

    unc_base = (smb.get("smb_zip_rel") or smb.get("unc_base") or "").strip()
    export_time = (
        meta.get("phase1_completed_at")
        or smb.get("published_at")
        or meta.get("phase1_finished_at")
        or meta.get("updated_at")
        or datetime.now().isoformat(timespec="seconds")
    )

    export_status, failed_steps, error_summary = summarize_phase1_steps(manifest)

    log_path = (jira.get("log_path") or "").strip()
    if not log_path:
        paths = collect_log_paths_from_urls_by_type(jira.get("urls_by_type"))
        log_path = format_log_paths_for_dashboard(paths) or primary_log_path_from_urls_by_type(
            jira.get("urls_by_type")
        )

    fields: Dict[str, Any] = {
        DashboardField.JIRA_KEY: issue_key,
        DashboardField.LOG_PATH: log_path,
        DashboardField.LOG_EXPORT_PATH: unc_base or "",
        DashboardField.LOG_EXPORT_TIME: export_time,
        DashboardField.AI_STATUS: AI_STATUS_NOT_STARTED,
        DashboardField.LOG_EXPORT_STATUS: export_status or EXPORT_STATUS_NOT_STARTED,
        DashboardField.LOG_EXPORT_FAILED_STEPS: failed_steps or "",
        DashboardField.LOG_EXPORT_ERROR: error_summary or "",
    }

    jira_url = _jira_browse_url(issue_key)
    if jira_url:
        fields[DashboardField.JIRA_URL] = {"link": jira_url, "text": issue_key}

    status_en = (jira.get("issue_status_en") or "").strip()
    if not status_en:
        status_en = _fetch_jira_status_en(issue_key)
    if status_en:
        fields[DashboardField.JIRA_STATUS] = status_en

    return fields


def update_dashboard_from_manifest(manifest_path: str) -> Dict[str, Any]:
    """Upsert 看板行。"""
    enabled = _envbool("FEISHU_DASHBOARD_ENABLED", True)
    required = _envbool("FEISHU_DASHBOARD_REQUIRED", False)

    result: Dict[str, Any] = {
        "enabled": enabled,
        "skipped": False,
        "ok": False,
        "required": required,
        "action": "",
        "record_id": "",
        "message": "",
    }

    if not enabled:
        result["skipped"] = True
        result["ok"] = True
        result["message"] = "FEISHU_DASHBOARD_ENABLED=0，已跳过"
        _write_back(manifest_path, result)
        return result

    app_id = (os.getenv("FEISHU_APP_ID") or "").strip()
    app_secret = (os.getenv("FEISHU_APP_SECRET") or "").strip()
    if not app_id or not app_secret:
        result["message"] = "缺少 FEISHU_APP_ID / FEISHU_APP_SECRET"
        result["ok"] = not required
        _write_back(manifest_path, result)
        return result

    try:
        fields = build_dashboard_fields_from_manifest(manifest_path)
        upsert = upsert_dashboard_record(fields)
        result["ok"] = bool(upsert.get("success"))
        result["action"] = upsert.get("action", "")
        result["record_id"] = upsert.get("record_id", "")
        result["jira_key"] = upsert.get("jira_key", fields.get(DashboardField.JIRA_KEY))
        if not result["ok"]:
            result["message"] = upsert.get("error", "upsert 失败")
        else:
            result["message"] = f"看板 {result['action']}: {result['jira_key']}"
        print(f"[dashboard] {result['message']} record_id={result['record_id']}")
    except Exception as exc:
        result["message"] = str(exc)
        result["ok"] = False
        print(f"[dashboard] 失败: {exc}", file=sys.stderr)

    _write_back(manifest_path, result)
    return result


def _write_back(manifest_path: str, result: Dict[str, Any]) -> None:
    try:
        manifest = load_manifest(manifest_path)
        meta = manifest.setdefault("_meta", {})
        meta["phase1_dashboard_bitable"] = {
            "ok": bool(result.get("ok")),
            "skipped": bool(result.get("skipped")),
            "action": result.get("action", ""),
            "record_id": result.get("record_id", ""),
            "message": (result.get("message") or "")[:2000],
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
        save_manifest(manifest_path, manifest)
    except Exception as exc:
        print(f"[dashboard] 写回 manifest 失败: {exc}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="Step 10: upsert 飞书分析看板")
    parser.add_argument("--manifest", required=True, help="job_manifest.json 绝对路径")
    args = parser.parse_args()

    result = update_dashboard_from_manifest(args.manifest)
    if result.get("skipped") or result.get("ok"):
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
