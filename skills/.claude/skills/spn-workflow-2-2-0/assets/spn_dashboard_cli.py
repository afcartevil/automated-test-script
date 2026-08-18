#!/usr/bin/env python3
"""SPN dashboard record/upload for connectivity/sub/spn workflow.

Uploads team-wide telemetry events with:
  command_path = spn/dashboard/record
  record_type  = spn_dashboard_stat

Agents MUST call `record` when reaching ANALYZED (analysis done) and again
when reaching SUBMITTED (after Gerrit), so the CarrierConfig remote dashboard
SPN tab can aggregate team results.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
import uuid
import webbrowser
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

DEFAULT_BACKEND_BASE_URL = "https://test-os-ai-statis-service-backend.transsion-os.com"
BACKEND_PATH_PREFIX = "/api/v1/harness"
SPN_DASHBOARD_COMMAND_PATH = "spn/dashboard/record"
SPN_DASHBOARD_RECORD_TYPE = "spn_dashboard_stat"
CC_DASHBOARD_COMMAND_PATH = "carrierconfig/dashboard/record"
CC_DASHBOARD_RECORD_TYPE = "carrierconfig_dashboard_stat"
DEFAULT_FETCH_DAYS = 365
DEFAULT_BATCH_SIZE = 100
MAX_BACKEND_BATCH_SIZE = 500
DEFAULT_MILESTONE_MIN_TOTAL = 30
DEFAULT_MILESTONE_MIN_SUCCESS_RATE = 0.0  # 0 = 不检查成功率，仅看单数
DAILY_TASK_NAME = "Harness-SPN-Dashboard-Daily-Check"
DAILY_TASK_TIME = "09:00"

FAULT_LINKS = (
    "状态栏/锁屏",
    "手动搜网",
    "displayName",
    "MVNO",
    "云网SPN",
    "注入/编译",
    "其他",
)
WORKFLOW_STATES = (
    "INTAKE",
    "ANALYZED",
    "PATCHED",
    "DIFF_APPROVED",
    "BRANCH_RESOLVED",
    "VERIFIED",
    "SUBMITTED",
)
PASS_FAIL = ("PASS", "FAIL", "CONDITIONAL")


def user_spn_dir() -> Path:
    path = Path.home() / ".tran_harness" / "spn"
    path.mkdir(parents=True, exist_ok=True)
    return path


def pending_path() -> Path:
    return user_spn_dir() / "dashboard_pending.jsonl"


def sent_dir() -> Path:
    return user_spn_dir() / "dashboard_sent"


def local_stats_path() -> Path:
    return user_spn_dir() / "dashboard_stats.jsonl"


def milestone_state_path() -> Path:
    return user_spn_dir() / "dashboard_milestone_state.json"


def daily_runner_path() -> Path:
    return user_spn_dir() / "run_daily_check.cmd"


def daily_log_path() -> Path:
    return user_spn_dir() / "daily_check.log"


def default_combined_dashboard_html() -> Path:
    path = user_spn_dir() / "dashboard" / "remote_dashboard.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _backend_config() -> tuple[str, int]:
    base_url = DEFAULT_BACKEND_BASE_URL
    timeout = 30
    try:
        from cli.config import get_config_value

        base_url = (
            get_config_value("telemetry.backend_base_url", "")
            or os.environ.get("HARNESS_TELEMETRY_BACKEND_BASE_URL", "")
            or DEFAULT_BACKEND_BASE_URL
        )
        timeout = int(
            get_config_value("telemetry.backend_timeout_seconds", "")
            or os.environ.get("HARNESS_TELEMETRY_BACKEND_TIMEOUT_SECONDS", "")
            or 30
        )
    except ImportError:
        base_url = os.environ.get("HARNESS_TELEMETRY_BACKEND_BASE_URL", base_url)
        timeout = int(os.environ.get("HARNESS_TELEMETRY_BACKEND_TIMEOUT_SECONDS", "30") or 30)
    return base_url, max(1, timeout)


def _backend_url(base_url: str, path: str) -> str:
    root = (base_url or DEFAULT_BACKEND_BASE_URL).rstrip("/")
    if not root.endswith(BACKEND_PATH_PREFIX):
        root = f"{root}{BACKEND_PATH_PREFIX}"
    return f"{root}{path}"


def _username() -> str:
    try:
        from cli.telemetry import _username as telemetry_username

        return telemetry_username()
    except Exception:
        return (
            os.environ.get("USERNAME")
            or os.environ.get("USER")
            or os.environ.get("HARNESS_USERNAME", "")
            or ""
        )


def _to_iso8601(check_time: str) -> str:
    text = str(check_time or "").strip()
    if not text:
        return datetime.now(timezone.utc).isoformat()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(text, fmt)
            return dt.replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text).astimezone(timezone.utc).isoformat()
    except ValueError:
        return datetime.now(timezone.utc).isoformat()


def build_spn_event(record: dict, *, event_id: str | None = None) -> dict:
    check_time = str(record.get("check_time") or datetime.now().strftime("%Y-%m-%d %H:%M"))
    jira_id = str(record.get("jira_id") or "UNKNOWN")
    eid = event_id or (
        f"evt-spn-dash-{jira_id}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
    )
    pass_fail = str(record.get("pass_fail") or "").upper()
    status = "error" if pass_fail == "FAIL" else "ok"
    payload = {
        "record_type": SPN_DASHBOARD_RECORD_TYPE,
        "domain": "connectivity-spn-workflow",
        "jira_id": jira_id,
        "check_time": check_time,
        "accuracy_score": record.get("accuracy_score"),
        "pass_fail": pass_fail,
        "fail_dimensions": str(record.get("fail_dimensions") or ""),
        "platform": str(record.get("platform") or "").upper(),
        "fault_link": str(record.get("fault_link") or ""),
        "operator_mccmnc": str(record.get("operator_mccmnc") or ""),
        "workflow_state": str(record.get("workflow_state") or "").upper(),
    }
    for key in ("change_url", "branch", "submit_phase"):
        value = str(record.get(key) or "").strip()
        if value:
            payload[key] = value
    return {
        "event_id": eid,
        "event_time": _to_iso8601(check_time),
        "command_path": SPN_DASHBOARD_COMMAND_PATH,
        "command": "spn",
        "subcommand": "dashboard/record",
        "command_label": "SPN 分析/提交看板记录",
        "command_category": "SPN",
        "inferred_skill": "spn-workflow",
        "status": status,
        "exit_code": 0 if pass_fail != "FAIL" else 1,
        "username": _username(),
        "params": payload,
        **payload,
    }


def append_pending(event: dict) -> Path:
    path = pending_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
    return path


def append_local_stats(record: dict) -> Path:
    path = local_stats_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    return path


def read_pending() -> list[dict]:
    path = pending_path()
    if not path.is_file():
        return []
    events: list[dict] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                item = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                events.append(item)
    return events


def _archive_pending() -> None:
    source = pending_path()
    if not source.is_file():
        return
    target_dir = sent_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"dashboard-{int(time.time())}.jsonl"
    source.replace(target)


def _post_backend_batch(events: list[dict], *, base_url: str, timeout_seconds: int) -> tuple[int, str, dict | None]:
    if not events:
        return 0, "no events", {"ok": True, "accepted": 0, "duplicate": 0, "failed": 0, "results": []}
    try:
        from cli.telemetry import upload_events_to_backend

        code, text = upload_events_to_backend(
            events,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            dry_run=False,
        )
        try:
            parsed = json.loads(text) if text else {}
        except json.JSONDecodeError:
            return code, text, None
        return code, text, parsed if isinstance(parsed, dict) else None
    except ImportError:
        pass

    payload = {
        "schema_version": 1,
        "source": "harness-cli",
        "client_upload_time": datetime.now(timezone.utc).isoformat(),
        "records": events,
    }
    url = _backend_url(base_url, "/telemetry/events:batch")
    try:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        req = urllib_request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json; charset=utf-8")
        with urllib_request.urlopen(req, timeout=timeout_seconds) as response:
            text = response.read().decode("utf-8", errors="replace")
            parsed = json.loads(text) if text else {}
            code = 0 if isinstance(parsed, dict) and parsed.get("ok") is True and int(parsed.get("failed") or 0) == 0 else 1
            return code, text, parsed if isinstance(parsed, dict) else None
    except urllib_error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return int(exc.code), detail, None
    except Exception as exc:
        return 1, str(exc), None


def flush_pending(*, dry_run: bool = False) -> dict:
    events = read_pending()
    if not events:
        return {"status": "ok", "uploaded": 0, "pending": 0, "message": "no pending SPN dashboard events"}
    base_url, timeout = _backend_config()
    if dry_run:
        return {
            "status": "ok",
            "dry_run": True,
            "pending": len(events),
            "backend_url": _backend_url(base_url, "/telemetry/events:batch"),
        }
    uploaded = 0
    last_response: dict | None = None
    for offset in range(0, len(events), DEFAULT_BATCH_SIZE):
        batch = events[offset:offset + MAX_BACKEND_BATCH_SIZE]
        code, text, parsed = _post_backend_batch(batch, base_url=base_url, timeout_seconds=timeout)
        last_response = parsed
        if code != 0:
            return {
                "status": "error",
                "uploaded": uploaded,
                "pending": len(events) - uploaded,
                "message": text,
                "response": parsed,
            }
        uploaded += len(batch)
    _archive_pending()
    return {
        "status": "ok",
        "uploaded": uploaded,
        "pending": 0,
        "backend_url": _backend_url(base_url, "/telemetry/events:batch"),
        "response": last_response,
    }


def _score_analysis(
    *,
    platform: str,
    fault_link: str,
    has_timeline: bool,
    has_log_evidence: bool,
    has_breakpoint: bool,
    confidence: str,
) -> tuple[float, str, str]:
    """Return accuracy_score, pass_fail, fail_dimensions for ANALYZED gate."""
    checks = []
    if platform.upper() in ("MTK", "QCOM"):
        checks.append(("平台识别", "PASS"))
    else:
        checks.append(("平台识别", "FAIL"))
    if fault_link:
        checks.append(("故障链路", "PASS"))
    else:
        checks.append(("故障链路", "FAIL"))
    if has_timeline:
        checks.append(("时间线", "PASS"))
    else:
        checks.append(("时间线", "FAIL"))
    if has_log_evidence:
        checks.append(("日志证据", "PASS"))
    else:
        checks.append(("日志证据", "FAIL"))
    if has_breakpoint:
        checks.append(("链路断点", "PASS"))
    else:
        checks.append(("链路断点", "FAIL"))

    conf = (confidence or "").strip()
    if conf in ("已证实", "高概率"):
        checks.append(("置信度", "PASS"))
    elif conf == "待确认":
        checks.append(("置信度", "WARN"))
    else:
        checks.append(("置信度", "FAIL"))

    scored = [c for c in checks if c[1] in ("PASS", "FAIL")]
    passed = sum(1 for c in scored if c[1] == "PASS")
    fail_count = sum(1 for c in checks if c[1] == "FAIL")
    warn_count = sum(1 for c in checks if c[1] == "WARN")
    accuracy = round(passed / len(scored) * 100, 1) if scored else 0.0
    if fail_count:
        pass_fail = "FAIL"
    elif warn_count:
        pass_fail = "CONDITIONAL"
    else:
        pass_fail = "PASS"
    fail_dims = ",".join(name for name, result in checks if result == "FAIL")
    return accuracy, pass_fail, fail_dims


def cmd_record(args: argparse.Namespace) -> dict:
    jira_id = str(args.jira_id or "").strip()
    if not jira_id:
        return {"status": "error", "message": "--jira-id is required"}
    platform = str(args.platform or "").strip().upper()
    if platform and platform not in ("MTK", "QCOM"):
        return {"status": "error", "message": "--platform must be MTK or QCOM"}
    workflow_state = str(args.workflow_state or "").strip().upper()
    if workflow_state and workflow_state not in WORKFLOW_STATES:
        return {"status": "error", "message": f"--workflow-state must be one of {', '.join(WORKFLOW_STATES)}"}
    pass_fail = str(args.pass_fail or "").strip().upper()
    accuracy_score = args.accuracy_score
    fail_dimensions = str(args.fail_dimensions or "")

    if getattr(args, "auto_score", False):
        accuracy_score, pass_fail, fail_dimensions = _score_analysis(
            platform=platform,
            fault_link=str(args.fault_link or ""),
            has_timeline=bool(args.has_timeline),
            has_log_evidence=bool(args.has_log_evidence),
            has_breakpoint=bool(args.has_breakpoint),
            confidence=str(args.confidence or ""),
        )

    if pass_fail not in PASS_FAIL:
        return {"status": "error", "message": "--pass-fail must be PASS|FAIL|CONDITIONAL (or use --auto-score)"}
    if accuracy_score is None:
        return {"status": "error", "message": "--accuracy-score is required (or use --auto-score)"}

    record = {
        "jira_id": jira_id,
        "check_time": args.check_time or datetime.now().strftime("%Y-%m-%d %H:%M"),
        "accuracy_score": float(accuracy_score),
        "pass_fail": pass_fail,
        "fail_dimensions": fail_dimensions,
        "platform": platform,
        "fault_link": str(args.fault_link or ""),
        "operator_mccmnc": str(args.operator_mccmnc or ""),
        "workflow_state": workflow_state or "ANALYZED",
        "change_url": str(getattr(args, "change_url", "") or ""),
        "branch": str(getattr(args, "branch", "") or ""),
        "submit_phase": str(getattr(args, "submit_phase", "") or ""),
    }
    local_path = append_local_stats(record)
    event = build_spn_event(record)
    append_pending(event)
    result = {
        "status": "ok",
        "domain": "connectivity-spn-workflow",
        "command": "spn dashboard record",
        "message": f"Recorded SPN dashboard stat for {jira_id}",
        "record": record,
        "event_id": event["event_id"],
        "paths": {
            "local_stats": str(local_path),
            "pending_upload": str(pending_path()),
        },
    }
    if not getattr(args, "no_upload", False):
        upload = flush_pending()
        result["upload"] = upload
        if upload.get("status") != "ok":
            result["status"] = "error"
            result["message"] = (
                f"Recorded locally but backend upload failed: {upload.get('message', 'unknown error')}"
            )
    return result


def cmd_flush(args: argparse.Namespace) -> dict:
    result = flush_pending(dry_run=bool(getattr(args, "dry_run", False)))
    base_url, _timeout = _backend_config()
    return {
        "status": result.get("status", "ok"),
        "domain": "connectivity-spn-workflow",
        "command": "spn dashboard flush",
        "upload": result,
        "paths": {"pending_upload": str(pending_path())},
        "backend": {
            "base_url": base_url,
            "upload_endpoint": _backend_url(base_url, "/telemetry/events:batch"),
            "command_path": SPN_DASHBOARD_COMMAND_PATH,
        },
    }


def _default_date_range(days: int) -> tuple[str, str]:
    today = datetime.now().astimezone().date()
    start = today - timedelta(days=max(1, int(days)) - 1)
    return start.isoformat(), today.isoformat()


def _get_backend_json(url: str, *, params: dict[str, str], timeout_seconds: int) -> dict:
    query = urllib_parse.urlencode(params)
    full_url = f"{url}?{query}" if query else url
    req = urllib_request.Request(full_url, method="GET")
    with urllib_request.urlopen(req, timeout=timeout_seconds) as response:
        text = response.read().decode("utf-8", errors="replace")
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise RuntimeError("backend returned non-object JSON response")
    return payload


def fetch_remote_events(
    *,
    fetch_days: int = DEFAULT_FETCH_DAYS,
    command_path: str = SPN_DASHBOARD_COMMAND_PATH,
) -> tuple[list[dict], dict]:
    date_from, date_to = _default_date_range(fetch_days)
    base_url, timeout = _backend_config()
    diagnostic = {
        "status": "ok",
        "command_path": command_path,
        "date_from": date_from,
        "date_to": date_to,
        "events": 0,
        "backend_base_url": base_url,
    }
    events: list[dict] = []
    offset = 0
    total: int | None = None
    while True:
        params = {
            "date_from": date_from,
            "date_to": date_to,
            "command_path": command_path,
            "include_raw": "true",
            "limit": str(MAX_BACKEND_BATCH_SIZE),
            "offset": str(offset),
        }
        try:
            payload = _get_backend_json(
                _backend_url(base_url, "/telemetry/events"),
                params=params,
                timeout_seconds=timeout,
            )
        except Exception as exc:
            diagnostic.update({"status": "error", "error": str(exc), "events": len(events)})
            return events, diagnostic
        items = payload.get("items") or []
        if not isinstance(items, list):
            diagnostic.update({"status": "error", "error": "backend response items is not a list"})
            return events, diagnostic
        events.extend(item for item in items if isinstance(item, dict))
        total_value = payload.get("total")
        if total_value is not None:
            try:
                total = int(total_value)
            except (TypeError, ValueError):
                total = None
        offset += len(items)
        if not items or (total is not None and offset >= total):
            break
    diagnostic["events"] = len(events)
    if total is not None:
        diagnostic["total"] = total
    return events, diagnostic


def _raw_payload(item: dict) -> dict:
    raw = item.get("raw_event_json")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = None
    source = raw if isinstance(raw, dict) else item
    params = source.get("params") if isinstance(source.get("params"), dict) else {}
    return params or source


def parse_spn_records(events: list[dict]) -> list[dict]:
    records = []
    for item in events:
        payload = _raw_payload(item)
        record_type = payload.get("record_type")
        command_path = item.get("command_path") or ""
        if record_type and record_type != SPN_DASHBOARD_RECORD_TYPE and command_path != SPN_DASHBOARD_COMMAND_PATH:
            continue
        score = payload.get("accuracy_score")
        try:
            score = float(score) if score is not None else None
        except (TypeError, ValueError):
            score = None
        records.append({
            "jira_id": str(payload.get("jira_id") or ""),
            "check_time": str(payload.get("check_time") or item.get("event_time") or ""),
            "accuracy_score": score,
            "pass_fail": str(payload.get("pass_fail") or "").upper(),
            "fail_dimensions": str(payload.get("fail_dimensions") or ""),
            "platform": str(payload.get("platform") or ""),
            "fault_link": str(payload.get("fault_link") or ""),
            "operator_mccmnc": str(payload.get("operator_mccmnc") or ""),
            "workflow_state": str(payload.get("workflow_state") or ""),
            "user_corrections": 0,
        })
    return records


def parse_cc_records(events: list[dict]) -> list[dict]:
    records = []
    for item in events:
        payload = _raw_payload(item)
        record_type = payload.get("record_type")
        command_path = item.get("command_path") or ""
        if record_type and record_type != CC_DASHBOARD_RECORD_TYPE and command_path != CC_DASHBOARD_COMMAND_PATH:
            continue
        score = payload.get("accuracy_score")
        try:
            score = float(score) if score is not None else None
        except (TypeError, ValueError):
            score = None
        try:
            corrections = int(payload.get("user_corrections") or 0)
        except (TypeError, ValueError):
            corrections = 0
        records.append({
            "jira_id": str(payload.get("jira_id") or ""),
            "check_time": str(payload.get("check_time") or item.get("event_time") or ""),
            "accuracy_score": score,
            "pass_fail": str(payload.get("pass_fail") or "").upper(),
            "fail_dimensions": str(payload.get("fail_dimensions") or ""),
            "platform": str(payload.get("platform") or ""),
            "carrier_name": str(payload.get("carrier_name") or ""),
            "user_corrections": corrections,
        })
    return records


def build_trend(records: list[dict]) -> dict:
    by_date: dict[str, list[str]] = {}
    for rec in records:
        time_str = str(rec.get("check_time") or "")
        date_key = time_str[:10] if len(time_str) >= 10 else "unknown"
        by_date.setdefault(date_key, []).append(str(rec.get("pass_fail") or ""))
    dates = sorted(d for d in by_date if d != "unknown")
    pass_rates = []
    for date in dates:
        outcomes = by_date[date]
        passed = sum(1 for o in outcomes if o == "PASS")
        pass_rates.append(round(passed / len(outcomes) * 100, 1) if outcomes else 0.0)
    return {"dates": dates, "pass_rates": pass_rates}


def build_fail_breakdown(records: list[dict]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for rec in records:
        if rec.get("pass_fail") != "FAIL":
            continue
        for dim in [d.strip() for d in str(rec.get("fail_dimensions") or "").split(",") if d.strip()]:
            counter[dim] += 1
    return dict(counter.most_common())


def build_field_breakdown(records: list[dict], field: str) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for rec in records:
        value = str(rec.get(field) or "").strip()
        if value:
            counter[value] += 1
    return dict(counter.most_common())


def build_spn_fail_breakdown(records: list[dict]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for rec in records:
        if rec.get("pass_fail") != "FAIL":
            continue
        fault_link = str(rec.get("fault_link") or "").strip()
        if fault_link:
            counter[fault_link] += 1
            continue
        for dim in [d.strip() for d in str(rec.get("fail_dimensions") or "").split(",") if d.strip()]:
            counter[dim] += 1
    return dict(counter.most_common())


def load_combined_remote_datasets(*, fetch_days: int = DEFAULT_FETCH_DAYS) -> dict:
    cc_events, cc_diag = fetch_remote_events(fetch_days=fetch_days, command_path=CC_DASHBOARD_COMMAND_PATH)
    spn_events, spn_diag = fetch_remote_events(fetch_days=fetch_days, command_path=SPN_DASHBOARD_COMMAND_PATH)
    cc_records = parse_cc_records(cc_events)
    spn_records = parse_spn_records(spn_events)
    return {
        "carrierconfig": {
            "records": cc_records,
            "summary": _build_summary_from_records(cc_records),
            "fail_breakdown": build_fail_breakdown(cc_records),
            "trend": build_trend(cc_records),
            "diagnostic": cc_diag,
        },
        "spn": {
            "records": spn_records,
            "summary": _build_summary_from_records(spn_records),
            "fail_breakdown": build_spn_fail_breakdown(spn_records),
            "platform_breakdown": build_field_breakdown(spn_records, "platform"),
            "fault_link_breakdown": build_field_breakdown(spn_records, "fault_link"),
            "trend": build_trend(spn_records),
            "diagnostic": spn_diag,
        },
    }


def cmd_summary(args: argparse.Namespace) -> dict:
    events, diagnostic = fetch_remote_events(
        fetch_days=int(getattr(args, "fetch_days", DEFAULT_FETCH_DAYS) or DEFAULT_FETCH_DAYS),
        command_path=SPN_DASHBOARD_COMMAND_PATH,
    )
    records = parse_spn_records(events)
    summary = _build_summary_from_records(records)
    base_url, _timeout = _backend_config()
    return {
        "status": "ok" if diagnostic.get("status") == "ok" else "error",
        "domain": "connectivity-spn-workflow",
        "command": "spn dashboard summary",
        "summary": summary,
        "records": records[-50:],
        "data_sources": {
            "remote": len(records),
            "remote_status": diagnostic.get("status"),
            "remote_diagnostic": diagnostic,
        },
        "backend": {
            "base_url": base_url,
            "query_endpoint": _backend_url(base_url, "/telemetry/events"),
            "command_path": SPN_DASHBOARD_COMMAND_PATH,
        },
    }


def _build_summary_from_records(records: list[dict]) -> dict:
    total = len(records)
    pass_count = sum(1 for r in records if r["pass_fail"] == "PASS")
    fail_count = sum(1 for r in records if r["pass_fail"] == "FAIL")
    conditional_count = sum(1 for r in records if r["pass_fail"] == "CONDITIONAL")
    scores = []
    for r in records:
        try:
            if r.get("accuracy_score") is not None:
                scores.append(float(r["accuracy_score"]))
        except (TypeError, ValueError):
            pass
    return {
        "total": total,
        "pass_count": pass_count,
        "fail_count": fail_count,
        "conditional_count": conditional_count,
        "success_rate": round(pass_count / total * 100, 1) if total else 0.0,
        "avg_accuracy": round(sum(scores) / len(scores), 1) if scores else 0.0,
        "unique_jira": len({r["jira_id"] for r in records if r.get("jira_id")}),
    }


def load_milestone_state() -> dict:
    path = milestone_state_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_milestone_state(state: dict) -> Path:
    path = milestone_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def evaluate_milestone(summary: dict, *, min_total: int, min_success_rate: float) -> dict:
    total = int(summary.get("total") or 0)
    success_rate = float(summary.get("success_rate") or 0.0)
    total_ok = total >= int(min_total)
    rate_check_enabled = float(min_success_rate) > 0
    rate_ok = success_rate >= float(min_success_rate) if rate_check_enabled else True
    milestone_met = total_ok and rate_ok
    return {
        "milestone_met": milestone_met,
        "total_ok": total_ok,
        "rate_ok": rate_ok,
        "rate_check_enabled": rate_check_enabled,
        "total": total,
        "success_rate": success_rate,
        "min_total": int(min_total),
        "min_success_rate": float(min_success_rate),
        "target_total": int(min_total),
        "remaining_to_total": max(0, int(min_total) - total),
        "remaining_to_rate": round(max(0.0, float(min_success_rate) - success_rate), 1) if rate_check_enabled else 0.0,
        "unique_jira": int(summary.get("unique_jira") or 0),
    }


def _total_notify_tier(total: int, min_total: int) -> int:
    """满 min_total 起算档位：30→1，60→2，90→3。"""
    if total < int(min_total):
        return 0
    return (total - int(min_total)) // int(min_total) + 1


def should_notify_milestone(
    milestone: dict,
    state: dict,
    *,
    force_notify: bool = False,
) -> tuple[bool, str]:
    if force_notify and milestone["milestone_met"]:
        return True, "force_notify"
    if not milestone["milestone_met"]:
        return False, "milestone_not_met"
    total = int(milestone["total"])
    success_rate = float(milestone["success_rate"])
    if not state.get("milestone_achieved"):
        return True, "first_achievement"
    last_total = int(state.get("last_notified_total") or 0)
    last_rate = float(state.get("last_notified_success_rate") or 0.0)
    if _total_notify_tier(total, int(milestone["min_total"])) > _total_notify_tier(
        last_total, int(milestone["min_total"])
    ):
        return True, "new_total_tier"
    if (
        milestone.get("rate_check_enabled")
        and success_rate >= milestone["min_success_rate"]
        and last_rate < milestone["min_success_rate"]
    ):
        return True, "rate_recovered"
    return False, "already_notified"


def format_milestone_message(milestone: dict) -> str:
    if milestone.get("rate_check_enabled"):
        return (
            f"SPN 远程看板已达 {milestone['total']} 单（>={milestone['min_total']} 单），"
            f"成功率 {milestone['success_rate']}%（>={milestone['min_success_rate']}%）"
        )
    return f"SPN 远程看板已达 {milestone['total']} 单（已满 {milestone['min_total']} 单阈值）"


def _run_powershell_file(script: str) -> tuple[int, str]:
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False, encoding="utf-8") as handle:
        handle.write(script)
        script_path = handle.name
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script_path],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        output = (proc.stderr or proc.stdout or "").strip()
        return proc.returncode, output
    except Exception as exc:
        return 1, str(exc)
    finally:
        try:
            os.unlink(script_path)
        except OSError:
            pass


def _show_windows_toast(title: str, message: str) -> dict:
    xml_title = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    xml_message = message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    ps_script = f"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$APP_ID = '{{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}}'
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml(@"
<toast activationType="foreground">
  <visual>
    <binding template="ToastGeneric">
      <text>{xml_title}</text>
      <text>{xml_message}</text>
    </binding>
  </visual>
  <audio src="ms-winsoundevent:Notification.Default"/>
</toast>
"@)
$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($APP_ID).Show($toast)
"""
    code, output = _run_powershell_file(ps_script)
    if code == 0:
        return {"status": "ok", "channel": "windows_toast"}
    return {"status": "error", "channel": "windows_toast", "message": output or "toast failed"}


