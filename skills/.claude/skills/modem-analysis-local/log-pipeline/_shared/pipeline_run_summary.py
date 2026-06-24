"""Phase 1 pipeline 运行摘要 — 供飞书看板与 manifest._meta 使用。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Tuple

# 与飞书「日志导出状态」单选选项一致
EXPORT_STATUS_NOT_STARTED = "未开始"
EXPORT_STATUS_SUCCESS = "成功"
EXPORT_STATUS_FAILED = "失败"


def append_phase1_step(
    manifest: Dict[str, Any],
    name: str,
    ok: bool,
    error: str = "",
) -> None:
    meta = manifest.setdefault("_meta", {})
    steps: List[Dict[str, Any]] = meta.setdefault("phase1_steps", [])
    steps.append(
        {
            "name": name,
            "ok": bool(ok),
            "error": (error or "").strip()[:2000],
            "at": datetime.now().isoformat(timespec="seconds"),
        }
    )


def finalize_phase1_run_meta(
    manifest: Dict[str, Any],
    *,
    overall_ok: bool,
    pipeline_log_file: str = "",
) -> None:
    meta = manifest.setdefault("_meta", {})
    meta["phase1_overall_ok"] = bool(overall_ok)
    meta["phase1_finished_at"] = datetime.now().isoformat(timespec="seconds")
    if pipeline_log_file:
        meta["pipeline_log_file"] = pipeline_log_file


def summarize_phase1_steps(manifest: Dict[str, Any]) -> Tuple[str, str, str]:
    """
    根据 manifest._meta 计算看板字段值。

    Returns:
        (export_status, failed_steps_csv, error_summary)
    """
    meta = manifest.get("_meta") or {}
    steps: List[Dict[str, Any]] = meta.get("phase1_steps") or []
    finished_at = meta.get("phase1_finished_at")

    if not steps and not finished_at:
        return EXPORT_STATUS_NOT_STARTED, "", ""

    failed = [s for s in steps if not s.get("ok")]
    failed_names = [str(s.get("name") or "?") for s in failed]
    errors = [str(s.get("error") or "").strip() for s in failed if s.get("error")]

    overall_ok = meta.get("phase1_overall_ok")
    packaged = bool(meta.get("phase1_completed_at"))

    if overall_ok is True and packaged:
        status = EXPORT_STATUS_SUCCESS
    elif overall_ok is True and not packaged:
        status = EXPORT_STATUS_FAILED
    else:
        status = EXPORT_STATUS_FAILED

    failed_csv = "; ".join(failed_names)
    error_parts: List[str] = []
    for name, err in zip(failed_names, errors):
        if err:
            error_parts.append(f"{name}: {err}")
        elif name:
            error_parts.append(name)
    error_summary = "\n".join(error_parts)[:4000]

    smb = meta.get("phase1_smb_publish") or {}
    if smb and not smb.get("ok") and packaged:
        smb_msg = (smb.get("message") or "Samba 发布失败")[:500]
        if smb_msg:
            error_summary = (error_summary + "\n" if error_summary else "") + f"samba-publish: {smb_msg}"
        if overall_ok is True:
            status = EXPORT_STATUS_SUCCESS

    return status, failed_csv, error_summary