def _show_windows_popup(title: str, message: str) -> dict:
    try:
        import ctypes

        flags = 0x40 | 0x40000
        result = ctypes.windll.user32.MessageBoxW(0, message, title, flags)
        if result == 0:
            return {"status": "error", "channel": "windows_popup", "message": "MessageBoxW returned 0"}
        return {"status": "ok", "channel": "windows_popup"}
    except Exception as exc:
        return {"status": "error", "channel": "windows_popup", "message": str(exc)}


def show_desktop_notification(title: str, message: str, *, style: str = "auto") -> dict:
    system = platform.system().lower()
    if system != "windows":
        return {"status": "skipped", "reason": f"desktop notification not implemented for {system}"}

    mode = (style or "auto").strip().lower()
    channels: list[dict] = []
    if mode in {"auto", "toast", "both"}:
        channels.append(_show_windows_toast(title, message))
    if mode in {"auto", "popup", "both"}:
        channels.append(_show_windows_popup(title, message))

    ok_channels = [item["channel"] for item in channels if item.get("status") == "ok"]
    if ok_channels:
        return {
            "status": "ok",
            "channels": channels,
            "channel": ok_channels[-1],
            "message": message,
        }
    return {
        "status": "error",
        "channels": channels,
        "message": channels[-1].get("message", "notification failed") if channels else "no channel",
    }


def print_milestone_banner(milestone: dict, *, notified: bool) -> None:
    title = "SPN 远程看板里程碑达成" if milestone["milestone_met"] else "SPN 远程看板进度"
    border = "=" * 52
    print(border)
    print(f"  {title}")
    total_tag = "[OK]" if milestone["total_ok"] else f"[还差 {milestone['remaining_to_total']} 单]"
    print(f"  远程校验单数: {milestone['total']} / 目标 >= {milestone['min_total']} 单 {total_tag}")
    print(f"  去重 Jira 数: {milestone.get('unique_jira', 0)}")
    if milestone.get("rate_check_enabled"):
        rate_tag = "[OK]" if milestone["rate_ok"] else f"[还差 {milestone['remaining_to_rate']}%]"
        print(f"  成功率:       {milestone['success_rate']}% / 目标 >= {milestone['min_success_rate']}% {rate_tag}")
    else:
        print(f"  成功率:       {milestone['success_rate']}%（仅供参考，不作为通知条件）")
    if milestone["milestone_met"]:
        print("  结论: 里程碑已达成")
        if notified:
            print("  已发送桌面通知（Toast + 弹窗）")
    else:
        print("  结论: 尚未达成里程碑")
    print(border)


def cmd_check(args: argparse.Namespace) -> dict:
    summary_result = cmd_summary(args)
    summary = summary_result.get("summary") or {}
    data_sources = summary_result.get("data_sources") or {}
    min_total = int(getattr(args, "min_total", DEFAULT_MILESTONE_MIN_TOTAL) or DEFAULT_MILESTONE_MIN_TOTAL)
    min_success_rate = float(
        getattr(args, "min_success_rate", DEFAULT_MILESTONE_MIN_SUCCESS_RATE) or DEFAULT_MILESTONE_MIN_SUCCESS_RATE
    )
    milestone = evaluate_milestone(summary, min_total=min_total, min_success_rate=min_success_rate)
    state = {} if getattr(args, "reset_state", False) else load_milestone_state()
    notify, notify_reason = should_notify_milestone(
        milestone,
        state,
        force_notify=bool(getattr(args, "force_notify", False)),
    )
    notification_result = None
    if notify and getattr(args, "notify", True) and milestone["milestone_met"]:
        notification_result = show_desktop_notification(
            "SPN 看板里程碑",
            format_milestone_message(milestone),
            style=str(getattr(args, "notify_style", "auto") or "auto"),
        )
    if milestone["milestone_met"] and notify:
        state = {
            "milestone_achieved": True,
            "last_notified_total": milestone["total"],
            "last_notified_success_rate": milestone["success_rate"],
            "last_notified_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "last_notify_reason": notify_reason,
        }
        save_milestone_state(state)
    result = {
        "status": "ok" if summary_result.get("status") == "ok" else "error",
        "milestone_status": "achieved" if milestone["milestone_met"] else "pending",
        "domain": "connectivity-spn-workflow",
        "command": "spn dashboard check",
        "message": format_milestone_message(milestone) if milestone["milestone_met"] else (
            f"尚未达成：当前 {milestone['total']} 单、成功率 {milestone['success_rate']}%"
        ),
        "summary": summary,
        "milestone": milestone,
        "notification": {
            "should_notify": notify,
            "reason": notify_reason,
            "enabled": bool(getattr(args, "notify", True)),
            "result": notification_result,
        },
        "data_sources": data_sources,
        "state_path": str(milestone_state_path()),
        "state": state,
    }
    if not getattr(args, "json", False):
        print_milestone_banner(
            milestone,
            notified=bool(notify and notification_result and notification_result.get("status") == "ok"),
        )
    return result


def _resolve_python() -> str:
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "harness" / "npm-venv" / "1.3.0" / "Scripts" / "python.exe",
        Path(sys.executable),
    ]
    for path in candidates:
        if path and path.is_file():
            return str(path)
    return sys.executable


def _write_daily_runner() -> Path:
    script = Path(__file__).resolve()
    python_exe = _resolve_python()
    runner = daily_runner_path()
    log = daily_log_path()
    site_packages = Path(python_exe).resolve().parent.parent / "Lib" / "site-packages"
    content = f"""@echo off
setlocal
set PYTHONPATH={site_packages}
set PYTHONIOENCODING=utf-8
echo ===== %date% %time% =====>> "{log}"
"{python_exe}" "{script}" --json check --min-total {DEFAULT_MILESTONE_MIN_TOTAL} >> "{log}" 2>&1
echo.>> "{log}"
"""
    runner.write_text(content, encoding="utf-8")
    return runner


def cmd_install_daily(args: argparse.Namespace) -> dict:
    if platform.system().lower() != "windows":
        return {"status": "error", "message": "install-daily currently supports Windows Task Scheduler only"}
    runner = _write_daily_runner()
    hour, minute = (getattr(args, "time", DAILY_TASK_TIME) or DAILY_TASK_TIME).split(":")
    task_name = getattr(args, "task_name", DAILY_TASK_NAME) or DAILY_TASK_NAME
    # /SC DAILY /ST HH:MM
    cmd = [
        "schtasks",
        "/Create",
        "/F",
        "/TN",
        task_name,
        "/TR",
        str(runner),
        "/SC",
        "DAILY",
        "/ST",
        f"{int(hour):02d}:{int(minute):02d}",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    ok = proc.returncode == 0
    return {
        "status": "ok" if ok else "error",
        "domain": "connectivity-spn-workflow",
        "command": "spn dashboard install-daily",
        "message": (proc.stdout or proc.stderr or "").strip() or ("installed" if ok else "install failed"),
        "task_name": task_name,
        "schedule": f"DAILY {int(hour):02d}:{int(minute):02d}",
        "min_total": DEFAULT_MILESTONE_MIN_TOTAL,
        "paths": {
            "runner": str(runner),
            "log": str(daily_log_path()),
            "script": str(Path(__file__).resolve()),
        },
    }


def cmd_uninstall_daily(args: argparse.Namespace) -> dict:
    if platform.system().lower() != "windows":
        return {"status": "error", "message": "uninstall-daily currently supports Windows Task Scheduler only"}
    task_name = getattr(args, "task_name", DAILY_TASK_NAME) or DAILY_TASK_NAME
    proc = subprocess.run(
        ["schtasks", "/Delete", "/F", "/TN", task_name],
        capture_output=True,
        text=True,
        check=False,
    )
    ok = proc.returncode == 0
    return {
        "status": "ok" if ok else "error",
        "domain": "connectivity-spn-workflow",
        "command": "spn dashboard uninstall-daily",
        "message": (proc.stdout or proc.stderr or "").strip() or ("uninstalled" if ok else "uninstall failed"),
        "task_name": task_name,
    }


def cmd_generate(args: argparse.Namespace) -> dict:
    # Ensure sibling module import works when invoked as script path
    assets_dir = Path(__file__).resolve().parent
    if str(assets_dir) not in sys.path:
        sys.path.insert(0, str(assets_dir))
    from generate_combined_dashboard import generate

    output, meta = generate(
        output_path=getattr(args, "output", None),
        fetch_days=int(getattr(args, "fetch_days", DEFAULT_FETCH_DAYS) or DEFAULT_FETCH_DAYS),
    )
    if getattr(args, "open", False):
        webbrowser.open(output.as_uri())
    datasets = meta["datasets"]
    return {
        "status": "ok",
        "domain": "connectivity-spn-workflow",
        "command": "spn dashboard generate",
        "message": f"Combined dashboard generated: {output}",
        "summary": {
            "carrierconfig": datasets["carrierconfig"]["summary"],
            "spn": datasets["spn"]["summary"],
        },
        "data_sources": {
            "carrierconfig": datasets["carrierconfig"]["diagnostic"],
            "spn": datasets["spn"]["diagnostic"],
        },
        "paths": {
            "dashboard_html": str(output),
            "legacy_html": meta.get("legacy_html"),
        },
    }


def cmd_remote(args: argparse.Namespace) -> dict:
    if not getattr(args, "output", None):
        args.output = default_combined_dashboard_html()
    args.open = bool(getattr(args, "open", False))
    result = cmd_generate(args)
    result["command"] = "spn dashboard remote"
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SPN dashboard (connectivity/sub/spn)")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--no-upload", action="store_true")
    parser.add_argument("--fetch-days", type=int, default=DEFAULT_FETCH_DAYS)
    sub = parser.add_subparsers(dest="command", required=True)

    p_record = sub.add_parser("record", help="record + upload one SPN dashboard stat")
    p_record.add_argument("--jira-id", required=True)
    p_record.add_argument("--platform", default="", help="MTK or QCOM")
    p_record.add_argument("--fault-link", default="", choices=("",) + FAULT_LINKS)
    p_record.add_argument("--operator-mccmnc", default="")
    p_record.add_argument("--workflow-state", default="ANALYZED", choices=WORKFLOW_STATES)
    p_record.add_argument("--pass-fail", default="", choices=("",) + PASS_FAIL)
    p_record.add_argument("--accuracy-score", type=float, default=None)
    p_record.add_argument("--fail-dimensions", default="")
    p_record.add_argument("--check-time", default=None)
    p_record.add_argument("--change-url", default="")
    p_record.add_argument("--branch", default="")
    p_record.add_argument("--submit-phase", default="")
    p_record.add_argument(
        "--auto-score",
        action="store_true",
        help="compute accuracy_score/pass_fail from evidence flags",
    )
    p_record.add_argument("--has-timeline", action=argparse.BooleanOptionalAction, default=True)
    p_record.add_argument("--has-log-evidence", action=argparse.BooleanOptionalAction, default=True)
    p_record.add_argument("--has-breakpoint", action=argparse.BooleanOptionalAction, default=True)
    p_record.add_argument("--confidence", default="已证实", help="已证实|高概率|待确认")

    p_flush = sub.add_parser("flush", help="flush pending SPN dashboard uploads")
    p_flush.add_argument("--dry-run", action="store_true")

    sub.add_parser("summary", help="summarize remote SPN dashboard stats")

    p_check = sub.add_parser(
        "check",
        help="check remote milestone (default >=30) and optionally notify",
    )
    p_check.add_argument(
        "--min-total",
        type=int,
        default=DEFAULT_MILESTONE_MIN_TOTAL,
        help=f"notify when remote total reaches this count (default {DEFAULT_MILESTONE_MIN_TOTAL})",
    )
    p_check.add_argument(
        "--min-success-rate",
        type=float,
        default=DEFAULT_MILESTONE_MIN_SUCCESS_RATE,
        help="minimum success rate percent; 0 disables rate check (default 0)",
    )
    p_check.add_argument(
        "--notify",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="show Windows desktop toast when milestone is met (default on)",
    )
    p_check.add_argument(
        "--notify-style",
        choices=["auto", "toast", "popup", "both"],
        default="auto",
        help="auto=Toast+弹窗, toast=仅右下角, popup=仅居中弹窗",
    )
    p_check.add_argument(
        "--force-notify",
        action="store_true",
        help="notify even if milestone was already announced",
    )
    p_check.add_argument(
        "--reset-state",
        action="store_true",
        help="clear saved milestone notification state before checking",
    )

    p_install = sub.add_parser(
        "install-daily",
        help="install Windows daily scheduled task (default 09:00)",
    )
    p_install.add_argument("--time", default=DAILY_TASK_TIME, help="HH:MM, default 09:00")
    p_install.add_argument("--task-name", default=DAILY_TASK_NAME)

    p_uninstall = sub.add_parser("uninstall-daily", help="remove Windows daily scheduled task")
    p_uninstall.add_argument("--task-name", default=DAILY_TASK_NAME)

    p_generate = sub.add_parser(
        "generate",
        help="generate combined CarrierConfig+SPN remote HTML dashboard",
    )
    p_generate.add_argument("--open", action="store_true", help="open browser after generate")
    p_generate.add_argument("--output", type=Path, default=None)

    p_remote = sub.add_parser(
        "remote",
        help="same as generate: team-wide dual-tab dashboard (CarrierConfig + SPN)",
    )
    p_remote.add_argument("--open", action="store_true", help="generate and open browser")
    p_remote.add_argument("--output", type=Path, default=None)
    return parser


def run_command(args: argparse.Namespace) -> dict:
    if args.command == "record":
        return cmd_record(args)
    if args.command == "flush":
        return cmd_flush(args)
    if args.command == "summary":
        return cmd_summary(args)
    if args.command == "check":
        return cmd_check(args)
    if args.command == "install-daily":
        return cmd_install_daily(args)
    if args.command == "uninstall-daily":
        return cmd_uninstall_daily(args)
    if args.command == "generate":
        return cmd_generate(args)
    if args.command == "remote":
        return cmd_remote(args)
    return {"status": "error", "message": f"unknown command: {args.command}"}


def main_cli(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = run_command(args)
    except Exception as exc:
        result = {"status": "error", "message": str(exc)}
    # check 非 --json 时已打印横幅，避免重复刷屏
    if getattr(args, "json", False) or args.command != "check":
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0 if result.get("status") in ("ok", "success") else 1


def main() -> None:
    sys.exit(main_cli())


if __name__ == "__main__":
    main()
