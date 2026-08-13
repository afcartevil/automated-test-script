"""游戏功耗澄清：归因类别判断（YAML 规则 + 步骤 12 数据汇总）。"""

from __future__ import annotations

import html
import itertools
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from skill_references import load_reference_yaml
from brightness_summary_bridge import brightness_findings_summary  # noqa: E402
from volume_summary_bridge import volume_findings_summary  # noqa: E402
from cause_snapshot_lib import (  # noqa: E402
    build_dual_duration_mismatch_finding,
    collect_category_evidence,
    collect_cause_evidence,
    format_cause_evidence_html,
    format_category_links_html,
    format_feature_difference_compare_table_html,
    format_feature_difference_table_html,
    format_test_methodology_compare_table_html,
    format_test_methodology_table_html,
    write_step_report_htmls,
)

_THREAD_CURVE_UID = itertools.count(1)
_TEMP_CURVE_UID = itertools.count(1)

_STEP_JSON_NAMES = (
    "game_time_window",
    "game_precondition",
    "game_power_model",
    "game_brightness",
    "game_volume",
    "game_cpu_gpu_ddr",
    "game_background",
    "game_network",
    "game_network_cap",
    "game_thermal",
    "game_kernel_cpu",
    "game_current_log_correlate",
    "game_current_cpu_spike",
)


def _find_labeled_network_cap(
    analysis_dir: Path,
    report_meta: dict[str, Any],
) -> dict[str, Any] | None:
    """从 workspace analysis/game_network_cap_<label>.json 回退加载。

    优先使用出现在 analysis_dir 路径中的机型标签，避免双机共用 meta 时串档。
    """
    path_str = str(analysis_dir)
    path_parts = set(analysis_dir.parts)
    labels: list[str] = []

    def _add(lab: str) -> None:
        lab = str(lab or "").strip()
        if lab and lab not in labels:
            labels.append(lab)

    # 1) 路径目录名优先（converted/CN6/...）
    for part in analysis_dir.parts:
        if part in {"analysis", "mobilelog", "converted", "downloads", "temp", "netlog", "networklog"}:
            continue
        if part.startswith("APLog"):
            continue
        if len(part) <= 24 and any(ch.isdigit() for ch in part) and part[0].isalpha():
            _add(part)

    # 2) meta 标签：仅当标签出现在本侧路径中
    for key in ("test_device_label", "compare_device_label", "device_label"):
        v = str(report_meta.get(key) or "").strip()
        if v and (v in path_parts or v in path_str):
            _add(v)

    if not labels:
        return None

    ws_dirs: list[Path] = []
    for parent in analysis_dir.parents:
        ws = parent / "analysis"
        if ws.is_dir():
            ws_dirs.append(ws)
            break
    if analysis_dir.name == "analysis":
        ws_dirs.insert(0, analysis_dir)

    for ws in ws_dirs:
        for lab in labels:
            path = ws / f"game_network_cap_{lab}.json"
            if not path.is_file():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(data, dict):
                data = dict(data)
                data["_loaded_from"] = str(path)
                return data
    return None


def skill_root() -> Path:
    return Path(__file__).resolve().parent.parent


def references_dir() -> Path:
    return skill_root() / "references"


def _get_path(obj: Any, path: str) -> Any:
    if not path:
        return obj
    cur = obj
    for part in path.split("."):
        if cur is None:
            return None
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def _is_empty(val: Any) -> bool:
    if val is None:
        return True
    if isinstance(val, str):
        return not val.strip()
    if isinstance(val, (list, dict)):
        return len(val) == 0
    return False


def _resolve_value(raw: Any, thresholds: dict[str, Any]) -> Any:
    if isinstance(raw, str) and raw.endswith("_ref") is False:
        if raw in thresholds:
            return thresholds[raw]
    if isinstance(raw, str) and raw.endswith("_ref"):
        return None
    return raw


def _resolve_threshold(rule: dict[str, Any], thresholds: dict[str, Any], key: str = "value") -> Any:
    if f"{key}_ref" in rule:
        ref = str(rule[f"{key}_ref"])
        return thresholds.get(ref, rule.get(key))
    val = rule.get(key)
    if isinstance(val, str) and val in thresholds:
        return thresholds[val]
    return val


def _find_tag(tags: Any, tag_id: str) -> dict[str, Any] | None:
    if not isinstance(tags, list):
        return None
    for item in tags:
        if isinstance(item, dict) and str(item.get("id")) == tag_id:
            return item
    return None


def _collect_evidence_text(obj: Any, out: list[str]) -> None:
    if isinstance(obj, dict):
        for key, val in obj.items():
            if key in ("raw_evidence", "evidence") and isinstance(val, str):
                out.append(val)
            else:
                _collect_evidence_text(val, out)
    elif isinstance(obj, list):
        for item in obj:
            _collect_evidence_text(item, out)


def _source_data(ctx: dict[str, Any], source: str) -> Any:
    if source in ctx:
        return ctx[source]
    if source == "summary":
        return ctx.get("summary", {})
    return {}


def _eval_simple_op(op: str, left: Any, right: Any) -> bool:
    if op == "eq":
        return left == right
    if op == "ne":
        return left != right
    if op == "gt":
        try:
            return float(left) > float(right)
        except (TypeError, ValueError):
            return False
    if op == "gte":
        try:
            return float(left) >= float(right)
        except (TypeError, ValueError):
            return False
    if op == "lt":
        try:
            return float(left) < float(right)
        except (TypeError, ValueError):
            return False
    if op == "lte":
        try:
            return float(left) <= float(right)
        except (TypeError, ValueError):
            return False
    if op == "in":
        if isinstance(right, list):
            return left in right
        return left == right
    if op == "empty":
        return _is_empty(left)
    if op == "not_empty":
        return not _is_empty(left)
    if op == "count_gte":
        if isinstance(left, list):
            return len(left) >= int(right)
        return False
    if op == "ne_path":
        return False
    return False


def _eval_check(check: dict[str, Any], ctx: dict[str, Any], thresholds: dict[str, Any]) -> tuple[bool, str]:
    check_type = str(check.get("check_type") or "path")

    if check_type == "path" or (check_type not in (
        "composite", "tag_scenario", "tag_status_in", "tag_value",
        "evidence_keyword", "meta_delta_gte", "requires_meta",
    ) and "path" in check):
        source = str(check.get("source") or "summary")
        path = str(check.get("path", ""))
        op = str(check.get("op", "eq"))
        right = _resolve_threshold(check, thresholds)
        left = _get_path(_source_data(ctx, source), path)
        if op == "ne_path":
            other_src = str(check.get("other_source", "summary"))
            other_path = str(check.get("other_path", ""))
            left = _get_path(_source_data(ctx, source), path)
            right = _get_path(_source_data(ctx, other_src), other_path)
            op = "ne"
        ok = _eval_simple_op(op, left, right)
        detail = f"{source}.{path}={left!r} {op} {right!r}"
        return ok, detail

    if check_type == "composite":
        op = str(check.get("op", "and")).lower()
        conditions = check.get("conditions") or []
        results: list[tuple[bool, str]] = []
        for sub in conditions:
            if not isinstance(sub, dict):
                continue
            results.append(_eval_check(sub, ctx, thresholds))
        if op == "or":
            ok = any(r[0] for r in results) if results else False
        elif op == "not":
            ok = not results[0][0] if results else False
        else:
            ok = all(r[0] for r in results) if results else False
        detail = "; ".join(f"{'✓' if r[0] else '✗'} {r[1]}" for r in results)
        return ok, detail

    if check_type == "tag_status_in":
        source = str(check.get("source") or "game_precondition")
        tag_id = str(check.get("tag_id", ""))
        statuses = [str(s) for s in (check.get("statuses") or [])]
        data = _source_data(ctx, source)
        tag = _find_tag(_get_path(data, "test_conditions.tags"), tag_id)
        if not tag:
            return False, f"tag {tag_id} not found"
        status = str(tag.get("status", ""))
        ok = status in statuses
        return ok, f"{tag_id} status={status}"

    if check_type == "tag_value":
        source = str(check.get("source") or "game_precondition")
        tag_id = str(check.get("tag_id", ""))
        values = [str(v) for v in (check.get("values") or [])]
        data = _source_data(ctx, source)
        tag = _find_tag(_get_path(data, "test_conditions.tags"), tag_id)
        if not tag:
            return False, f"tag {tag_id} not found"
        val = str(tag.get("value", ""))
        ok = val in values or any(v in val for v in values)
        return ok, f"{tag_id} value={val}"

    if check_type == "tag_scenario":
        source = str(check.get("source") or "game_precondition")
        scenario = str(check.get("scenario_network") or ctx.get("report_meta", {}).get("expected_network", "wifi"))
        tag_id = str(check.get("tag_id", ""))
        bad_values = [str(v) for v in (check.get("bad_values") or [])]
        data = _source_data(ctx, source)
        tags = _get_path(data, "test_conditions.tags")
        net_tag = _find_tag(tags, scenario if scenario in ("wifi", "data") else "wifi")
        bad_tag = _find_tag(tags, tag_id)
        if not bad_tag:
            return False, f"tag {tag_id} not found"
        if net_tag and str(net_tag.get("value", "")).upper() not in ("ON", "开启"):
            return False, f"scenario {scenario} not active"
        val = str(bad_tag.get("value", ""))
        ok = val in bad_values
        return ok, f"{scenario}场景下 {tag_id}={val}"

    if check_type == "evidence_keyword":
        keywords = [str(k) for k in (check.get("keywords") or [])]
        min_hits = int(check.get("min_hits", 1))
        source = str(check.get("source") or "")
        texts: list[str] = []
        if source:
            _collect_evidence_text(_source_data(ctx, source), texts)
        else:
            for key, val in ctx.items():
                if key.startswith("game_") or key == "summary":
                    _collect_evidence_text(val, texts)
        blob = "\n".join(texts)
        matched = [kw for kw in keywords if kw in blob]
        ok = len(matched) >= min_hits
        # 取第一条同时含命中关键词的证据行，供报告精简展示
        sample = ""
        if matched:
            for line in texts:
                if any(kw in line for kw in matched):
                    sample = line.strip()
                    break
        if ok:
            detail = f"命中关键词：{'、'.join(matched[:5])}"
            if sample:
                detail = f"{detail} || {sample[:360]}"
        else:
            detail = f"keyword hits=0 keywords={keywords[:3]}"
        return ok, detail

    if check_type == "meta_delta_gte":
        meta = ctx.get("report_meta") or {}
        meta_key = str(check.get("meta_key", ""))
        threshold = float(_resolve_threshold(check, thresholds, key="threshold") or 0)
        raw = meta.get(meta_key)
        if raw is None:
            return False, f"report_meta.{meta_key} missing"
        try:
            delta = abs(float(raw))
        except (TypeError, ValueError):
            return False, f"report_meta.{meta_key} invalid"
        ok = delta >= threshold
        return ok, f"|{meta_key}|={delta}mA >= {threshold}mA"

    if check_type == "requires_meta":
        meta = ctx.get("report_meta") or {}
        meta_key = str(check.get("meta_key", ""))
        expect = check.get("meta_value", True)
        ok = meta.get(meta_key) == expect
        return ok, f"report_meta.{meta_key}={meta.get(meta_key)!r}"

    return False, f"unknown check_type {check_type}"


def _eval_rule(rule: dict[str, Any], ctx: dict[str, Any], thresholds: dict[str, Any]) -> dict[str, Any]:
    triggered, detail = _eval_check(rule, ctx, thresholds)
    return {
        "id": rule.get("id", ""),
        "category_id": rule.get("_category_id", ""),
        "category_title": rule.get("_category_title", ""),
        "subcategory": rule.get("subcategory", ""),
        "label": rule.get("label", ""),
        "priority": rule.get("priority", "P2"),
        "triggered": triggered,
        "detail": detail,
        "confidence": "high" if triggered and "missing" not in detail else ("medium" if triggered else "low"),
    }


def load_judgment_rules(ref_dir: Path | None = None) -> dict[str, Any]:
    ref = ref_dir or references_dir()
    return load_reference_yaml(ref, "cause-judgment-rules.yaml")


def load_report_defaults(ref_dir: Path | None = None) -> dict[str, Any]:
    ref = ref_dir or references_dir()
    return load_reference_yaml(ref, "report-defaults.yaml")


def _synthesize_summary(ctx: dict[str, Any]) -> dict[str, Any]:
    tw = ctx.get("game_time_window") or {}
    pre = ctx.get("game_precondition") or {}
    gw = tw.get("game_window") or pre.get("game_window") or {}
    return {
        "status": tw.get("status", "partial"),
        "blocked_reason": tw.get("blocked_reason", ""),
        "game_window": gw,
        "test_conditions": pre.get("test_conditions") or {},
        "missing_logs": [],
        "analysis_meta": {
            "game_package": gw.get("package", ""),
            "build_version": "",
            "soc_model": "",
            "device_model": "",
        },
        "comparison_outputs": {
            "brightness_stats": (ctx.get("game_brightness") or {}),
            "brightness_findings": brightness_findings_summary(ctx),
            "volume_findings": volume_findings_summary(ctx),
            "volume_stats": (ctx.get("game_volume") or {}),
            "frame_rate_stats": (ctx.get("game_brightness") or {}).get("refresh_rate", {}),
            "cpu_frequency_stats": {},
        },
        "abnormal_processes": (ctx.get("game_kernel_cpu") or {}).get("abnormal_processes", []),
        "top_background_packages": (ctx.get("game_background") or {}).get("top_background_packages", []),
    }


def _enrich_log_inventory(ctx: dict[str, Any]) -> None:
    """确保 summary / game_time_window 带有 log_inventory（兼容旧 JSON）。

    若 inventory 仍标记 bugreport 缺失，会按 log_path 向上重扫 ``bugreports/``。
    """
    try:
        from game_time_window_lib import (  # type: ignore
            build_log_inventory,
            _discover_bugreports_near,
        )
    except ImportError:
        gtw_scripts = Path(__file__).resolve().parents[2] / "game_time_window" / "scripts"
        if str(gtw_scripts) not in sys.path:
            sys.path.insert(0, str(gtw_scripts))
        try:
            from game_time_window_lib import (  # type: ignore
                build_log_inventory,
                _discover_bugreports_near,
            )
        except ImportError:
            return

    summary = ctx.get("summary")
    tw = ctx.get("game_time_window") or {}
    if not isinstance(summary, dict):
        return
    inv = summary.get("log_inventory")
    if not isinstance(inv, dict) or not inv:
        avail = summary.get("log_availability") or {}
        coverage = tw.get("log_coverage") if isinstance(tw, dict) else {}
        inv = build_log_inventory({}, log_coverage=coverage or {}, log_availability=avail)
        # 兼容旧 missing_logs：若 inventory 为空且有 missing_logs，映射到 optional/核心
        old_missing = summary.get("missing_logs") or []
        if isinstance(old_missing, list) and old_missing and not inv.get("missing_for_report"):
            core = set(inv.get("mobile_core_keys") or [])
            inv["mobile_core_missing"] = [x for x in old_missing if x in core]
            inv["optional_missing"] = [x for x in old_missing if x not in core and x != "bugreport"]
            inv["missing_for_report"] = list(inv["mobile_core_missing"])
            inv["incomplete"] = bool(inv["missing_for_report"])
            inv["no_logs"] = False
        summary["log_inventory"] = inv

    # 旧分析结果常因只扫 APLog 而漏检 <SN>/bugreports；加载时补扫
    inv = dict(summary.get("log_inventory") or {})
    bug_missing = (
        not inv.get("bugreport_present")
        or str(inv.get("bugreport") or "").lower() == "missing"
        or "bugreport" in [str(x).lower() for x in (inv.get("missing_for_report") or [])]
    )
    if bug_missing:
        log_path_raw = (
            summary.get("log_path")
            or (tw.get("log_path") if isinstance(tw, dict) else None)
            or ""
        )
        if log_path_raw:
            try:
                found = _discover_bugreports_near(Path(str(log_path_raw)))
            except OSError:
                found = []
            if found:
                inv["bugreport"] = "ok"
                inv["bugreport_present"] = True
                inv["bugreport_files"] = [str(p) for p in found[:8]]
                miss = [
                    x
                    for x in (inv.get("missing_for_report") or [])
                    if str(x).lower() != "bugreport"
                ]
                inv["missing_for_report"] = miss
                inv["incomplete"] = bool(inv.get("mobile_core_missing") or miss)
                summary["log_inventory"] = inv
                old_miss = summary.get("missing_logs")
                if isinstance(old_miss, list):
                    summary["missing_logs"] = [
                        x for x in old_miss if str(x).lower() != "bugreport"
                    ]
                avail = dict(summary.get("log_availability") or {})
                avail["bugreport"] = "ok"
                summary["log_availability"] = avail

    if isinstance(tw, dict) and not isinstance(tw.get("log_inventory"), dict):
        tw["log_inventory"] = build_log_inventory(
            {},
            log_coverage=tw.get("log_coverage") or {},
            log_availability=summary.get("log_availability") or {},
        )
        # 合并 scene_coverage_missing
        if inv.get("scene_coverage_missing") is None or inv.get("scene_coverage_missing") == []:
            scene_miss = (tw.get("log_inventory") or {}).get("scene_coverage_missing") or []
            if scene_miss:
                inv = dict(summary.get("log_inventory") or {})
                inv["scene_coverage_missing"] = scene_miss
                summary["log_inventory"] = inv
        ctx["game_time_window"] = tw
    elif isinstance(tw, dict) and isinstance(summary.get("log_inventory"), dict):
        tw["log_inventory"] = dict(summary["log_inventory"])
        ctx["game_time_window"] = tw


_JIRA_BROWSE_BASE = "http://jira.transsion.com/browse/"
_JIRA_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]+-\d+$")


def _find_jira_workspace_root(start: Path) -> Path | None:
    """从 analysis 目录向上查找含 jira_info.json / analysis/jira_*.json 的工作区根。"""
    cur = start.resolve()
    for p in [cur, *cur.parents]:
        if (p / "jira_info.json").is_file():
            return p
        if (p / "analysis" / "jira_analysis_summary.json").is_file():
            return p
        if (p / "analysis" / "jira_testcase_parse.json").is_file():
            return p
        # 避免爬得过深
        if p.parent == p:
            break
        # 常见边界：temp 根或盘符根
        if p.name.lower() in {"temp", "users", "windows"}:
            break
    return None


def _enrich_report_meta_from_jira_workspace(analysis_dir: Path, rm: dict[str, Any]) -> None:
    """从 JIRA 工作区产物补齐单号 / 标题要素 / 链接。"""
    ws = _find_jira_workspace_root(analysis_dir)
    if ws is None:
        return

    def _fill(key: str, value: Any) -> None:
        if rm.get(key) in (None, "", "xxxxxxxx", "#") and value not in (None, ""):
            rm[key] = value

    # 1) jira_info.json
    info_path = ws / "jira_info.json"
    if info_path.is_file():
        try:
            info = json.loads(info_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            info = {}
        if isinstance(info, dict):
            key = str(info.get("key") or "").strip()
            if _JIRA_KEY_RE.match(key):
                _fill("jira_key", key)
            _fill("device_model", info.get("affect_project"))

    # 2) analysis/jira_analysis_summary.json
    summary_path = ws / "analysis" / "jira_analysis_summary.json"
    if summary_path.is_file():
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            summary = {}
        if isinstance(summary, dict):
            key = str(summary.get("jira_key") or "").strip()
            if _JIRA_KEY_RE.match(key):
                _fill("jira_key", key)

    # 3) analysis/jira_testcase_parse.json → 场景 / 游戏 / 外放等标题要素
    parse_path = ws / "analysis" / "jira_testcase_parse.json"
    if parse_path.is_file():
        try:
            parsed = json.loads(parse_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            parsed = {}
        if isinstance(parsed, dict):
            key = str(parsed.get("jira_key") or "").strip()
            if _JIRA_KEY_RE.match(key):
                _fill("jira_key", key)
            derived = parsed.get("derived") if isinstance(parsed.get("derived"), dict) else {}
            if derived.get("test_case") == "nps":
                _fill("test_case", "nps")
                _fill("test_case_label", "NPS场景")
            else:
                _fill("test_case", derived.get("test_case"))
                case = str(derived.get("test_case") or "").strip()
                if case and not rm.get("test_case_label"):
                    _fill("test_case_label", case)
            _fill("game_title", derived.get("game_title"))
            _fill("speaker_mode", derived.get("speaker_mode"))
            _fill("device_model", derived.get("dut_model"))
            # JIRA 前置条件：亮度/音量/刷新率（max → 测试条件左侧「要求」文案）
            _fill("jira_brightness", derived.get("brightness"))
            _fill("jira_volume", derived.get("volume"))
            _fill("jira_refresh_rate", derived.get("refresh_rate"))
            if str(derived.get("brightness") or "").strip().lower() == "max":
                _fill("brightness_requirement", "最大亮度")
            if str(derived.get("volume") or "").strip().lower() == "max":
                _fill("volume_requirement", "最大音量")
            if str(derived.get("refresh_rate") or "").strip().lower() == "max":
                _fill("refresh_rate_requirement", "最高档位")
            net = derived.get("network") if isinstance(derived.get("network"), dict) else {}
            if net:
                if rm.get("jira_network") in (None, "", {}):
                    rm["jira_network"] = dict(net)
                _fill("jira_carrier", net.get("carrier"))
                _fill("jira_sim_slot", net.get("sim_slot"))
                if rm.get("jira_mobile_data") is None and net.get("mobile_data") is not None:
                    rm["jira_mobile_data"] = net.get("mobile_data")
            # 无 derived.network.sim_slot 时，从 precondition 原文再补一次
            if rm.get("jira_sim_slot") in (None, "") or not rm.get("jira_carrier"):
                pre_lines = ((parsed.get("sections") or {}).get("precondition") or [])
                pre_blob = "\n".join(str(x) for x in pre_lines)
                if not rm.get("jira_carrier"):
                    m_car = re.search(r"(联通|移动|电信)", pre_blob)
                    if m_car:
                        rm["jira_carrier"] = m_car.group(1)
                if rm.get("jira_sim_slot") in (None, ""):
                    m_slot = re.search(r"卡槽\s*([12])|卡\s*([12])\s*(?:插入|放|装)", pre_blob)
                    if m_slot:
                        rm["jira_sim_slot"] = int(m_slot.group(1) or m_slot.group(2))
                    elif re.search(r"插入.*(?:联通|移动|电信)|(?:联通|移动|电信).*插入", pre_blob):
                        rm["jira_sim_slot"] = 1
                if rm.get("jira_mobile_data") is None:
                    if re.search(r"关闭数据流量|关闭流量", pre_blob):
                        rm["jira_mobile_data"] = False
                    elif re.search(r"开启数据流量|打开数据流量|开启流量", pre_blob):
                        rm["jira_mobile_data"] = True

    # 4) 路径名兜底：.../CN6OS16-2121/...
    if rm.get("jira_key") in (None, "", "xxxxxxxx"):
        for p in [analysis_dir, *analysis_dir.resolve().parents]:
            name = p.name.strip()
            if _JIRA_KEY_RE.match(name):
                rm["jira_key"] = name
                break
            if p.parent == p:
                break

    key = str(rm.get("jira_key") or "").strip()
    if _JIRA_KEY_RE.match(key) and rm.get("issue_url") in (None, "", "#"):
        rm["issue_url"] = f"{_JIRA_BROWSE_BASE}{key}"


def load_analysis_bundle(analysis_dir: Path, report_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    analysis_dir = analysis_dir.resolve()
    # 与调用方共享同一 dict，保证 jira_key 等补齐能回流到 render
    rm = report_meta if isinstance(report_meta, dict) else {}
    ctx: dict[str, Any] = {
        "report_meta": rm,
        "analysis_dir": str(analysis_dir),
        "log_path": str(analysis_dir.parent if analysis_dir.name == "analysis" else analysis_dir),
    }
    for name in _STEP_JSON_NAMES:
        path = analysis_dir / f"{name}.json"
        if path.is_file():
            ctx[name] = json.loads(path.read_text(encoding="utf-8"))
    # 抓包 JSON 可能落在 workspace analysis/game_network_cap_<机型>.json
    if "game_network_cap" not in ctx:
        labeled = _find_labeled_network_cap(analysis_dir, rm)
        if labeled is not None:
            ctx["game_network_cap"] = labeled
    summary_path = analysis_dir / "game_power_compare_summary.json"
    if summary_path.is_file():
        ctx["summary"] = json.loads(summary_path.read_text(encoding="utf-8"))
    else:
        ctx["summary"] = _synthesize_summary(ctx)
    _enrich_log_inventory(ctx)
    meta_path = analysis_dir / "game_analysis_meta.json"
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if isinstance(meta, dict):
                ctx["game_analysis_meta"] = meta
                # 补齐 report_meta 中缺失的项目/用例/音量档
                for key in (
                    "project",
                    "test_case",
                    "test_case_label",
                    "game_title",
                    "expected_scene",
                    "volume_index",
                    "brightness_level",
                    "brightness_nits",
                    "jira_key",
                    "issue_url",
                    "speaker_mode",
                ):
                    if rm.get(key) in (None, "", "xxxxxxxx", "#") and meta.get(key) not in (None, ""):
                        rm[key] = meta[key]
        except (OSError, json.JSONDecodeError):
            pass
    _enrich_report_meta_from_jira_workspace(analysis_dir, rm)
    # 若仅有单号、无链接，补默认 JIRA browse 链接
    key = str(rm.get("jira_key") or "").strip()
    if _JIRA_KEY_RE.match(key) and rm.get("issue_url") in (None, "", "#"):
        rm["issue_url"] = f"{_JIRA_BROWSE_BASE}{key}"
    return ctx


def judge_root_causes(
    ctx: dict[str, Any],
    rules_doc: dict[str, Any] | None = None,
) -> dict[str, Any]:
    doc = rules_doc or load_judgment_rules()
    thresholds = dict(doc.get("thresholds") or {})
    categories_cfg = doc.get("categories") or {}

    all_rules: list[dict[str, Any]] = []
    for cat_id, cat_body in sorted(
        categories_cfg.items(),
        key=lambda x: int((x[1] or {}).get("order", 99)),
    ):
        if not isinstance(cat_body, dict):
            continue
        patterns = cat_body.get("patterns") or []
        for pat in patterns:
            if not isinstance(pat, dict):
                continue
            enriched = dict(pat)
            enriched["_category_id"] = cat_id
            enriched["_category_title"] = cat_body.get("title", cat_id)
            all_rules.append(enriched)

    findings = [_eval_rule(rule, ctx, thresholds) for rule in all_rules]
    triggered = [f for f in findings if f["triggered"]]

    by_category: dict[str, dict[str, Any]] = {}
    for cat_id, cat_body in categories_cfg.items():
        if not isinstance(cat_body, dict):
            continue
        cat_findings = [f for f in findings if f["category_id"] == cat_id]
        cat_triggered = [f for f in cat_findings if f["triggered"]]
        by_category[cat_id] = {
            "order": cat_body.get("order"),
            "title": cat_body.get("title", cat_id),
            "triggered_count": len(cat_triggered),
            "findings": cat_findings,
            "triggered": cat_triggered,
        }

    primary = sorted(triggered, key=lambda f: (f["priority"], f["category_id"]))[:5]

    return {
        "skill": "game_root_cause",
        "status": "ok",
        "analysis_time": datetime.now().isoformat(timespec="seconds"),
        "summary_status": _get_path(ctx.get("summary"), "status"),
        "triggered_count": len(triggered),
        "total_rules": len(findings),
        "primary_causes": primary,
        "categories": by_category,
        "findings": findings,
        "thresholds": thresholds,
    }


def _tag_display(ctx: dict[str, Any], tag_id: str, default: str = "—") -> str:
    pre = ctx.get("game_precondition") or {}
    tags = _get_path(pre, "test_conditions.tags") or _get_path(ctx.get("summary"), "test_conditions.tags")
    tag = _find_tag(tags, tag_id)
    if not tag:
        return default
    return str(tag.get("value") or tag.get("label") or default)


def _tag_standard(ctx: dict[str, Any], tag_id: str, default: str = "—") -> str:
    pre = ctx.get("game_precondition") or {}
    tags = _get_path(pre, "test_conditions.tags") or _get_path(ctx.get("summary"), "test_conditions.tags")
    tag = _find_tag(tags, tag_id)
    if not tag:
        return default
    std = tag.get("standard")
    if std is None or str(std).strip() == "":
        return default
    return str(std)


# 未检测到 / 空值在报告中统一显示为短线「—」
_MISSING_DISPLAY = "—"
_MISSING_TOKENS = frozenset(
    {
        "",
        "—",
        "-",
        "–",
        "未检测到",
        "未识别",
        "无",
        "无数据",
        "None",
        "none",
        "null",
        "N/A",
        "n/a",
    }
)


def _is_missing_display(val: Any) -> bool:
    return str(val or "").strip() in _MISSING_TOKENS


def _display_or_none(val: Any, *, fallback: str = _MISSING_DISPLAY) -> str:
    """有值则原样返回，未检测到/空则显示短线。"""
    s = str(val or "").strip()
    if _is_missing_display(s):
        return fallback
    return s


def _scene_actual_display(ctx: dict[str, Any]) -> str:
    tw = ctx.get("game_time_window") or {}
    name = str(tw.get("game_name") or "").strip()
    if name:
        return name
    gw = tw.get("game_window") or {}
    pkg = str(tw.get("game_package") or gw.get("package") or "").strip()
    return pkg or _MISSING_DISPLAY


def _scene_scenario_name(ctx: dict[str, Any]) -> str:
    """测试场景名称：优先预设/JIRA 导入（test_case_label）。"""
    meta = ctx.get("report_meta") or {}
    gmeta = ctx.get("game_analysis_meta") or {}
    pre = ctx.get("game_precondition") or {}
    scenario = ((pre.get("test_conditions") or {}).get("scenario") or {})
    for src in (
        meta.get("test_case_label"),
        gmeta.get("test_case_label"),
        scenario.get("label"),
        meta.get("test_case"),
        gmeta.get("test_case"),
        scenario.get("id"),
    ):
        text = str(src or "").strip()
        if text:
            return text
    return "测试场景"


def _scene_expected_game_name(ctx: dict[str, Any]) -> str:
    """游戏名：优先预设/JIRA 导入，其次日志识别结果。"""
    meta = ctx.get("report_meta") or {}
    gmeta = ctx.get("game_analysis_meta") or {}
    for src in (
        meta.get("game_title"),
        meta.get("expected_scene"),
        gmeta.get("game_title"),
        gmeta.get("expected_scene"),
    ):
        text = str(src or "").strip()
        if text and not _is_missing_display(text):
            return text
    detected = _scene_actual_display(ctx)
    return detected if not _is_missing_display(detected) else "—"


def _scene_yes_no(ctx: dict[str, Any], *, expected_game: str) -> tuple[str, str]:
    """机型是否识别到对应游戏场景：返回 (是/否, css class)。"""
    actual = _scene_actual_display(ctx)
    if _is_missing_display(actual):
        return "否", "bad"
    exp = str(expected_game or "").strip()
    if not exp or _is_missing_display(exp):
        return "是", "ok"
    a = actual.casefold()
    e = exp.casefold()
    if e in a or a in e:
        return "是", "ok"
    # 允许简写匹配，如 PUBG vs PUBG Mobile
    token = e.split()[0] if e.split() else e
    if token and token in a:
        return "是", "ok"
    return "否", "bad"


def _background_actual_display(ctx: dict[str, Any]) -> str:
    bg = ctx.get("game_background") or {}
    summary = bg.get("background_summary") or {}
    during = summary.get("during_game") if isinstance(summary, dict) else {}
    suspicious = None
    if isinstance(during, dict) and during.get("suspicious_packages") is not None:
        try:
            suspicious = int(during.get("suspicious_packages"))
        except (TypeError, ValueError):
            suspicious = None
    tops = bg.get("top_background_packages") or []
    names: list[str] = []
    for row in tops[:2]:
        if isinstance(row, dict):
            n = str(row.get("package_or_process") or row.get("package") or "").strip()
            if n:
                names.append(n)
    inv = bg.get("background_investigation") or {}
    step1 = inv.get("step1_process_autostart") if isinstance(inv, dict) else {}
    alive = (step1 or {}).get("still_alive_without_die") or []
    if suspicious and suspicious > 0:
        suffix = "、".join(names)
        if suffix:
            return f"{suspicious}个可疑（{suffix}）"
        return f"{suspicious}个可疑后台"
    if isinstance(alive, list) and alive:
        pkgs = [
            str(a.get("package") or "").strip()
            for a in alive[:3]
            if isinstance(a, dict) and a.get("package")
        ]
        if pkgs:
            return "存活: " + "、".join(pkgs)
    if names:
        return "活动: " + "、".join(names)
    return "未见明显异常"


def _pre_test_brightness_volume_display(ctx: dict[str, Any]) -> str | None:
    """测试条件「亮度/音量」：测试前亮度等级 / STREAM_MUSIC 末值档位，如 140/9（随日志变化）。"""
    bf = brightness_findings_summary(ctx)
    vf = volume_findings_summary(ctx)
    level = (bf.get("pre_game_setting") or {}).get("brightness_level")
    vol_idx = (vf.get("pre_test_setting") or {}).get("index")
    gv = ctx.get("game_volume") or {}
    if level is None:
        stats = _get_path(ctx.get("summary"), "comparison_outputs.brightness_stats") or {}
        ba = stats.get("brightness_analysis") or {}
        pg = ba.get("pre_game_setting") or stats.get("baseline_before_game") or {}
        if pg.get("brightness_level") is not None:
            level = int(pg["brightness_level"])
        elif pg.get("level") is not None:
            level = int(pg["level"])
    if vol_idx is None:
        base = (gv.get("pre_test_volume") or {}).get("baseline") or {}
        if base.get("index") is not None:
            vol_idx = int(base["index"])
        else:
            vstats = _get_path(ctx.get("summary"), "comparison_outputs.volume_stats") or {}
            base2 = vstats.get("baseline_before_game") or {}
            if base2.get("index") is not None:
                vol_idx = int(base2["index"])
    if level is None and vol_idx is None:
        return None
    left = str(level) if level is not None else "—"
    right = str(vol_idx) if vol_idx is not None else "—"
    return f"{left}/{right}"


_ON_OFF_TAG_IDS = frozenset({
    "auto_brightness",
    "bt",
    "airplane",
    "nfc",
    "gps",
    "data",
    "logger",
    "gesture_nav",
    "auto_rotate",
})


def _on_off_zh(val: str) -> str:
    v = str(val).strip().upper()
    if v in ("ON", "TRUE", "1", "开启", "开"):
        return "开"
    if v in ("OFF", "FALSE", "0", "关闭", "关"):
        return "关"
    return str(val)


def _rat_display_label(rat: str) -> str:
    u = str(rat).upper()
    if "NR" in u or u == "5G":
        return "5G"
    if "LTE" in u or "4G" in u:
        return "4G"
    if "WCDMA" in u or "3G" in u or "UMTS" in u:
        return "3G"
    if "EDGE" in u or "GPRS" in u or "2G" in u:
        return "2G"
    return str(rat)


def _operator_from_rf(rf: dict[str, Any]) -> str:
    gw = rf.get("game_window") or {}
    ops: list[str] = list(gw.get("operator_samples") or [])
    if ops:
        return ops[-1]
    for line in rf.get("raw_evidence") or []:
        for key in ("mOperatorAlphaLong=", "mOperatorAlphaShort="):
            m = re.search(rf"{re.escape(key)}([^,}}]+)", str(line))
            if not m:
                continue
            op = m.group(1).strip()
            if op and op.lower() not in ("null", "none", ""):
                return op
    return ""


def _network_cond_display(ctx: dict[str, Any]) -> str:
    net = ctx.get("game_network") or {}
    rf = net.get("rf_stats") or {}
    ntype = str(rf.get("network_type") or "").lower()
    gw = rf.get("game_window") or {}
    rats: list[str] = list(gw.get("cell_rat_samples") or [])

    if ntype == "wifi":
        return "WiFi"
    if ntype == "cellular" or rats:
        rat = _rat_display_label(rats[-1] if rats else "")
        op = _operator_from_rf(rf)
        label = f"数据 {rat}" if rat else "数据网络"
        return f"{label} · {op}" if op else label

    wifi_v = _tag_display(ctx, "wifi", "")
    data_v = _tag_display(ctx, "data", "")
    if wifi_v == "ON" and data_v != "ON":
        return "WiFi"
    if data_v == "ON":
        return "数据网络"
    if wifi_v == "ON":
        return "WiFi"
    if wifi_v and not _is_missing_display(wifi_v):
        return wifi_v
    if data_v and not _is_missing_display(data_v):
        return data_v
    return _MISSING_DISPLAY


def _brightness_setting_from_ctx(ctx: dict[str, Any]) -> dict[str, Any]:
    """从 game_precondition / game_brightness 取项目×用例亮度设定。"""
    pre = ctx.get("game_precondition") or {}
    tc = pre.get("test_conditions") or {}
    setting = dict(tc.get("brightness_volume_setting") or {})
    scenario = dict(tc.get("scenario") or {})
    tag = _find_tag(tc.get("tags"), "brightness") or {}
    gb = ctx.get("game_brightness") or {}
    inv = gb.get("brightness_investigation") or {}
    s1 = inv.get("step1_test_setting") or {}
    setting_from_inv = inv.get("brightness_volume_setting") or {}
    if setting_from_inv and not setting:
        setting = dict(setting_from_inv)

    compare_mode = str(
        tag.get("compare_mode")
        or setting.get("compare_mode")
        or s1.get("compare_mode")
        or scenario.get("compare_mode")
        or "level"
    )
    expected_level = (
        tag.get("expected_level")
        if tag.get("expected_level") is not None
        else setting.get("brightness_level")
        if setting.get("brightness_level") is not None
        else s1.get("expected_level")
        if s1.get("expected_level") is not None
        else scenario.get("target_brightness_level")
    )
    expected_nits = (
        tag.get("expected_nits")
        if tag.get("expected_nits") is not None
        else setting.get("brightness_nits")
        if setting.get("brightness_nits") is not None
        else s1.get("expected_nits")
        if s1.get("expected_nits") is not None
        else scenario.get("target_brightness_nits")
    )
    measured_level = tag.get("numeric_level")
    if measured_level is None:
        measured_level = s1.get("brightness_level")
    measured_nits = tag.get("numeric_nits")
    if measured_nits is None:
        measured_nits = s1.get("measured_nits")
    measured_curve = tag.get("numeric_curve")
    if measured_curve is None:
        measured_curve = s1.get("hwc_curve_val")

    return {
        "compare_mode": compare_mode,
        "project": tag.get("project") or setting.get("project") or s1.get("project") or scenario.get("project"),
        "test_case": tag.get("test_case") or setting.get("test_case") or s1.get("test_case") or scenario.get("id"),
        "test_case_label": setting.get("test_case_label") or s1.get("test_case_label") or scenario.get("label"),
        "expected_level": expected_level,
        "expected_nits": expected_nits,
        "measured_level": measured_level,
        "measured_curve": measured_curve,
        "measured_nits": measured_nits,
        "align_metric": s1.get("align_metric") or tag.get("align_metric"),
        "aligned": s1.get("aligned_with_standard") if "aligned_with_standard" in s1 else tag.get("status"),
        "status": tag.get("status"),
        "standard": tag.get("standard") or "",
    }


def _brightness_actual_display(ctx: dict[str, Any]) -> str:
    info = _brightness_setting_from_ctx(ctx)
    # 最大亮度展示优先级：level → 曲线 → nits
    if info.get("compare_mode") == "nits":
        level = info.get("measured_level")
        if level is not None:
            return str(level)
        curve = info.get("measured_curve")
        if curve is not None:
            return f"curve={curve}"
        nits = info.get("measured_nits")
        if nits is not None:
            try:
                return f"{float(nits):g}nit"
            except (TypeError, ValueError):
                return f"{nits}nit"
        val = _tag_display(ctx, "brightness", "")
        if val and not _is_missing_display(val):
            return val
        return _MISSING_DISPLAY

    pair = _pre_test_brightness_volume_display(ctx)
    if pair and "/" in pair:
        left = pair.split("/", 1)[0].strip()
        if left and not _is_missing_display(left):
            return left
    level = info.get("measured_level")
    if level is not None:
        return str(level)
    val = _tag_display(ctx, "brightness", "")
    if val and not _is_missing_display(val):
        return val
    return _MISSING_DISPLAY


def _brightness_required_display(ctx: dict[str, Any], cfg: dict[str, Any] | None = None) -> str:
    meta = ctx.get("report_meta") or {}
    info = _brightness_setting_from_ctx(ctx)
    # 优先 JIRA：屏幕亮度调至最大 → 只显示「最大亮度」，不拼 level=255
    if _is_max_requirement(meta.get("brightness_requirement") or meta.get("jira_brightness")):
        return "最大亮度"
    if str(info.get("test_case") or meta.get("test_case") or "").strip().lower() == "nps":
        return "最大亮度"
    if info.get("compare_mode") == "nits":
        return "最大亮度"
    level = info.get("expected_level")
    try:
        if level is not None and int(level) >= 255:
            return "最大亮度"
    except (TypeError, ValueError):
        pass
    if level is not None:
        return str(level)
    std = info.get("standard") or _tag_standard(ctx, "brightness", "")
    if std:
        if _is_max_requirement(std) or "最大亮度" in str(std):
            return "最大亮度"
        m = re.search(r"level\s*=\s*(\d+)", str(std), re.IGNORECASE)
        if m:
            try:
                if int(m.group(1)) >= 255:
                    return "最大亮度"
            except ValueError:
                pass
            return m.group(1)
        if "未匹配" not in str(std) and "查表" not in str(std):
            return str(std)
    return str((cfg or {}).get("standard") or "按项目查表")


def _is_max_requirement(value: Any) -> bool:
    """JIRA/用例要求是否为「最大/最高」。"""
    s = str(value or "").strip().lower()
    if not s:
        return False
    if s in ("max", "maximum", "最高", "最大", "满", "full"):
        return True
    return any(k in str(value or "") for k in ("最大", "最高", "满量程", "max"))


def _volume_setting_from_ctx(ctx: dict[str, Any]) -> dict[str, Any]:
    """从 game_precondition / meta 取项目×用例音量设定。"""
    pre = ctx.get("game_precondition") or {}
    tc = pre.get("test_conditions") or {}
    setting = dict(tc.get("brightness_volume_setting") or {})
    scenario = dict(tc.get("scenario") or {})
    tag = _find_tag(tc.get("tags"), "volume") or {}
    meta = ctx.get("report_meta") or {}
    analysis_meta = ctx.get("game_analysis_meta") or {}
    expected = (
        tag.get("expected_volume_index")
        if tag.get("expected_volume_index") is not None
        else setting.get("volume_index")
        if setting.get("volume_index") is not None
        else scenario.get("target_volume_index")
        if scenario.get("target_volume_index") is not None
        else analysis_meta.get("volume_index")
        if analysis_meta.get("volume_index") is not None
        else meta.get("volume_index")
    )
    measured = tag.get("numeric_volume_index")
    if measured is None:
        measured = (volume_findings_summary(ctx).get("pre_test_setting") or {}).get("index")
    return {
        "project": tag.get("project") or setting.get("project") or scenario.get("project") or analysis_meta.get("project"),
        "test_case": tag.get("test_case") or setting.get("test_case") or scenario.get("id") or analysis_meta.get("test_case") or meta.get("test_case"),
        "expected_volume_index": expected,
        "measured_volume_index": measured,
        "status": tag.get("status"),
        "standard": tag.get("standard") or "",
    }


def _volume_required_display(ctx: dict[str, Any], cfg: dict[str, Any] | None = None) -> str:
    meta = ctx.get("report_meta") or {}
    info = _volume_setting_from_ctx(ctx)
    # 优先 JIRA：音量等级调至最大 → 「最大音量」，不用「按项目查表」
    if _is_max_requirement(meta.get("volume_requirement") or meta.get("jira_volume")):
        return "最大音量"
    if str(info.get("test_case") or meta.get("test_case") or "").strip().lower() == "nps":
        return "最大音量"
    expected = info.get("expected_volume_index")
    if expected is not None:
        return str(expected)
    std = info.get("standard") or _tag_standard(ctx, "volume", "")
    if std:
        if _is_max_requirement(std) or "最大音量" in str(std):
            return "最大音量"
        m = re.search(r"(?:volume_index|目标)\s*[=:：]?\s*(\d+)", str(std), re.IGNORECASE)
        if m:
            return m.group(1)
        if re.fullmatch(r"\d+", str(std).strip()):
            return str(std).strip()
        if "未匹配" not in str(std) and "查表" not in str(std):
            return str(std)
    return str((cfg or {}).get("standard") or "按项目查表")


def _refresh_rate_required_display(ctx: dict[str, Any], cfg: dict[str, Any] | None = None) -> str:
    """刷新率要求：JIRA「调整到项目支持的最高档位」→ 最高档位。"""
    meta = ctx.get("report_meta") or {}
    if _is_max_requirement(meta.get("refresh_rate_requirement") or meta.get("jira_refresh_rate")):
        return "最高档位"
    if str(meta.get("test_case") or (ctx.get("game_analysis_meta") or {}).get("test_case") or "").strip().lower() == "nps":
        return "最高档位"
    std = _tag_standard(ctx, "refresh_rate", "")
    if std and not _is_missing_display(std):
        if _is_max_requirement(std) or "最高" in str(std) or "最大" in str(std):
            return "最高档位"
        return str(std)
    cfg_std = str((cfg or {}).get("standard") or "").strip()
    return cfg_std if cfg_std else "—"


def _volume_actual_display(ctx: dict[str, Any]) -> str:
    pair = _pre_test_brightness_volume_display(ctx)
    if pair and "/" in pair:
        right = pair.split("/", 1)[1].strip()
        if right and not _is_missing_display(right):
            return right
    info = _volume_setting_from_ctx(ctx)
    if info.get("measured_volume_index") is not None:
        return str(info["measured_volume_index"])
    vf = volume_findings_summary(ctx)
    idx = (vf.get("pre_test_setting") or {}).get("index")
    if idx is not None:
        return str(idx)
    val = _tag_display(ctx, "volume", "")
    if val and not _is_missing_display(val):
        if val in ("ON", "OFF"):
            return _on_off_zh(val)
        return val
    return _MISSING_DISPLAY


def _sim_data_part_display(ctx: dict[str, Any], tag_id: str, *, required: bool = False) -> str:
    raw = _tag_standard(ctx, tag_id, "") if required else _tag_display(ctx, tag_id, "")
    if not raw or _is_missing_display(raw):
        return _MISSING_DISPLAY if not required else "—"
    if tag_id == "data" or raw.upper() in ("ON", "OFF"):
        if _is_missing_display(raw):
            return _MISSING_DISPLAY if not required else "—"
        return _on_off_zh(raw)
    return raw


def _sim_data_actual_display(ctx: dict[str, Any]) -> str:
    # 与标签「SIM/数据」对齐：左侧 SIM，右侧数据
    sim_v = _sim_data_part_display(ctx, "sim", required=False)
    data_v = _sim_data_part_display(ctx, "data", required=False)
    return f"{sim_v}/{data_v}"


def _sim_data_required_display(ctx: dict[str, Any]) -> str:
    """JIRA：卡槽1插入1张联通数据卡，开启数据流量 → 卡1联通/开启。"""
    meta = ctx.get("report_meta") or {}
    net = meta.get("jira_network") if isinstance(meta.get("jira_network"), dict) else {}
    carrier = str(net.get("carrier") or meta.get("jira_carrier") or "").strip()
    if carrier in ("数据卡",):
        carrier = ""
    slot = net.get("sim_slot")
    if slot is None:
        slot = meta.get("jira_sim_slot")
    try:
        slot_i = int(slot) if slot is not None else None
    except (TypeError, ValueError):
        slot_i = None
    mobile_data = net.get("mobile_data")
    if mobile_data is None:
        mobile_data = meta.get("jira_mobile_data")

    if carrier or slot_i is not None or mobile_data is not None:
        slot_i = slot_i if slot_i in (1, 2) else 1
        data_txt = "关闭" if mobile_data is False else "开启"
        left = f"卡{slot_i}{carrier}" if carrier else f"卡{slot_i}"
        return f"{left}/{data_txt}"

    # 无 JIRA 信息时回退旧文案（顺序与 SIM/数据 对齐）
    sim_r = _sim_data_part_display(ctx, "sim", required=True)
    data_r = _sim_data_part_display(ctx, "data", required=True)
    if data_r == "—" and sim_r == "—":
        return "已插入/开"
    return f"{sim_r if sim_r != '—' else '已插入'}/{data_r if data_r != '—' else '开'}"


def _cond_display_value(ctx: dict[str, Any], tag_id: str) -> str:
    if tag_id == "scene":
        return _scene_actual_display(ctx)
    if tag_id == "background":
        return _background_actual_display(ctx)
    if tag_id == "brightness":
        return _brightness_actual_display(ctx)
    if tag_id == "volume":
        return _volume_actual_display(ctx)
    if tag_id == "sim_data":
        return _sim_data_actual_display(ctx)
    if tag_id == "wifi":
        return _network_cond_display(ctx)
    if tag_id in _ON_OFF_TAG_IDS:
        val = _tag_display(ctx, tag_id)
        if not _is_missing_display(val):
            return _on_off_zh(val)
        return _MISSING_DISPLAY
    val = _tag_display(ctx, tag_id)
    if val in ("ON", "OFF"):
        return _on_off_zh(val)
    return _display_or_none(val)


def _cond_required_display(
    ctx: dict[str, Any],
    tag_id: str,
    cfg: dict[str, Any] | None = None,
) -> str:
    cfg = cfg or {}
    if tag_id == "scene":
        meta = ctx.get("report_meta") or {}
        return str(
            meta.get("expected_scene")
            or cfg.get("standard")
            or meta.get("game_title")
            or "游戏前台稳定段"
        )
    if tag_id == "background":
        meta = ctx.get("report_meta") or {}
        return str(meta.get("expected_background") or cfg.get("standard") or "无异常后台")
    if tag_id == "brightness":
        return _brightness_required_display(ctx, cfg)
    if tag_id == "volume":
        return _volume_required_display(ctx, cfg)
    if tag_id == "refresh_rate":
        return _refresh_rate_required_display(ctx, cfg)
    if tag_id == "sim_data":
        return _sim_data_required_display(ctx)
    if tag_id == "wifi":
        meta = ctx.get("report_meta") or {}
        expected = str(meta.get("expected_network") or "wifi").strip().lower()
        if expected in ("wifi", "wi-fi", "wlan"):
            return "WIFI"
        if expected in ("data", "cellular", "mobile"):
            return "数据网络"
        return expected.upper() if expected else "WIFI"
    std = _tag_standard(ctx, tag_id, "")
    if not std:
        std = str(cfg.get("standard") or "")
    if not std:
        return "—"
    if tag_id in _ON_OFF_TAG_IDS or std.upper() in ("ON", "OFF"):
        return _on_off_zh(std)
    return std


def _media_row(label: str, text: str, *, muted: bool = False) -> str:
    color = "var(--color-text-tertiary)" if muted else "var(--color-text-primary)"
    return (
        f'<div style="display:flex;gap:8px;font-size:13px;margin-bottom:6px;">'
        f'<span style="color:var(--color-text-secondary);min-width:72px;">{label}</span>'
        f'<span style="color:{color};">{_esc(text)}</span></div>'
    )


def _format_brightness_media_block(ctx: dict[str, Any]) -> str:
    """测试手法内嵌：亮度三段摘要（含项目×用例对齐）。"""
    findings = brightness_findings_summary(ctx)
    info = _brightness_setting_from_ctx(ctx)
    if (
        findings.get("coverage") == "missing"
        and not info.get("measured_level")
        and not info.get("measured_curve")
        and not info.get("measured_nits")
    ):
        return ""
    pg = findings.get("pre_game_setting") or {}
    launch = findings.get("launch_window") or {}
    in_game = findings.get("in_game_changes") or {}

    rows: list[str] = []
    proj = info.get("project") or "—"
    case_label = info.get("test_case_label") or info.get("test_case") or "—"
    rows.append(_media_row("项目/用例", f"{proj} / {case_label}"))

    if info.get("compare_mode") == "nits":
        # 最大亮度：优先展示 level，其次曲线，最后 nits
        level = info.get("measured_level")
        curve = info.get("measured_curve")
        nits = info.get("measured_nits")
        bits: list[str] = []
        if level is not None:
            bits.append(f"等级 {level}/255")
        elif curve is not None:
            bits.append(f"曲线 {curve}/4095")
        if nits is not None:
            try:
                bits.append(f"{float(nits):g}nit")
            except (TypeError, ValueError):
                bits.append(f"{nits}nit")
        bits.append("目标最大亮度")
        align = info.get("aligned")
        align_s = "对齐" if align is True or align == "ok" else ("未对齐" if align is False or align == "bad" else "未知")
        bits.append(align_s)
        metric = info.get("align_metric")
        if metric:
            bits.append(f"判据={metric}")
        rows.append(_media_row("NPS亮度", " · ".join(bits) if bits else "—"))
    else:
        level = info.get("measured_level")
        if level is None:
            level = pg.get("brightness_level")
        expected = info.get("expected_level")
        curve = pg.get("curve_val")
        pre_txt: list[str] = []
        if level is not None:
            pre_txt.append(f"等级 {level}/255")
        if expected is not None:
            pre_txt.append(f"目标 {expected}")
        if curve is not None:
            pre_txt.append(f"曲线 {curve}/4095")
        align = info.get("aligned")
        if align is True or align == "ok":
            pre_txt.append("对齐")
        elif align is False or align == "bad":
            pre_txt.append("未对齐")
        rows.append(_media_row("测试前", " · ".join(pre_txt) if pre_txt else "—"))

    def _phase_text(label: str, block: dict[str, Any]) -> str:
        cnt = block.get("phase_count") or 0
        if not cnt:
            return _media_row(label, "无变光", muted=True)
        stats = block.get("stats") or {}
        detail = f"{stats.get('curve_min')}~{stats.get('curve_max')} · {cnt}段"
        phases = block.get("phases") or []
        if phases:
            p0 = phases[0]
            detail += f" · 首段 {p0.get('duration_seconds')}s"
        return _media_row(label, detail)

    rows.append(_phase_text("启动20s", launch))
    rows.append(_phase_text("游戏内", in_game))
    return (
        '<div style="margin-bottom:10px;padding:10px 12px;background:var(--color-background-secondary);'
        'border-radius:var(--border-radius-md);">'
        '<p style="margin:0 0 8px;font-size:12px;font-weight:500;color:var(--color-text-secondary);'
        'display:flex;align-items:center;gap:6px;">'
        '<i class="ti ti-sun-low" style="font-size:14px;" aria-hidden="true"></i>亮度分析</p>'
        f'{"".join(rows)}'
        "</div>"
    )


def _format_volume_media_block(ctx: dict[str, Any]) -> str:
    """测试手法内嵌：音量摘要（测试前 / 游戏内）。"""
    findings = volume_findings_summary(ctx)
    if findings.get("coverage") == "missing":
        return ""
    pre = findings.get("pre_test_setting") or {}
    in_game = findings.get("in_game_volume") or {}
    route = findings.get("audio_route") or {}
    max_idx = pre.get("max_index") or 15

    rows: list[str] = []
    idx = pre.get("index")
    pct = pre.get("index_pct")
    if idx is not None:
        pre_txt = f"档位 {idx}/{max_idx}"
        if pct is not None:
            pre_txt += f" ({pct}%)"
        if pre.get("time"):
            pre_txt += f" @ {pre['time']}"
    else:
        pre_txt = "—"
    rows.append(_media_row("测试前", pre_txt))

    if in_game.get("changed"):
        cnt = in_game.get("transition_count") or 0
        lo = in_game.get("index_min")
        hi = in_game.get("index_max")
        lo_pct = in_game.get("index_min_pct")
        hi_pct = in_game.get("index_max_pct")
        detail = f"变音量 {cnt} 段 · index {lo}~{hi}"
        if lo_pct is not None and hi_pct is not None:
            detail += f" ({lo_pct}%~{hi_pct}%)"
        rows.append(_media_row("游戏内", detail))
    elif in_game.get("index_min") is not None:
        lo = in_game.get("index_min")
        hi = in_game.get("index_max")
        lo_pct = in_game.get("index_min_pct")
        if lo == hi:
            detail = f"恒定 {lo}/{max_idx}"
            if lo_pct is not None:
                detail += f" ({lo_pct}%)"
        else:
            detail = f"{lo}~{hi}/{max_idx}"
        if in_game.get("coverage") == "partial":
            detail += " · 沿用测试前基线"
        rows.append(_media_row("游戏内", detail))
    else:
        rows.append(_media_row("游戏内", "无有效采样", muted=True))

    device = route.get("dominant_device_label")
    if device:
        rows.append(_media_row("输出", str(device)))

    return (
        '<div style="margin-bottom:10px;padding:10px 12px;background:var(--color-background-secondary);'
        'border-radius:var(--border-radius-md);">'
        '<p style="margin:0 0 8px;font-size:12px;font-weight:500;color:var(--color-text-secondary);'
        'display:flex;align-items:center;gap:6px;">'
        '<i class="ti ti-volume" style="font-size:14px;" aria-hidden="true"></i>音量分析</p>'
        f'{"".join(rows)}'
        "</div>"
    )


def _cpu_gpu_ddr_block(ctx: dict[str, Any]) -> dict[str, Any]:
    return ctx.get("game_cpu_gpu_ddr") or {}


def _format_perf_lock_media_block(ctx: dict[str, Any]) -> str:
    """不同优化策略内嵌：perfLockAcq 提频策略（T_game）。"""
    perf = _cpu_gpu_ddr_block(ctx).get("cpu_perf_lock") or {}
    strategies = perf.get("by_strategy_idx") or []
    if perf.get("coverage") == "missing" or not strategies:
        return ""

    rows: list[str] = []
    total = perf.get("total_acquire_count")
    if total is not None:
        rows.append(_media_row("合计", f"T_game 共 {total} 次 acquire"))

    for item in strategies[:5]:
        idx = item.get("idx")
        label = item.get("label") or ""
        cnt = item.get("acquire_count", 0)
        user = item.get("top_lock_user") or "—"
        dur = item.get("duration_ms") or {}
        dur_txt = ""
        if dur.get("min") is not None and dur.get("max") is not None:
            dmin, dmax = dur["min"], dur["max"]
            dur_txt = f" · duration {dmin}~{dmax}ms" if dmin != dmax else f" · duration {dmin}ms"
        title = f"idx {idx}"
        if label:
            title += f" ({label})"
        rows.append(_media_row(title, f"{cnt} 次 · {user}{dur_txt}"))

    return (
        '<div style="margin-bottom:10px;padding:10px 12px;background:var(--color-background-secondary);'
        'border-radius:var(--border-radius-md);">'
        '<p style="margin:0 0 8px;font-size:12px;font-weight:500;color:var(--color-text-secondary);'
        'display:flex;align-items:center;gap:6px;">'
        '<i class="ti ti-cpu" style="font-size:14px;" aria-hidden="true"></i>'
        "perfLockAcq 提频策略</p>"
        f'{"".join(rows)}'
        "</div>"
    )


def _fps_curve_svg(
    points: list[dict[str, Any]],
    *,
    avg_fps: float | None = None,
    low_periods: list[dict[str, Any]] | None = None,
    width: int = 1200,
    height: int = 200,
    show_value_labels: bool = False,
    value_unit: str = "fps",
    aria_label: str = "图层帧率时间曲线",
) -> str:
    """纯 SVG 帧率/刷新率时间曲线：左右铺满；悬停显示时间与数值；可选点上标注数值。"""
    clean: list[tuple[str, float]] = []
    for p in points:
        raw = p.get("fps") if p.get("fps") is not None else p.get("hz")
        if raw is None:
            continue
        try:
            fps = float(raw)
        except (TypeError, ValueError):
            continue
        t = str(p.get("time") or p.get("time_raw") or "")
        clean.append((t, fps))
    if len(clean) < 2:
        return ""
    times = [t for t, _ in clean]
    vals = [v for _, v in clean]
    pad_l, pad_r, pad_t, pad_b = 28, 8, (22 if show_value_labels else 14), 26
    # 有 avg 时预留顶部空间，避免标注压在曲线上
    if avg_fps is not None:
        pad_t = max(pad_t, 36)
    plot_w = max(1, width - pad_l - pad_r)
    plot_h = max(1, height - pad_t - pad_b)
    y_max = max(60.0, max(vals) * 1.08, float(avg_fps or 0) * 1.08)
    y_min = 0.0
    n = len(vals)

    def _xy(i: int, fps: float) -> tuple[float, float]:
        x = pad_l + (i / (n - 1)) * plot_w
        y = pad_t + (1.0 - (fps - y_min) / (y_max - y_min)) * plot_h
        return x, y

    poly = " ".join(f"{_xy(i, v)[0]:.1f},{_xy(i, v)[1]:.1f}" for i, v in enumerate(vals))
    bands = ""
    for period in low_periods or []:
        if not isinstance(period, dict):
            continue
        t0 = str(period.get("start") or "")
        t1 = str(period.get("end") or "")
        if not t0 or not t1:
            continue
        idxs = [i for i, t in enumerate(times) if t0 <= t <= t1]
        if not idxs:
            continue
        i0, i1 = idxs[0], idxs[-1]
        x0, _ = _xy(i0, vals[i0])
        x1, _ = _xy(i1, vals[i1])
        bands += (
            f'<rect x="{x0:.1f}" y="{pad_t}" width="{max(2.0, x1 - x0):.1f}" height="{plot_h}" '
            f'fill="rgba(220, 38, 38, 0.12)" />'
        )

    avg_line = ""
    if avg_fps is not None:
        _, ay = _xy(0, float(avg_fps))
        ax_mid = pad_l + plot_w / 2.0
        # 抬高标注，避免压在均值虚线/曲线上；允许进入顶部 padding，避免高均值时贴线
        avg_label_y = max(16.0, ay - 30.0)
        avg_line = (
            f'<line x1="{pad_l}" y1="{ay:.1f}" x2="{width - pad_r}" y2="{ay:.1f}" '
            f'stroke="var(--amber-600, #b45309)" stroke-width="1" stroke-dasharray="4 3" />'
            f'<text x="{ax_mid:.1f}" y="{avg_label_y:.1f}" text-anchor="middle" '
            f'font-size="15" font-weight="700" fill="var(--amber-600, #b45309)">'
            f"avg {float(avg_fps):.1f}</text>"
        )

    value_labels = ""
    if show_value_labels:
        # 仅 max/min/末点；靠近 Y 轴右移，避免与刻度重叠
        priority: list[int] = []
        for i in (
            max(range(n), key=lambda i: vals[i]),
            min(range(n), key=lambda i: vals[i]),
            n - 1,
            0,
        ):
            if i not in priority:
                priority.append(i)
        color = "var(--blue-600, #2563eb)"
        seen_v: list[float] = []
        candidates: list[tuple[float, float, float, str]] = []
        for i in priority:
            v = vals[i]
            if any(abs(v - sv) < 0.8 for sv in seen_v):
                continue
            x, y = _xy(i, v)
            candidates.append((x, y, v, color))
            seen_v.append(v)
            if len(candidates) >= 3:
                break
        value_labels = _emit_sparse_point_labels(
            candidates,
            min_dx=100,
            min_dy=22,
            font_size=9,
            max_labels=4,
            pad_l=float(pad_l),
            plot_right=float(width - pad_r),
        )

    y_ticks = [0, y_max / 2, y_max]
    tick_html = "".join(
        f'<text x="{pad_l - 4}" y="{_xy(0, y)[1] + 3:.1f}" text-anchor="end" '
        f'font-size="10" fill="var(--color-text-tertiary, #888)">{y:.0f}</text>'
        for y in y_ticks
    )
    t_first = _esc(_format_curve_time_display(times[0]))
    t_last = _esc(_format_curve_time_display(times[-1]))
    axis_times = (
        f'<text x="{pad_l}" y="{height - 6}" font-size="11" fill="var(--color-text-tertiary, #888)">{t_first}</text>'
        f'<text x="{width - pad_r}" y="{height - 6}" text-anchor="end" font-size="11" '
        f'fill="var(--color-text-tertiary, #888)">{t_last}</text>'
    )

    times_js = ",".join(json.dumps(_format_curve_time_display(t), ensure_ascii=False) for t in times)
    fps_js = ",".join(f"{v:.2f}" for v in vals)
    tip_unit = _esc(value_unit)
    tip_name = "刷新率" if str(value_unit).lower() == "hz" else "帧率"
    uid = f"fpscurve{abs(hash((times[0], times[-1], n, value_unit))) % 10_000_000}"
    return (
        f'<div id="{uid}-wrap" class="fps-curve-wrap" style="position:relative;width:100%;'
        f'box-sizing:border-box;"'
        f' data-pad-l="{pad_l}" data-pad-r="{pad_r}" data-pad-t="{pad_t}" data-pad-b="{pad_b}"'
        f' data-vb-w="{width}" data-vb-h="{height}">'
        f'<svg id="{uid}-svg" viewBox="0 0 {width} {height}" preserveAspectRatio="none" '
        f'width="100%" height="{height}" role="img" aria-label="{_esc(aria_label)}" '
        f'style="display:block;width:100%;height:{height}px;min-width:100%;cursor:crosshair;">'
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="transparent"/>'
        f"{bands}"
        f'<line x1="{pad_l}" y1="{pad_t}" x2="{pad_l}" y2="{height - pad_b}" '
        f'stroke="var(--color-border-tertiary, #ddd)" stroke-width="1"/>'
        f'<line x1="{pad_l}" y1="{height - pad_b}" x2="{width - pad_r}" y2="{height - pad_b}" '
        f'stroke="var(--color-border-tertiary, #ddd)" stroke-width="1"/>'
        f"{tick_html}{avg_line}"
        f'<polyline fill="none" stroke="var(--blue-600, #2563eb)" stroke-width="2" '
        f'vector-effect="non-scaling-stroke" points="{poly}"/>'
        f"{value_labels}{axis_times}"
        f'<circle id="{uid}-dot" cx="0" cy="0" r="4" fill="var(--blue-600, #2563eb)" '
        f'stroke="#fff" stroke-width="1.5" visibility="hidden" '
        f'vector-effect="non-scaling-stroke"/>'
        f"</svg>"
        f'<div id="{uid}-tip" style="display:none;position:absolute;z-index:5;pointer-events:none;'
        f'padding:6px 8px;border-radius:6px;font-size:12px;line-height:1.4;'
        f'background:rgba(28,28,30,.92);color:#fff;box-shadow:0 2px 8px rgba(0,0,0,.18);'
        f'white-space:nowrap;"></div>'
        f"<script>(function(){{"
        f"var wrap=document.getElementById('{uid}-wrap');"
        f"var svg=document.getElementById('{uid}-svg');"
        f"var tip=document.getElementById('{uid}-tip');"
        f"var dot=document.getElementById('{uid}-dot');"
        f"if(!wrap||!svg||!tip||!dot)return;"
        f"var times=[{times_js}];"
        f"var fps=[{fps_js}];"
        f"var n=times.length; if(n<2)return;"
        f"var padL=+wrap.dataset.padL, padR=+wrap.dataset.padR, padT=+wrap.dataset.padT, padB=+wrap.dataset.padB;"
        f"var vbW=+wrap.dataset.vbW, vbH=+wrap.dataset.vbH;"
        f"var yMax={y_max:.4f}, yMin=0;"
        f"function xy(i,v){{var x=padL+(i/(n-1))*(vbW-padL-padR);"
        f"var y=padT+(1-(v-yMin)/(yMax-yMin))*(vbH-padT-padB); return [x,y];}}"
        f"function show(i,clientX,clientY){{"
        f"var t=times[i], v=fps[i]; var p=xy(i,+v);"
        f"dot.setAttribute('cx',p[0]); dot.setAttribute('cy',p[1]); dot.setAttribute('visibility','visible');"
        f"tip.style.display='block'; tip.innerHTML='时间：'+t+'<br>{tip_name}：'+v+' {tip_unit}';"
        f"var wr=wrap.getBoundingClientRect();"
        f"var left=clientX-wr.left+12, top=clientY-wr.top-36;"
        f"if(left+tip.offsetWidth>wr.width-4) left=clientX-wr.left-tip.offsetWidth-12;"
        f"if(top<4) top=clientY-wr.top+16;"
        f"tip.style.left=left+'px'; tip.style.top=top+'px';}}"
        f"function hide(){{tip.style.display='none'; dot.setAttribute('visibility','hidden');}}"
        f"svg.addEventListener('mousemove',function(e){{"
        f"var r=svg.getBoundingClientRect();"
        f"var xr=(e.clientX-r.left)/Math.max(1,r.width);"
        f"var xVb=xr*vbW;"
        f"var x0=padL, x1=vbW-padR;"
        f"var t=(xVb-x0)/Math.max(1e-6,x1-x0);"
        f"t=Math.max(0,Math.min(1,t));"
        f"var i=Math.round(t*(n-1));"
        f"show(i,e.clientX,e.clientY);"
        f"}});"
        f"svg.addEventListener('mouseleave',hide);"
        f"}})();</script></div>"
    )


def _layer_short_label(layer: str) -> str:
    """从完整 layer 名提取短说明，用于同包名区分。"""
    s = str(layer or "").strip()
    if not s:
        return "—"
    m = re.search(
        r"SurfaceView\[[^\]]*\](?:\((?P<mode>[^)]+)\))?#(?P<id>\d+)",
        s,
        re.IGNORECASE,
    )
    if m:
        mode = (m.group("mode") or "").strip()
        return f"SurfaceView({mode})#{m.group('id')}" if mode else f"SurfaceView#{m.group('id')}"
    m = re.search(r"/([^/#\s]+)#(?P<id>\d+)\s*$", s)
    if m:
        return f"Activity#{m.group('id')}"
    m = re.search(r"(?P<name>[A-Za-z][\w.]*)#(?P<id>\d+)\s*$", s)
    if m:
        return f"{m.group('name')}#{m.group('id')}"
    return s if len(s) <= 48 else s[:45] + "…"


def _layer_display_name(layer: dict[str, Any], *, show_hint: bool) -> str:
    pkg = str(layer.get("package") or "—")
    mark = " ★" if layer.get("is_game_layer") else ""
    hint = str(layer.get("layer_short") or _layer_short_label(str(layer.get("layer") or "")))
    if show_hint and hint and hint != "—":
        return f"{pkg}{mark} · {hint}"
    return f"{pkg}{mark}"


_FPS_SERIES_COLORS = (
    "var(--blue-600, #2563eb)",
    "var(--orange-600, #c2410c)",
    "var(--green-600, #16a34a)",
    "var(--violet-600, #7c3aed)",
    "var(--rose-600, #e11d48)",
    "var(--cyan-600, #0891b2)",
)


def _format_curve_value_label(v: float) -> str:
    """缩短曲线点标注，降低重叠概率。"""
    try:
        fv = float(v)
    except (TypeError, ValueError):
        return str(v)
    if abs(fv - round(fv)) < 0.05:
        return f"{round(fv):g}"
    return f"{fv:.1f}"


def _emit_sparse_point_labels(
    candidates: list[tuple[float, float, float, str]],
    *,
    min_dx: float = 72.0,
    min_dy: float = 18.0,
    font_size: int = 9,
    max_labels: int = 8,
    pad_l: float = 36.0,
    plot_right: float = 1190.0,
) -> str:
    """按文字包围盒避让输出点上数值；靠近 Y 轴时右移，避免与刻度重叠。

    candidates: (x, y, value, color) 按优先级从高到低。
    """
    placed: list[tuple[float, float, float, float]] = []  # cx, cy, half_w, half_h
    html_parts: list[str] = []

    def _overlaps(cx: float, cy: float, hw: float, hh: float) -> bool:
        for px, py, phw, phh in placed:
            if abs(px - cx) < (hw + phw) and abs(py - cy) < (hh + phh):
                return True
        return False

    for x, y, v, color in candidates:
        if len(html_parts) >= max_labels:
            break
        text = _format_curve_value_label(v)
        hw = max(18.0, len(text) * 3.2)
        hh = max(min_dy / 2, font_size * 0.7)
        near_left = x < pad_l + 42
        near_right = x > plot_right - 36
        if near_left:
            trials: list[tuple[float, float, str]] = [
                (max(x, pad_l) + hw + 14, y - 2, "start"),
                (max(x, pad_l) + hw + 14, y + 14, "start"),
                (max(x, pad_l) + hw + 14, y + 28, "start"),
            ]
        elif near_right:
            trials = [
                (x - 6, y - 8, "end"),
                (x - 6, y + 12, "end"),
            ]
        else:
            trials = [
                (x, y - 9, "middle"),
                (x, y + 13, "middle"),
                (x + hw + 4, y - 2, "start"),
                (x - hw - 4, y - 2, "end"),
            ]
        chosen: tuple[float, float, str] | None = None
        for tx, ty, anchor in trials:
            # 水平间距不足即冲突（避免左侧一列竖排叠字 / 与 Y 刻度抢位）
            if any(abs(px - tx) < min_dx for px, py, _, _ in placed):
                continue
            if any(abs(py - ty) < min_dy and abs(px - tx) < min_dx * 1.6 for px, py, _, _ in placed):
                continue
            if _overlaps(tx, ty, hw, hh):
                continue
            if tx < pad_l + 20 or tx > plot_right + 4:
                continue
            # 再避开左上角 Y 轴最大刻度附近
            if tx < pad_l + 55 and ty < 40:
                continue
            chosen = (tx, ty, anchor)
            break
        if chosen is None:
            continue
        tx, ty, anchor = chosen
        placed.append((tx, ty, hw, hh))
        html_parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.0" fill="{color}" stroke="#fff" stroke-width="0.7"/>'
            f'<text x="{tx:.1f}" y="{ty:.1f}" text-anchor="{anchor}" font-size="{font_size}" '
            f'fill="{color}">{_esc(text)}</text>'
        )
    return "".join(html_parts)


def _multi_fps_curve_svg(
    series: list[dict[str, Any]],
    *,
    avg_fps: float | None = None,
    width: int = 1200,
    height: int = 240,
) -> str:
    """多图层帧率曲线：按绝对时间对齐；图例区分；悬停显示各层数值。"""
    prepared: list[dict[str, Any]] = []
    all_dt: list[datetime] = []
    all_vals: list[float] = []
    for si, ser in enumerate(series):
        pts_in = ser.get("points") or []
        pts: list[tuple[datetime, str, float]] = []
        for p in pts_in:
            raw = p.get("fps") if p.get("fps") is not None else p.get("hz")
            if raw is None:
                continue
            try:
                v = float(raw)
            except (TypeError, ValueError):
                continue
            t_raw = str(p.get("time") or p.get("time_raw") or "")
            dt = _parse_curve_time(t_raw)
            if not dt:
                continue
            pts.append((dt, t_raw, v))
            all_dt.append(dt)
            all_vals.append(v)
        if len(pts) < 2:
            continue
        pts.sort(key=lambda x: x[0])
        prepared.append(
            {
                "label": str(ser.get("label") or f"图层{si + 1}"),
                "color": str(ser.get("color") or _FPS_SERIES_COLORS[si % len(_FPS_SERIES_COLORS)]),
                "points": pts,
            }
        )
    if not prepared or not all_dt:
        return ""

    t0, t1 = min(all_dt), max(all_dt)
    span = max(1.0, (t1 - t0).total_seconds())
    legend_rows = max(1, (len(prepared) + 2) // 3)
    pad_l, pad_r, pad_t, pad_b = 36, 10, 18 + legend_rows * 14, 28
    if avg_fps is not None:
        pad_t = max(pad_t, pad_t + 12)
    plot_w = max(1, width - pad_l - pad_r)
    plot_h = max(1, height - pad_t - pad_b)
    y_max = max(60.0, max(all_vals) * 1.12, float(avg_fps or 0) * 1.12)
    y_min = 0.0

    def _xy_dt(dt: datetime, v: float) -> tuple[float, float]:
        x = pad_l + ((dt - t0).total_seconds() / span) * plot_w
        y = pad_t + (1.0 - (v - y_min) / (y_max - y_min)) * plot_h
        return x, y

    polylines = ""
    legend = ""
    tip_series_js: list[str] = []
    label_candidates: list[tuple[float, float, float, str]] = []
    for si, ser in enumerate(prepared):
        color = ser["color"]
        pts = ser["points"]
        poly = " ".join(f"{_xy_dt(dt, v)[0]:.1f},{_xy_dt(dt, v)[1]:.1f}" for dt, _, v in pts)
        polylines += (
            f'<polyline fill="none" stroke="{color}" stroke-width="2" '
            f'vector-effect="non-scaling-stroke" points="{poly}"/>'
        )
        n = len(pts)
        # 每层最多标 max/min/末点，跨层统一避让
        idxs: list[int] = []
        for i in (
            max(range(n), key=lambda i: pts[i][2]),
            min(range(n), key=lambda i: pts[i][2]),
            n - 1,
        ):
            if i not in idxs:
                idxs.append(i)
        seen_v: list[float] = []
        for i in idxs[:3]:
            v = float(pts[i][2])
            if any(abs(v - sv) < 0.8 for sv in seen_v):
                continue
            dt, _t, _ = pts[i]
            x, y = _xy_dt(dt, v)
            label_candidates.append((x, y, v, color))
            seen_v.append(v)
        lx = pad_l + (si % 3) * 280
        ly = 10 + (si // 3) * 13
        legend += (
            f'<rect x="{lx}" y="{ly}" width="12" height="3" fill="{color}"/>'
            f'<text x="{lx + 16}" y="{ly + 4}" font-size="11" fill="var(--color-text-secondary, #5f5e5a)">'
            f'{_esc(ser["label"])} ({n})</text>'
        )
        times_js = ",".join(
            json.dumps(_format_curve_time_display(t), ensure_ascii=False) for _, t, _ in pts
        )
        fps_js = ",".join(f"{v:.2f}" for _, _, v in pts)
        xs_js = ",".join(f"{_xy_dt(dt, v)[0]:.2f}" for dt, _, v in pts)
        ys_js = ",".join(f"{_xy_dt(dt, v)[1]:.2f}" for dt, _, v in pts)
        tip_series_js.append(
            "{"
            f"label:{json.dumps(ser['label'], ensure_ascii=False)},"
            f"color:{json.dumps(color)},"
            f"times:[{times_js}],fps:[{fps_js}],xs:[{xs_js}],ys:[{ys_js}]"
            "}"
        )

    value_labels = _emit_sparse_point_labels(
        label_candidates,
        min_dx=100,
        min_dy=22,
        font_size=9,
        max_labels=6,
        pad_l=float(pad_l),
        plot_right=float(width - pad_r),
    )

    avg_line = ""
    if avg_fps is not None:
        _, ay = _xy_dt(t0, float(avg_fps))
        ax_mid = pad_l + plot_w / 2.0
        # 抬高标注，避免压在均值虚线/曲线上；允许进入顶部 padding，避免高均值时贴线
        avg_label_y = max(16.0, ay - 30.0)
        avg_line = (
            f'<line x1="{pad_l}" y1="{ay:.1f}" x2="{width - pad_r}" y2="{ay:.1f}" '
            f'stroke="var(--amber-600, #b45309)" stroke-width="1" stroke-dasharray="4 3" />'
            f'<text x="{ax_mid:.1f}" y="{avg_label_y:.1f}" text-anchor="middle" '
            f'font-size="15" font-weight="700" fill="var(--amber-600, #b45309)">'
            f"avg {float(avg_fps):.1f}</text>"
        )

    y_ticks = [0, y_max / 2, y_max]
    tick_html = "".join(
        f'<text x="{pad_l - 4}" y="{_xy_dt(t0, y)[1] + 3:.1f}" text-anchor="end" '
        f'font-size="10" fill="var(--color-text-tertiary, #888)">{y:.0f}</text>'
        for y in y_ticks
    )
    t_first = _esc(_format_curve_time_display(prepared[0]["points"][0][1]))
    end_raw = ""
    for ser in prepared:
        for dt, t_raw, _ in ser["points"]:
            if dt == t1:
                end_raw = t_raw
    t_last = _esc(_format_curve_time_display(end_raw or prepared[-1]["points"][-1][1]))
    axis_times = (
        f'<text x="{pad_l}" y="{height - 6}" font-size="11" fill="var(--color-text-tertiary, #888)">{t_first}</text>'
        f'<text x="{width - pad_r}" y="{height - 6}" text-anchor="end" font-size="11" '
        f'fill="var(--color-text-tertiary, #888)">{t_last}</text>'
    )

    uid = f"mfps{abs(hash((str(t0), str(t1), len(prepared)))) % 10_000_000}"
    series_js = ",".join(tip_series_js)
    return (
        f'<div id="{uid}-wrap" class="fps-curve-wrap" style="position:relative;width:100%;'
        f'box-sizing:border-box;" data-pad-l="{pad_l}" data-pad-r="{pad_r}" data-vb-w="{width}">'
        f'<svg id="{uid}-svg" viewBox="0 0 {width} {height}" preserveAspectRatio="none" '
        f'width="100%" height="{height}" role="img" aria-label="多图层帧率时间曲线" '
        f'style="display:block;width:100%;height:{height}px;min-width:100%;cursor:crosshair;">'
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="transparent"/>'
        f"{legend}"
        f'<line x1="{pad_l}" y1="{pad_t}" x2="{pad_l}" y2="{height - pad_b}" '
        f'stroke="var(--color-border-tertiary, #ddd)" stroke-width="1"/>'
        f'<line x1="{pad_l}" y1="{height - pad_b}" x2="{width - pad_r}" y2="{height - pad_b}" '
        f'stroke="var(--color-border-tertiary, #ddd)" stroke-width="1"/>'
        f"{tick_html}{avg_line}{polylines}{value_labels}{axis_times}"
        f'<circle id="{uid}-dot" cx="0" cy="0" r="4" fill="var(--blue-600, #2563eb)" '
        f'stroke="#fff" stroke-width="1.5" visibility="hidden" '
        f'vector-effect="non-scaling-stroke"/>'
        f"</svg>"
        f'<div id="{uid}-tip" style="display:none;position:absolute;z-index:5;pointer-events:none;'
        f'padding:6px 8px;border-radius:6px;font-size:12px;line-height:1.4;'
        f'background:rgba(28,28,30,.92);color:#fff;box-shadow:0 2px 8px rgba(0,0,0,.18);'
        f'white-space:nowrap;"></div>'
        f"<script>(function(){{"
        f"var wrap=document.getElementById('{uid}-wrap');"
        f"var svg=document.getElementById('{uid}-svg');"
        f"var tip=document.getElementById('{uid}-tip');"
        f"var dot=document.getElementById('{uid}-dot');"
        f"if(!wrap||!svg||!tip||!dot)return;"
        f"var series=[{series_js}];"
        f"var vbW=+wrap.dataset.vbW;"
        f"function nearest(ser,xVb){{var xs=ser.xs,best=0,bd=1e18;"
        f"for(var i=0;i<xs.length;i++){{var d=Math.abs(xs[i]-xVb); if(d<bd){{bd=d;best=i;}}}} return best;}}"
        f"function show(xVb,clientX,clientY){{"
        f"var lines=[],bestD=1e18,bx=0,by=0,bc=null;"
        f"for(var s=0;s<series.length;s++){{var ser=series[s]; if(!ser.xs.length)continue;"
        f"var i=nearest(ser,xVb);"
        f"lines.push(`<span style=\"color:${{ser.color}}\">${{ser.label}}: ${{ser.fps[i]}} fps</span> · ${{ser.times[i]}}`);"
        f"var d=Math.abs(ser.xs[i]-xVb); if(d<bestD){{bestD=d;bx=ser.xs[i];by=ser.ys[i];bc=ser.color;}}"
        f"}}"
        f"if(!lines.length)return;"
        f"tip.style.display='block'; tip.innerHTML=lines.join('<br>');"
        f"var wr=wrap.getBoundingClientRect();"
        f"var left=clientX-wr.left+12, top=clientY-wr.top-36;"
        f"if(left+tip.offsetWidth>wr.width-4) left=clientX-wr.left-tip.offsetWidth-12;"
        f"if(top<4) top=clientY-wr.top+16;"
        f"tip.style.left=left+'px'; tip.style.top=top+'px';"
        f"dot.setAttribute('cx',bx); dot.setAttribute('cy',by); dot.setAttribute('visibility','visible');"
        f"if(bc)dot.setAttribute('fill',bc);"
        f"}}"
        f"function hide(){{tip.style.display='none'; dot.setAttribute('visibility','hidden');}}"
        f"svg.addEventListener('mousemove',function(e){{"
        f"var r=svg.getBoundingClientRect();"
        f"var xr=(e.clientX-r.left)/Math.max(1,r.width);"
        f"show(xr*vbW,e.clientX,e.clientY);"
        f"}});"
        f"svg.addEventListener('mouseleave',hide);"
        f"}})();</script></div>"
    )


def _layer_avg_fps(layer: dict[str, Any]) -> float:
    try:
        return float(layer.get("avg_queuebuffer_fps") or 0)
    except (TypeError, ValueError):
        return 0.0


def _layer_fluctuation_pct(layer: dict[str, Any]) -> float:
    raw = layer.get("fps_fluctuation_pct")
    if raw is not None:
        try:
            return float(raw)
        except (TypeError, ValueError):
            pass
    avg = _layer_avg_fps(layer)
    try:
        mn = float(layer.get("min_queuebuffer_fps"))
        mx = float(layer.get("max_queuebuffer_fps"))
    except (TypeError, ValueError):
        return 0.0
    if avg <= 0:
        return 0.0
    return (mx - mn) / avg * 100.0


def _curve_block_html(title: str, svg: str) -> str:
    return (
        '<div style="margin:8px 0 6px;padding:6px 0;width:100%;box-sizing:border-box;'
        'background:var(--color-background-primary);'
        'border:0.5px solid var(--color-border-tertiary);border-radius:var(--border-radius-md);">'
        f'<p style="margin:0 0 6px;padding:0 8px;font-size:11px;color:var(--color-text-tertiary);">{_esc(title)}</p>'
        f'<div style="width:100%;padding:0;box-sizing:border-box;">{svg}</div></div>'
    )


def _format_frame_rate_media_block(ctx: dict[str, Any]) -> str:
    """软件策略差异内嵌：图层帧率（≥10fps；游戏曲线与高波动其他图层曲线分开）。"""
    fr = _cpu_gpu_ddr_block(ctx).get("frame_rate") or {}
    layers = fr.get("layers") or []
    if fr.get("coverage") == "missing" or not layers:
        return ""

    min_fps = 10.0
    fluct_thr = 5.0
    kept = [x for x in layers if _layer_avg_fps(x) >= min_fps]
    if not kept:
        return (
            '<div style="margin-bottom:10px;padding:10px 12px;background:var(--color-background-secondary);'
            'border-radius:var(--border-radius-md);">'
            '<p style="margin:0;font-size:12px;color:var(--color-text-tertiary);">'
            "图层帧率：无平均帧率≥10 的图层</p></div>"
        )

    main = fr.get("main_game_layer") or {}
    if main and _layer_avg_fps(main) < min_fps:
        main = next((x for x in kept if x.get("is_game_layer")), {})
    below = fr.get("game_below_avg_fps") or {}
    below_periods = below.get("periods") or []

    pkg_counts: dict[str, int] = {}
    for layer in kept:
        pkg = str(layer.get("package") or "—")
        pkg_counts[pkg] = pkg_counts.get(pkg, 0) + 1

    avg_fps = None
    try:
        avg_fps = float(
            main.get("merged_layer_avg_fps")
            or main.get("avg_queuebuffer_fps")
            or below.get("layer_avg_fps")
        )
    except (TypeError, ValueError):
        avg_fps = None

    rows: list[str] = []
    if main:
        main_name = _layer_display_name(main, show_hint=True)
        rows.append(
            _media_row(
                "游戏主图层",
                f"{main_name} · avg {main.get('avg_queuebuffer_fps')} fps "
                f"({main.get('min_queuebuffer_fps')}~{main.get('max_queuebuffer_fps')}) · "
                f"{main.get('sample_count')} 采样",
            )
        )
    if below_periods:
        bsum = below.get("summary") or {}
        rows.append(
            _media_row(
                "低于均值时段",
                f"均值 {below.get('layer_avg_fps', '—')} fps · 共 {bsum.get('period_count', 0)} 段 / "
                f"{bsum.get('total_duration_seconds', 0)}s · "
                f"段内加权均值 {bsum.get('weighted_avg_fps', '—')} fps",
            )
        )

    game_layers = [x for x in kept if x.get("is_game_layer")]
    other_fluct_layers = [
        x
        for x in kept
        if (not x.get("is_game_layer"))
        and _layer_avg_fps(x) >= min_fps
        and _layer_fluctuation_pct(x) > fluct_thr
        and len(x.get("fps_timeline") or []) >= 2
    ]

    def _series_from(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for gi, layer in enumerate(items):
            tl = layer.get("fps_timeline") or []
            if len(tl) < 2:
                continue
            hint = str(layer.get("layer_short") or _layer_short_label(str(layer.get("layer") or "")))
            out.append(
                {
                    "label": hint,
                    "color": _FPS_SERIES_COLORS[gi % len(_FPS_SERIES_COLORS)],
                    "points": tl,
                }
            )
        return out

    game_curve_html = ""
    game_series = _series_from(game_layers)
    if len(game_series) >= 2:
        svg = _multi_fps_curve_svg(game_series, avg_fps=avg_fps, height=250)
        if svg:
            game_curve_html = _curve_block_html(
                "游戏图层帧率曲线（分色=不同 Surface/Activity；点上标 fps）", svg
            )
    elif game_series:
        svg = _fps_curve_svg(
            game_series[0]["points"],
            avg_fps=avg_fps,
            low_periods=below_periods,
            show_value_labels=True,
        )
        if svg:
            game_curve_html = _curve_block_html(
                f"游戏图层帧率曲线 · {game_series[0]['label']}（红带=低于均值时段）", svg
            )

    other_curve_html = ""
    other_series = _series_from(other_fluct_layers)
    if len(other_series) >= 2:
        svg = _multi_fps_curve_svg(other_series, height=230)
        if svg:
            other_curve_html = _curve_block_html(
                "其他图层帧率曲线（avg>10 且波动>5%；与游戏图层分开）", svg
            )
    elif other_series:
        svg = _fps_curve_svg(
            other_series[0]["points"],
            show_value_labels=True,
            aria_label="其他图层帧率曲线",
        )
        if svg:
            other_curve_html = _curve_block_html(
                f"其他图层帧率曲线 · {other_series[0]['label']}（avg>10 且波动>5%）", svg
            )

    header = (
        '<div style="display:grid;grid-template-columns:1.2fr 0.7fr 0.9fr 0.5fr;gap:6px;'
        'font-size:11px;color:var(--color-text-tertiary);margin:10px 0 4px;padding-bottom:4px;'
        'border-bottom:0.5px solid var(--color-border-tertiary);">'
        "<span>图层 / 包名</span><span>avg fps</span><span>min~max fps</span><span>采样</span></div>"
    )
    layer_rows: list[str] = []
    snaps: list[str] = []
    for layer in kept[:12]:
        pkg = str(layer.get("package") or "—")
        show_hint = pkg_counts.get(pkg, 0) > 1
        name = _layer_display_name(layer, show_hint=show_hint)
        avg = layer.get("avg_queuebuffer_fps", "—")
        lo = layer.get("min_queuebuffer_fps", "—")
        hi = layer.get("max_queuebuffer_fps", "—")
        cnt = layer.get("sample_count", 0)
        fluct = _layer_fluctuation_pct(layer)
        fluct_txt = f" · 波动 {fluct:.1f}%" if fluct > 0 else ""
        raw = _strip_log_snapshot_prefix(str(layer.get("raw_evidence") or ""))
        if raw and raw not in snaps:
            # 快照带图层短名，便于对应
            hint = str(layer.get("layer_short") or _layer_short_label(str(layer.get("layer") or "")))
            snaps.append(f"[{hint}] {raw}" if hint and hint != "—" else raw)
        layer_rows.append(
            f'<div style="display:grid;grid-template-columns:1.2fr 0.7fr 0.9fr 0.5fr;gap:6px;'
            f'font-size:12px;line-height:1.45;margin-bottom:4px;">'
            f'<span style="color:var(--color-text-primary);" title="{_esc(layer.get("layer", ""))}">'
            f'{_esc(name)}{_esc(fluct_txt)}</span>'
            f'<span style="color:var(--blue-600);font-weight:500;">{_esc(avg)}</span>'
            f'<span style="color:var(--color-text-secondary);">{_esc(lo)}~{_esc(hi)}</span>'
            f'<span style="color:var(--color-text-tertiary);">{_esc(cnt)}</span></div>'
        )
    extra = ""
    skipped = len(layers) - len(kept)
    if skipped > 0:
        extra = (
            f'<p style="margin:4px 0 0;font-size:11px;color:var(--color-text-tertiary);">'
            f"已过滤平均帧率&lt;10 的图层 {skipped} 个</p>"
        )
    if len(kept) > 12:
        extra += (
            f'<p style="margin:4px 0 0;font-size:11px;color:var(--color-text-tertiary);">'
            f"另有 {len(kept) - 12} 个≥10fps 图层，详见 game_cpu_gpu_ddr.json</p>"
        )

    snap_html = ""
    if snaps:
        body = "".join(
            f'<pre style="margin:0 0 4px;white-space:pre-wrap;word-break:break-all;'
            f'font-size:10px;line-height:1.4;color:var(--color-text-secondary);">{_esc(s)}</pre>'
            for s in snaps[:12]
        )
        snap_html = (
            '<details style="margin-top:8px;">'
            f'<summary style="cursor:pointer;font-size:11px;color:var(--color-text-tertiary);">'
            f"日志快照（{len(snaps)}）· 默认隐藏，点击展开</summary>"
            f'<div style="margin-top:6px;padding:8px 10px;background:var(--color-background-primary);'
            f'border-radius:var(--border-radius-md);">{body}</div></details>'
        )

    return (
        '<div style="margin-bottom:10px;padding:10px 12px;background:var(--color-background-secondary);'
        'border-radius:var(--border-radius-md);">'
        '<p style="margin:0 0 8px;font-size:12px;font-weight:500;color:var(--color-text-secondary);'
        'display:flex;align-items:center;gap:6px;">'
        '<i class="ti ti-chart-line" style="font-size:14px;" aria-hidden="true"></i>'
        f"图层帧率（T_game · 展示 {len(kept)}/{len(layers)} 层，avg≥10）</p>"
        f'{"".join(rows)}'
        f"{game_curve_html}"
        f"{other_curve_html}"
        f"{header}"
        f'{"".join(layer_rows)}'
        f"{extra}"
        f"{snap_html}"
        "</div>"
    )


def _strip_log_snapshot_prefix(line: str) -> str:
    """去掉 `file:lineno:` 前缀，保留原始日志正文。"""
    s = str(line or "").strip()
    m = re.match(r"^[A-Za-z0-9_./\\-]+:(\d+:\s*.+)$", s)
    disp = m.group(1).strip() if m else s
    m2 = re.match(r"^\d+:\s*(.+)$", disp)
    return (m2.group(1).strip() if m2 else disp).strip()


def _format_refresh_rate_media_block(ctx: dict[str, Any]) -> str:
    """软件策略 · 屏幕刷新率：支持/实际 Hz、带数值的曲线、默认折叠日志快照。"""
    gb = ctx.get("game_brightness") or {}
    inv = (gb.get("brightness_investigation") or {}) if isinstance(gb, dict) else {}
    s6 = inv.get("step6_refresh_rate") or {}
    if not isinstance(s6, dict) or s6.get("coverage") == "missing":
        return ""
    summary = str(s6.get("report_summary") or "").strip()
    supported = s6.get("supported_fps") or {}
    actual = s6.get("actual_fps") or {}
    if not summary:
        bits: list[str] = []
        if supported.get("last_hz") is not None:
            bits.append(f"支持={supported.get('last_hz')}Hz")
        if actual.get("last_hz") is not None:
            bits.append(f"实际≈{actual.get('last_hz')}Hz")
        summary = "屏幕刷新率：" + (" · ".join(bits) if bits else "已观测")

    rows: list[str] = []
    if supported.get("last_hz") is not None:
        rows.append(
            _media_row(
                "支持刷新率",
                f"{supported.get('last_hz')} Hz · PowerHalWrapper updateFps · "
                f"{supported.get('sample_count', 0)} 采样",
            )
        )
    if actual.get("last_hz") is not None:
        avg = actual.get("avg_hz")
        avg_txt = f" · 均值 {avg} Hz" if avg is not None else ""
        rows.append(
            _media_row(
                "实际送显",
                f"{actual.get('last_hz')} Hz · hwcomposer fps{avg_txt} · "
                f"{actual.get('sample_count', 0)} 采样",
            )
        )

    timeline = (
        s6.get("hz_timeline")
        or actual.get("timeline")
        or supported.get("timeline")
        or []
    )
    avg_hz = None
    try:
        avg_hz = float(actual.get("avg_hz") or supported.get("avg_hz"))
    except (TypeError, ValueError):
        avg_hz = None
    curve_html = ""
    if timeline:
        svg = _fps_curve_svg(
            timeline,
            avg_fps=avg_hz,
            show_value_labels=True,
            value_unit="Hz",
            aria_label="屏幕刷新率时间曲线",
            height=220,
        )
        if svg:
            curve_html = (
                '<div style="margin:8px 0 6px;padding:6px 0;width:100%;box-sizing:border-box;'
                'background:var(--color-background-primary);'
                'border:0.5px solid var(--color-border-tertiary);border-radius:var(--border-radius-md);">'
                '<p style="margin:0 0 6px;padding:0 8px;font-size:11px;color:var(--color-text-tertiary);">'
                "T_game 屏幕刷新率曲线（点上标注 Hz；悬停看时间）</p>"
                f'<div style="width:100%;padding:0;box-sizing:border-box;">{svg}</div></div>'
            )

    snaps = []
    for ev in s6.get("report_evidence") or []:
        disp = _strip_log_snapshot_prefix(str(ev))
        if disp and disp not in snaps:
            snaps.append(disp)
    snap_html = ""
    if snaps:
        body = "".join(
            f'<pre style="margin:0 0 4px;white-space:pre-wrap;word-break:break-all;'
            f'font-size:10px;line-height:1.4;color:var(--color-text-secondary);">{_esc(s)}</pre>'
            for s in snaps[:6]
        )
        snap_html = (
            '<details style="margin-top:6px;">'
            f'<summary style="cursor:pointer;font-size:11px;color:var(--color-text-tertiary);">'
            f"日志快照（{len(snaps)}）· 默认隐藏，点击展开</summary>"
            f'<div style="margin-top:6px;padding:8px 10px;background:var(--color-background-primary);'
            f'border-radius:var(--border-radius-md);">{body}</div></details>'
        )

    return (
        '<div style="margin:8px 0 10px;padding:8px 10px;border:0.5px solid var(--color-border-tertiary);'
        'border-radius:var(--border-radius-md);background:var(--color-background-secondary);">'
        '<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">'
        '<span style="font-size:11px;font-weight:600;padding:1px 6px;border-radius:4px;'
        'background:var(--blue-50, #eff6ff);color:var(--blue-700, #1d4ed8);">已观测</span>'
        '<span style="font-size:12px;font-weight:600;color:var(--color-text-primary);">屏幕刷新率</span>'
        "</div>"
        f'<p style="margin:0 0 6px;font-size:12px;color:var(--color-text-secondary);">{_esc(summary)}</p>'
        f'{"".join(rows)}{curve_html}{snap_html}</div>'
    )


def _format_backlight_2_media_block(ctx: dict[str, Any]) -> str:
    """软件策略 · 背光2.0：展示实时 nits、下降比例与 DisplayPowerController 证据。"""
    gb = ctx.get("game_brightness") or {}
    inv = (gb.get("brightness_investigation") or {}) if isinstance(gb, dict) else {}
    s3 = inv.get("step3_backlight_2_0") or {}
    if not isinstance(s3, dict) or s3.get("skipped"):
        return ""
    summary = str(s3.get("report_summary") or s3.get("note") or "").strip()
    if not summary and not s3.get("in_backlight_2_list"):
        summary = str(s3.get("message") or "背光2.0").strip()
    if not summary:
        return ""
    nits = s3.get("realtime_nits")
    drop = s3.get("drop_ratio_pct")
    exp = s3.get("expected_brightness_drop_pct")
    status = str(s3.get("status") or "")
    applied = bool(s3.get("applied") or s3.get("effective"))
    badge_bg = "var(--green-50)" if applied else "var(--amber-50)"
    badge_fg = "var(--green-700, #047857)" if applied else "var(--amber-700, #b45309)"
    badge = "已生效" if applied else ("未生效" if status in ("miss", "missing", "not_in_list") else "已观测")
    metrics: list[str] = []
    if nits is not None:
        metrics.append(f"实时nits={float(nits):g}")
    if drop is not None:
        metrics.append(f"下降比例={float(drop):g}%")
    if exp is not None:
        metrics.append(f"期望≈{float(exp):g}%")
    metric_html = (
        f'<div style="margin:4px 0 6px;font-size:12px;color:var(--color-text-secondary);">'
        f'{_esc(" · ".join(metrics))}</div>'
        if metrics
        else ""
    )
    snaps = ""
    for ev in (s3.get("report_evidence") or [])[:2]:
        line = str(ev).strip()
        # 去文件名前缀
        m = re.match(r"^[A-Za-z0-9_./\\-]+:(\d+:\s*.+)$", line)
        disp = m.group(1).strip() if m else line
        m2 = re.match(r"^\d+:\s*(.+)$", disp)
        disp = m2.group(1).strip() if m2 else disp
        if disp:
            snaps += (
                f'<div style="font-size:11px;color:var(--color-text-tertiary);'
                f'word-break:break-all;margin:2px 0;">{_esc(disp)}</div>'
            )
    return (
        '<div style="margin:8px 0 10px;padding:8px 10px;border:0.5px solid var(--color-border-tertiary);'
        'border-radius:var(--border-radius-md);background:var(--color-background-secondary);">'
        '<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">'
        f'<span style="font-size:11px;font-weight:600;padding:1px 6px;border-radius:4px;'
        f'background:{badge_bg};color:{badge_fg};">{_esc(badge)}</span>'
        '<span style="font-size:12px;font-weight:600;color:var(--color-text-primary);">背光2.0</span>'
        "</div>"
        f'<p style="margin:0;font-size:12px;color:var(--color-text-secondary);">{_esc(summary)}</p>'
        f"{metric_html}{snaps}</div>"
    )


def _strategy_status_badge(kind: str) -> tuple[str, str, str]:
    """返回 (文案, bg, fg)。kind: ok|warn|observe|skip|suspect."""
    k = str(kind or "observe").lower()
    if k in ("ok", "applied", "effective", "on"):
        return "已生效", "var(--green-50)", "var(--green-700, #047857)"
    if k in ("suspect", "weak", "attention"):
        return "信号可疑", "var(--amber-50)", "var(--amber-700, #b45309)"
    if k in ("warn", "miss", "missing", "off", "inactive"):
        return "未生效", "var(--amber-50)", "var(--amber-700, #b45309)"
    if k in ("skip", "skipped"):
        return "跳过", "var(--color-background-tertiary)", "var(--color-text-tertiary)"
    return "已观测", "var(--blue-50, #eff6ff)", "var(--blue-700, #1d4ed8)"


def _strategy_compare_table(
    rows: list[tuple[str, str, str | None]],
    *,
    label_a: str,
    label_b: str = "",
) -> str:
    """数值对比表；无对比机时仅两列。"""
    if not rows:
        return ""
    dual = bool(label_b)
    head = (
        f"<thead><tr><th>指标</th><th>{_esc(label_a or '本机')}</th>"
        f'{f"<th>{_esc(label_b)}</th>" if dual else ""}'
        f"</tr></thead>"
    )
    body_parts: list[str] = []
    for metric, va, vb in rows:
        cells = f"<td>{_esc(metric)}</td><td>{_esc(va if va not in (None, '') else '—')}</td>"
        if dual:
            cells += f"<td>{_esc(vb if vb not in (None, '') else '—')}</td>"
        body_parts.append(f"<tr>{cells}</tr>")
    return (
        '<table class="cause-table methodology-table strategy-compare-table" style="margin:8px 0;">'
        f"{head}<tbody>{''.join(body_parts)}</tbody></table>"
    )


def _strategy_fold_snaps(snaps: list[str], *, dual_labels: tuple[str, str] | None = None) -> str:
    cleaned: list[str] = []
    for s in snaps:
        disp = _strip_log_snapshot_prefix(str(s))
        if disp and disp not in cleaned:
            cleaned.append(disp)
    if not cleaned:
        return ""
    body = "".join(
        f'<pre style="margin:0 0 4px;white-space:pre-wrap;word-break:break-all;'
        f'font-size:10px;line-height:1.4;color:var(--color-text-secondary);">{_esc(s)}</pre>'
        for s in cleaned[:12]
    )
    return (
        '<details style="margin-top:8px;">'
        f'<summary style="cursor:pointer;font-size:11px;color:var(--color-text-tertiary);">'
        f"日志快照（{len(cleaned)}）· 默认隐藏，点击展开</summary>"
        f'<div style="margin-top:6px;padding:8px 10px;background:var(--color-background-primary);'
        f'border-radius:var(--border-radius-md);">{body}</div></details>'
    )


def _strategy_dual_charts(chart_a: str, chart_b: str, *, label_a: str, label_b: str) -> str:
    if not chart_a and not chart_b:
        return ""
    if not label_b or not chart_b:
        return chart_a or chart_b
    return (
        '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:8px 0;">'
        f'<div><p style="margin:0 0 4px;font-size:11px;color:var(--color-text-tertiary);">{_esc(label_a)}</p>'
        f"{chart_a or '<p style=\"margin:0;font-size:12px;color:var(--color-text-tertiary);\">—</p>'}</div>"
        f'<div><p style="margin:0 0 4px;font-size:11px;color:var(--color-text-tertiary);">{_esc(label_b)}</p>'
        f"{chart_b or '<p style=\"margin:0;font-size:12px;color:var(--color-text-tertiary);\">—</p>'}</div>"
        "</div>"
    )


def _strategy_item_html(
    title: str,
    *,
    badge_kind: str = "observe",
    summary: str = "",
    table_rows: list[tuple[str, str, str | None]] | None = None,
    label_a: str = "本机",
    label_b: str = "",
    charts_html: str = "",
    snaps: list[str] | None = None,
) -> str:
    """统一策略项：标题（徽章在右）→ 总结 → 表格 → 图 → 折叠快照。"""
    badge_txt, badge_bg, badge_fg = _strategy_status_badge(badge_kind)
    table_html = _strategy_compare_table(table_rows or [], label_a=label_a, label_b=label_b)
    snap_html = _strategy_fold_snaps(snaps or [])
    if not summary and not table_html and not charts_html and not snap_html:
        return ""
    summary_html = (
        f'<p style="margin:0 0 6px;font-size:12px;line-height:1.5;color:var(--color-text-secondary);">'
        f"{_esc(summary)}</p>"
        if summary
        else ""
    )
    return (
        f'<div style="margin:10px 0 12px;padding:10px 12px;border:0.5px solid var(--color-border-tertiary);'
        f'border-radius:var(--border-radius-md);background:var(--color-background-secondary);">'
        f'<div style="display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:6px;">'
        f'<span style="font-size:13px;font-weight:600;color:var(--color-text-primary);">{_esc(title)}</span>'
        f'<span style="font-size:11px;font-weight:600;padding:2px 8px;border-radius:4px;'
        f'background:{badge_bg};color:{badge_fg};white-space:nowrap;">{_esc(badge_txt)}</span>'
        f"</div>{summary_html}{table_html}{charts_html or ''}{snap_html}</div>"
    )


def _refresh_rate_chart_html(ctx: dict[str, Any]) -> str:
    gb = ctx.get("game_brightness") or {}
    inv = (gb.get("brightness_investigation") or {}) if isinstance(gb, dict) else {}
    s6 = inv.get("step6_refresh_rate") or {}
    if not isinstance(s6, dict):
        return ""
    supported = s6.get("supported_fps") or {}
    actual = s6.get("actual_fps") or {}
    timeline = s6.get("hz_timeline") or actual.get("timeline") or supported.get("timeline") or []
    avg_hz = None
    try:
        avg_hz = float(actual.get("avg_hz") or supported.get("avg_hz"))
    except (TypeError, ValueError):
        avg_hz = None
    if not timeline:
        return ""
    svg = _fps_curve_svg(
        timeline,
        avg_fps=avg_hz,
        show_value_labels=True,
        value_unit="Hz",
        aria_label="屏幕刷新率时间曲线",
        height=200,
    )
    if not svg:
        return ""
    return (
        '<div style="padding:6px 0;width:100%;box-sizing:border-box;'
        'background:var(--color-background-primary);'
        'border:0.5px solid var(--color-border-tertiary);border-radius:var(--border-radius-md);">'
        '<p style="margin:0 0 4px;padding:0 8px;font-size:11px;color:var(--color-text-tertiary);">'
        "T_game 刷新率曲线（Hz）</p>"
        f'<div style="width:100%;box-sizing:border-box;">{svg}</div></div>'
    )


def _strategy_refresh_section(
    ctx: dict[str, Any],
    peer: dict[str, Any] | None,
    *,
    label_a: str,
    label_b: str,
) -> str:
    def _pack(c: dict[str, Any]) -> dict[str, Any]:
        inv = ((c.get("game_brightness") or {}).get("brightness_investigation") or {})
        s6 = inv.get("step6_refresh_rate") or {}
        if not isinstance(s6, dict) or s6.get("coverage") == "missing":
            return {}
        supported = s6.get("supported_fps") or {}
        actual = s6.get("actual_fps") or {}
        return {
            "supported": supported.get("last_hz"),
            "actual_last": actual.get("last_hz"),
            "actual_avg": actual.get("avg_hz"),
            "sup_n": supported.get("sample_count"),
            "act_n": actual.get("sample_count"),
            "summary": str(s6.get("report_summary") or ""),
            "evidence": list(s6.get("report_evidence") or []),
        }

    a = _pack(ctx)
    b = _pack(peer) if peer else {}
    if not a and not b:
        return ""
    def _fmt(v: Any, unit: str = "Hz") -> str:
        if v is None or v == "":
            return "—"
        try:
            return f"{float(v):g} {unit}"
        except (TypeError, ValueError):
            return str(v)

    rows = [
        ("支持刷新率 (PowerHal)", _fmt(a.get("supported")), _fmt(b.get("supported")) if peer else None),
        ("实际送显末值 (hwcomposer)", _fmt(a.get("actual_last")), _fmt(b.get("actual_last")) if peer else None),
        ("实际送显均值", _fmt(a.get("actual_avg")), _fmt(b.get("actual_avg")) if peer else None),
        ("PowerHal 采样数", str(a.get("sup_n") or "—"), str(b.get("sup_n") or "—") if peer else None),
        ("hwcomposer 采样数", str(a.get("act_n") or "—"), str(b.get("act_n") or "—") if peer else None),
    ]
    summary = ""
    if peer and a and b:
        try:
            da = float(a.get("actual_avg") or a.get("actual_last") or 0)
            db = float(b.get("actual_avg") or b.get("actual_last") or 0)
            if da and db:
                diff = da - db
                summary = (
                    f"{label_a} 实际均值 {_fmt(da)}，{label_b} {_fmt(db)}，"
                    f"差 {diff:+.1f} Hz。"
                )
        except (TypeError, ValueError):
            summary = "两侧均观测到刷新率采样。"
    else:
        summary = str((a or b).get("summary") or "已观测屏幕刷新率。")
    snaps = list(a.get("evidence") or [])
    if peer:
        snaps.extend([f"[{label_b}] {x}" for x in (b.get("evidence") or [])])
    charts = _strategy_dual_charts(
        _refresh_rate_chart_html(ctx),
        _refresh_rate_chart_html(peer) if peer else "",
        label_a=label_a,
        label_b=label_b,
    )
    return _strategy_item_html(
        "屏幕刷新率",
        badge_kind="observe",
        summary=summary,
        table_rows=rows,
        label_a=label_a,
        label_b=label_b if peer else "",
        charts_html=charts,
        snaps=snaps,
    )


def _frame_rate_chart_html(ctx: dict[str, Any]) -> str:
    # 复用现有帧率媒体块中的曲线部分：抽取简版主图层曲线
    fr = _cpu_gpu_ddr_block(ctx).get("frame_rate") or {}
    layers = fr.get("layers") or []
    main = fr.get("main_game_layer") or {}
    if not main:
        main = next((x for x in layers if x.get("is_game_layer")), {})
    tl = (main.get("fps_timeline") or []) if isinstance(main, dict) else []
    if len(tl) < 2:
        return ""
    avg = None
    try:
        avg = float(main.get("avg_queuebuffer_fps") or main.get("merged_layer_avg_fps"))
    except (TypeError, ValueError):
        avg = None
    svg = _fps_curve_svg(tl, avg_fps=avg, show_value_labels=True, height=200)
    if not svg:
        return ""
    return (
        '<div style="padding:6px 0;width:100%;box-sizing:border-box;'
        'background:var(--color-background-primary);'
        'border:0.5px solid var(--color-border-tertiary);border-radius:var(--border-radius-md);">'
        '<p style="margin:0 0 4px;padding:0 8px;font-size:11px;color:var(--color-text-tertiary);">'
        "游戏主图层帧率</p>"
        f'<div style="width:100%;box-sizing:border-box;">{svg}</div></div>'
    )


def _strategy_frame_section(
    ctx: dict[str, Any],
    peer: dict[str, Any] | None,
    *,
    label_a: str,
    label_b: str,
) -> str:
    def _pack(c: dict[str, Any]) -> dict[str, Any]:
        fr = _cpu_gpu_ddr_block(c).get("frame_rate") or {}
        if fr.get("coverage") == "missing":
            return {}
        main = fr.get("main_game_layer") or {}
        return {
            "avg": main.get("avg_queuebuffer_fps") or main.get("merged_layer_avg_fps"),
            "min": main.get("min_queuebuffer_fps"),
            "max": main.get("max_queuebuffer_fps"),
            "n": main.get("sample_count"),
            "name": _layer_display_name(main, show_hint=True) if main else "—",
            "layers": len(fr.get("layers") or []),
        }

    a = _pack(ctx)
    b = _pack(peer) if peer else {}
    if not a and not b:
        return ""
    def _f(v: Any) -> str:
        if v is None or v == "":
            return "—"
        try:
            return f"{float(v):g} fps"
        except (TypeError, ValueError):
            return str(v)
    rows = [
        ("游戏主图层", str(a.get("name") or "—"), str(b.get("name") or "—") if peer else None),
        ("平均帧率", _f(a.get("avg")), _f(b.get("avg")) if peer else None),
        ("帧率范围", (f"{a.get('min')}~{a.get('max')}" if a.get("min") is not None else "—"),
         (f"{b.get('min')}~{b.get('max')}" if peer and b.get("min") is not None else ("—" if peer else None))),
        ("采样数", str(a.get("n") or "—"), str(b.get("n") or "—") if peer else None),
    ]
    summary = "已观测游戏图层帧率。"
    if peer and a.get("avg") is not None and b.get("avg") is not None:
        try:
            da, db = float(a["avg"]), float(b["avg"])
            summary = f"{label_a} 主图层均值 {da:g} fps，{label_b} {db:g} fps，差 {da-db:+.1f} fps。"
        except (TypeError, ValueError):
            pass
    return _strategy_item_html(
        "帧率",
        badge_kind="observe",
        summary=summary,
        table_rows=rows,
        label_a=label_a,
        label_b=label_b if peer else "",
        charts_html=_strategy_dual_charts(
            _frame_rate_chart_html(ctx),
            _frame_rate_chart_html(peer) if peer else "",
            label_a=label_a,
            label_b=label_b,
        ),
        snaps=[],
    )


def _strategy_backlight2_section(
    ctx: dict[str, Any],
    peer: dict[str, Any] | None,
    *,
    label_a: str,
    label_b: str,
) -> str:
    def _pack(c: dict[str, Any]) -> dict[str, Any]:
        s3 = ((c.get("game_brightness") or {}).get("brightness_investigation") or {}).get("step3_backlight_2_0") or {}
        if not isinstance(s3, dict) or s3.get("skipped"):
            return {"skipped": True}
        return {
            "nits": s3.get("realtime_nits"),
            "drop": s3.get("drop_ratio_pct"),
            "exp": s3.get("expected_brightness_drop_pct"),
            "applied": bool(s3.get("applied") or s3.get("effective")),
            "status": str(s3.get("status") or ""),
            "summary": str(s3.get("report_summary") or s3.get("note") or s3.get("message") or ""),
            "evidence": list(s3.get("report_evidence") or []),
            "skipped": False,
        }
    a = _pack(ctx)
    b = _pack(peer) if peer else {"skipped": True}
    if a.get("skipped") and (not peer or b.get("skipped")):
        return ""
    def _f(v: Any, suf: str = "") -> str:
        if v is None or v == "":
            return "—"
        try:
            return f"{float(v):g}{suf}"
        except (TypeError, ValueError):
            return str(v)
    rows = [
        ("实时 nits", _f(a.get("nits")), _f(b.get("nits")) if peer else None),
        ("下降比例", _f(a.get("drop"), "%"), _f(b.get("drop"), "%") if peer else None),
        ("期望下降比例", _f(a.get("exp"), "%"), _f(b.get("exp"), "%") if peer else None),
        ("是否生效", "是" if a.get("applied") else ("跳过" if a.get("skipped") else "否"),
         ("是" if b.get("applied") else ("跳过" if b.get("skipped") else "否")) if peer else None),
    ]
    applied = bool(a.get("applied"))
    badge = "ok" if applied else ("skip" if a.get("skipped") else "warn")
    if peer:
        summary = (
            f"{label_a} {'已生效' if a.get('applied') else '未生效'}（nits={_f(a.get('nits'))}，降幅 {_f(a.get('drop'),'%')}）；"
            f"{label_b} {'已生效' if b.get('applied') else '未生效'}（nits={_f(b.get('nits'))}，降幅 {_f(b.get('drop'),'%')}）。"
        )
    else:
        summary = str(a.get("summary") or "背光2.0结论见上表。")
    snaps = list(a.get("evidence") or [])
    if peer:
        snaps.extend([f"[{label_b}] {x}" for x in (b.get("evidence") or [])])
    return _strategy_item_html(
        "背光2.0",
        badge_kind=badge,
        summary=summary,
        table_rows=rows,
        label_a=label_a,
        label_b=label_b if peer else "",
        snaps=snaps,
    )


def _strategy_aal_section(
    ctx: dict[str, Any],
    peer: dict[str, Any] | None,
    *,
    label_a: str,
    label_b: str,
) -> str:
    def _fmt_nits(v: Any) -> str:
        if v is None or v == "":
            return "—"
        try:
            f = float(v)
            return str(int(round(f))) if abs(f - round(f)) < 0.05 else f"{f:.1f}"
        except (TypeError, ValueError):
            return str(v)

    def _beautify_aal_timeline(text: Any) -> str:
        """曲线值（nit）→ …；兼容旧格式「4095 700nit」。"""
        raw = str(text or "").strip()
        if not raw or raw == "—":
            return "—"
        parts = re.split(r"\s*→\s*", raw)
        out: list[str] = []
        for part in parts:
            s = part.strip()
            if not s:
                continue
            # 已是新格式：4095（700nit）
            if re.fullmatch(r"\d+[（(]\d+(?:\.\d+)?nit[）)]", s, flags=re.IGNORECASE):
                out.append(s.replace("(", "（").replace(")", "）"))
                continue
            # 旧格式：4095 700nit / 曲线4095/700nit
            m = re.fullmatch(
                r"(?:曲线)?(\d+)\s*[ /]?\s*(\d+(?:\.\d+)?)\s*nit",
                s,
                flags=re.IGNORECASE,
            )
            if m:
                curve, nits = m.group(1), m.group(2)
                try:
                    nits_s = str(int(round(float(nits))))
                except (TypeError, ValueError):
                    nits_s = nits
                out.append(f"{curve}（{nits_s}nit）")
                continue
            m2 = re.fullmatch(r"(?:曲线)?(\d+)", s)
            if m2:
                out.append(f"曲线{m2.group(1)}")
                continue
            out.append(s)
        return " → ".join(out) if out else "—"

    def _pack(c: dict[str, Any]) -> dict[str, Any]:
        s4 = ((c.get("game_brightness") or {}).get("brightness_investigation") or {}).get("step4_aal_strategy") or {}
        if not isinstance(s4, dict) or s4.get("coverage") == "missing":
            return {}
        timeline = _beautify_aal_timeline(
            s4.get("timeline")
            or (
                f"{s4.get('in_game_bl_from') or s4.get('scene_start_bl') or s4.get('first_bl')}"
                f" → {s4.get('in_game_bl_to') or s4.get('stable_bl') or s4.get('last_bl')}"
            )
        )
        return {
            "timeline": timeline,
            "summary": s4.get("report_summary") or s4.get("note") or "",
            "effective": bool(s4.get("effective") or s4.get("active")),
            "from": s4.get("in_game_bl_from") or s4.get("scene_start_bl") or s4.get("first_bl"),
            "to": s4.get("in_game_bl_to") or s4.get("stable_bl") or s4.get("last_bl"),
            "pre_nits": s4.get("pre_nits"),
            "in_nits": s4.get("in_game_nits"),
            "evidence": list(s4.get("report_evidence") or []),
        }
    a = _pack(ctx)
    b = _pack(peer) if peer else {}
    if not a and not b:
        return ""
    def _f(v: Any) -> str:
        return "—" if v is None or v == "" else str(v)
    rows = [
        ("背光时间线（曲线/nit）", _f(a.get("timeline")), _f(b.get("timeline")) if peer else None),
        ("进游戏前曲线", _f(a.get("from")), _f(b.get("from")) if peer else None),
        ("局内稳定曲线", _f(a.get("to")), _f(b.get("to")) if peer else None),
        ("进游戏前 nits", _fmt_nits(a.get("pre_nits")), _fmt_nits(b.get("pre_nits")) if peer else None),
        ("局内 nits", _fmt_nits(a.get("in_nits")), _fmt_nits(b.get("in_nits")) if peer else None),
    ]
    badge = "ok" if a.get("effective") else "warn"
    if peer:
        summary = (
            f"{label_a}：{a.get('timeline') or '—'}；"
            f"{label_b}：{b.get('timeline') or '—'}。"
        )
    else:
        summary = str(a.get("timeline") or a.get("summary") or "AAL/降背光结论见上表。")
        if a.get("summary") and "→" not in str(summary):
            summary = _beautify_aal_timeline(a.get("summary"))
    snaps = list(a.get("evidence") or [])
    if peer:
        snaps.extend([f"[{label_b}] {x}" for x in (b.get("evidence") or [])])
    return _strategy_item_html(
        "AAL背光",
        badge_kind=badge,
        summary=summary,
        table_rows=rows,
        label_a=label_a,
        label_b=label_b if peer else "",
        snaps=snaps,
    )


def _strategy_perf_section(
    ctx: dict[str, Any],
    peer: dict[str, Any] | None,
    *,
    label_a: str,
    label_b: str,
) -> str:
    def _pack(c: dict[str, Any]) -> dict[str, Any]:
        perf = _cpu_gpu_ddr_block(c).get("cpu_perf_lock") or {}
        if perf.get("coverage") == "missing":
            return {}
        strategies = perf.get("by_strategy_idx") or []
        top = strategies[0] if strategies else {}
        return {
            "total": perf.get("total_acquire_count"),
            "n_strat": len(strategies),
            "top_idx": top.get("idx"),
            "top_label": top.get("label"),
            "top_cnt": top.get("acquire_count"),
            "top_user": top.get("top_lock_user"),
        }
    a = _pack(ctx)
    b = _pack(peer) if peer else {}
    if not a and not b:
        return ""
    def _f(v: Any) -> str:
        return "—" if v is None or v == "" else str(v)
    rows = [
        ("T_game acquire 合计", _f(a.get("total")), _f(b.get("total")) if peer else None),
        ("策略数", _f(a.get("n_strat")), _f(b.get("n_strat")) if peer else None),
        ("Top 策略", (f"idx {a.get('top_idx')} ({a.get('top_label') or '—'})" if a else "—"),
         (f"idx {b.get('top_idx')} ({b.get('top_label') or '—'})" if peer and b else ("—" if peer else None))),
        ("Top 次数 / 用户", (f"{_f(a.get('top_cnt'))} · {_f(a.get('top_user'))}" if a else "—"),
         (f"{_f(b.get('top_cnt'))} · {_f(b.get('top_user'))}" if peer and b else ("—" if peer else None))),
    ]
    summary = "已观测 perfLockAcq 提频。"
    if peer and a.get("total") is not None and b.get("total") is not None:
        try:
            summary = (
                f"{label_a} acquire {int(a['total'])} 次，{label_b} {int(b['total'])} 次，"
                f"差 {int(a['total'])-int(b['total']):+d}。"
            )
        except (TypeError, ValueError):
            pass
    return _strategy_item_html(
        "perfLockAcq提频",
        badge_kind="observe",
        summary=summary,
        table_rows=rows,
        label_a=label_a,
        label_b=label_b if peer else "",
    )


def _thermal_chart_html(ctx: dict[str, Any]) -> str:
    th = ctx.get("game_thermal") or {}
    report = th.get("thermal_report") or {}
    curves = report.get("temp_curves") or {}
    timeline = report.get("temp_timeline") or []
    max_temp = report.get("temp_max_c")
    series_spec = [
        ("vt_shell", "vt_shell 壳温", "#c2410c"),
        ("SKIN", "SKIN", "#2563eb"),
        ("CPU", "CPU", "#16a34a"),
    ]
    series: list[dict[str, Any]] = []
    for key, label, color in series_spec:
        block = curves.get(key) or {}
        pts = block.get("points") or []
        if len(pts) >= 2:
            series.append({"key": key, "label": label, "color": color, "points": pts})
    if not series and timeline:
        series.append({"key": "temp", "label": "温度", "color": "#c2410c", "points": timeline})
    if not series:
        return ""

    # temperature 的时间范围，用于对齐“亮度曲线 / 温度曲线”的 x 轴
    temp_all_points: list[dict[str, Any]] = []
    for s in series:
        temp_all_points.extend(s.get("points") or [])
    temp_times: list[tuple[datetime, str]] = []
    for p in temp_all_points:
        t_raw = str(p.get("time") or "")
        dt = _parse_curve_time(t_raw)
        if dt is not None:
            temp_times.append((dt, t_raw))

    temp_t0_dt = min(temp_times, key=lambda x: x[0])[0] if temp_times else None
    temp_t1_dt = max(temp_times, key=lambda x: x[0])[0] if temp_times else None
    t0_str = next((t for dt, t in temp_times if temp_t0_dt is not None and dt == temp_t0_dt), "") if temp_times else ""
    t1_str = next((t for dt, t in temp_times if temp_t1_dt is not None and dt == temp_t1_dt), "") if temp_times else ""

    # —— 亮度曲线（上方）——
    brightness_svg = ""
    try:
        gb = ctx.get("game_brightness") or {}
        inv = ((gb.get("brightness_investigation") or {}) if isinstance(gb.get("brightness_investigation"), dict) else {})
        step4 = (inv or {}).get("step4_aal_strategy") or {}
        step5 = (inv or {}).get("step5_thermal_control") or {}
        step3 = (inv or {}).get("step3_backlight_2_0") or {}

        curve_max = step4.get("curve_max") or 4095
        level_max = 255

        def _as_float(v: Any) -> float | None:
            try:
                if v is None:
                    return None
                return float(v)
            except (TypeError, ValueError):
                return None

        def _derive_level_from_curve(curve_val: int | float | None) -> int | None:
            if curve_val is None or curve_max in (None, 0):
                return None
            try:
                return int(round(float(curve_val) / float(curve_max) * float(level_max)))
            except (TypeError, ValueError):
                return None

        # brightness points：来自
        # - step4.key_points：背光2.0/AAL（main: curve_val；sys: dpc_nits）
        # - step5.relevant_hits：thermalLightController（thermal: level / brightness_nits）
        bp_all: list[dict[str, Any]] = []

        # 1) 背光2.0 / AAL：step4 key_points
        for kp in step4.get("key_points") or []:
            if not isinstance(kp, dict):
                continue
            time_raw = kp.get("time")
            if not time_raw:
                continue
            nits = _as_float(kp.get("dpc_nits")) if kp.get("dpc_nits") is not None else _as_float(kp.get("nits"))
            if nits is None:
                continue
            curve_val = kp.get("curve_val")
            curve_i = int(curve_val) if curve_val is not None else None
            level_i = _derive_level_from_curve(curve_i)
            cause = "背光2.0" if kp.get("dpc_raw") else ("AAL" if kp.get("aal_raw") else "AAL")

            dt_bp = _parse_curve_time(str(time_raw))
            if dt_bp is None:
                continue
            # 约束到 temperature 时间窗内，避免 x 轴拖得太宽
            if temp_t0_dt and dt_bp < temp_t0_dt:
                continue
            if temp_t1_dt and dt_bp > temp_t1_dt:
                continue
            bp_all.append(
                {
                    "_dt": dt_bp,
                    "time": time_raw,
                    "nits": nits,
                    "curve_val": curve_i,
                    "level": level_i,
                    "cause": cause,
                }
            )

        # 1.1) 背光2.0：step3 t_game_events（补全即时 DPC/BrightnessEvent 亮度变化点）
        for ev in step3.get("t_game_events") or []:
            if not isinstance(ev, dict):
                continue
            time_raw = ev.get("time")
            if not time_raw:
                continue
            nits = _as_float(ev.get("nits"))
            if nits is None:
                continue
            dt_bp = _parse_curve_time(str(time_raw))
            if dt_bp is None:
                continue
            if temp_t0_dt and dt_bp < temp_t0_dt:
                continue
            if temp_t1_dt and dt_bp > temp_t1_dt:
                continue

            # DPC 只给 brt(brt_pct) 与 nits；用它近似主 log 的 curve/level 展示（detail 层面，不影响 x 对齐）
            brt_pct = _as_float(ev.get("brt_pct"))
            curve_i = int(round(float(curve_max) * float(brt_pct) / 100.0)) if brt_pct is not None else None
            level_i = int(round(float(level_max) * float(brt_pct) / 100.0)) if brt_pct is not None else None

            bp_all.append(
                {
                    "_dt": dt_bp,
                    "time": time_raw,
                    "nits": nits,
                    "curve_val": curve_i,
                    "level": level_i,
                    "cause": "背光2.0",
                }
            )

        # 2) thermal：step5 relevant_hits
        for h in step5.get("relevant_hits") or []:
            if not isinstance(h, dict):
                continue
            time_raw = h.get("time")
            if not time_raw:
                continue
            nits = _as_float(h.get("brightness_nits"))
            if nits is None:
                continue
            dt_h = _parse_curve_time(str(time_raw))
            if dt_h is None:
                continue
            if temp_t0_dt and dt_h < temp_t0_dt:
                continue
            if temp_t1_dt and dt_h > temp_t1_dt:
                continue

            # thermal 点的 curve_val：尽量从 step4 key_points 按时间取最近值
            curve_i = None
            if bp_all:
                nearest = min(bp_all, key=lambda x: abs((x.get("_dt") or datetime.min) - dt_h).total_seconds())
                curve_i = nearest.get("curve_val")

            # thermalLightController 的 level 可能是温控档位，不一定等于 0-255 亮度 level；
            # 因此优先用推断出的 curve_i 反推展示 level/255。
            level_i = _derive_level_from_curve(curve_i)

            bp_all.append(
                {
                    "_dt": dt_h,
                    "time": time_raw,
                    "nits": nits,
                    "curve_val": curve_i,
                    "level": level_i,
                    "cause": "thermal",
                }
            )

        # 去重：只合并极近似（<=3ms）的重复行；避免把 thermal(500) 与 DPC(450) 在 16ms 内的两次变化合并掉
        bp_all.sort(key=lambda x: x.get("_dt") or datetime.min)
        merged_bp: list[dict[str, Any]] = []
        for bp in bp_all:
            if not merged_bp:
                merged_bp.append(bp)
                continue
            prev = merged_bp[-1]
            prev_dt = prev.get("_dt")
            if isinstance(prev_dt, datetime):
                if abs((bp.get("_dt") or prev_dt) - prev_dt).total_seconds() <= 0.003:
                    # thermal > 背光2.0 > AAL
                    pri = {"thermal": 2, "背光2.0": 1, "AAL": 0}
                    if pri.get(bp.get("cause"), 0) > pri.get(prev.get("cause"), 0):
                        merged_bp[-1] = bp
                    continue
            merged_bp.append(bp)

        # brightness_plot_points：用于画曲线
        brightness_plot_points: list[dict[str, Any]] = [
            {"time": bp.get("time"), "temp_c": bp.get("nits")} for bp in merged_bp if bp.get("time") and bp.get("nits") is not None
        ]
        if merged_bp and temp_t0_dt and temp_t1_dt and t0_str and t1_str:
            def _nearest_bp(dt: datetime) -> dict[str, Any]:
                return min(merged_bp, key=lambda x: abs((x.get("_dt") or datetime.min) - dt).total_seconds())

            bp0 = _nearest_bp(temp_t0_dt)
            bp1 = _nearest_bp(temp_t1_dt)
            brightness_plot_points = (
                [{"time": t0_str, "temp_c": bp0.get("nits")}] + brightness_plot_points + [{"time": t1_str, "temp_c": bp1.get("nits")}]
            )

        # markers：竖线标注在 brightness 变化点
        if brightness_plot_points:
            marker_color = {"thermal": "#7c3aed", "背光2.0": "#b45309", "AAL": "#3b82f6"}
            brightness_markers: list[dict[str, Any]] = []
            for bp in merged_bp:
                nits = bp.get("nits")
                try:
                    nits_i = int(round(float(nits)))
                except (TypeError, ValueError):
                    nits_i = None
                cause = str(bp.get("cause") or "")
                label = f"{cause} {nits_i}nit" if nits_i is not None else cause

                curve_i = bp.get("curve_val")
                level_i = bp.get("level")
                detail_bits: list[str] = []
                if level_i is not None:
                    detail_bits.append(f"level={int(level_i)}/255")
                if curve_i is not None:
                    try:
                        detail_bits.append(f"curve={int(curve_i)}/{int(curve_max)}")
                    except (TypeError, ValueError):
                        pass
                if nits is not None:
                    try:
                        detail_bits.append(f"{int(round(float(nits)))}nit")
                    except (TypeError, ValueError):
                        pass
                detail = " · ".join(detail_bits)

                brightness_markers.append(
                    {
                        "time": bp.get("time"),
                        "label": label,
                        "detail": detail,
                        "color": marker_color.get(cause) or "#b45309",
                        "value": float(nits) if nits is not None else None,
                    }
                )

            max_nits = max((p.get("temp_c") for p in brightness_plot_points if p.get("temp_c") is not None), default=None)
            brightness_svg = _temp_curve_svg(
                series=[
                    {
                        "key": "brightness",
                        "label": "亮度（nit）",
                        "color": "#0ea5e9",
                        "points": brightness_plot_points,
                    }
                ],
                max_temp=max_nits if isinstance(max_nits, (int, float)) else None,
                markers=brightness_markers,
                width=1200,
                height=140,
                y_unit_label="nit",
            )
    except Exception:
        brightness_svg = ""

    markers = _collect_thermal_chart_markers(ctx)
    svg = _temp_curve_svg(
        series=series,
        max_temp=max_temp if isinstance(max_temp, (int, float)) else None,
        markers=markers,
    )
    if not svg:
        return ""
    legend_extra = ""
    if markers:
        kinds = {str(m.get("kind") or "") for m in markers}
        bits = []
        if "freq" in kinds:
            bits.append('<span style="color:#b45309;">│ 限频</span>')
        if "dim" in kinds:
            bits.append('<span style="color:#7c3aed;">│ 降亮</span>')
        if bits:
            legend_extra = (
                '<p style="margin:0 0 4px;padding:0 8px;font-size:11px;color:var(--color-text-tertiary);">'
                f'标注：{"　".join(bits)}（竖线=生效时刻）</p>'
            )
    brightness_legend = ""
    if brightness_svg:
        brightness_legend = (
            '<p style="margin:0 0 4px;padding:0 8px;font-size:11px;color:var(--color-text-tertiary);">'
            "标注：AAL / 背光2.0 / thermal（竖线=亮度变化点）</p>"
        )

    # 亮度曲线在上，温度曲线在下：对齐两个曲线时间
    return (
        '<div style="padding:6px 0;width:100%;box-sizing:border-box;'
        'background:var(--color-background-primary);'
        'border:0.5px solid var(--color-border-tertiary);border-radius:var(--border-radius-md);">'
        '<p style="margin:0 0 4px;padding:0 8px;font-size:11px;color:var(--color-text-tertiary);">'
        "亮度曲线（nit）</p>"
        f"{brightness_legend}"
        f"{('<div style=\"width:100%;box-sizing:border-box;\">' + brightness_svg + '</div>') if brightness_svg else ''}"
        '<p style="margin:8px 0 4px;padding:0 8px;font-size:11px;color:var(--color-text-tertiary);">'
        "温度曲线</p>"
        f"{legend_extra}"
        f'<div style="width:100%;box-sizing:border-box;">{svg}</div></div>'
    )


def _collect_thermal_chart_markers(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    """收集 thermal 限频 / 降亮生效点，供温度曲线标注。"""
    markers: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    def _add(
        *,
        kind: str,
        time_raw: Any,
        label: str,
        detail: str = "",
        color: str = "",
    ) -> None:
        t = str(time_raw or "").strip()
        if not t or not label:
            return
        key = (kind, t[:19], label)
        if key in seen:
            return
        seen.add(key)
        markers.append(
            {
                "kind": kind,
                "time": t,
                "label": label,
                "detail": detail,
                "color": color
                or ("#b45309" if kind == "freq" else "#7c3aed" if kind == "dim" else "#64748b"),
            }
        )

    th = ctx.get("game_thermal") or {}
    report = th.get("thermal_report") if isinstance(th, dict) else {}
    if not isinstance(report, dict):
        report = {}

    # 1) 限频档位（thermal_report.freq_throttle.gears）
    freq = report.get("freq_throttle") if isinstance(report.get("freq_throttle"), dict) else {}
    for g in freq.get("gears") or []:
        if not isinstance(g, dict):
            continue
        gear = g.get("gear")
        status = str(g.get("throttle_status") or "").strip()
        temp = g.get("temp_c")
        bits = ["限频"]
        if gear is not None:
            bits.append(f"档{gear}")
        if status:
            bits.append(status)
        detail_bits = []
        if temp is not None:
            try:
                detail_bits.append(f"{float(temp):.1f}℃")
            except (TypeError, ValueError):
                detail_bits.append(f"{temp}℃")
        limits = g.get("active_limits")
        if isinstance(limits, dict):
            nz = {k: v for k, v in limits.items() if v not in (None, 0, "0", "")}
            if nz:
                detail_bits.append(
                    "、".join(f"{k}={v}" for k, v in list(nz.items())[:3])
                )
        _add(
            kind="freq",
            time_raw=g.get("time"),
            label=" ".join(bits),
            detail=" · ".join(detail_bits),
        )

    # 2) 限频状态切换（thermal_throttle.events，去重）
    tt = th.get("thermal_throttle") if isinstance(th, dict) else {}
    if isinstance(tt, dict):
        last_st = None
        for ev in tt.get("events") or []:
            if not isinstance(ev, dict):
                continue
            st = str(ev.get("throttle_status") or "").strip()
            if not st or st == last_st:
                continue
            last_st = st
            # 若 gears 已覆盖相近时刻则跳过重复标签风格，仍允许补充
            label = f"限频 {st}"
            detail_bits = []
            if ev.get("temp_c") is not None:
                try:
                    detail_bits.append(f"{float(ev['temp_c']):.1f}℃")
                except (TypeError, ValueError):
                    detail_bits.append(f"{ev['temp_c']}℃")
            if ev.get("thermalux_freq") is not None:
                detail_bits.append(f"freq={ev.get('thermalux_freq')}")
            if ev.get("cpu") is not None:
                detail_bits.append(f"cpu={ev.get('cpu')}")
            # 仅当 gears 为空时用 events，避免双标注刷屏
            if not (freq.get("gears") or []):
                _add(
                    kind="freq",
                    time_raw=ev.get("time"),
                    label=label,
                    detail=" · ".join(detail_bits),
                )

    # 3) 降亮：brightness step5 relevant_hits（T_game）
    gb = ctx.get("game_brightness") or {}
    s5 = (
        ((gb.get("brightness_investigation") or {}).get("step5_thermal_control") or {})
        if isinstance(gb, dict)
        else {}
    )
    hits = []
    if isinstance(s5, dict):
        hits = [h for h in (s5.get("relevant_hits") or []) if isinstance(h, dict)]
        if not hits:
            hits = [
                h
                for h in (s5.get("hits") or [])
                if isinstance(h, dict) and str(h.get("window") or "") in ("T_game", "game_entry", "launch")
            ]
    for h in hits:
        win = str(h.get("window") or "")
        # 优先游戏内；T_pre 仅保留贴近进游戏的（其余由曲线时间窗裁剪）
        if win and win not in ("T_game", "game_entry", "launch", "T_pre", ""):
            continue
        level = h.get("level")
        nits = h.get("brightness_nits")
        bits = ["降亮"]
        if level is not None:
            bits.append(f"Lv{level}")
        if nits is not None:
            try:
                bits.append(f"{int(round(float(nits)))}nit")
            except (TypeError, ValueError):
                bits.append(f"{nits}nit")
        detail_bits = []
        if h.get("temp_c") is not None:
            try:
                detail_bits.append(f"{float(h['temp_c']):.1f}℃")
            except (TypeError, ValueError):
                detail_bits.append(f"{h['temp_c']}℃")
        pkg = str(h.get("package") or "").strip()
        if pkg:
            detail_bits.append(pkg.split(".")[-1])
        _add(
            kind="dim",
            time_raw=h.get("time"),
            label=" ".join(bits),
            detail=" · ".join(detail_bits),
        )

    # 4) thermal_backlight.events：若尚无降亮点，至少标 update 时刻
    tb = th.get("thermal_backlight") if isinstance(th, dict) else {}
    if isinstance(tb, dict) and not any(m.get("kind") == "dim" for m in markers):
        for ev in tb.get("events") or []:
            if not isinstance(ev, dict):
                continue
            _add(
                kind="dim",
                time_raw=ev.get("time"),
                label="降亮",
                detail=str(ev.get("action") or ev.get("pattern_id") or ""),
            )

    # 按时间排序，同种过多时节流（最多 8 个）
    def _sort_key(m: dict[str, Any]) -> datetime:
        return _parse_curve_time(str(m.get("time") or "")) or datetime.min

    markers.sort(key=_sort_key)
    if len(markers) > 8:
        # 保留每种前几个 + 最后几个
        freq_m = [m for m in markers if m.get("kind") == "freq"]
        dim_m = [m for m in markers if m.get("kind") == "dim"]
        other = [m for m in markers if m.get("kind") not in ("freq", "dim")]
        markers = (freq_m[:3] + dim_m[:4] + other[:1])[:8]
        markers.sort(key=_sort_key)
    return markers


def _strategy_thermal_section(
    ctx: dict[str, Any],
    peer: dict[str, Any] | None,
    *,
    label_a: str,
    label_b: str,
) -> str:
    def _pack(c: dict[str, Any]) -> dict[str, Any]:
        th = c.get("game_thermal") or {}
        if not isinstance(th, dict) or not th:
            return {}
        report = th.get("thermal_report") or {}
        dim = report.get("backlight_dim") or {}
        freq = report.get("freq_throttle") or {}
        if not dim and not freq:
            during = (th.get("thermal_summary") or {}).get("during_game") or {}
            dim = {"report_summary": "thermal降温/降亮：生效" if during.get("thermal_backlight") else "thermal降温/降亮：未生效", "report_evidence": []}
            freq = {"report_summary": "thermal限频：生效" if during.get("freq_throttle") else "thermal限频：未生效", "report_evidence": []}
        t_game = (th.get("temperature") or {}).get("T_game") or {}
        return {
            "dim": str(dim.get("report_summary") or ""),
            "freq": str(freq.get("report_summary") or ""),
            "dim_on": "生效" in str(dim.get("report_summary") or "") and "未生效" not in str(dim.get("report_summary") or ""),
            "freq_on": "生效" in str(freq.get("report_summary") or "") and "未生效" not in str(freq.get("report_summary") or ""),
            "max_c": report.get("temp_max_c") or t_game.get("max_c"),
            "evidence": list(dim.get("report_evidence") or []) + list(freq.get("report_evidence") or []),
        }
    a = _pack(ctx)
    b = _pack(peer) if peer else {}
    if not a and not b:
        return ""
    def _f(v: Any) -> str:
        if v is None or v == "":
            return "—"
        try:
            return f"{float(v):g} ℃"
        except (TypeError, ValueError):
            return str(v)
    rows = [
        ("限频策略", a.get("freq") or ("生效" if a.get("freq_on") else "未生效"),
         (b.get("freq") or ("生效" if b.get("freq_on") else "未生效")) if peer else None),
        ("降温/降亮策略", a.get("dim") or ("生效" if a.get("dim_on") else "未生效"),
         (b.get("dim") or ("生效" if b.get("dim_on") else "未生效")) if peer else None),
        ("T_game 最高温", _f(a.get("max_c")), _f(b.get("max_c")) if peer else None),
    ]
    any_on = bool(a.get("freq_on") or a.get("dim_on"))
    badge = "ok" if any_on else "warn"
    if peer:
        summary = (
            f"限频：{label_a}{'开' if a.get('freq_on') else '关'} / {label_b}{'开' if b.get('freq_on') else '关'}；"
            f"降温：{label_a}{'开' if a.get('dim_on') else '关'} / {label_b}{'开' if b.get('dim_on') else '关'}。"
        )
    else:
        summary = f"{a.get('freq') or ''}；{a.get('dim') or ''}".strip("；")
    snaps = list(a.get("evidence") or [])
    if peer:
        snaps.extend([f"[{label_b}] {x}" for x in (b.get("evidence") or [])])
    return _strategy_item_html(
        "thermal策略",
        badge_kind=badge,
        summary=summary,
        table_rows=rows,
        label_a=label_a,
        label_b=label_b if peer else "",
        charts_html=_strategy_dual_charts(
            _thermal_chart_html(ctx),
            _thermal_chart_html(peer) if peer else "",
            label_a=label_a,
            label_b=label_b,
        ),
        snaps=snaps,
    )


def _fmt_bytes_compact(value: Any) -> str:
    if value is None or value == "":
        return "—"
    try:
        n = float(value)
    except (TypeError, ValueError):
        return str(value)
    sign = "-" if n < 0 else ""
    n = abs(n)
    if n >= 1_000_000_000:
        return f"{sign}{n / 1_000_000_000:.2f} GB"
    if n >= 1_000_000:
        return f"{sign}{n / 1_000_000:.1f} MB"
    if n >= 1000:
        return f"{sign}{n / 1000:.1f} KB"
    return f"{sign}{int(n)} B"


def _fmt_dbm_compact(value: Any, *, unit: str = "dBm") -> str:
    if value is None or value == "":
        return "—"
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(f - round(f)) < 0.05:
        return f"{int(round(f))} {unit}"
    return f"{f:.1f} {unit}"


def _network_quality_usage_text(usage: Any) -> str:
    if not isinstance(usage, dict) or not usage:
        return "—"
    order = ("excellent", "good", "fair", "poor")
    label_map = {
        "excellent": "优",
        "good": "良",
        "fair": "中",
        "poor": "差",
    }
    bits: list[str] = []
    for key in order:
        if key not in usage:
            continue
        try:
            pct = float(usage[key])
        except (TypeError, ValueError):
            continue
        bits.append(f"{label_map.get(key, key)}{pct:g}%")
    if not bits:
        for key, val in usage.items():
            try:
                pct = float(val)
            except (TypeError, ValueError):
                continue
            bits.append(f"{label_map.get(str(key), key)}{pct:g}%")
    return " / ".join(bits) if bits else "—"


def _network_analysis_pack(ctx: dict[str, Any]) -> dict[str, Any]:
    net = ctx.get("game_network") or {}
    if not isinstance(net, dict) or not net:
        return {}
    inv = net.get("network_investigation") or {}
    if not isinstance(inv, dict):
        inv = {}
    s1 = inv.get("step1_wifi_rssi") if isinstance(inv.get("step1_wifi_rssi"), dict) else {}
    s2 = inv.get("step2_wifi_scenario") if isinstance(inv.get("step2_wifi_scenario"), dict) else {}
    s3 = inv.get("step3_cellular_signal") if isinstance(inv.get("step3_cellular_signal"), dict) else {}
    s4 = inv.get("step4_ccmni_transfer") if isinstance(inv.get("step4_ccmni_transfer"), dict) else {}
    dual = inv.get("dual_channel") if isinstance(inv.get("dual_channel"), dict) else {}
    rf = net.get("rf_stats") if isinstance(net.get("rf_stats"), dict) else {}
    evidence: list[str] = []
    for ev in (rf.get("raw_evidence") or [])[:6]:
        if ev:
            evidence.append(str(ev))
    for note in (rf.get("notes") or net.get("notes") or inv.get("warnings") or [])[:4]:
        if note and str(note) not in evidence:
            evidence.append(str(note))
    for ev in (dual.get("evidence") or [])[:4]:
        if ev and str(ev) not in evidence:
            evidence.append(str(ev))
    bands = s3.get("bands_observed") or []
    if isinstance(bands, list):
        bands_txt = ",".join(str(b) for b in bands) if bands else "—"
    else:
        bands_txt = str(bands) if bands not in (None, "") else "—"
    level = str(rf.get("level") or "").strip().lower()
    wa = s1.get("wifi_assistant") if isinstance(s1.get("wifi_assistant"), dict) else {}
    ssids = wa.get("ssids_observed") if isinstance(wa.get("ssids_observed"), list) else []
    ssid_txt = str(wa.get("ssid") or "").strip()
    if not ssid_txt and ssids:
        ssid_txt = ", ".join(str(x) for x in ssids if x)
    if ssid_txt and ssids and len(ssids) > 1:
        extra = [str(x) for x in ssids if str(x) != ssid_txt]
        if extra:
            ssid_txt = f"{ssid_txt}（另见 {', '.join(extra)}）"
    dual_verdict = str(dual.get("verdict") or "").strip()
    dual_map = {
        "yes": "是（双通道）",
        "no": "否",
        "no_signal_only": "否（仅蜂窝信号）",
        "cellular_only": "否（偏蜂窝）",
        "unknown": "未知",
    }
    dual_txt = dual_map.get(dual_verdict, dual.get("summary") or "—")
    return {
        "has_data": True,
        "level": level or "unknown",
        "network_type": str(rf.get("network_type") or "unknown"),
        "summary": str(rf.get("summary") or "").strip(),
        "rssi_avg": s1.get("rssi_dbm_avg"),
        "rssi_min": s1.get("rssi_dbm_min"),
        "rssi_max": s1.get("rssi_dbm_max"),
        "rssi_samples": s1.get("sample_count"),
        "rssi_curve_samples": s1.get("curve_sample_count"),
        "rssi_stats_scope": s1.get("stats_scope"),
        "rssi_t_game_sparse": bool(s1.get("t_game_rssi_sparse")),
        "rssi_quality": _network_quality_usage_text(s1.get("rssi_quality_usage_pct")),
        "rssi_curve": list(s1.get("rssi_curve") or []),
        "wifi_ssid": ssid_txt or None,
        "wifi_network_id": wa.get("network_id"),
        "wifi_user_ignored": wa.get("user_ignored"),
        "wifi_scored_current": wa.get("is_scored_current_network"),
        "wifi_no_candidate_count": wa.get("no_candidate_count"),
        "wifi_monitor_starts": wa.get("monitor_start_count_t_game"),
        "wifi_monitor_stops": wa.get("monitor_stop_count_t_game"),
        "wifi_whitelist_apps": wa.get("whitelist_top_apps_t_game"),
        "wifi_rssi_gap_conclusion": (
            s1.get("rssi_gap_conclusion")
            or wa.get("rssi_gap_conclusion")
        ),
        "dual_channel": dual_txt,
        "dual_channel_summary": dual.get("summary"),
        "is_dual_channel": bool(dual.get("is_dual_channel")),
        "cellular_data": bool(s2.get("cellular_data_during_game")),
        "wifi_if_changes": s2.get("wifi_interface_changes"),
        "rsrp_avg": s3.get("rsrp_avg"),
        "rsrq_avg": s3.get("rsrq_avg"),
        "sinr_avg": s3.get("sinr_avg"),
        "band_changed": bool(s3.get("band_changed")),
        "bands": bands_txt,
        "rsrp_curve": list(s3.get("rsrp_curve") or []),
        "rsrq_curve": list(s3.get("rsrq_curve") or []),
        "sinr_curve": list(s3.get("sinr_curve") or []),
        "ccmni_if": s4.get("primary_interface"),
        "rx_delta": s4.get("primary_rx_bytes_delta"),
        "tx_delta": s4.get("primary_tx_bytes_delta"),
        "evidence": evidence,
    }


def _network_chart_html(ctx: dict[str, Any]) -> str:
    pack = _network_analysis_pack(ctx)
    if not pack:
        return ""
    series: list[dict[str, Any]] = []
    rssi_pts = [
        {"time": p.get("time"), "temp_c": p.get("rssi_dbm")}
        for p in pack.get("rssi_curve") or []
        if isinstance(p, dict) and p.get("rssi_dbm") is not None and p.get("time")
    ]
    if len(rssi_pts) == 1:
        # 单点补一个同值点，确保折线可见
        rssi_pts = [rssi_pts[0], dict(rssi_pts[0])]
    if len(rssi_pts) >= 2:
        series.append({"key": "rssi", "label": "WiFi RSSI", "color": "#2563eb", "points": rssi_pts})
    rsrp_pts = [
        {"time": p.get("time"), "temp_c": p.get("rsrp")}
        for p in pack.get("rsrp_curve") or []
        if isinstance(p, dict) and p.get("rsrp") is not None and p.get("time")
    ]
    if len(rsrp_pts) >= 2:
        series.append({"key": "rsrp", "label": "蜂窝 RSRP", "color": "#c2410c", "points": rsrp_pts})
    if not series:
        return ""
    # RSSI 为负值，不可钳到 0；RSRP 日志值可能为正
    has_rssi = any(s.get("key") == "rssi" for s in series)
    svg = _temp_curve_svg(
        series=series,
        clamp_y_min_zero=not has_rssi,
        y_unit_label="dBm",
        height=220,
    )
    if not svg:
        return ""
    note = ""
    gap = str(pack.get("wifi_rssi_gap_conclusion") or "").strip()
    if gap:
        note = (
            '<p style="margin:4px 8px 0;font-size:11px;color:var(--color-text-tertiary);">'
            f"说明：{gap} 信号曲线仅展示游戏时段（T_game）。</p>"
        )
    elif pack.get("rssi_t_game_sparse"):
        note = (
            '<p style="margin:4px 8px 0;font-size:11px;color:var(--color-text-tertiary);">'
            "说明：局内 WiFi RSSI 埋点稀疏；信号曲线仅展示游戏时段（T_game）。</p>"
        )
    return (
        '<div style="padding:6px 0;width:100%;box-sizing:border-box;'
        'background:var(--color-background-primary);'
        'border:0.5px solid var(--color-border-tertiary);border-radius:var(--border-radius-md);">'
        '<p style="margin:0 0 4px;padding:0 8px;font-size:11px;color:var(--color-text-tertiary);">'
        "网络信号曲线（RSSI / RSRP）</p>"
        f'<div style="width:100%;box-sizing:border-box;">{svg}</div>{note}</div>'
    )


def _strategy_network_section(
    ctx: dict[str, Any],
    peer: dict[str, Any] | None,
    *,
    label_a: str,
    label_b: str,
) -> str:
    """异常问题：网络四步排查结果（双机对比表 + 信号曲线 + 日志快照）。"""

    def _pack(c: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(c, dict):
            return {}
        return _network_analysis_pack(c)

    a = _pack(ctx)
    b = _pack(peer) if peer else {}
    if not a and not b:
        return ""

    def _on_off(flag: bool) -> str:
        return "是" if flag else "否"

    def _level_txt(p: dict[str, Any]) -> str:
        if not p:
            return "—"
        lv = str(p.get("level") or "unknown")
        ntype = str(p.get("network_type") or "")
        return f"{ntype}/{lv}" if ntype else lv

    def _bool_cn(v: Any) -> str:
        if v is True:
            return "true"
        if v is False:
            return "false"
        return "—"

    def _num_or_dash(v: Any) -> str:
        return str(v) if v is not None and v != "" else "—"

    rows = [
        ("RF 判定", _level_txt(a), _level_txt(b) if peer else None),
        ("WiFi SSID", a.get("wifi_ssid") or "—", (b.get("wifi_ssid") or "—") if peer else None),
        (
            "WiFi Network ID",
            _num_or_dash(a.get("wifi_network_id")),
            _num_or_dash(b.get("wifi_network_id")) if peer else None,
        ),
        ("WiFi RSSI 均值", _fmt_dbm_compact(a.get("rssi_avg")), _fmt_dbm_compact(b.get("rssi_avg")) if peer else None),
        (
            "WiFi RSSI 范围",
            (
                f"{_fmt_dbm_compact(a.get('rssi_min'))} ~ {_fmt_dbm_compact(a.get('rssi_max'))}"
                if a.get("rssi_min") is not None or a.get("rssi_max") is not None
                else "—"
            ),
            (
                f"{_fmt_dbm_compact(b.get('rssi_min'))} ~ {_fmt_dbm_compact(b.get('rssi_max'))}"
                if peer and (b.get("rssi_min") is not None or b.get("rssi_max") is not None)
                else ("—" if peer else None)
            ),
        ),
        ("WiFi 质量占比", a.get("rssi_quality") or "—", (b.get("rssi_quality") or "—") if peer else None),
        (
            "userIgnored",
            _bool_cn(a.get("wifi_user_ignored")),
            _bool_cn(b.get("wifi_user_ignored")) if peer else None,
        ),
        (
            "isScoredCurrentNetwork",
            _bool_cn(a.get("wifi_scored_current")),
            _bool_cn(b.get("wifi_scored_current")) if peer else None,
        ),
        (
            "mNoCandidateCount",
            _num_or_dash(a.get("wifi_no_candidate_count")),
            _num_or_dash(b.get("wifi_no_candidate_count")) if peer else None,
        ),
        (
            "WiFi 监控启动次数",
            _num_or_dash(a.get("wifi_monitor_starts")),
            _num_or_dash(b.get("wifi_monitor_starts")) if peer else None,
        ),
        (
            "WiFi 监控停止次数",
            _num_or_dash(a.get("wifi_monitor_stops")),
            _num_or_dash(b.get("wifi_monitor_stops")) if peer else None,
        ),
        (
            "局内无 RSSI 原因",
            a.get("wifi_rssi_gap_conclusion") or "—",
            (b.get("wifi_rssi_gap_conclusion") or "—") if peer else None,
        ),
        (
            "双通道（WiFi+蜂窝）",
            a.get("dual_channel") or "—",
            (b.get("dual_channel") or "—") if peer else None,
        ),
        (
            "局内走蜂窝数据",
            _on_off(bool(a.get("cellular_data"))) if a else "—",
            (_on_off(bool(b.get("cellular_data"))) if b else "—") if peer else None,
        ),
        ("蜂窝 RSRP 均值", _fmt_dbm_compact(a.get("rsrp_avg")), _fmt_dbm_compact(b.get("rsrp_avg")) if peer else None),
        ("Band", a.get("bands") or "—", (b.get("bands") or "—") if peer else None),
        (
            "Band 切换",
            _on_off(bool(a.get("band_changed"))) if a else "—",
            (_on_off(bool(b.get("band_changed"))) if b else "—") if peer else None,
        ),
        (
            "ccmni 收/发增量",
            f"{_fmt_bytes_compact(a.get('rx_delta'))} / {_fmt_bytes_compact(a.get('tx_delta'))}",
            (
                f"{_fmt_bytes_compact(b.get('rx_delta'))} / {_fmt_bytes_compact(b.get('tx_delta'))}"
                if peer
                else None
            ),
        ),
    ]

    def _suspect(p: dict[str, Any]) -> bool:
        return str(p.get("level") or "").lower() in {"suspect", "weak", "bad", "poor"}

    any_suspect = _suspect(a) or _suspect(b)
    badge = "suspect" if any_suspect else "observe"
    if peer:
        summary = (
            f"{label_a} {_level_txt(a)}"
            + (f"：{a.get('summary')}" if a.get("summary") else "")
            + f"；{label_b} {_level_txt(b)}"
            + (f"：{b.get('summary')}" if b.get("summary") else "")
        )
    else:
        summary = a.get("summary") or f"RF={_level_txt(a)}"
    snaps = list(a.get("evidence") or [])
    if peer:
        snaps.extend([f"[{label_b}] {x}" for x in (b.get("evidence") or [])])
    return _strategy_item_html(
        "网络/RF 分析",
        badge_kind=badge,
        summary=summary,
        table_rows=rows,
        label_a=label_a,
        label_b=label_b if peer else "",
        charts_html=_strategy_dual_charts(
            _network_chart_html(ctx),
            _network_chart_html(peer) if peer else "",
            label_a=label_a,
            label_b=label_b,
        ),
        snaps=snaps,
    )


def _cap_power_pack(ctx: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(ctx, dict):
        return {}
    cap = ctx.get("game_network_cap") or {}
    if not isinstance(cap, dict) or not cap:
        return {}
    pi = cap.get("power_impact") if isinstance(cap.get("power_impact"), dict) else {}
    dual = cap.get("dual_channel") if isinstance(cap.get("dual_channel"), dict) else {}
    status = str(cap.get("status") or "")
    if status in {"skipped", "missing"} and not pi.get("has_impact"):
        # 无抓包或未启动：不展示空块
        if status == "skipped" or not cap.get("files"):
            return {}
    return {
        "status": status,
        "level": str(pi.get("level") or ("info" if status else "unknown")),
        "summary": pi.get("summary") or dual.get("summary") or "",
        "has_impact": bool(pi.get("has_impact")),
        "dual_verdict": (dual.get("verdict") or (pi.get("metrics") or {}).get("dual_verdict") or "—"),
        "dual_summary": dual.get("summary") or "—",
        "report_rows": list(pi.get("report_rows") or []),
        "impact_factors": list(pi.get("impact_factors") or []),
        "factors": list(pi.get("factors") or []),
        "evidence": list(pi.get("evidence") or dual.get("evidence") or [])[:10],
        "metrics": pi.get("metrics") if isinstance(pi.get("metrics"), dict) else {},
        "overlap_caps": cap.get("overlapping_cap_count") or len(cap.get("files") or []),
        "gate_reason": ((cap.get("gate") or {}) if isinstance(cap.get("gate"), dict) else {}).get("reason"),
    }


def _strategy_network_cap_section(
    ctx: dict[str, Any],
    peer: dict[str, Any] | None,
    *,
    label_a: str,
    label_b: str,
) -> str:
    """抓包 .cap 功耗影响因子（双机对比）。"""
    a = _cap_power_pack(ctx)
    b = _cap_power_pack(peer) if peer else {}
    if not a and not b:
        return ""

    def _cell(p: dict[str, Any], key: str, default: str = "—") -> str:
        if not p:
            return default
        v = p.get(key)
        return str(v) if v not in (None, "") else default

    def _pps(p: dict[str, Any]) -> str:
        m = p.get("metrics") or {}
        pps = m.get("packet_rate_pps")
        return f"{pps} pkt/s" if pps is not None else "—"

    def _bps(p: dict[str, Any]) -> str:
        m = p.get("metrics") or {}
        bps = m.get("avg_byte_rate_bps")
        if bps is None:
            return "—"
        try:
            return f"{float(bps) / 1024:.1f} KB/s"
        except (TypeError, ValueError):
            return str(bps)

    def _factors_txt(p: dict[str, Any]) -> str:
        items = p.get("impact_factors") or []
        if not items:
            return "未见明确抬升因子" if p else "—"
        return "；".join(str(x.get("title") or "") for x in items[:4] if x.get("title"))

    def _hints_txt(p: dict[str, Any]) -> str:
        items = p.get("impact_factors") or []
        if not items:
            return _cell(p, "summary")
        return "；".join(
            str(x.get("power_hint") or x.get("detail") or "") for x in items[:3]
        )

    rows: list[tuple[str, str, str | None]] = [
        ("抓包状态", _cell(a, "status"), _cell(b, "status") if peer else None),
        ("重叠 cap 数", _cell(a, "overlap_caps"), _cell(b, "overlap_caps") if peer else None),
        (
            "抓包双通道",
            f"{_cell(a, 'dual_verdict')}（{_cell(a, 'dual_summary')}）",
            (f"{_cell(b, 'dual_verdict')}（{_cell(b, 'dual_summary')}）" if peer else None),
        ),
        ("局内包速率", _pps(a), _pps(b) if peer else None),
        ("数据字节率", _bps(a), _bps(b) if peer else None),
        ("功耗影响因子", _factors_txt(a), _factors_txt(b) if peer else None),
        ("影响说明", _hints_txt(a), _hints_txt(b) if peer else None),
    ]

    any_impact = bool(a.get("has_impact") or b.get("has_impact"))
    badge = "suspect" if any_impact else "observe"
    if peer:
        summary = (
            f"{label_a}: {a.get('summary') or a.get('status') or '—'}"
            f"；{label_b}: {b.get('summary') or b.get('status') or '—'}"
        )
    else:
        summary = str(a.get("summary") or "抓包功耗分析")

    snaps = list(a.get("evidence") or [])
    for f in a.get("impact_factors") or []:
        detail = f.get("detail") or f.get("power_hint")
        if detail:
            snaps.append(f"[{f.get('title')}] {detail}")
    if peer:
        for x in b.get("evidence") or []:
            snaps.append(f"[{label_b}] {x}")
        for f in b.get("impact_factors") or []:
            detail = f.get("detail") or f.get("power_hint")
            if detail:
                snaps.append(f"[{label_b}/{f.get('title')}] {detail}")

    return _strategy_item_html(
        "抓包功耗影响",
        badge_kind=badge,
        summary=summary,
        table_rows=rows,
        label_a=label_a,
        label_b=label_b if peer else "",
        charts_html="",
        snaps=snaps,
    )


def _format_network_analysis_media(
    ctx: dict[str, Any],
    compare_ctx: dict[str, Any] | None = None,
    *,
    label_a: str = "测试机",
    label_b: str = "对比机",
) -> str:
    peer = compare_ctx if isinstance(compare_ctx, dict) and compare_ctx else None
    la = label_a or "测试机"
    lb = (label_b or "对比机") if peer else ""
    parts = [
        _strategy_network_section(ctx, peer, label_a=la, label_b=lb),
        _strategy_network_cap_section(ctx, peer, label_a=la, label_b=lb),
    ]
    return "".join(p for p in parts if p)


def _format_optimization_strategy_media(
    ctx: dict[str, Any],
    compare_ctx: dict[str, Any] | None = None,
    *,
    label_a: str = "测试机",
    label_b: str = "对比机",
) -> str:
    """软件策略差异统一框：固定顺序；单/双机同一标题；表对比 + 左右图 + 折叠快照。

    顺序：1刷新率 2帧率 3背光2.0 4AAL背光 5perfLockAcq提频 6thermal策略。
    """
    peer = compare_ctx if isinstance(compare_ctx, dict) and compare_ctx else None
    la = label_a or "测试机"
    lb = (label_b or "对比机") if peer else ""
    parts = [
        _strategy_refresh_section(ctx, peer, label_a=la, label_b=lb),
        _strategy_frame_section(ctx, peer, label_a=la, label_b=lb),
        _strategy_perf_section(ctx, peer, label_a=la, label_b=lb),
        _strategy_thermal_section(ctx, peer, label_a=la, label_b=lb),
    ]
    return "".join(p for p in parts if p)

def _parse_curve_time(raw: str) -> datetime | None:
    s = str(raw or "").strip()
    if not s:
        return None
    for fmt in ("%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S.%f", "%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(s[:26] if "%f" in fmt else s[:19], fmt)
            if dt.year == 1900:
                dt = dt.replace(year=2026)
            return dt
        except ValueError:
            continue
    return None


def _format_curve_time_display(raw: str) -> str:
    """曲线表展示用时间：精确到秒（去掉毫秒/微秒）。"""
    s = str(raw or "").strip()
    if not s:
        return ""
    dt = _parse_curve_time(s)
    if dt is not None:
        if re.match(r"^\d{4}-", s):
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        return dt.strftime("%m-%d %H:%M:%S")
    # 解析失败时仍尽量截掉小数秒
    return re.sub(r"\.\d+\s*$", "", s)


def _temp_curve_svg(
    points: list[dict[str, Any]] | None = None,
    *,
    series: list[dict[str, Any]] | None = None,
    max_temp: float | None = None,
    markers: list[dict[str, Any]] | None = None,
    width: int = 1200,
    height: int = 260,
    clamp_y_min_zero: bool = True,
    y_unit_label: str = "℃",
    value_change_threshold: float | None = None,
) -> str:
    """通用时序折线（默认温度）；markers 为竖线标注。

    clamp_y_min_zero：温度场景钳到 ≥0；网络 RSSI 等负值场景传 False。
    value_change_threshold：相对上一标注点变化超过该阈值时显示数值；
    温度单位默认 1.0，亮度等非温度单位默认不标。
    """
    # series: [{key,label,color,points:[{time,temp_c}]}]
    if series is None:
        series = [
            {
                "key": "default",
                "label": "温度",
                "color": "#c2410c",
                "points": points or [],
            }
        ]
    # SVG stroke 用实色，避免 CSS 变量在部分环境下解析失败导致色块感
    _color_fallback = {
        "vt_shell": "#c2410c",
        "SKIN": "#2563eb",
        "CPU": "#16a34a",
        "temp": "#c2410c",
        "default": "#c2410c",
    }
    prepared: list[dict[str, Any]] = []
    all_vals: list[float] = []
    all_dts: list[datetime] = []
    for ser in series:
        clean: list[tuple[datetime, str, float]] = []
        for p in ser.get("points") or []:
            if p.get("temp_c") is None:
                continue
            try:
                temp = float(p["temp_c"])
            except (TypeError, ValueError):
                continue
            t_raw = str(p.get("time") or "")
            dt = _parse_curve_time(t_raw)
            if not dt:
                continue
            clean.append((dt, t_raw, temp))
            all_vals.append(temp)
            all_dts.append(dt)
        if len(clean) < 2:
            continue
        clean.sort(key=lambda x: x[0])
        key = str(ser.get("key") or ser.get("label") or "s")
        raw_color = str(ser.get("color") or "")
        if not raw_color or "var(" in raw_color:
            raw_color = _color_fallback.get(key, "#c2410c")
        prepared.append(
            {
                "key": key,
                "label": ser.get("label") or key or "温度",
                "color": raw_color,
                "points": clean,
            }
        )
    if not prepared:
        return ""

    t0 = min(all_dts)
    t1 = max(all_dts)
    span_s = max(1.0, (t1 - t0).total_seconds())
    marker_rows = [m for m in (markers or []) if isinstance(m, dict)]
    # 温度曲线预留顶部空间给 max/min 标注
    _unit = str(y_unit_label or "")
    _is_temp = ("℃" in _unit) or _unit.strip() in ("C", "c", "°C", "摄氏度")
    pad_l, pad_r, pad_t, pad_b = 40, 16, (56 if marker_rows or _is_temp else 28), 30
    plot_w = max(1, width - pad_l - pad_r)
    plot_h = max(1, height - pad_t - pad_b)
    y_max = max(all_vals + ([float(max_temp)] if max_temp is not None else []))
    y_min = min(all_vals)
    y_span = max(1.0, y_max - y_min)
    y_max = y_max + y_span * 0.12
    y_pad_lo = y_min - y_span * 0.08
    y_min = max(0.0, y_pad_lo) if clamp_y_min_zero else y_pad_lo

    def _xy_dt(dt: datetime, temp: float) -> tuple[float, float]:
        x = pad_l + ((dt - t0).total_seconds() / span_s) * plot_w
        y = pad_t + (1.0 - (temp - y_min) / (y_max - y_min)) * plot_h
        return x, y

    def _downsample(
        pts: list[tuple[datetime, str, float]], *, max_pts: int = 400
    ) -> list[tuple[datetime, str, float]]:
        """过密采样抽稀，保留首尾与峰值，折线更清晰。"""
        n = len(pts)
        if n <= max_pts:
            return pts
        peak_i = max(range(n), key=lambda i: pts[i][2])
        keep: set[int] = {0, n - 1, peak_i}
        step = n / float(max_pts - 1)
        for k in range(max_pts):
            keep.add(min(n - 1, int(round(k * step))))
        return [pts[i] for i in sorted(keep)]

    polylines = ""
    legend = ""
    tip_series_js: list[str] = []
    grid = ""
    for gy in (0.25, 0.5, 0.75):
        yy = pad_t + plot_h * gy
        grid += (
            f'<line x1="{pad_l}" y1="{yy:.1f}" x2="{width - pad_r}" y2="{yy:.1f}" '
            f'stroke="var(--color-border-tertiary, #e8e6e0)" stroke-width="1" '
            f'stroke-dasharray="3 4"/>'
        )

    for si, ser in enumerate(prepared):
        color = ser["color"]
        pts_full = ser["points"]
        pts = _downsample(pts_full)
        poly = " ".join(f"{_xy_dt(dt, v)[0]:.1f},{_xy_dt(dt, v)[1]:.1f}" for dt, _, v in pts)
        polylines += (
            f'<polyline fill="none" stroke="{color}" stroke-width="2.2" '
            f'stroke-linejoin="round" stroke-linecap="round" '
            f'vector-effect="non-scaling-stroke" points="{poly}"/>'
        )
        n = len(pts_full)
        lx = pad_l + si * 160
        legend += (
            f'<line x1="{lx}" y1="8" x2="{lx + 18}" y2="8" stroke="{color}" '
            f'stroke-width="2.2" stroke-linecap="round"/>'
            f'<text x="{lx + 24}" y="11" font-size="11" fill="var(--color-text-secondary, #5f5e5a)">'
            f'{_esc(ser["label"])} ({n})</text>'
        )
        # 悬停用全量点，定位更准；展示时间精确到秒
        times_js = ",".join(
            json.dumps(_format_curve_time_display(t), ensure_ascii=False) for _, t, _ in pts_full
        )
        temps_js = ",".join(f"{v:.2f}" for _, _, v in pts_full)
        xs_js = ",".join(f"{_xy_dt(dt, v)[0]:.2f}" for dt, _, v in pts_full)
        tip_series_js.append(
            "{"
            f"label:{json.dumps(ser['label'], ensure_ascii=False)},"
            f"color:{json.dumps(color)},"
            f"times:[{times_js}],temps:[{temps_js}],xs:[{xs_js}]"
            "}"
        )

    # thermal / 亮度 竖线标签：避让曲线；同一竖线多点强制一上一下
    marker_html = ""
    drawn_markers = 0
    used_label_boxes: list[tuple[float, float, float, float]] = []  # cx, cy, hw, hh
    # 预采样曲线点，供标签碰撞检测
    curve_pts_xy: list[tuple[float, float]] = []
    for ser in prepared:
        for dt, _t, v in ser["points"]:
            curve_pts_xy.append(_xy_dt(dt, v))

    def _label_box(tx: float, ty: float, text: str, anchor: str) -> tuple[float, float, float, float]:
        tw = max(14.0, len(text) * 6.2)
        th = 11.0
        if anchor == "end":
            cx = tx - tw / 2.0
        elif anchor == "middle":
            cx = tx
        else:
            cx = tx + tw / 2.0
        return (cx, ty - 3.0, tw / 2.0 + 3.0, th / 2.0 + 2.0)

    def _box_hits_curve(cx: float, cy: float, hw: float, hh: float) -> bool:
        for px, py in curve_pts_xy:
            if abs(px - cx) <= hw + 6 and abs(py - cy) <= hh + 5:
                return True
        return False

    def _box_hits_labels(cx: float, cy: float, hw: float, hh: float) -> bool:
        for px, py, phw, phh in used_label_boxes:
            if abs(px - cx) < (hw + phw) and abs(py - cy) < (hh + phh):
                return True
        return False

    # 先解析有效 marker，并按竖线（相近 x）分组，组内按锚点 y 排序后交替上/下
    resolved: list[dict[str, Any]] = []
    for mk in marker_rows:
        dt = _parse_curve_time(str(mk.get("time") or ""))
        if not dt or dt < t0 or dt > t1:
            continue
        x = pad_l + ((dt - t0).total_seconds() / span_s) * plot_w
        color = str(mk.get("color") or "#b45309")
        label = str(mk.get("label") or "").strip()
        detail = str(mk.get("detail") or "").strip()
        tip = label + (f" · {detail}" if detail else "")

        # 优先用 marker 自身数值定位锚点（亮度同刻多点）；否则取曲线最近点
        own_val = mk.get("value")
        if own_val is None:
            own_val = mk.get("temp_c")
        if own_val is None:
            own_val = mk.get("nits")
        anchor_y: float
        try:
            if own_val is not None:
                anchor_y = _xy_dt(dt, float(own_val))[1]
            else:
                raise TypeError
        except (TypeError, ValueError):
            curve_ys: list[float] = []
            for ser in prepared:
                pts = ser.get("points") or []
                if not pts:
                    continue
                nearest = min(pts, key=lambda p: abs((p[0] - dt).total_seconds()))
                curve_ys.append(_xy_dt(nearest[0], nearest[2])[1])
            anchor_y = min(curve_ys) if curve_ys else (pad_t + plot_h * 0.35)

        resolved.append(
            {
                "x": x,
                "dt": dt,
                "color": color,
                "label": label,
                "tip": tip,
                "time": str(mk.get("time") or ""),
                "anchor_y": float(anchor_y),
            }
        )

    # 分组：x 相差 ≤8px 视为同一竖线
    groups: list[list[dict[str, Any]]] = []
    for item in sorted(resolved, key=lambda r: (r["x"], r["anchor_y"])):
        if groups and abs(groups[-1][0]["x"] - item["x"]) <= 8.0:
            groups[-1].append(item)
        else:
            groups.append([item])

    for group in groups:
        # 同一竖线：按锚点从上到下（y 小→大），偶数上、奇数下
        group.sort(key=lambda r: r["anchor_y"])
        for gi, item in enumerate(group):
            x = float(item["x"])
            color = str(item["color"])
            label = str(item["label"])
            tip = str(item["tip"])
            anchor_y = float(item["anchor_y"])
            prefer_above = (gi % 2 == 0)
            # 组内错开幅度
            step = (gi // 2) * 12

            if prefer_above:
                candidates = [
                    (x + 5, anchor_y - 12 - step, "start"),
                    (x - 5, anchor_y - 12 - step, "end"),
                    (x + 5, anchor_y - 24 - step, "start"),
                    (x - 5, anchor_y - 24 - step, "end"),
                    (x + 18, pad_t - 6 - step, "start"),
                    (x - 18, pad_t - 6 - step, "end"),
                    # 实在不行再落到下方
                    (x + 5, anchor_y + 16 + step, "start"),
                    (x - 5, anchor_y + 16 + step, "end"),
                ]
            else:
                candidates = [
                    (x + 5, anchor_y + 16 + step, "start"),
                    (x - 5, anchor_y + 16 + step, "end"),
                    (x + 5, anchor_y + 28 + step, "start"),
                    (x - 5, anchor_y + 28 + step, "end"),
                    (x + 5, height - pad_b - 6 - step, "start"),
                    (x - 5, height - pad_b - 6 - step, "end"),
                    # 兜底上方
                    (x + 5, anchor_y - 12 - step, "start"),
                    (x - 5, anchor_y - 12 - step, "end"),
                ]

            chosen: tuple[float, float, str] | None = None
            for tx, ty, anchor in candidates:
                ty = max(12.0, min(float(height - 8), float(ty)))
                tx = max(pad_l + 2.0, min(float(width - pad_r - 2), float(tx)))
                cx, cy, hw, hh = _label_box(tx, ty, label or "·", anchor)
                if _box_hits_labels(cx, cy, hw, hh):
                    continue
                if _box_hits_curve(cx, cy, hw, hh):
                    continue
                chosen = (tx, ty, anchor)
                break
            if chosen is None:
                if prefer_above:
                    ty = max(12.0, min(anchor_y - 14 - step, pad_t - 4))
                else:
                    ty = min(float(height - 8), anchor_y + 18 + step)
                tx = x + (8 if x < width * 0.72 else -8)
                anchor = "start" if x < width * 0.72 else "end"
                chosen = (tx, ty, anchor)

            tx, ty, text_anchor = chosen
            cx, cy, hw, hh = _label_box(tx, ty, label or "·", text_anchor)
            used_label_boxes.append((cx, cy, hw, hh))

            leader = ""
            dist = ((tx - x) ** 2 + (ty - anchor_y) ** 2) ** 0.5
            if dist > 12.0:
                if text_anchor == "end":
                    lx2 = tx - 1
                elif text_anchor == "middle":
                    lx2 = tx
                else:
                    lx2 = tx + 1
                leader = (
                    f'<line x1="{x:.1f}" y1="{anchor_y:.1f}" x2="{lx2:.1f}" y2="{ty - 2:.1f}" '
                    f'stroke="{color}" stroke-width="1" stroke-dasharray="2 2" opacity="0.75"/>'
                    f'<circle cx="{x:.1f}" cy="{anchor_y:.1f}" r="2.2" fill="{color}" '
                    f'stroke="#fff" stroke-width="0.8"/>'
                )

            marker_html += (
                f'<line x1="{x:.1f}" y1="{pad_t}" x2="{x:.1f}" y2="{height - pad_b}" '
                f'stroke="{color}" stroke-width="1.4" stroke-dasharray="4 3" opacity="0.85">'
                f'<title>{_esc(tip)} @ {_esc(_format_curve_time_display(str(item["time"])))}</title></line>'
                f'<circle cx="{x:.1f}" cy="{pad_t}" r="3" fill="{color}" stroke="#fff" stroke-width="1">'
                f'<title>{_esc(tip)}</title></circle>'
                f"{leader}"
                f'<text x="{tx:.1f}" y="{ty:.1f}" text-anchor="{text_anchor}" '
                f'font-size="10" font-weight="600" fill="{color}">'
                f'<title>{_esc(tip)} @ {_esc(_format_curve_time_display(str(item["time"])))}</title>'
                f'{_esc(label)}</text>'
            )
            drawn_markers += 1

    # 温度曲线：先标注每条曲线的最大/最小温度（一上一下），再标 ≥阈值 的变化点
    value_labels_html = ""
    unit_raw = str(y_unit_label or "")
    is_temp_unit = ("℃" in unit_raw) or unit_raw.strip() in ("C", "c", "°C", "摄氏度")
    extrema_html = ""
    overall_max: float | None = None
    overall_min: float | None = None
    if is_temp_unit and prepared:
        for ser in prepared:
            pts_full = ser["points"]
            if not pts_full:
                continue
            color = ser["color"]
            peak_pt = max(pts_full, key=lambda p: p[2])
            trough_pt = min(pts_full, key=lambda p: p[2])
            peak_v = float(peak_pt[2])
            trough_v = float(trough_pt[2])
            overall_max = peak_v if overall_max is None else max(overall_max, peak_v)
            overall_min = trough_v if overall_min is None else min(overall_min, trough_v)

            extrema_items: list[tuple[tuple, str, bool]] = [
                (peak_pt, f"max {_format_curve_value_label(peak_v)}", True),
            ]
            if abs(peak_v - trough_v) >= 0.05:
                extrema_items.append(
                    (trough_pt, f"min {_format_curve_value_label(trough_v)}", False)
                )

            for pt, text, prefer_above in extrema_items:
                x, y = _xy_dt(pt[0], float(pt[2]))
                if prefer_above:
                    trials = [
                        (x, y - 14, "middle"),
                        (x + 12, y - 14, "start"),
                        (x - 12, y - 14, "end"),
                        (x + 18, y - 26, "start"),
                        (x - 18, y - 26, "end"),
                        (x, y + 16, "middle"),
                    ]
                else:
                    trials = [
                        (x, y + 16, "middle"),
                        (x + 12, y + 16, "start"),
                        (x - 12, y + 16, "end"),
                        (x + 18, y + 28, "start"),
                        (x - 18, y + 28, "end"),
                        (x, y - 14, "middle"),
                    ]
                chosen: tuple[float, float, str] | None = None
                for tx, ty, anchor in trials:
                    ty = max(14.0, min(float(height - 8), float(ty)))
                    tx = max(pad_l + 2.0, min(float(width - pad_r - 2), float(tx)))
                    cx, cy, hw, hh = _label_box(tx, ty, text, anchor)
                    if _box_hits_labels(cx, cy, hw, hh):
                        continue
                    chosen = (tx, ty, anchor)
                    break
                if chosen is None:
                    ty = max(14.0, y - 14) if prefer_above else min(float(height - 8), y + 16)
                    tx = x + (10 if x < width * 0.72 else -10)
                    anchor = "start" if x < width * 0.72 else "end"
                    chosen = (tx, ty, anchor)
                tx, ty, text_anchor = chosen
                cx, cy, hw, hh = _label_box(tx, ty, text, text_anchor)
                used_label_boxes.append((cx, cy, hw, hh))
                if text_anchor == "end":
                    lx2 = tx - 1
                elif text_anchor == "middle":
                    lx2 = tx
                else:
                    lx2 = tx + 1
                leader = (
                    f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{lx2:.1f}" y2="{ty - 2:.1f}" '
                    f'stroke="{color}" stroke-width="1" stroke-dasharray="2 2" opacity="0.75"/>'
                )
                extrema_html += (
                    f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.2" fill="none" '
                    f'stroke="{color}" stroke-width="1.8"/>'
                    f'<circle cx="{x:.1f}" cy="{y:.1f}" r="1.6" fill="{color}"/>'
                    f"{leader}"
                    f'<text x="{tx:.1f}" y="{ty:.1f}" text-anchor="{text_anchor}" '
                    f'font-size="11" font-weight="700" fill="{color}">{_esc(text)}</text>'
                )
        value_labels_html += extrema_html

    thr = value_change_threshold
    if thr is None and is_temp_unit:
        thr = 1.0
    if thr is not None and thr > 0:
        # 每条曲线独立累计变化；候选按 |Δ| 与峰值优先
        temp_candidates: list[tuple[float, float, float, str, float]] = []
        # (x, y, value, color, priority)
        for si, ser in enumerate(prepared):
            pts_full = ser["points"]
            if not pts_full:
                continue
            color = ser["color"]
            last_labeled: float | None = None
            peak_i = max(range(len(pts_full)), key=lambda i: pts_full[i][2])
            trough_i = min(range(len(pts_full)), key=lambda i: pts_full[i][2])
            labeled_idxs: set[int] = set()
            for i, (dt, _t, v) in enumerate(pts_full):
                if last_labeled is None or abs(float(v) - float(last_labeled)) >= float(thr) - 1e-9:
                    labeled_idxs.add(i)
                    last_labeled = float(v)
            labeled_idxs.add(0)
            labeled_idxs.add(len(pts_full) - 1)
            # 极值已有专用标注，变化点不再重复标同一点
            labeled_idxs.discard(peak_i)
            labeled_idxs.discard(trough_i)
            for i in sorted(labeled_idxs):
                dt, _t, v = pts_full[i]
                x, y = _xy_dt(dt, float(v))
                pri = abs(float(v) - float(pts_full[max(0, i - 1)][2]))
                if i in (0, len(pts_full) - 1):
                    pri = max(pri, 50.0)
                temp_candidates.append((x, y, float(v), color, pri))
        temp_candidates.sort(key=lambda c: -c[4])
        max_temp_labels = 28
        placed_n = 0
        for x, y, v, color, _pri in temp_candidates:
            if placed_n >= max_temp_labels:
                break
            text = _format_curve_value_label(v)
            prefer_above = (placed_n % 2 == 0)
            if prefer_above:
                trials = [
                    (x, y - 11, "middle"),
                    (x + 10, y - 11, "start"),
                    (x - 10, y - 11, "end"),
                    (x, y + 14, "middle"),
                    (x + 14, y - 2, "start"),
                    (x - 14, y - 2, "end"),
                ]
            else:
                trials = [
                    (x, y + 14, "middle"),
                    (x + 10, y + 14, "start"),
                    (x - 10, y + 14, "end"),
                    (x, y - 11, "middle"),
                    (x + 14, y + 4, "start"),
                    (x - 14, y + 4, "end"),
                ]
            chosen = None
            for tx, ty, anchor in trials:
                ty = max(12.0, min(float(height - 8), float(ty)))
                tx = max(pad_l + 2.0, min(float(width - pad_r - 2), float(tx)))
                cx, cy, hw, hh = _label_box(tx, ty, text, anchor)
                if _box_hits_labels(cx, cy, hw, hh):
                    continue
                if _box_hits_curve(cx, cy, hw * 0.85, hh * 0.85):
                    if abs(ty - y) < 8 and abs(tx - x) < 8:
                        continue
                chosen = (tx, ty, anchor)
                break
            if chosen is None:
                continue
            tx, ty, text_anchor = chosen
            cx, cy, hw, hh = _label_box(tx, ty, text, text_anchor)
            used_label_boxes.append((cx, cy, hw, hh))
            leader = ""
            dist = ((tx - x) ** 2 + (ty - y) ** 2) ** 0.5
            if dist > 10.0:
                if text_anchor == "end":
                    lx2 = tx - 1
                elif text_anchor == "middle":
                    lx2 = tx
                else:
                    lx2 = tx + 1
                leader = (
                    f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{lx2:.1f}" y2="{ty - 2:.1f}" '
                    f'stroke="{color}" stroke-width="0.9" stroke-dasharray="2 2" opacity="0.65"/>'
                )
            value_labels_html += (
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.0" fill="{color}" '
                f'stroke="#fff" stroke-width="0.7"/>'
                f"{leader}"
                f'<text x="{tx:.1f}" y="{ty:.1f}" text-anchor="{text_anchor}" '
                f'font-size="10" font-weight="600" fill="{color}">{_esc(text)}</text>'
            )
            placed_n += 1

    y_ticks = [y_min, (y_min + y_max) / 2, y_max]
    tick_html = "".join(
        f'<text x="{pad_l - 4}" y="{_xy_dt(t0, y)[1] + 3:.1f}" text-anchor="end" '
        f'font-size="10" fill="var(--color-text-tertiary, #888)">{y:.1f}</text>'
        for y in y_ticks
    )
    t_first = _esc(
        _format_curve_time_display(prepared[0]["points"][0][1] if prepared else "")
    )
    end_raw = ""
    for ser in prepared:
        for dt, t_raw, _ in ser["points"]:
            if dt == t1:
                end_raw = t_raw
    t_last = _esc(
        _format_curve_time_display(
            end_raw or (prepared[-1]["points"][-1][1] if prepared else "")
        )
    )
    axis_times = (
        f'<text x="{pad_l}" y="{height - 6}" font-size="11" fill="var(--color-text-tertiary, #888)">{t_first}</text>'
        f'<text x="{width - pad_r}" y="{height - 6}" text-anchor="end" font-size="11" '
        f'fill="var(--color-text-tertiary, #888)">{t_last}</text>'
    )
    max_note = ""
    max_marker = ""
    if is_temp_unit and overall_max is not None and overall_min is not None:
        max_note = (
            f'<text x="{width - pad_r}" y="{pad_t - 8}" text-anchor="end" font-size="11" '
            f'font-weight="600" fill="#9a3412">'
            f"max {_format_curve_value_label(overall_max)} / min {_format_curve_value_label(overall_min)}"
            f"{_esc(y_unit_label)}</text>"
        )
    elif max_temp is not None:
        max_note = (
            f'<text x="{width - pad_r}" y="{pad_t - 8}" text-anchor="end" font-size="11" '
            f'fill="#9a3412">max {float(max_temp):.2f}{_esc(y_unit_label)}</text>'
        )
        peak_ser = max(prepared, key=lambda s: max(p[2] for p in s["points"]))
        peak_pt = max(peak_ser["points"], key=lambda p: p[2])
        px, py = _xy_dt(peak_pt[0], peak_pt[2])
        max_marker = (
            f'<circle cx="{px:.1f}" cy="{py:.1f}" r="3.5" fill="none" '
            f'stroke="{peak_ser["color"]}" stroke-width="1.8"/>'
        )

    uid = f"tempcurve{next(_TEMP_CURVE_UID)}"
    unit_js = json.dumps(y_unit_label, ensure_ascii=False)
    series_js = ",".join(tip_series_js)
    return (
        f'<div id="{uid}-wrap" class="temp-curve-wrap" style="position:relative;width:100%;'
        f'box-sizing:border-box;"'
        f' data-pad-l="{pad_l}" data-pad-r="{pad_r}" data-vb-w="{width}">'
        f'<svg id="{uid}-svg" viewBox="0 0 {width} {height}" preserveAspectRatio="none" '
        f'width="100%" height="{height}" role="img" aria-label="游戏场景温度曲线" '
        f'style="display:block;width:100%;height:{height}px;min-width:100%;cursor:crosshair;">'
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#fff"/>'
        f"{grid}"
        f'<line x1="{pad_l}" y1="{pad_t}" x2="{pad_l}" y2="{height - pad_b}" '
        f'stroke="var(--color-border-tertiary, #ddd)" stroke-width="1"/>'
        f'<line x1="{pad_l}" y1="{height - pad_b}" x2="{width - pad_r}" y2="{height - pad_b}" '
        f'stroke="var(--color-border-tertiary, #ddd)" stroke-width="1"/>'
        f"{legend}{tick_html}{max_note}{polylines}{marker_html}{value_labels_html}{max_marker}{axis_times}"
        f'<line id="{uid}-guide" x1="0" y1="{pad_t}" x2="0" y2="{height - pad_b}" '
        f'stroke="#94a3b8" stroke-width="1" stroke-dasharray="3 3" visibility="hidden"/>'
        f'<circle id="{uid}-dot" cx="0" cy="0" r="4" fill="#c2410c" '
        f'stroke="#fff" stroke-width="1.5" visibility="hidden" '
        f'vector-effect="non-scaling-stroke"/>'
        f"</svg>"
        f'<div id="{uid}-tip" style="display:none;position:absolute;z-index:5;pointer-events:none;'
        f'padding:6px 8px;border-radius:6px;font-size:12px;line-height:1.4;'
        f'background:rgba(28,28,30,.92);color:#fff;box-shadow:0 2px 8px rgba(0,0,0,.18);'
        f'white-space:nowrap;"></div>'
        f"<script>(function(){{"
        f"var wrap=document.getElementById('{uid}-wrap');"
        f"var svg=document.getElementById('{uid}-svg');"
        f"var tip=document.getElementById('{uid}-tip');"
        f"var dot=document.getElementById('{uid}-dot');"
        f"var guide=document.getElementById('{uid}-guide');"
        f"if(!wrap||!svg||!tip||!dot)return;"
        f"var series=[{series_js}];"
        f"var padL=+wrap.dataset.padL, padR=+wrap.dataset.padR, vbW=+wrap.dataset.vbW;"
        f"var yMin={y_min:.4f}, yMax={y_max:.4f}, padT={pad_t}, padB={pad_b}, vbH={height};"
        f"var unit={unit_js};"
        f"function nearest(ser,xVb){{var xs=ser.xs,best=0,bd=1e9;"
        f"for(var i=0;i<xs.length;i++){{var d=Math.abs(xs[i]-xVb); if(d<bd){{bd=d;best=i;}}}}"
        f"return best;}}"
        f"function show(xVb,clientX,clientY){{"
        f"var lines=[], bestX=null, bestY=null, bestColor=null, tipT='', bestDist=1e18;"
        f"for(var s=0;s<series.length;s++){{var ser=series[s]; if(!ser.xs||!ser.xs.length)continue;"
        f"var i=nearest(ser,xVb); var t=ser.times[i], v=ser.temps[i];"
        f"lines.push('<span style=\"color:'+ser.color+'\">'+ser.label+'</span>：'+v+' '+unit);"
        f"var d=Math.abs(ser.xs[i]-xVb);"
        f"if(d<bestDist){{bestDist=d; bestX=ser.xs[i]; bestColor=ser.color; tipT=t;"
        f"bestY=padT+(1-(+v-yMin)/(yMax-yMin))*(vbH-padT-padB);}}}}"
        f"if(!lines.length)return;"
        f"dot.setAttribute('cx',bestX); dot.setAttribute('cy',bestY); "
        f"dot.setAttribute('fill',bestColor||'#c2410c'); dot.setAttribute('visibility','visible');"
        f"if(guide){{guide.setAttribute('x1',bestX);guide.setAttribute('x2',bestX);"
        f"guide.setAttribute('visibility','visible');}}"
        f"tip.style.display='block'; tip.innerHTML='时间：'+tipT+'<br>'+lines.join('<br>');"
        f"var wr=wrap.getBoundingClientRect();"
        f"var left=clientX-wr.left+12, top=clientY-wr.top-36;"
        f"if(left+tip.offsetWidth>wr.width-4) left=clientX-wr.left-tip.offsetWidth-12;"
        f"if(top<4) top=clientY-wr.top+16;"
        f"tip.style.left=left+'px'; tip.style.top=top+'px';}}"
        f"function hide(){{tip.style.display='none'; dot.setAttribute('visibility','hidden');"
        f"if(guide)guide.setAttribute('visibility','hidden');}}"
        f"svg.addEventListener('mousemove',function(e){{"
        f"var r=svg.getBoundingClientRect();"
        f"var xr=(e.clientX-r.left)/Math.max(1,r.width);"
        f"var xVb=xr*vbW;"
        f"show(xVb,e.clientX,e.clientY);"
        f"}});"
        f"svg.addEventListener('mouseleave',hide);"
        f"}})();</script></div>"
    )


def _format_thermal_strategy_media_block(ctx: dict[str, Any]) -> str:
    """软件策略差异：thermal降亮度 / 限频一句话 + 分档 + T_game 温度曲线。"""
    th = ctx.get("game_thermal") or {}
    if not isinstance(th, dict) or not th:
        return ""
    report = th.get("thermal_report") or {}
    dim = report.get("backlight_dim") or {}
    freq = report.get("freq_throttle") or {}
    # 兼容旧 JSON：无 thermal_report 时从 summary 拼一句话
    if not dim and not freq:
        during = (th.get("thermal_summary") or {}).get("during_game") or {}
        t_game = (th.get("temperature") or {}).get("T_game") or {}
        dim = {
            "report_summary": (
                "thermal降亮度：生效" if during.get("thermal_backlight") else "thermal降亮度：未生效"
            ),
            "report_evidence": [],
        }
        freq = {
            "report_summary": (
                "thermal限频：生效" if during.get("freq_throttle") else "thermal限频：未生效"
            ),
            "report_evidence": [],
        }
        timeline = []
        max_temp = t_game.get("max_c")
    else:
        timeline = report.get("temp_timeline") or []
        max_temp = report.get("temp_max_c")
        if not timeline:
            # fallback: investigation curve
            s1 = (th.get("thermal_investigation") or {}).get("step1_thermal_info") or {}
            timeline = [
                p
                for p in (s1.get("temp_curve") or [])
                if p.get("source") == "tran_thermal_engine" and p.get("temp_c") is not None
            ]

    rows: list[str] = []
    snaps: list[str] = []
    for block in (dim, freq):
        summary = str(block.get("report_summary") or "").strip()
        if not summary:
            continue
        rows.append(
            f'<p style="margin:4px 0 0;font-size:13px;color:var(--color-text-secondary);">{_esc(summary)}</p>'
        )
        for line in block.get("report_evidence") or []:
            disp = _strip_log_snapshot_prefix(str(line))
            if disp and disp not in snaps:
                snaps.append(disp)

    curve_html = ""
    curves = report.get("temp_curves") or {}
    series_spec = [
        ("vt_shell", "vt_shell 壳温", "#c2410c"),
        ("SKIN", "SKIN", "#2563eb"),
        ("CPU", "CPU", "#16a34a"),
    ]
    series: list[dict[str, Any]] = []
    missing_notes: list[str] = []
    for key, label, color in series_spec:
        block = curves.get(key) or {}
        pts = block.get("points") or []
        if len(pts) >= 2:
            series.append({"key": key, "label": label, "color": color, "points": pts})
        elif key == "CPU":
            missing_notes.append("CPU温度：日志未获取到")
        elif not curves and key == "vt_shell" and timeline:
            # 旧 JSON 无 temp_curves：退回单曲线
            series.append({"key": key, "label": label, "color": color, "points": timeline})

    if not series and timeline:
        series.append(
            {
                "key": "temp",
                "label": "温度",
                "color": "var(--orange-600, #c2410c)",
                "points": timeline,
            }
        )

    if series:
        # —— 亮度曲线（来自 main: level/curve + sys: nits）+ 温度曲线（下方）——
        # 使用 game_brightness 已解析的关键点：step4_aal_strategy（曲线/背光事件）+ step5_thermal_control（thermal 触发）
        brightness_svg = ""
        try:
            gb = ctx.get("game_brightness") or {}
            inv = gb.get("brightness_investigation") or {}
            step4 = inv.get("step4_aal_strategy") or {}
            step5 = inv.get("step5_thermal_control") or {}

            curve_max = step4.get("curve_max") or 4095
            level_max = 255

            def _as_float(v: Any) -> float | None:
                try:
                    if v is None:
                        return None
                    return float(v)
                except (TypeError, ValueError):
                    return None

            # collect brightness change points
            bps: list[dict[str, Any]] = []
            # 1) 背光2.0 / AAL：优先用 step4.key_points 中的 dpc_nits（DisplayPowerController/BrightnessEvent）
            for kp in step4.get("key_points") or []:
                if not isinstance(kp, dict):
                    continue
                time_raw = kp.get("time")
                if not time_raw:
                    continue
                nits = _as_float(kp.get("dpc_nits")) if kp.get("dpc_nits") is not None else _as_float(kp.get("nits"))
                if nits is None:
                    continue
                curve_val = kp.get("curve_val")
                curve_i = int(curve_val) if curve_val is not None else None
                level_i = None
                if curve_i is not None and curve_max:
                    # 以 curve 映射 level（0-255）；用于展示/标注，不作为对齐判定依据
                    try:
                        level_i = int(round(float(curve_i) / float(curve_max) * float(level_max)))
                    except (TypeError, ValueError):
                        level_i = None

                aal_raw_present = bool(kp.get("aal_raw"))
                dpc_raw_present = bool(kp.get("dpc_raw"))
                # backlight2.0 is DPC/BrightnessEvent; priority over AAL
                cause = "背光2.0" if dpc_raw_present else ("AAL" if aal_raw_present else "AAL")
                bps.append(
                    {
                        "time": time_raw,
                        "nits": nits,
                        "curve_val": curve_i,
                        "level": level_i,
                        "cause": cause,
                    }
                )

            # 2) thermal 触发：step5.relevant_hits（thermalLightController brightnessNits）
            for h in step5.get("relevant_hits") or []:
                if not isinstance(h, dict):
                    continue
                win = str(h.get("window") or "")
                if win and win not in ("T_game", "game_entry", "launch"):
                    continue
                time_raw = h.get("time")
                if not time_raw:
                    continue
                nits = _as_float(h.get("brightness_nits"))
                if nits is None:
                    continue
                curve_i = None
                # try infer curve from nearest step4 key_point
                try:
                    dt_h = _parse_curve_time(str(time_raw))
                except Exception:
                    dt_h = None
                if dt_h is not None and bps:
                    best_bp = min(
                        bps,
                        key=lambda x: abs((_parse_curve_time(str(x.get("time") or "")) or datetime.min) - dt_h).total_seconds(),
                    )
                    curve_i = best_bp.get("curve_val")
                bps.append(
                    {
                        "time": time_raw,
                        "nits": nits,
                        "curve_val": curve_i,
                        "level": h.get("level"),
                        "cause": "thermal",
                    }
                )

            # dedupe by time (within 0.2s) to avoid too many near-identical markers
            merged: list[dict[str, Any]] = []
            for bp in sorted(bps, key=lambda x: str(x.get("time") or "")):
                dt_bp = _parse_curve_time(str(bp.get("time") or ""))
                if dt_bp is None:
                    continue
                if not merged:
                    bp["_dt"] = dt_bp
                    merged.append(bp)
                    continue
                prev_dt = merged[-1].get("_dt")
                if isinstance(prev_dt, datetime) and abs((dt_bp - prev_dt).total_seconds()) <= 0.2:
                    # keep the one with higher priority: thermal > 背光2.0 > AAL
                    pri = {"thermal": 2, "背光2.0": 1, "AAL": 0}
                    if pri.get(bp.get("cause"), 0) > pri.get(merged[-1].get("cause"), 0):
                        bp["_dt"] = dt_bp
                        merged[-1] = bp
                    continue
                bp["_dt"] = dt_bp
                merged.append(bp)

            # build temp range for x-axis alignment
            temp_pts: list[dict[str, Any]] = []
            for s in series:
                temp_pts.extend(s.get("points") or [])
            temp_times: list[tuple[datetime, str]] = []
            for p in temp_pts:
                t_raw = str(p.get("time") or "")
                dt = _parse_curve_time(t_raw)
                if dt is not None:
                    temp_times.append((dt, t_raw))
            if temp_times:
                temp_t0, temp_t1 = min(temp_times, key=lambda x: x[0])[0], max(temp_times, key=lambda x: x[0])[0]
                # choose time strings from temp
                t0_str = next(t for dt, t in temp_times if dt == temp_t0)
                t1_str = next(t for dt, t in temp_times if dt == temp_t1)
            else:
                temp_t0 = temp_t1 = None
                t0_str = t1_str = ""

            # plot points for brightness curve
            brightness_plot_points: list[dict[str, Any]] = []
            for bp in merged:
                brightness_plot_points.append({"time": bp.get("time"), "temp_c": bp.get("nits")})

            # add endpoints for alignment
            if temp_t0 is not None and temp_t1 is not None and merged:
                def _nearest_bp(dt: datetime) -> dict[str, Any]:
                    return min(merged, key=lambda x: abs((x.get("_dt") or datetime.min) - dt).total_seconds())

                bp0 = _nearest_bp(temp_t0)
                bp1 = _nearest_bp(temp_t1)
                brightness_plot_points = (
                    [{"time": t0_str, "temp_c": bp0.get("nits")}] + brightness_plot_points + [{"time": t1_str, "temp_c": bp1.get("nits")}]
                )

            if brightness_plot_points and merged:
                # markers on brightness panel
                marker_color = {"thermal": "#7c3aed", "背光2.0": "#b45309", "AAL": "#3b82f6"}
                brightness_markers: list[dict[str, Any]] = []
                for bp in merged:
                    cause = str(bp.get("cause") or "")
                    nits = bp.get("nits")
                    try:
                        nits_i = int(round(float(nits)))
                    except (TypeError, ValueError):
                        nits_i = None
                    label = f"{cause} {nits_i}nit" if nits_i is not None else f"{cause}"
                    curve_i = bp.get("curve_val")
                    level_i = bp.get("level")
                    detail_bits: list[str] = []
                    if level_i is not None:
                        detail_bits.append(f"level={int(level_i)}/255")
                    if curve_i is not None:
                        detail_bits.append(f"curve={int(curve_i)}/{int(curve_max)}")
                    detail = " · ".join(detail_bits)
                    brightness_markers.append(
                        {
                            "time": bp.get("time"),
                            "label": label,
                            "detail": detail,
                            "color": marker_color.get(cause) or "#b45309",
                            "value": float(nits) if nits is not None else None,
                        }
                    )

                brightness_svg = _temp_curve_svg(
                    series=[
                        {
                            "key": "brightness",
                            "label": "亮度（nit）",
                            "color": "#0ea5e9",
                            "points": brightness_plot_points,
                        }
                    ],
                    max_temp=max(p.get("temp_c") for p in brightness_plot_points if p.get("temp_c") is not None)
                    if brightness_plot_points
                    else None,
                    markers=brightness_markers,
                    width=1200,
                    height=120,
                    y_unit_label="nit",
                )

        except Exception:
            brightness_svg = ""

        svg = _temp_curve_svg(
            series=series,
            max_temp=max_temp if isinstance(max_temp, (int, float)) else None,
            markers=_collect_thermal_chart_markers(ctx),
            width=1200,
            height=180,
        )
        if svg:
            note_html = "".join(
                f'<p style="margin:4px 0 0;padding:0 8px;font-size:11px;color:var(--color-text-tertiary);">'
                f"{_esc(n)}</p>"
                for n in missing_notes
            )
            curve_html_parts: list[str] = [
                '<div style="margin:8px 0 6px;padding:6px 0;width:100%;box-sizing:border-box;'
                'background:var(--color-background-primary);'
                'border:0.5px solid var(--color-border-tertiary);border-radius:var(--border-radius-md);">'
            ]
            if brightness_svg:
                curve_html_parts.append(
                    '<p style="margin:0 0 6px;padding:0 8px;font-size:11px;color:var(--color-text-tertiary);">'
                    "测试期间亮度变化曲线（悬停显示时间与nit；竖线标注 AAL / 背光2.0 / thermal）</p>"
                )
                curve_html_parts.append(f'<div style="width:100%;padding:0;box-sizing:border-box;">{brightness_svg}</div>')
            curve_html_parts.append(
                '<p style="margin:8px 0 6px;padding:0 8px;font-size:11px;color:var(--color-text-tertiary);">'
                "测试期间温度变化曲线（vt_shell / SKIN / CPU；悬停显示时间与温度）</p>"
            )
            curve_html_parts.append(f"{note_html}")
            curve_html_parts.append(f'<div style="width:100%;padding:0;box-sizing:border-box;">{svg}</div></div>')
            curve_html = "".join(curve_html_parts)

    snap_html = ""
    if snaps:
        body = "".join(
            f'<pre style="margin:0 0 4px;white-space:pre-wrap;word-break:break-all;'
            f'font-size:10px;line-height:1.4;color:var(--color-text-secondary);">{_esc(s)}</pre>'
            for s in snaps[:8]
        )
        snap_html = (
            '<details style="margin-top:8px;">'
            f'<summary style="cursor:pointer;font-size:11px;color:var(--color-text-tertiary);">'
            f"日志快照（{len(snaps)}）· 默认隐藏，点击展开</summary>"
            f'<div style="margin-top:6px;padding:8px 10px;background:var(--color-background-primary);'
            f'border-radius:var(--border-radius-md);">{body}</div></details>'
        )

    if not rows and not curve_html:
        return ""
    return (
        '<div style="margin:8px 0 10px;padding:8px 10px;border:0.5px solid var(--color-border-tertiary);'
        'border-radius:var(--border-radius-md);background:var(--color-background-secondary);">'
        '<p style="margin:0;font-size:12px;font-weight:500;color:var(--color-text-primary);">Thermal 策略</p>'
        f'{"".join(rows)}{curve_html}{snap_html}</div>'
    )


_FINDING_TYPE_ZH = {
    "spike": "CPU突增",
    "single_shot": "单次高占用",
    "persistent_non_baseline": "持续非基线",
    "game_thread": "游戏线程",
    "baseline_thread": "正常基线",
}

_THREAD_KIND_ZH = {
    "game": "游戏",
    "normal": "正常",
    "abnormal": "异常",
}


_BG_CATEGORY_ZH = {
    "binder": "Binder",
    "sensor": "传感器",
    "job": "Job",
    "alarm": "Alarm",
    "broadcast": "广播",
    "wakelock": "WakeLock",
    "process_start": "进程拉起",
    "service_start": "服务启动",
    "service_bind": "服务绑定",
    "foreground_service": "前台服务",
    "gc": "GC",
    "game_download": "游戏下载",
}

_BG_JUNK_MARKERS = (".json", "MonoMethod", "System.Reflection")


def _is_displayable_bg_target(name: str) -> bool:
    if not name or len(name) < 3:
        return False
    return not any(m in name for m in _BG_JUNK_MARKERS)


def _bg_impact_score(item: dict[str, Any]) -> float:
    score = float(item.get("boost_ratio") or 0) * 10.0
    if item.get("related_cpu_usage"):
        score += 25.0
    if item.get("wakelock_total_duration_s"):
        score += 15.0
    prio = str(item.get("priority") or "P2").upper()
    if prio == "P0":
        score += 30.0
    elif prio == "P1":
        score += 15.0
    if item.get("high_confidence_candidate"):
        score += 20.0
    return score


def _thread_impact_score(item: dict[str, Any]) -> float:
    prio = str(item.get("priority") or "P2").upper()
    score = {"P0": 30.0, "P1": 15.0}.get(prio, 0.0)
    score += float(item.get("avg_usage") or 0) * 2.0
    score += float(item.get("sample_ratio") or 0) * 25.0
    score += float(item.get("max_usage") or 0)
    return score


def _optimization_suggestions(ctx: dict[str, Any]) -> list[dict[str, str]]:
    summary = ctx.get("summary") or {}
    existing = summary.get("optimization_suggestions") or []
    if existing:
        return [dict(x) for x in existing if isinstance(x, dict)]
    out: list[dict[str, str]] = []
    bg_src = summary.get("top_background_packages") or []
    if not bg_src:
        bg_src = (ctx.get("game_background") or {}).get("top_background_packages") or []
    for item in bg_src:
        if not isinstance(item, dict):
            continue
        pkg = str(item.get("package_or_process") or "")
        if not _is_displayable_bg_target(pkg):
            continue
        br = item.get("boost_ratio")
        prio = str(item.get("priority") or "P2")
        cats = ", ".join(
            _BG_CATEGORY_ZH.get(c, c) for c in (item.get("categories") or []) if c
        )
        issue = f"{pkg} 游戏时段活动升高"
        if br:
            issue += f"（T_game 频次约为 T_pre 的 {br:.1f} 倍）"
        if cats:
            issue += f" [{cats}]"
        out.append(
            {
                "priority": prio,
                "issue": issue,
                "suggestion": "排查后台唤醒/绑定/服务拉起，必要时冻结或延长心跳",
                "benefit": str(item.get("power_estimate_mws") or "待量化"),
                "_score": _bg_impact_score(item),
                "package": pkg,
            }
        )
    out.sort(key=lambda x: float(x.get("_score") or 0), reverse=True)
    for row in out:
        row.pop("_score", None)
    return out[:6]


def _game_flow_scripts_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "scripts"


def _ensure_game_flow_scripts_path() -> None:
    scripts = _game_flow_scripts_dir()
    s = str(scripts)
    if s not in sys.path:
        sys.path.insert(0, s)


def _load_baseline_for_threads() -> dict[str, Any]:
    _ensure_game_flow_scripts_path()
    from game_power_parser import load_baseline_processes  # type: ignore

    return load_baseline_processes(_game_flow_scripts_dir())


def _match_baseline_process_name(name: str, rules: list[dict[str, str]]) -> bool:
    _ensure_game_flow_scripts_path()
    from game_power_parser import match_baseline_process  # type: ignore

    return bool(match_baseline_process(name, rules))


def _is_game_thread_name(
    name: str,
    pid: int | None,
    game_package: str,
    game_ctx: dict[str, Any],
) -> bool:
    """仅判定游戏主进程/子线程（不含系统基线白名单）。"""
    try:
        pid_i = int(pid) if pid is not None else None
    except (TypeError, ValueError):
        pid_i = None
    game_pids = {int(x) for x in (game_ctx.get("game_pids") or []) if str(x).isdigit() or isinstance(x, int)}
    if pid_i is not None and pid_i in game_pids:
        return True
    if game_package:
        if name == game_package or name.startswith(f"{game_package}:"):
            return True
        pkg_tail = game_package.split(".")[-1]
        if len(pkg_tail) >= 3 and (pkg_tail in name or name.endswith(pkg_tail)):
            return True
    tail = name.split(":")[-1] if ":" in name else name
    for suf in game_ctx.get("subprocess_suffixes") or []:
        if not suf:
            continue
        if tail == suf or name.endswith(suf) or suf in tail:
            return True
    for pkg in game_ctx.get("packages") or []:
        if not pkg:
            continue
        if name == pkg or name.startswith(f"{pkg}:") or str(pkg).endswith(name):
            return True
    return False


def _classify_thread_kind(
    name: str,
    pid: int | None,
    *,
    game_package: str,
    game_ctx: dict[str, Any],
    baseline_rules: list[dict[str, str]],
    finding_names: set[str],
) -> str:
    if _is_game_thread_name(name, pid, game_package, game_ctx):
        return "game"
    if _match_baseline_process_name(name, baseline_rules):
        return "normal"
    if name in finding_names:
        return "abnormal"
    # 未进 finding、也不在基线：仍按异常候选展示（可能未达持续阈值）
    return "abnormal"


def _thread_kind_badge(kind: str, priority: str) -> tuple[str, str, str]:
    """返回 (label, bg, fg)。"""
    k = str(kind or "abnormal")
    if k == "game":
        return "游戏", "var(--green-50, #ecfdf5)", "var(--green-700, #047857)"
    if k == "normal":
        return "正常", "var(--color-background-secondary)", "var(--color-text-secondary)"
    p = (priority or "P2").upper()
    p_bg, p_fg = _priority_badge(p)
    return p, p_bg, p_fg


def _t_game_cpu_samples(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    """取 T_game 内 [K] 线程采样轮次（优先 summary.comparison_outputs）。"""
    summary = ctx.get("summary") or {}
    cmp_out = summary.get("comparison_outputs") or {}
    samples = cmp_out.get("cpu_samples")
    if not isinstance(samples, list) or not samples:
        for key in ("game_cpu_gpu_ddr", "game_kernel_cpu"):
            block: Any = ctx.get(key) or {}
            if key == "game_cpu_gpu_ddr" and isinstance(block, dict):
                block = block.get("kernel_cpu") or block
            if isinstance(block, dict):
                samples = block.get("cpu_samples")
            if isinstance(samples, list) and samples:
                break
    if not isinstance(samples, list):
        return []
    out = [s for s in samples if isinstance(s, dict) and s.get("window") == "T_game"]

    # summary 常缺 threads_raw / cpus_usage_raw：从 kernel 产物按时间对齐补齐
    raw_src: list[dict[str, Any]] = []
    for key in ("game_kernel_cpu", "game_cpu_gpu_ddr"):
        block = ctx.get(key) or {}
        if key == "game_cpu_gpu_ddr" and isinstance(block, dict):
            block = block.get("kernel_cpu") or block
        if not isinstance(block, dict):
            continue
        cand = block.get("cpu_samples")
        if isinstance(cand, list) and cand:
            raw_src = [s for s in cand if isinstance(s, dict) and s.get("window") == "T_game"]
            if any(s.get("cpus_usage_raw") or s.get("threads_raw") for s in raw_src):
                break
    if not raw_src:
        return out

    by_time: dict[str, dict[str, Any]] = {}
    by_round: dict[int, dict[str, Any]] = {}
    for s in raw_src:
        t = str(s.get("time") or "")
        if t and t not in by_time:
            by_time[t] = s
        try:
            rnd = int(s.get("round"))
        except (TypeError, ValueError):
            continue
        if rnd not in by_round:
            by_round[rnd] = s

    enriched: list[dict[str, Any]] = []
    for s in out:
        src = by_time.get(str(s.get("time") or ""))
        if src is None:
            try:
                src = by_round.get(int(s.get("round")))
            except (TypeError, ValueError):
                src = None
        if not isinstance(src, dict):
            enriched.append(s)
            continue
        merged = dict(s)
        for field in ("cpus_usage_raw", "threads_raw", "raw_lines"):
            if not merged.get(field) and src.get(field):
                merged[field] = src[field]
        # 线程级 raw
        src_threads = src.get("threads") or []
        dst_threads = merged.get("threads") or []
        if (
            isinstance(src_threads, list)
            and isinstance(dst_threads, list)
            and src_threads
            and dst_threads
            and not any(isinstance(t, dict) and t.get("raw") for t in dst_threads)
        ):
            by_pid = {
                (th.get("pid"), str(th.get("name") or "")): th
                for th in src_threads
                if isinstance(th, dict)
            }
            new_threads: list[dict[str, Any]] = []
            for th in dst_threads:
                if not isinstance(th, dict):
                    continue
                nt = dict(th)
                src_th = by_pid.get((th.get("pid"), str(th.get("name") or "")))
                if isinstance(src_th, dict) and src_th.get("raw") and not nt.get("raw"):
                    nt["raw"] = src_th["raw"]
                new_threads.append(nt)
            merged["threads"] = new_threads
        enriched.append(merged)
    return enriched


def _thread_usage_by_round(
    name: str,
    samples: list[dict[str, Any]],
    existing: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """按日志打印轮次对齐：出现则带 CPU%，未进入 Top 列表视为未出现。"""
    if existing and len(existing) == len(samples):
        out: list[dict[str, Any]] = []
        for idx, pt in enumerate(existing):
            if not isinstance(pt, dict):
                continue
            usage = pt.get("usage")
            present = bool(pt.get("present")) if "present" in pt else usage is not None
            out.append(
                {
                    "round": pt.get("round", samples[idx].get("round", idx + 1)),
                    "round_idx": idx,
                    "time": str(pt.get("time") or samples[idx].get("time") or ""),
                    "usage": int(usage) if usage is not None else None,
                    "present": present,
                    "pid": pt.get("pid"),
                }
            )
        if out:
            return out

    series: list[dict[str, Any]] = []
    for idx, sample in enumerate(samples):
        usage = None
        pid = None
        for th in sample.get("threads") or []:
            if not isinstance(th, dict):
                continue
            if str(th.get("name") or "").strip() != name:
                continue
            try:
                usage = int(th.get("usage") or 0)
            except (TypeError, ValueError):
                usage = 0
            pid = th.get("pid")
            break
        series.append(
            {
                "round": sample.get("round", idx + 1),
                "round_idx": idx,
                "time": str(sample.get("time") or ""),
                "usage": usage,
                "present": usage is not None,
                "pid": pid,
            }
        )
    return series


_K_THREAD_HEATMAP_FIXED = 10
_K_THREAD_HEATMAP_COLORS = (
    "#2563eb",
    "#dc2626",
    "#16a34a",
    "#d97706",
    "#7c3aed",
    "#0891b2",
    "#db2777",
    "#4f46e5",
    "#059669",
    "#ea580c",
    "#0284c7",
    "#c026d3",
    "#65a30d",
    "#e11d48",
    "#0d9488",
    "#9333ea",
    "#ca8a04",
    "#0ea5e9",
    "#f43f5e",
    "#14b8a6",
)
_K_THREAD_HEATMAP_UID = itertools.count(1)


def _thread_heatmap_color(name: str) -> str:
    """按线程名稳定分配颜色。"""
    s = str(name or "")
    h = 0
    for ch in s:
        h = (h * 131 + ord(ch)) & 0xFFFFFFFF
    return _K_THREAD_HEATMAP_COLORS[h % len(_K_THREAD_HEATMAP_COLORS)]


def _build_k_thread_heatmap_payload(ctx: dict[str, Any]) -> dict[str, Any] | None:
    """构建 [K] 时间×线程方块图数据。

    纵轴：固定 10 行（自下而上 CPU 高→低，第 1 行为应用场景），
    异常线程从第 11 行起；某轮未出现则该格为空。
    """
    samples = _t_game_cpu_samples(ctx)
    if not samples:
        return None
    findings = _thread_investigation_findings(ctx)
    if not findings:
        return None

    def _avg(item: dict[str, Any]) -> float:
        try:
            return float(item.get("avg_usage") or 0.0)
        except (TypeError, ValueError):
            return 0.0

    def _max_u(item: dict[str, Any]) -> float:
        try:
            return float(item.get("max_usage") or 0.0)
        except (TypeError, ValueError):
            return 0.0

    active = [f for f in findings if int(f.get("occurrence_count") or 0) > 0]
    if not active:
        return None

    game_items = [f for f in active if str(f.get("thread_kind") or "") == "game"]
    app = max(game_items, key=_avg) if game_items else None

    non_abn = sorted(
        [
            f
            for f in active
            if str(f.get("thread_kind") or "") != "abnormal"
            and (app is None or str(f.get("name") or "") != str(app.get("name") or ""))
        ],
        key=lambda f: (-_avg(f), -_max_u(f), str(f.get("name") or "")),
    )

    fixed: list[dict[str, Any] | None] = [None] * _K_THREAD_HEATMAP_FIXED
    if app is not None:
        fixed[0] = app
    fill_i = 1 if app is not None else 0
    for f in non_abn:
        if fill_i >= _K_THREAD_HEATMAP_FIXED:
            break
        fixed[fill_i] = f
        fill_i += 1

    fixed_names = {
        str(f.get("name") or "")
        for f in fixed
        if isinstance(f, dict) and str(f.get("name") or "").strip()
    }
    abnormal = sorted(
        [
            f
            for f in active
            if str(f.get("thread_kind") or "") == "abnormal"
            and str(f.get("name") or "") not in fixed_names
        ],
        key=lambda f: (
            -_avg(f),
            -int(f.get("occurrence_count") or 0),
            -_max_u(f),
            str(f.get("name") or ""),
        ),
    )

    rounds: list[dict[str, Any]] = []
    for idx, sample in enumerate(samples):
        rounds.append(
            {
                "round": sample.get("round", idx + 1),
                "time": str(sample.get("time") or ""),
            }
        )

    kind_zh = {"game": "游戏", "normal": "正常", "abnormal": "异常"}
    lanes: list[dict[str, Any]] = []
    lane_no = 0
    for slot in fixed:
        lane_no += 1
        if not isinstance(slot, dict):
            lanes.append(
                {
                    "lane": lane_no,
                    "name": "",
                    "kind": "",
                    "kind_label": "",
                    "color": "#cbd5e1",
                    "usages": [None] * len(samples),
                    "avg_usage": None,
                    "fixed": True,
                    "empty": True,
                }
            )
            continue
        name = str(slot.get("name") or "").strip()
        series = slot.get("usage_by_round") or _thread_usage_by_round(name, samples)
        usages: list[int | None] = []
        for pt in series:
            if pt.get("present") and pt.get("usage") is not None:
                try:
                    usages.append(int(pt.get("usage")))
                except (TypeError, ValueError):
                    usages.append(0)
            else:
                usages.append(None)
        while len(usages) < len(samples):
            usages.append(None)
        usages = usages[: len(samples)]
        is_app = lane_no == 1 and str(slot.get("thread_kind") or "") == "game"
        kind = str(slot.get("thread_kind") or "")
        lanes.append(
            {
                "lane": lane_no,
                "name": name,
                "kind": kind,
                "kind_label": "应用场景" if is_app else kind_zh.get(kind, kind),
                "color": _thread_heatmap_color(name),
                "usages": usages,
                "avg_usage": slot.get("avg_usage"),
                "fixed": True,
                "empty": False,
            }
        )

    for slot in abnormal:
        lane_no += 1
        name = str(slot.get("name") or "").strip()
        if not name:
            continue
        series = slot.get("usage_by_round") or _thread_usage_by_round(name, samples)
        usages = []
        for pt in series:
            if pt.get("present") and pt.get("usage") is not None:
                try:
                    usages.append(int(pt.get("usage")))
                except (TypeError, ValueError):
                    usages.append(0)
            else:
                usages.append(None)
        while len(usages) < len(samples):
            usages.append(None)
        usages = usages[: len(samples)]
        lanes.append(
            {
                "lane": lane_no,
                "name": name,
                "kind": "abnormal",
                "kind_label": "异常",
                "color": _thread_heatmap_color(name),
                "usages": usages,
                "avg_usage": slot.get("avg_usage"),
                "fixed": False,
                "empty": False,
            }
        )

    if not any(not lane.get("empty") for lane in lanes):
        return None

    # 每轮 [K] Top 列表里实际出现的进程（悬停用，不含「未出现」占位）
    app_name = str(app.get("name") or "").strip() if isinstance(app, dict) else ""
    kind_zh = {"game": "游戏", "normal": "正常", "abnormal": "异常"}
    finding_kind = {
        str(f.get("name") or "").strip(): str(f.get("thread_kind") or "")
        for f in findings
        if str(f.get("name") or "").strip()
    }
    round_threads: list[list[dict[str, Any]]] = []
    for sample in samples:
        items: list[dict[str, Any]] = []
        for th in sample.get("threads") or []:
            if not isinstance(th, dict):
                continue
            name = str(th.get("name") or "").strip()
            if not name:
                continue
            try:
                usage = int(th.get("usage") or 0)
            except (TypeError, ValueError):
                usage = 0
            k = finding_kind.get(name, "")
            if name == app_name:
                kl = "应用场景"
            else:
                kl = kind_zh.get(k, "")
            items.append(
                {
                    "name": name,
                    "usage": usage,
                    "pid": th.get("pid"),
                    "kind_label": kl,
                }
            )
        items.sort(key=lambda x: (-int(x.get("usage") or 0), str(x.get("name") or "")))
        round_threads.append(items)

    return {
        "rounds": rounds,
        "lanes": lanes,
        "round_threads": round_threads,
        "fixed_count": _K_THREAD_HEATMAP_FIXED,
        "round_count": len(rounds),
        "lane_count": len(lanes),
    }


_HEATMAP_GENERIC_LABELS = {
    "",
    "converted",
    "analysis",
    "mobilelog",
    "downloads",
    "temp",
    "netlog",
    "networklog",
    "aplog",
    "高功耗",
    "低功耗",
}


def _is_generic_heatmap_label(label: str) -> bool:
    s = str(label or "").strip()
    if not s:
        return True
    if s.lower() in _HEATMAP_GENERIC_LABELS:
        return True
    if s in {"测试机", "对比机"}:
        return True
    return False


def _infer_device_label_from_path(path_like: Any) -> str:
    """从 APLog 路径推断机型/项目名，如 .../APLog_xxx_CN6 -> CN6。"""
    try:
        p = Path(str(path_like or ""))
    except Exception:
        return ""
    parts = list(p.parts)
    for part in reversed(parts):
        name = str(part)
        if name.startswith("APLog"):
            # APLog_2026_0626_163327__6_CN6 / APLog_xxx_X6887
            m = re.search(r"_([A-Za-z][A-Za-z0-9]{1,15})$", name)
            if m and m.group(1).lower() not in _HEATMAP_GENERIC_LABELS:
                return m.group(1)
        if (
            len(name) <= 16
            and name[0].isalpha()
            and any(ch.isdigit() for ch in name)
            and name.lower() not in _HEATMAP_GENERIC_LABELS
            and not name.startswith("APLog")
        ):
            # e.g. directory CN6 / X6887
            return name
    return ""


def _heatmap_display_label(ctx: dict[str, Any] | None, label: str = "") -> str:
    """方块图标题用项目/机型名，避免 converted 等目录名。"""
    primary: list[str] = []
    secondary: list[str] = []

    def _add(bucket: list[str], v: Any) -> None:
        s = str(v or "").strip()
        if s and s not in bucket:
            bucket.append(s)

    raw_label = str(label or "").strip()
    if raw_label and not _is_generic_heatmap_label(raw_label):
        _add(primary, raw_label)

    if isinstance(ctx, dict):
        # 路径机型优先（APLog_xxx_CN6 / APLog_xxx_X6887），避免双机都落到 project=CN6
        for key in ("log_path", "analysis_dir", "log_dir"):
            raw = str(ctx.get(key) or "")
            if not raw:
                continue
            _add(primary, _infer_device_label_from_path(raw))
            try:
                p = Path(raw)
                if p.name == "analysis":
                    _add(primary, _infer_device_label_from_path(p.parent))
            except Exception:
                pass

        meta = ctx.get("game_analysis_meta") or ctx.get("report_meta") or {}
        if not isinstance(meta, dict):
            meta = {}
        for key in (
            "device_label",
            "test_device_label",
            "compare_device_label",
            "device_model",
        ):
            _add(secondary, meta.get(key))
        for key in ("project", "affect_project"):
            _add(secondary, meta.get(key))
        summary = ctx.get("summary") or {}
        if isinstance(summary, dict):
            am = summary.get("analysis_meta") or {}
            if isinstance(am, dict):
                _add(secondary, am.get("device_model"))
                _add(secondary, am.get("project"))
            gw = summary.get("game_window") or {}
            if isinstance(gw, dict):
                _add(secondary, gw.get("device"))

    for cand in primary + secondary:
        if not _is_generic_heatmap_label(cand):
            return cand
    if raw_label:
        return raw_label
    return "测试机"


def _format_k_thread_heatmap_html(
    payload: dict[str, Any] | None,
    *,
    label: str = "",
) -> str:
    """渲染 [K] 时间×线程小方块泳道图。

    悬停时画纵向数值虚线，并列出该轮 [K] 采样中实际出现的全部进程与 CPU%。
    """
    if not payload or not payload.get("lanes") or not payload.get("rounds"):
        return ""
    uid = f"kthm_{next(_K_THREAD_HEATMAP_UID)}"
    data_json = json.dumps(payload, ensure_ascii=False)
    title = "线程占用方块图（[K] 采样）"
    if label:
        title = f"{label} · {title}"
    n_lane = max(1, int(payload.get("lane_count") or len(payload.get("lanes") or [])))
    canvas_h = max(220, min(720, 28 + n_lane * 22 + 36))
    return (
        f'<div id="{uid}" class="k-thread-heatmap" style="margin:0 0 12px;">'
        f'<p style="margin:0 0 6px;font-size:12px;font-weight:600;color:var(--color-text-primary);">'
        f"{_esc(title)}</p>"
        f'<p style="margin:0 0 6px;font-size:11px;color:var(--color-text-tertiary);">'
        "横轴为 [K] 采样时间；纵轴自下而上 CPU 由高到低，固定 10 行（第 1 行为应用场景），"
        "异常线程从第 11 行起；未出现的轮次不画方块；"
        "悬停显示纵向虚线，并列出该轮 [K] 采样中实际出现的全部进程与 CPU%。"
        "</p>"
        f'<canvas id="{uid}_cv" style="width:100%;height:{canvas_h}px;border:1px solid '
        f'var(--color-border-tertiary);border-radius:8px;background:#fff;display:block;"></canvas>'
        f"<script>(function(){{"
        f"const payload={data_json};"
        f"const root=document.getElementById('{uid}'); if(!root) return;"
        f"const canvas=document.getElementById('{uid}_cv'); if(!canvas) return;"
        "const tip=document.createElement('div');"
        "tip.style.cssText='position:fixed;display:none;pointer-events:none;z-index:9999;"
        "background:rgba(17,24,39,0.92);color:#fff;padding:6px 8px;border-radius:6px;"
        "font-size:12px;line-height:1.45;box-shadow:0 6px 18px rgba(0,0,0,0.18);"
        "max-height:70vh;overflow:auto;max-width:360px';"
        "document.body.appendChild(tip);"
        "let hoverRi=null;"
        "function fit(){const r=canvas.getBoundingClientRect();"
        "canvas.width=Math.max(320,Math.floor(r.width));"
        "canvas.height=Math.max(180,Math.floor(r.height));}"
        "function draw(){fit(); const ctx=canvas.getContext('2d');"
        "const w=canvas.width,h=canvas.height;"
        "const padL=128,padR=10,padT=10,padB=28;"
        "ctx.clearRect(0,0,w,h);"
        "const lanes=payload.lanes||[], rounds=payload.rounds||[];"
        "const nL=Math.max(lanes.length,1), nR=Math.max(rounds.length,1);"
        "const plotW=Math.max(1,w-padL-padR), plotH=Math.max(1,h-padT-padB);"
        "const laneH=plotH/nL, cellW=plotW/nR;"
        "const sq=Math.max(3, Math.min(laneH*0.72, cellW*0.72));"
        "ctx.strokeStyle='rgba(226,232,240,0.9)'; ctx.lineWidth=1;"
        "for(let i=0;i<=nL;i++){ const y=padT+i*laneH; ctx.beginPath();"
        "ctx.moveTo(padL,y); ctx.lineTo(w-padR,y); ctx.stroke(); }"
        "const fixedN=Number(payload.fixed_count||10);"
        "if(nL>fixedN){ const ySplit=padT+(nL-fixedN)*laneH;"
        "ctx.strokeStyle='rgba(245,158,11,0.55)'; ctx.setLineDash([4,3]);"
        "ctx.beginPath(); ctx.moveTo(4,ySplit); ctx.lineTo(w-padR,ySplit); ctx.stroke();"
        "ctx.setLineDash([]); ctx.fillStyle='#d97706'; ctx.font='10px sans-serif';"
        "ctx.fillText('异常 ↑', 6, ySplit-3); }"
        "lanes.forEach((lane,li)=>{ const drawIdx=nL-1-li;"
        "const y=padT+drawIdx*laneH; const name=String(lane.name||'');"
        "const label=name?(name.length>14?name.slice(0,13)+'…':name):'—';"
        "ctx.fillStyle=lane.empty?'#cbd5e1':(lane.fixed?'#334155':'#b45309');"
        "ctx.font='11px sans-serif'; ctx.fillText(label, 6, y+laneH*0.62);"
        "if(lane.empty||!name) return;"
        "(lane.usages||[]).forEach((u,ri)=>{ if(u==null) return;"
        "const x=padL+ri*cellW+(cellW-sq)/2; const yy=y+(laneH-sq)/2;"
        "ctx.globalAlpha=0.92; ctx.fillStyle=lane.color||'#2563eb';"
        "ctx.fillRect(x,yy,sq,sq); ctx.globalAlpha=1;"
        "ctx.strokeStyle='rgba(15,23,42,0.12)'; ctx.strokeRect(x,yy,sq,sq); });"
        "});"
        "ctx.fillStyle='#64748b'; ctx.font='10px sans-serif';"
        "const ticks=nR<=8?[...Array(nR).keys()]:"
        "[0, Math.floor((nR-1)/2), nR-1];"
        "ticks.forEach(i=>{ const t=rounds[i]||{}; const lab=t.time?"
        "String(t.time).slice(-8):('R'+String(t.round||i+1));"
        "const x=padL+i*cellW+cellW/2; ctx.textAlign='center';"
        "ctx.fillText(lab, x, h-8); }); ctx.textAlign='start';"
        "if(hoverRi!=null && hoverRi>=0 && hoverRi<nR){"
        "const vx=padL+hoverRi*cellW+cellW/2;"
        "ctx.strokeStyle='rgba(15,23,42,0.65)'; ctx.lineWidth=1.4;"
        "ctx.setLineDash([5,4]); ctx.beginPath(); ctx.moveTo(vx,padT);"
        "ctx.lineTo(vx,h-padB); ctx.stroke(); ctx.setLineDash([]); ctx.lineWidth=1;"
        "}"
        "canvas._hm={padL,padR,padT,padB,laneH,cellW,nL,nR,sq}; }"
        "function show(ev,lines){ tip.innerHTML=lines.join('<br>'); tip.style.display='block';"
        "let left=ev.clientX+14, top=ev.clientY+14;"
        "tip.style.left=left+'px'; tip.style.top=top+'px';"
        "const rect=tip.getBoundingClientRect();"
        "if(rect.right>window.innerWidth-8) tip.style.left=Math.max(8, ev.clientX-rect.width-12)+'px';"
        "if(rect.bottom>window.innerHeight-8) tip.style.top=Math.max(8, ev.clientY-rect.height-12)+'px'; }"
        "function hide(){ tip.style.display='none'; }"
        "canvas.onmousemove=function(ev){ const m=canvas._hm; if(!m) return;"
        "const r=canvas.getBoundingClientRect(); const x=ev.clientX-r.left, y=ev.clientY-r.top;"
        "if(x<m.padL||x>canvas.width-m.padR||y<m.padT||y>canvas.height-m.padB){"
        "if(hoverRi!=null){ hoverRi=null; draw(); } hide(); return; }"
        "const ri=Math.min(m.nR-1, Math.max(0, Math.floor((x-m.padL)/m.cellW)));"
        "if(hoverRi!==ri){ hoverRi=ri; draw(); }"
        "const rnd=(payload.rounds||[])[ri]||{};"
        "const rows=(payload.round_threads||[])[ri]||[];"
        "const lines=['轮次 R'+String(rnd.round||ri+1)+(rnd.time?(' · '+rnd.time):''),"
        "'—— 本轮已有进程（'+rows.length+'） ——'];"
        "if(!rows.length){ lines.push('（本轮无线程采样）'); }"
        "rows.forEach(th=>{"
        "const kl=String(th.kind_label||'');"
        "const kind=kl?('['+kl+'] '):'';"
        "const text=kind+String(th.name||'')+': '+String(th.usage??0)+'%';"
        "const esc=text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');"
        "lines.push(kl==='异常'?('<span style=\"color:#f87171\">'+esc+'</span>'):esc);"
        "});"
        "show(ev, lines); };"
        "canvas.onmouseleave=function(){ hoverRi=null; draw(); hide(); };"
        "draw(); window.addEventListener('resize', draw);"
        "})();</script></div>"
    )


def _format_k_thread_heatmap_block(
    ctx: dict[str, Any],
    *,
    label: str = "",
    peer_ctx: dict[str, Any] | None = None,
    peer_label: str = "",
) -> str:
    """单机或双机 [K] 线程方块图。"""
    self_html = _format_k_thread_heatmap_html(
        _build_k_thread_heatmap_payload(ctx),
        label=_heatmap_display_label(ctx, label),
    )
    if peer_ctx is None:
        return self_html
    peer_html = _format_k_thread_heatmap_html(
        _build_k_thread_heatmap_payload(peer_ctx),
        label=_heatmap_display_label(peer_ctx, peer_label),
    )
    return self_html + peer_html


def _format_k_thread_stat_line(th: dict[str, Any]) -> str:
    """对齐 kernel [K] 线程行：usage%  pid  name。"""
    name = str(th.get("name") or "")
    pid = th.get("pid")
    avg = th.get("avg_usage")
    max_u = th.get("max_usage")
    kind = str(th.get("thread_kind") or "")
    try:
        avg_i = int(round(float(avg))) if avg is not None else None
    except (TypeError, ValueError):
        avg_i = None
    pid_s = str(pid) if pid is not None else "-"
    usage_s = f"{avg_i}%" if avg_i is not None else "-%"
    line = f"{usage_s:>4}  {pid_s:>6}  {name}"
    extras: list[str] = []
    kind_zh = _THREAD_KIND_ZH.get(kind, "")
    if kind_zh:
        extras.append(f"{kind_zh}线程")
    if avg is not None and max_u is not None and max_u != avg:
        extras.append(f"峰值{max_u:g}%")
    type_zh = _FINDING_TYPE_ZH.get(str(th.get("finding_type") or ""), "")
    if type_zh and type_zh not in ("游戏线程", "正常基线"):
        extras.append(type_zh)
    if extras:
        line += f"  （{' · '.join(extras)}）"
    return line


def _reconstruct_k_thread_raw(th: dict[str, Any]) -> str:
    """从结构化字段近似还原 [K] 线程行（无真实 raw 时用）。"""
    if isinstance(th.get("raw"), str) and th["raw"].strip():
        return str(th["raw"]).strip()
    try:
        usage = int(th.get("usage") or 0)
    except (TypeError, ValueError):
        usage = 0
    pid = th.get("pid")
    name = str(th.get("name") or "").strip()
    total_ns = th.get("total_ns")
    oom = th.get("oom_adj")
    pid_s = f"{int(pid):>8}" if pid is not None else f"{'-':>8}"
    total_s = f"{int(total_ns)}(ns)" if total_ns is not None else ""
    oom_s = f"{int(oom):>6}" if oom is not None else ""
    return f"[K]  {usage:>6}%  {pid_s}  {name:<20}  {total_s:>18}  {oom_s}".rstrip()


def _reconstruct_k_cpus_raw(cpus: list[Any]) -> str:
    """从 per-core 列表还原 Cpus Usage 行。"""
    vals: list[int] = []
    for v in cpus:
        try:
            vals.append(int(v))
        except (TypeError, ValueError):
            continue
    if not vals:
        return ""
    # 日志偶发第 5/6 核之间缺逗号；展示时统一带逗号，便于阅读
    parts = ", ".join(f"[{v}]" for v in vals)
    return f"[K]  Cpus Usage {parts}"


def _sample_threads_raw_lines(sample: dict[str, Any]) -> list[str]:
    raws = sample.get("threads_raw")
    if isinstance(raws, list) and raws:
        return [str(x).strip() for x in raws if str(x).strip()]
    out: list[str] = []
    for th in sample.get("threads") or []:
        if not isinstance(th, dict):
            continue
        out.append(_reconstruct_k_thread_raw(th))
    return out


def _sample_cpus_raw_line(sample: dict[str, Any]) -> str:
    raw = sample.get("cpus_usage_raw")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return _reconstruct_k_cpus_raw(list(sample.get("cpus_usage") or []))


def _cpus_core_usage_rows(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """每个核一行：usage_by_round + 汇总说明。"""
    n_cores = 0
    for sample in samples:
        cpus = sample.get("cpus_usage") or []
        if isinstance(cpus, list):
            n_cores = max(n_cores, len(cpus))
    rows: list[dict[str, Any]] = []
    for core_id in range(n_cores):
        series: list[dict[str, Any]] = []
        usages: list[int] = []
        for idx, sample in enumerate(samples):
            cpus = sample.get("cpus_usage") or []
            usage: int | None = None
            if isinstance(cpus, list) and core_id < len(cpus):
                try:
                    usage = int(cpus[core_id])
                except (TypeError, ValueError):
                    usage = None
            if usage is not None:
                usages.append(usage)
            series.append(
                {
                    "round": sample.get("round", idx + 1),
                    "round_idx": idx,
                    "time": str(sample.get("time") or ""),
                    "usage": usage,
                    "present": usage is not None,
                }
            )
        avg = round(sum(usages) / len(usages), 1) if usages else None
        mn = min(usages) if usages else None
        mx = max(usages) if usages else None
        avg_s = f"{avg:g}%" if avg is not None else "—"
        range_s = ""
        if mn is not None and mx is not None:
            range_s = f" · min={mn}% · max={mx}%"
        rows.append(
            {
                "title": f"CPU{core_id}",
                "kind": "cpus",
                "occurrence_count": len(usages),
                "total_rounds": len(samples),
                "usage_by_round": series,
                "avg_usage": avg,
                "max_usage": mx,
                "summary": f"[K] Cpus Usage · CPU{core_id} avg={avg_s}{range_s}",
            }
        )
    return rows


def _format_k_sample_raw_details(samples: list[dict[str, Any]]) -> str:
    """底部折叠：每轮 Top 线程原始行 + Cpus Usage 原始行。"""
    if not samples:
        return ""
    thread_blocks: list[str] = []
    cpus_blocks: list[str] = []
    for idx, sample in enumerate(samples):
        rnd = sample.get("round", idx + 1)
        t = str(sample.get("time") or "")
        header = f"轮次 {rnd}" + (f" · {t}" if t else "")
        th_lines = _sample_threads_raw_lines(sample)
        if th_lines:
            body = "\n".join(th_lines)
            thread_blocks.append(
                f'<pre style="margin:0 0 8px;white-space:pre-wrap;word-break:break-all;'
                f'font-size:10px;line-height:1.4;color:var(--color-text-secondary);">'
                f"<strong>{_esc(header)}</strong>\n{_esc(body)}</pre>"
            )
        cpus_line = _sample_cpus_raw_line(sample)
        if cpus_line:
            cpus_blocks.append(
                f'<pre style="margin:0 0 4px;white-space:pre-wrap;word-break:break-all;'
                f'font-size:10px;line-height:1.4;color:var(--color-text-secondary);">'
                f"{_esc(header)}  {_esc(cpus_line)}</pre>"
            )

    parts: list[str] = []
    if thread_blocks:
        parts.append(
            '<details style="margin-top:8px;">'
            f'<summary style="cursor:pointer;font-size:11px;color:var(--color-text-tertiary);">'
            f"线程日志快照（{len(thread_blocks)} 轮 × Top10）· 默认隐藏，点击展开</summary>"
            f'<div style="margin-top:6px;padding:8px 10px;background:var(--color-background-primary);'
            f'border-radius:var(--border-radius-md);">{"".join(thread_blocks)}</div></details>'
        )
    if cpus_blocks:
        parts.append(
            '<details style="margin-top:6px;">'
            f'<summary style="cursor:pointer;font-size:11px;color:var(--color-text-tertiary);">'
            f"Cpus Usage 日志快照（{len(cpus_blocks)}）· 默认隐藏，点击展开</summary>"
            f'<div style="margin-top:6px;padding:8px 10px;background:var(--color-background-primary);'
            f'border-radius:var(--border-radius-md);">{"".join(cpus_blocks)}</div></details>'
        )
    return "".join(parts)


def _thread_round_curve_svg(series: list[dict[str, Any]], *, height: int = 72) -> str:
    """轮次曲线：按实际峰值自动比例；悬停显示轮次与 CPU%。"""
    if not series:
        return ""
    n = len(series)
    width = 340
    pad_l, pad_r, pad_t, pad_b = 28, 40, 12, 16
    plot_w = max(1, width - pad_l - pad_r)
    plot_h = max(20, height - pad_t - pad_b)
    baseline = pad_t + plot_h

    usages: list[float | None] = []
    rounds: list[Any] = []
    for i, pt in enumerate(series):
        rounds.append(pt.get("round", i + 1))
        if pt.get("present"):
            try:
                usages.append(float(pt.get("usage") or 0))
            except (TypeError, ValueError):
                usages.append(0.0)
        else:
            usages.append(None)
    present_vals = [u for u in usages if u is not None]
    if not present_vals:
        return (
            f'<div class="thread-round-wrap" style="position:relative;width:100%;">'
            f'<svg class="thread-round-curve" viewBox="0 0 {width} {height}" width="100%" '
            f'height="{height}" preserveAspectRatio="xMidYMid meet" role="img">'
            f'<text x="{width / 2:.0f}" y="{height / 2:.0f}" text-anchor="middle" '
            f'font-size="11" fill="#94a3b8">—</text></svg></div>'
        )

    raw_max = max(present_vals)
    # 按真实峰值留白；游戏线程可 >100%，不再封顶 120
    y_max = max(10.0, raw_max * 1.15)
    if y_max <= 20:
        y_max = max(10.0, round(y_max * 2) / 2)
    elif y_max <= 100:
        y_max = float(int((y_max + 4) // 5 * 5) or 5)
    else:
        y_max = float(int((y_max + 9) // 10 * 10))

    def _x(i: int) -> float:
        if n <= 1:
            return pad_l + plot_w / 2
        return pad_l + (i / (n - 1)) * plot_w

    def _y(v: float) -> float:
        vv = max(0.0, min(float(v), y_max))
        return pad_t + (1.0 - (vv / y_max)) * plot_h

    segments: list[list[tuple[float, float]]] = []
    cur: list[tuple[float, float]] = []
    for i, u in enumerate(usages):
        if u is None:
            if cur:
                segments.append(cur)
                cur = []
            continue
        cur.append((_x(i), _y(u)))
    if cur:
        segments.append(cur)

    lines = ""
    for seg in segments:
        if len(seg) == 1:
            x, y = seg[0]
            lines += f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.2" fill="#ef4444"/>'
        else:
            pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in seg)
            lines += (
                f'<polyline fill="none" stroke="#ef4444" stroke-width="1.8" '
                f'stroke-linejoin="round" stroke-linecap="round" '
                f'vector-effect="non-scaling-stroke" points="{pts}"/>'
            )

    grid = ""
    for frac, label in ((0.0, f"{y_max:.0f}"), (0.5, f"{y_max / 2:.0f}"), (1.0, "0")):
        yy = pad_t + plot_h * frac
        grid += (
            f'<line x1="{pad_l}" y1="{yy:.1f}" x2="{width - pad_r}" y2="{yy:.1f}" '
            f'stroke="#eceae4" stroke-width="1"/>'
            f'<text x="{pad_l - 4}" y="{yy + 3:.1f}" text-anchor="end" '
            f'font-size="9" fill="#94a3b8">{label}</text>'
        )

    x_labels = ""
    tick_idx = sorted({0, (n - 1) // 2, n - 1})
    for i in tick_idx:
        x_labels += (
            f'<text x="{_x(i):.1f}" y="{height - 3}" text-anchor="middle" '
            f'font-size="9" fill="#94a3b8">R{_esc(rounds[i])}</text>'
        )

    last_i = max(i for i, u in enumerate(usages) if u is not None)
    last_v = float(usages[last_i] or 0)
    end_label = (
        f'<text x="{min(_x(last_i) + 4, width - pad_r):.1f}" y="{_y(last_v) + 3:.1f}" '
        f'font-size="10" font-weight="600" fill="#dc2626">{last_v:.0f}%</text>'
    )
    avg_v = sum(present_vals) / len(present_vals)
    meta = (
        f'<text x="{width - 4}" y="10" text-anchor="end" font-size="9" fill="#64748b">'
        f"avg {avg_v:.0f}% · {len(present_vals)}/{n}</text>"
    )

    xs_js = ",".join(f"{_x(i):.2f}" for i in range(n))
    us_js = ",".join("null" if u is None else f"{u:.2f}" for u in usages)
    rd_js = ",".join(json.dumps(str(r), ensure_ascii=False) for r in rounds)
    # 每条曲线唯一 id，避免同轮次多线程 hash 碰撞导致悬停失效
    uid = f"trcurve{next(_THREAD_CURVE_UID)}"

    return (
        f'<div id="{uid}-wrap" class="thread-round-wrap" style="position:relative;width:100%;'
        f'box-sizing:border-box;" data-pad-l="{pad_l}" data-vb-w="{width}">'
        f'<svg id="{uid}-svg" class="thread-round-curve" viewBox="0 0 {width} {height}" width="100%" '
        f'height="{height}" preserveAspectRatio="xMidYMid meet" role="img" '
        f'aria-label="线程轮次 CPU 曲线" style="display:block;cursor:crosshair;">'
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#fff"/>'
        f"{grid}"
        f'<line x1="{pad_l}" y1="{baseline}" x2="{width - pad_r}" y2="{baseline}" '
        f'stroke="#d4d2cb" stroke-width="1"/>'
        f"{lines}{end_label}{x_labels}{meta}"
        f'<line id="{uid}-guide" x1="0" y1="{pad_t}" x2="0" y2="{baseline}" '
        f'stroke="#94a3b8" stroke-width="1" stroke-dasharray="3 3" visibility="hidden"/>'
        f'<circle id="{uid}-dot" cx="0" cy="0" r="3.5" fill="#ef4444" stroke="#fff" '
        f'stroke-width="1.2" visibility="hidden"/>'
        f"</svg>"
        f'<div id="{uid}-tip" style="display:none;position:absolute;z-index:6;pointer-events:none;'
        f'padding:5px 8px;border-radius:6px;font-size:11px;line-height:1.35;'
        f'background:rgba(28,28,30,.92);color:#fff;white-space:nowrap;"></div>'
        f"<script>(function(){{"
        f"var wrap=document.getElementById('{uid}-wrap');"
        f"var svg=document.getElementById('{uid}-svg');"
        f"var tip=document.getElementById('{uid}-tip');"
        f"var dot=document.getElementById('{uid}-dot');"
        f"var guide=document.getElementById('{uid}-guide');"
        f"if(!wrap||!svg||!tip||!dot)return;"
        f"var xs=[{xs_js}], us=[{us_js}], rd=[{rd_js}];"
        f"var yMax={y_max:.4f}, padT={pad_t}, padB={pad_b}, vbH={height}, vbW={width};"
        f"function nearest(xVb){{var best=0,bd=1e9;for(var i=0;i<xs.length;i++){{"
        f"var d=Math.abs(xs[i]-xVb);if(d<bd){{bd=d;best=i;}}}}return best;}}"
        f"function show(xVb,cx,cy){{var i=nearest(xVb);var v=us[i];"
        f"if(v===null||v===undefined){{tip.style.display='none';"
        f"dot.setAttribute('visibility','hidden');"
        f"if(guide)guide.setAttribute('visibility','hidden');return;}}"
        f"var y=padT+(1-(+v)/yMax)*(vbH-padT-padB);"
        f"dot.setAttribute('cx',xs[i]);dot.setAttribute('cy',y);"
        f"dot.setAttribute('visibility','visible');"
        f"if(guide){{guide.setAttribute('x1',xs[i]);guide.setAttribute('x2',xs[i]);"
        f"guide.setAttribute('visibility','visible');}}"
        f"tip.style.display='block';"
        f"tip.textContent='R'+rd[i]+' · '+(+v).toFixed(0)+'%';"
        f"var wr=wrap.getBoundingClientRect();"
        f"var left=cx-wr.left+10, top=cy-wr.top-28;"
        f"if(left+tip.offsetWidth>wr.width-4) left=cx-wr.left-tip.offsetWidth-10;"
        f"if(top<2) top=cy-wr.top+14;"
        f"tip.style.left=left+'px';tip.style.top=top+'px';}}"
        f"function hide(){{tip.style.display='none';dot.setAttribute('visibility','hidden');"
        f"if(guide)guide.setAttribute('visibility','hidden');}}"
        f"svg.addEventListener('mousemove',function(e){{"
        f"var r=svg.getBoundingClientRect();"
        f"var xVb=((e.clientX-r.left)/Math.max(1,r.width))*vbW;"
        f"show(xVb,e.clientX,e.clientY);}});"
        f"svg.addEventListener('mouseleave',hide);"
        f"}})();</script></div>"
    )


def _thread_investigation_findings(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    """T_game [K] 全量线程整体统计：游戏 + 正常基线 + 异常，同名一次，按出现次数降序。"""
    summary = ctx.get("summary") or {}
    cmp_out = summary.get("comparison_outputs") or {}
    inv = cmp_out.get("cpu_thread_investigation") or {}
    raw = [dict(f) for f in (inv.get("findings") or []) if isinstance(f, dict)]
    samples = _t_game_cpu_samples(ctx)
    if not samples:
        return []

    finding_by_name: dict[str, dict[str, Any]] = {}
    type_rank = {"persistent_non_baseline": 0, "spike": 1, "single_shot": 2}
    for f in raw:
        name = str(f.get("name") or "").strip()
        if not name:
            continue
        prev = finding_by_name.get(name)
        if not prev:
            finding_by_name[name] = f
            continue
        prev_occ = int(prev.get("occurrence_count") or 0)
        cur_occ = int(f.get("occurrence_count") or 0)
        prev_tr = type_rank.get(str(prev.get("finding_type")), 9)
        cur_tr = type_rank.get(str(f.get("finding_type")), 9)
        if cur_occ > prev_occ or (cur_occ == prev_occ and cur_tr < prev_tr):
            if not f.get("usage_by_round") and prev.get("usage_by_round"):
                f = dict(f)
                f["usage_by_round"] = prev.get("usage_by_round")
            finding_by_name[name] = f

    # 从采样轮次聚合全部线程名
    all_names: set[str] = set()
    for sample in samples:
        for th in sample.get("threads") or []:
            if isinstance(th, dict):
                n = str(th.get("name") or "").strip()
                if n:
                    all_names.add(n)
    all_names.update(finding_by_name.keys())

    game_ctx = inv.get("game_process_context") or {}
    if not isinstance(game_ctx, dict):
        game_ctx = {}
    game_package = ""
    meta = ctx.get("game_analysis_meta") or {}
    tw = ctx.get("game_time_window") or {}
    gw = (summary.get("game_window") or tw.get("game_window") or {}) if isinstance(summary, dict) else {}
    if isinstance(gw, dict):
        game_package = str(gw.get("package") or "")
    if not game_package and isinstance(meta, dict):
        game_package = str(meta.get("game_package") or "")
    if not game_package:
        pkgs = game_ctx.get("packages") or []
        if pkgs:
            game_package = str(pkgs[0])

    try:
        baseline = _load_baseline_for_threads()
        baseline_rules = list(baseline.get("common_processes") or [])
        # 补齐后缀到 game_ctx，便于识别游戏线程
        suffixes = list(game_ctx.get("subprocess_suffixes") or [])
        for suf in baseline.get("game_thread_suffixes") or []:
            if suf and suf not in suffixes:
                suffixes.append(suf)
        game_ctx = dict(game_ctx)
        game_ctx["subprocess_suffixes"] = suffixes
    except Exception:
        baseline_rules = []

    findings: list[dict[str, Any]] = []
    for name in all_names:
        base = dict(finding_by_name.get(name) or {"name": name})
        series = _thread_usage_by_round(name, samples, base.get("usage_by_round"))
        occ = sum(1 for p in series if p.get("present"))
        usages = [int(p["usage"]) for p in series if p.get("present") and p.get("usage") is not None]
        pid = base.get("pid")
        for p in reversed(series):
            if p.get("present") and p.get("pid") is not None:
                pid = p.get("pid")
                break
        kind = _classify_thread_kind(
            name,
            pid if isinstance(pid, int) or (pid is not None and str(pid).isdigit()) else None,
            game_package=game_package,
            game_ctx=game_ctx,
            baseline_rules=baseline_rules,
            finding_names=set(finding_by_name.keys()),
        )
        if kind == "game":
            finding_type = "game_thread"
            priority = "GAME"
            detail = "游戏主进程/子线程（[K] Top 列表统计）"
        elif kind == "normal":
            finding_type = "baseline_thread"
            priority = "NORMAL"
            detail = "系统基线正常线程（[K] Top 列表统计）"
        else:
            finding_type = str(base.get("finding_type") or "persistent_non_baseline")
            priority = str(base.get("priority") or ("P1" if occ >= 3 else "P2"))
            detail = str(base.get("detail") or "非基线线程（[K] Top 列表统计）")

        item = {
            **base,
            "name": name,
            "pid": int(pid) if pid is not None and str(pid).isdigit() else pid,
            "thread_kind": kind,
            "finding_type": finding_type,
            "priority": priority,
            "detail": detail,
            "usage_by_round": series,
            "occurrence_count": occ,
            "total_rounds": len(series),
            "avg_usage": round(sum(usages) / len(usages), 2) if usages else None,
            "max_usage": max(usages) if usages else None,
        }
        findings.append(item)

    findings.sort(
        key=lambda x: (
            -int(x.get("occurrence_count") or 0),
            {"abnormal": 0, "game": 1, "normal": 2}.get(str(x.get("thread_kind")), 9),
            -float(x.get("avg_usage") or 0),
            -float(x.get("max_usage") or 0),
        )
    )
    return findings


def _background_category_highlights(ctx: dict[str, Any]) -> list[str]:
    bg = ctx.get("game_background") or {}
    breakdown = bg.get("category_breakdown_T_game") or {}
    if not isinstance(breakdown, dict):
        return []
    lines: list[tuple[int, str]] = []
    for cat, count in breakdown.items():
        try:
            n = int(count)
        except (TypeError, ValueError):
            continue
        if n <= 0:
            continue
        label = _BG_CATEGORY_ZH.get(str(cat), str(cat))
        lines.append((n, f"{label} {n} 次"))
    lines.sort(reverse=True)
    return [text for _, text in lines[:5]]


_TRIGGER_DIRECTION: dict[str, str] = {
    "abn_background_process": "对照 baseline 进程列表冻结可疑后台，逐项关闭后复测 CPU 与电流",
    "abn_process_restart": "抓取 am_proc_start 触发源，测试前清理自启动/关联应用后复测",
    "abn_broadcast_storm": "定位高频 Broadcast 注册方，评估 sticky/有序广播是否过量",
    "abn_alarm_storm": "核对 AlarmManager / JobScheduler 触发频率与对齐窗口",
    "abn_gc_storm": "排查内存泄漏或大对象分配导致的频繁 GC",
    "abn_thermal_ineffective": "核对温控降频策略是否生效，对比竞品同场景温度曲线",
    "abn_weak_rf_power": "弱网时核对 RSRP 与发射功率，建议固定 WiFi 或强信号环境复测",
    "abn_freq_boost": "核对内核 cpufreq 提频策略与游戏场景调度是否合理",
}


def _prio_sort_key(priority: str) -> tuple[int, int]:
    order = {"P0": 0, "P1": 1, "P2": 2, "OBSERVE": 3}
    return (order.get(str(priority or "P2").upper(), 9), 0)


def _humanize_rule_detail(detail: str) -> str:
    text = str(detail or "").strip()
    if not text:
        return "规则命中，详见仪表板原始证据"
    if "abnormal_processes=" in text:
        return "多进程在 T_game 内持续超出基线 CPU 占用（详见上方线程明细）"
    m = re.search(r"category_breakdown_T_game\.(\w+)=(\d+)", text)
    if m:
        cat = _BG_CATEGORY_ZH.get(m.group(1), m.group(1))
        return f"游戏时段{cat}事件 {m.group(2)} 次"
    if "max_c=" in text and "freq_throttle" in text:
        return "游戏时段温升明显但未触发降频节流"
    if "rf_stats.level" in text or "wifi_rssi" in text or "rsrp" in text.lower():
        if "suspect" in text or "weak" in text:
            return "网络射频质量判定为弱/可疑（相对强网标准或波动偏大）"
        return "网络信号相关规则命中"
    # 去掉规则引擎原始 ✓/✗ 串
    if "game_network." in text and (" in [" in text or " eq " in text or " lt " in text):
        return "网络信号相关规则命中（详见具体原因）"
    if len(text) > 120:
        return text[:117] + "…"
    return text


def _looks_like_raw_log(text: str) -> bool:
    """owner_hint / detail 若是原始日志行，报告侧不直接展示。"""
    t = str(text or "").strip()
    if not t:
        return False
    if re.search(r"\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}", t):
        return True
    markers = (
        "am_proc_",
        "am_proc_start",
        "events_log",
        "main_log",
        "sys_log",
        "Binder:",
        "queueBuffer:",
        " uid=",
        " pid=",
    )
    if any(m in t for m in markers):
        return True
    # path:line: 前缀的证据行
    if re.match(r"^[\w.\-]+(?:/\S+)?:\d+:\s", t):
        return True
    return False


def _thread_direction(th: dict[str, Any], ctx: dict[str, Any]) -> str:
    kind = str(th.get("thread_kind") or "")
    name = str(th.get("name") or "").lower()
    if kind == "game":
        return "游戏主进程/子线程对照基线；若明显高于对比机，核对画质/帧率/引擎负载"
    if kind == "normal":
        return "系统基线线程；若明显高于对比机，核对唤醒源、策略差异与关联服务"
    if "bluetooth" in name or name.startswith("bt"):
        if _tag_display(ctx, "bt", "") == "ON":
            return "关闭蓝牙后复测，确认 com.android.bluetooth 与 BLE 扫描是否消失"
        return "排查蓝牙协议栈与后台扫描策略"
    if "touch" in name:
        return "移交 TP/触控驱动，核对触控上报频率与游戏场景负载"
    if "mali" in name or "gpu" in name:
        return "核对 GPU 频率与画质档位，对比同场景 GPU 占用"
    if "hif_thread" in name or "wlan" in name or "wifi" in name:
        return "核对 WiFi 吞吐与扫描策略，必要时固定信道后复测"
    if "kfps" in name or name.endswith("fps"):
        return "核对显示/合成帧率策略与 vsync，排除异常刷帧"
    if "dsp" in name:
        return "核对多媒体 DSP/音频通路是否在游戏时段异常唤醒"
    if "kswapd" in name or name.startswith("mm_"):
        return "排查内存压力与回收路径，核对是否存在泄漏或后台杀进程抖动"
    if "surfaceflinger" in name or "composer" in name or "hwc" in name:
        return "核对刷新率/HWC 合成策略与图层复杂度"
    if "audioserver" in name or "audio" in name:
        return "核对游戏音量与音频轨占用，排除后台录音/播报"
    if "system_server" in name:
        return "结合 binder/job/alarm 关联，定位 system_server 忙碌来源"
    if "binder" in name:
        return "排查高频 binder 调用方与跨进程通信热点"
    if "logd" in name:
        return "确认是否开启过量日志/埋点导致 logd 抬升"
    if "rms" in name or "transsion" in name:
        return "核对传音系统服务策略（自启动/场景识别）是否在游戏时段过度介入"
    if "gms" in name or "google" in name or "firebase" in name:
        return "冻结/限制 GMS 相关后台后复测，排除推送与同步"
    if name.startswith("cpu") and name[3:].isdigit():
        return "对照同段 Top 线程与温控限频，确认该核高占用责任线程"
    return "对照 [K] 关联日志与同名进程归属，排除非基线负载后复测"


def _thread_module(th: dict[str, Any]) -> str:
    """线程/核涉及模块（短标签，供说明列展示）。"""
    kind = str(th.get("thread_kind") or "")
    name = str(th.get("name") or "").strip()
    name_l = name.lower()
    hints = th.get("owner_hints") if isinstance(th.get("owner_hints"), list) else []
    hint = str(th.get("owner_hint") or (hints[0] if hints else "") or "").strip()
    if kind == "game":
        return "游戏进程/引擎"
    if name_l.startswith("cpu") and name_l[3:].isdigit():
        return "CPU 调度 / cpufreq"
    rules: list[tuple[str, str]] = [
        (r"touch", "触控/TP 驱动"),
        (r"mali|gpu", "GPU/图形驱动"),
        (r"hif_thread|wlan|wifi", "WiFi/WLAN 驱动"),
        (r"bluetooth|^bt", "蓝牙协议栈"),
        (r"surfaceflinger|composer|hwc", "显示合成 (SF/HWC)"),
        (r"audioserver|audio", "音频 (audioserver)"),
        (r"system_server", "系统框架 (system_server)"),
        (r"kfps|(^|[^a-z])fps", "显示/帧率内核线程"),
        (r"dsp", "多媒体 DSP"),
        (r"kswapd|^mm_", "内存回收"),
        (r"logd", "日志服务 (logd)"),
        (r"binder", "Binder IPC"),
        (r"rms|transsion", "传音系统服务"),
        (r"gms|google|firebase|katana", "GMS/第三方服务"),
        (r"ue4|unity|il2cpp|pubgm|\.ig:|ncent\.ig", "游戏引擎/游戏进程"),
    ]
    for pat, label in rules:
        if re.search(pat, name_l):
            return label
    if hint:
        # 取 hint 前段作模块名，避免贴整段原始日志
        short = re.split(r"[「，,：:]", hint)[0].strip()
        short = re.sub(r"\s+", " ", short)
        if short and not _looks_like_raw_log(short):
            return short[:40]
    if kind == "normal":
        return "系统基线进程"
    return "待定（按进程名/PID 归属排查）"


def _fmt_usage_pct(val: Any) -> str:
    if val is None or val == "":
        return "—"
    try:
        return f"{float(val):.0f}%"
    except (TypeError, ValueError):
        return "—"


def _thread_compare_snap_line(
    entry: dict[str, Any],
    peer: dict[str, Any] | None,
) -> str:
    """有对比日志时：同名单项 avg/峰值/出现次数对比。缺侧不写文案（单元格留空）。"""
    if entry.get("missing"):
        return ""
    if not peer or peer.get("missing"):
        return "同项对比：对比侧未出现"
    sa, sm = entry.get("avg_usage"), entry.get("max_usage")
    pa, pm = peer.get("avg_usage"), peer.get("max_usage")
    so = int(entry.get("occ") or 0)
    st = int(entry.get("total") or 0)
    po = int(peer.get("occ") or 0)
    pt = int(peer.get("total") or 0)
    delta = ""
    try:
        if sa is not None and pa is not None:
            d = float(sa) - float(pa)
            if abs(d) < 1:
                delta = "（接近）"
            else:
                delta = f"（本侧{'高' if d > 0 else '低'} {abs(d):.0f}pp）"
    except (TypeError, ValueError):
        delta = ""
    return (
        f"同项对比：avg {_fmt_usage_pct(sa)}→{_fmt_usage_pct(pa)}{delta}"
        f" · 峰值 {_fmt_usage_pct(sm)}→{_fmt_usage_pct(pm)}"
        f" · 出现 {so}/{st or '—'}→{po}/{pt or '—'}"
    )


def _build_thread_detail_snap_html(
    *,
    summary: str,
    direction: str = "",
    module: str = "",
    compare_line: str = "",
) -> str:
    """说明列：[K] 摘要 +（可选）同项对比 + 排查方向 + 涉及模块。"""
    lines: list[tuple[str, str]] = []
    if summary:
        lines.append(("", summary))
    if compare_line:
        lines.append(("同项", compare_line))
    if direction:
        lines.append(("排查方向", direction if direction.startswith("排查") else f"排查方向：{direction}"))
    if module:
        lines.append(("涉及模块", module if module.startswith("涉及") else f"涉及模块：{module}"))
    parts: list[str] = []
    for kind, text in lines:
        color = "var(--color-text-secondary)"
        if kind == "同项":
            color = "var(--blue-700, #1d4ed8)"
        elif kind in ("排查方向", "涉及模块"):
            color = "var(--color-text-primary)"
        parts.append(
            f'<div class="snap-line" style="color:{color};">{_esc(text)}</div>'
        )
    return "".join(parts) if parts else '<div class="snap-line">—</div>'


def _finalize_abnormal_entry_html(
    entry: dict[str, Any],
    peer: dict[str, Any] | None = None,
    *,
    with_compare: bool = False,
) -> dict[str, Any]:
    """根据结构化字段重渲染行 HTML；with_compare 时写入同项对比。"""
    out = dict(entry)
    if entry.get("missing"):
        out["compare_line"] = ""
        out["html"] = _abnormal_thread_row_html(
            left_html=str(entry.get("left_html") or _esc(str(entry.get("key") or "—"))),
            count_html="",
            snap_html="",
            curve_html="",
        )
        return out
    compare_line = _thread_compare_snap_line(entry, peer) if with_compare else ""
    out["compare_line"] = compare_line
    snap = _build_thread_detail_snap_html(
        summary=str(entry.get("summary") or "—"),
        direction=str(entry.get("direction") or ""),
        module=str(entry.get("module") or ""),
        compare_line=compare_line,
    )
    out["html"] = _abnormal_thread_row_html(
        left_html=str(entry.get("left_html") or _esc(str(entry.get("key") or "—"))),
        count_html=str(entry.get("count_html") or "—"),
        snap_html=snap,
        curve_html=str(entry.get("curve_html") or "—"),
    )
    return out


def _abnormal_triple_rows(problem: str, reason: str, direction: str) -> str:
    fields = (
        ("问题", problem, "var(--coral-600)", "500"),
        ("原因", reason, "var(--color-text-secondary)", "400"),
        ("分析方向", direction, "var(--blue-600)", "400"),
    )
    rows: list[str] = []
    for label, text, color, weight in fields:
        if not text:
            continue
        rows.append(
            f'<div style="display:grid;grid-template-columns:64px 1fr;column-gap:10px;'
            f'row-gap:2px;font-size:12px;line-height:1.55;margin-bottom:5px;">'
            f'<span style="color:var(--color-text-tertiary);font-weight:500;">{_esc(label)}</span>'
            f'<span style="color:{color};font-weight:{weight};">{_esc(text)}</span></div>'
        )
    return "".join(rows)


def _abnormal_insight_card(
    *,
    title: str,
    problem: str,
    reason: str,
    direction: str,
    priority: str,
    source: str = "",
) -> str:
    p_bg, p_fg = _priority_badge(priority)
    source_html = ""
    if source:
        source_html = (
            f'<span style="margin-left:auto;font-size:11px;color:var(--color-text-tertiary);">'
            f'{_esc(source)}</span>'
        )
    return (
        f'<div style="padding:10px 12px;margin-bottom:8px;background:var(--color-background-primary);'
        f'border-radius:var(--border-radius-md);border:0.5px solid var(--color-border-tertiary);">'
        f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">'
        f'<span style="font-size:11px;font-weight:600;padding:2px 8px;border-radius:4px;'
        f'background:{p_bg};color:{p_fg};">{_esc(priority)}</span>'
        f'<span style="font-size:13px;font-weight:600;color:var(--color-text-primary);">{_esc(title)}</span>'
        f"{source_html}"
        f"</div>"
        f"{_abnormal_triple_rows(problem, reason, direction)}"
        f"</div>"
    )


def _build_thread_insight_items(
    threads: list[dict[str, Any]],
    ctx: dict[str, Any],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for th in threads:
        name = str(th.get("name") or "")
        kind = str(th.get("thread_kind") or "abnormal")
        type_zh = _FINDING_TYPE_ZH.get(str(th.get("finding_type") or ""), _THREAD_KIND_ZH.get(kind, "线程"))
        occ = int(th.get("occurrence_count") or 0)
        total = int(th.get("total_rounds") or 0)
        k_line = _format_k_thread_stat_line(th)
        direction = _thread_direction(th, ctx)
        module = _thread_module(th)
        items.append(
            {
                "kind": "thread",
                "thread_kind": kind,
                "title": name,
                "problem": name,
                "summary": k_line,
                "reason": type_zh,
                "direction": direction,
                "module": module,
                "priority": str(th.get("priority") or "P2"),
                "source": "线程排查",
                "occurrence_count": occ,
                "total_rounds": total,
                "avg_usage": th.get("avg_usage"),
                "max_usage": th.get("max_usage"),
                "usage_by_round": th.get("usage_by_round") or [],
                "owner_hint": th.get("owner_hint"),
                "owner_hints": th.get("owner_hints") or [],
                "_score": float(occ),
            }
        )
    return items


def _build_bg_insight_items(suggestions: list[dict[str, str]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for sug in suggestions[:4]:
        pkg = str(sug.get("package") or "")
        title = pkg or "后台活动"
        issue = str(sug.get("issue") or "")
        problem = f"{title} 游戏时段后台活动显著升高"
        reason = issue
        if issue.startswith(title):
            reason = issue[len(title) :].strip(" ，")
        if not reason:
            reason = "T_game 相对 T_pre 后台事件频次明显升高"
        items.append(
            {
                "kind": "background",
                "title": f"后台 · {title}",
                "problem": problem,
                "summary": reason or "T_game 相对 T_pre 后台事件频次明显升高",
                "reason": reason,
                "direction": str(sug.get("suggestion") or "排查唤醒链路与服务绑定"),
                "priority": str(sug.get("priority") or "P2"),
                "source": "优化建议",
                "occurrence_count": None,
                "_score": 0.0,
            }
        )
    return items


def _build_triggered_insight_items(triggered: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for rule in triggered:
        rid = str(rule.get("id") or "")
        label = str(rule.get("label") or rid)
        if rid == "abn_background_process":
            # 与「异常进程CPU…」重复，统一由线程明细 + 前者概括
            continue
        reason = _humanize_rule_detail(str(rule.get("detail") or ""))
        items.append(
            {
                "kind": "rule",
                "rule_id": rid,
                "title": label,
                "problem": label,
                "summary": reason,
                "reason": reason,
                "raw_detail": str(rule.get("detail") or ""),
                "direction": _TRIGGER_DIRECTION.get(rid, "结合仪表板证据逐项排除后复测"),
                "priority": str(rule.get("priority") or "P2"),
                "source": "规则命中",
                "occurrence_count": None,
                "_score": 0.0,
            }
        )
    return items


def _abnormal_row_detail_lines(item: dict[str, Any]) -> list[str]:
    """异常问题说明栏：一句话摘要 +（可选）短分析方向；不贴原始日志。"""
    summary = str(item.get("summary") or "").strip()
    if not summary:
        summary = str(item.get("problem") or item.get("reason") or "").strip()
    if _looks_like_raw_log(summary):
        summary = str(item.get("direction") or "详见关联子报告").strip()
    # 总结表不再把「分析方向」混进现象列
    if str(item.get("kind") or "") in ("rule", "background"):
        return [summary if len(summary) <= 160 else summary[:157] + "…"] if summary else ["—"]
    direction = str(item.get("direction") or "").strip()
    lines: list[str] = []
    if summary:
        lines.append(summary if len(summary) <= 160 else summary[:157] + "…")
    if direction and direction != summary and not _looks_like_raw_log(direction):
        if direction not in summary:
            lines.append(direction if len(direction) <= 120 else direction[:117] + "…")
    return lines or ["—"]


def _top_abnormal_thread_names(ctx: dict[str, Any], *, limit: int = 4) -> list[str]:
    names: list[str] = []
    for th in _thread_investigation_findings(ctx):
        if str(th.get("thread_kind") or "") != "abnormal":
            continue
        name = str(th.get("name") or "").strip()
        if name and name not in names:
            names.append(name)
        if len(names) >= limit:
            break
    return names


def _summary_specific_cause(item: dict[str, Any], ctx: dict[str, Any]) -> str:
    """总结项末列：具体原因说明（区别于上方线程明细）。"""
    kind = str(item.get("kind") or "")
    rid = str(item.get("rule_id") or "")
    if kind == "rule":
        if rid in ("abn_cpu_over_10_not_game", "abn_background_process"):
            tops = _top_abnormal_thread_names(ctx)
            if tops:
                return (
                    "非基线线程持续进入 [K] Top："
                    + "、".join(tops)
                    + " 等（详见上方线程明细）"
                )
            return "T_game 内存在持续超出基线的非游戏/非白名单进程（详见上方线程明细）"
        if rid == "abn_process_restart":
            return "游戏时段 am_proc_start / 进程拉起事件偏多，后台服务反复启动增加唤醒与 CPU"
        if rid == "abn_wifi_weak_or_volatile":
            return "射频质量判定为弱/可疑（rf_stats=suspect），弱网易抬升数传与扫描功耗"
        if rid == "abn_broadcast_storm":
            return "游戏时段 Broadcast 频次异常偏高，导致进程唤醒与 binder 开销上升"
        if rid == "abn_alarm_storm":
            return "Alarm/Job 触发偏密，周期性唤醒抬升待机与前台边沿功耗"
        if rid == "abn_gc_storm":
            return "频繁 GC 占用 CPU，多与内存抖动或大对象分配有关"
        if rid == "abn_weak_rf_power":
            return "弱信号下发射功率抬升，数传功耗明显高于强网环境"
        direction = str(item.get("direction") or "").strip()
        return direction or "结合上方线程/网络子报告进一步确认"
    if kind == "background":
        summary = str(item.get("summary") or item.get("reason") or "")
        title = str(item.get("title") or "")
        tag = ""
        for m in re.finditer(r"\[([^\]]+)\]", summary):
            tag = m.group(1)
            break
        boost = ""
        m2 = re.search(r"(\d+(?:\.\d+)?)\s*倍", summary)
        if m2:
            boost = m2.group(1)
        name = title.replace("后台 · ", "").strip() or "后台组件"
        if tag.lower() in ("job", "alarm"):
            return (
                f"{name} 在 T_game 的 {tag} 活动约为 T_pre 的 {boost or '多'} 倍，"
                f"周期性唤醒/调度抬升后台功耗"
            )
        if "crash" in tag.lower():
            return f"{name} 崩溃上报链路在游戏时段活跃（约 {boost or '多'} 倍），额外占用 CPU/网络"
        if boost:
            return f"{name} 游戏时段后台事件约为开局前的 {boost} 倍，存在额外唤醒或绑定"
        return str(item.get("direction") or "后台组件在游戏时段活动升高，需排查唤醒链路")
    return str(item.get("direction") or "—")


def _build_abnormal_insight_items(
    ctx: dict[str, Any],
    triggered: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    suggestions = _optimization_suggestions(ctx)
    threads = _thread_investigation_findings(ctx)
    items: list[dict[str, Any]] = []
    items.extend(_build_thread_insight_items(threads, ctx))
    other: list[dict[str, Any]] = []
    other.extend(_build_triggered_insight_items(triggered))
    other.extend(_build_bg_insight_items(suggestions))
    other.sort(key=lambda x: (_prio_sort_key(x.get("priority", "P2")), -float(x.get("_score") or 0)))
    seen_titles: set[str] = {str(x.get("title") or "") for x in items}
    for item in other:
        key = str(item.get("title") or "")
        if key in seen_titles:
            continue
        seen_titles.add(key)
        items.append(item)
    other_cap = 8
    out: list[dict[str, Any]] = []
    other_n = 0
    for item in items:
        if item.get("kind") == "thread":
            out.append(item)
            continue
        if other_n >= other_cap:
            continue
        out.append(item)
        other_n += 1
    return out


def _format_current_spike_abnormal_item(ctx: dict[str, Any]) -> str:
    """异常问题第 1 项：电流图对比（DOU current_cpu_spike）。"""
    block = ctx.get("game_current_cpu_spike") or ctx.get("game_current_waveform") or {}
    head = (
        '<p style="margin:0 0 8px;font-size:12px;line-height:1.5;color:var(--color-text-secondary);">'
        '<span style="font-weight:600;color:var(--amber-600);">一、电流图分析：</span>'
        "双机 pt5 对齐对比（DOU current_cpu_spike）；无两份电流图则跳过</p>"
    )
    if not isinstance(block, dict) or not block:
        return (
            head
            + '<p style="margin:0 0 12px;font-size:13px;color:var(--color-text-tertiary);">'
            "未提供电流图（pt5），跳过电流对比分析。可用 "
            "<code>run_game_current_cpu_spike.py</code> 生成后刷新本报告。</p>"
        )
    html_frag = str(block.get("report_html") or "").strip()
    if html_frag:
        return head + f'<div style="margin:0 0 12px;">{html_frag}</div>'
    status = str(block.get("status") or "")
    if status == "skipped":
        return (
            head
            + '<p style="margin:0 0 12px;font-size:13px;color:var(--color-text-tertiary);">'
            f'{_esc(block.get("message") or "未提供电流图，跳过电流分析")}</p>'
        )
    summary = str(block.get("summary") or block.get("message") or "").strip()
    if summary:
        return (
            head
            + f'<p style="margin:0 0 12px;font-size:13px;color:var(--color-text-secondary);">'
            f"{_esc(summary)}</p>"
        )
    return (
        head
        + '<p style="margin:0 0 12px;font-size:13px;color:var(--color-text-tertiary);">'
        "电流图分析结果为空</p>"
    )


def _format_hardware_difference_media(ctx: dict[str, Any]) -> str:
    """器件差异：不再嵌入电流图（已迁至异常问题第 1 项）。"""
    _ = ctx
    return ""


def _abnormal_thread_row_html(
    *,
    left_html: str,
    count_html: str,
    snap_html: str,
    curve_html: str = "",
) -> str:
    _ = curve_html  # 轮次曲线已合并到上方 [K] 方块图
    return (
        f'<tr><td class="cause">{left_html}</td>'
        f'<td class="count">{_esc(count_html)}</td>'
        f'<td class="detail"><div class="snap-compact">{snap_html}</div></td></tr>'
    )


def _abnormal_side_cells_html(entry: dict[str, Any]) -> str:
    """单侧：总次数 + 说明（不含线程/核名）。缺侧留空以保持对齐。"""
    if entry.get("missing"):
        return (
            '<td class="count"></td>'
            '<td class="detail"></td>'
        )
    snap = _build_thread_detail_snap_html(
        summary=str(entry.get("summary") or "—"),
        direction=str(entry.get("direction") or ""),
        module=str(entry.get("module") or ""),
        compare_line=str(entry.get("compare_line") or ""),
    )
    return (
        f'<td class="count">{_esc(str(entry.get("count_html") or "—"))}</td>'
        f'<td class="detail"><div class="snap-compact">{snap}</div></td>'
    )


def _abnormal_merged_row_html(entry_a: dict[str, Any], entry_b: dict[str, Any]) -> str:
    """双机合并行：共用线程/核名，其余左右分列。"""
    if entry_a.get("missing") and not entry_b.get("missing"):
        left = str(entry_b.get("left_html") or _esc(str(entry_b.get("key") or "—")))
    else:
        left = str(
            entry_a.get("left_html")
            or entry_b.get("left_html")
            or _esc(str(entry_a.get("key") or entry_b.get("key") or "—"))
        )
    return (
        f'<tr><td class="cause">{left}</td>'
        f"{_abnormal_side_cells_html(entry_a)}"
        f"{_abnormal_side_cells_html(entry_b)}"
        f"</tr>"
    )


def _abnormal_missing_row_html(title: str, *, kind_badge: str = "—") -> str:
    return str(_abnormal_missing_entry(title, kind_badge=kind_badge).get("html") or "—")


def _abnormal_missing_entry(title: str, *, kind_badge: str = "—") -> dict[str, Any]:
    """对齐缺侧占位：同名行保留，缺侧次数/说明/曲线留空。"""
    kind = "abnormal"
    if kind_badge == "游戏":
        kind = "game"
    elif kind_badge == "正常":
        kind = "normal"
    left = (
        f'<span style="font-size:11px;font-weight:600;padding:1px 6px;border-radius:4px;'
        f'margin-right:6px;background:var(--color-background-tertiary);'
        f'color:var(--color-text-tertiary);">{_esc(kind_badge)}</span>'
        f"{_esc(title)}"
    )
    entry = {
        "key": title,
        "missing": True,
        "badge": kind_badge,
        "group": "core" if kind_badge == "核" else "thread",
        "thread_kind": kind,
        "left_html": left,
        "count_html": "",
        "curve_html": "",
        "summary": "",
        "direction": "",
        "module": "",
        "compare_line": "",
        "avg_usage": None,
        "max_usage": None,
        "occ": 0,
        "total": 0,
    }
    # 不渲染说明文案；html 仅供单机缺行兼容
    out = dict(entry)
    out["html"] = _abnormal_thread_row_html(
        left_html=left,
        count_html="",
        snap_html="",
        curve_html="",
    )
    return out


def _collect_abnormal_table_entries(
    ctx: dict[str, Any],
    triggered: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """返回 (thread_entries, core_entries, meta)。entry 含 key/html/sort 信息。"""
    items = _build_abnormal_insight_items(ctx, triggered)
    samples = _t_game_cpu_samples(ctx)
    total_rounds = len(samples)
    thread_items = [x for x in items if x.get("kind") == "thread"]
    summary_items = [x for x in items if x.get("kind") in ("rule", "background")]
    cpus_rows = _cpus_core_usage_rows(samples) if samples else []
    kind_rank = {"game": 0, "abnormal": 1, "normal": 2}

    thread_entries: list[dict[str, Any]] = []
    for item in thread_items:
        title = str(item.get("title") or item.get("problem") or "线程")
        tk = str(item.get("thread_kind") or "abnormal")
        label, p_bg, p_fg = _thread_kind_badge(tk, str(item.get("priority") or "P2"))
        left = (
            f'<span style="font-size:11px;font-weight:600;padding:1px 6px;border-radius:4px;'
            f'margin-right:6px;background:{p_bg};color:{p_fg};">{_esc(label)}</span>'
            f"{_esc(title)}"
        )
        occ = item.get("occurrence_count")
        total = item.get("total_rounds") or total_rounds
        if occ is None:
            count_html = "—"
        elif total:
            count_html = f"{int(occ)}/{int(total)}"
        else:
            count_html = str(int(occ))
        entry = {
            "key": title,
            "group": "thread",
            "thread_kind": tk,
            "occ": int(occ or 0),
            "total": int(total or 0),
            "avg_usage": item.get("avg_usage"),
            "max_usage": item.get("max_usage"),
            "badge": label,
            "left_html": left,
            "count_html": count_html,
            "curve_html": "",
            "summary": str(item.get("summary") or "—"),
            "direction": str(item.get("direction") or "").strip(),
            "module": str(item.get("module") or "").strip() or _thread_module(item),
            "sort": (kind_rank.get(tk, 9), -int(occ or 0), title.lower()),
        }
        thread_entries.append(_finalize_abnormal_entry_html(entry, with_compare=False))

    core_entries: list[dict[str, Any]] = []
    for item in cpus_rows:
        title = str(item.get("title") or "CPU")
        left = (
            f'<span style="font-size:11px;font-weight:600;padding:1px 6px;border-radius:4px;'
            f'margin-right:6px;background:var(--blue-50, #eff6ff);color:var(--blue-700, #1d4ed8);">核</span>'
            f"{_esc(title)}"
        )
        occ = item.get("occurrence_count")
        total = item.get("total_rounds") or total_rounds
        if occ is None:
            count_html = "—"
        elif total:
            count_html = f"{int(occ)}/{int(total)}"
        else:
            count_html = str(int(occ))
        try:
            core_idx = int(title.replace("CPU", "").strip() or "0")
        except ValueError:
            core_idx = 99
        entry = {
            "key": title,
            "group": "core",
            "badge": "核",
            "occ": int(occ or 0),
            "total": int(total or 0),
            "avg_usage": item.get("avg_usage"),
            "max_usage": item.get("max_usage"),
            "left_html": left,
            "count_html": count_html,
            "curve_html": "",
            "summary": str(item.get("summary") or "—"),
            "direction": "对照同段 Top 线程与温控限频，确认该核高占用责任线程",
            "module": "CPU 调度 / cpufreq",
            "sort": (core_idx,),
        }
        core_entries.append(_finalize_abnormal_entry_html(entry, with_compare=False))

    meta = {
        "total_rounds": total_rounds,
        "thread_items": thread_items,
        "summary_items": summary_items,
        "cpus_rows": cpus_rows,
        "samples": samples,
        "cat_hi": _background_category_highlights(ctx),
        "n_game": sum(1 for x in thread_items if x.get("thread_kind") == "game"),
        "n_normal": sum(1 for x in thread_items if x.get("thread_kind") == "normal"),
        "n_abn": sum(1 for x in thread_items if x.get("thread_kind") == "abnormal"),
    }
    return thread_entries, core_entries, meta


def _align_abnormal_entries(
    entries_a: list[dict[str, Any]],
    entries_b: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """按 key 对齐两侧行；缺侧补「日志未搜到」。"""
    by_a = {str(e["key"]): e for e in entries_a}
    by_b = {str(e["key"]): e for e in entries_b}
    # 排序：用两侧更优的 sort key
    keys = sorted(
        set(by_a) | set(by_b),
        key=lambda k: (by_a.get(k) or by_b.get(k) or {}).get("sort") or (9, 0, k),
    )
    out_a: list[dict[str, Any]] = []
    out_b: list[dict[str, Any]] = []
    for k in keys:
        ea = by_a.get(k)
        eb = by_b.get(k)
        badge = (ea or eb or {}).get("badge") or "—"
        if ea:
            out_a.append(ea)
        else:
            out_a.append(_abnormal_missing_entry(k, kind_badge=str(badge)))
        if eb:
            out_b.append(eb)
        else:
            out_b.append(_abnormal_missing_entry(k, kind_badge=str(badge)))
    return out_a, out_b


def _apply_abnormal_peer_compare(
    entries_a: list[dict[str, Any]],
    entries_b: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """双机对齐后，两侧说明列写入同项对比。"""
    out_a = [
        _finalize_abnormal_entry_html(ea, eb, with_compare=True)
        for ea, eb in zip(entries_a, entries_b)
    ]
    out_b = [
        _finalize_abnormal_entry_html(eb, ea, with_compare=True)
        for ea, eb in zip(entries_a, entries_b)
    ]
    return out_a, out_b


def _abnormal_thread_head_html(
    meta: dict[str, Any],
    *,
    peer_meta: dict[str, Any] | None = None,
    label_a: str = "",
    label_b: str = "",
) -> str:
    """线程明细标题；双机时合并为一行说明。"""
    def _bits(m: dict[str, Any], label: str = "") -> list[str]:
        bits: list[str] = []
        total_rounds = m.get("total_rounds") or 0
        cpus_rows = m.get("cpus_rows") or []
        thread_items = m.get("thread_items") or []
        n_game = m.get("n_game") or 0
        n_normal = m.get("n_normal") or 0
        n_abn = m.get("n_abn") or 0
        prefix = f"{label} " if label else ""
        if total_rounds:
            bits.append(f"{prefix}T_game {total_rounds} 轮" if label else f"T_game 共 {total_rounds} 轮 [K] 采样")
        if cpus_rows and not label:
            bits.append(f"Cpus Usage {len(cpus_rows)} 核")
        if thread_items and not label:
            bits.append(
                f"线程 {len(thread_items)} 个（异常 {n_abn} / 游戏 {n_game} / 正常 {n_normal}）"
            )
        elif thread_items and label:
            bits.append(f"线程 {len(thread_items)}")
        return bits

    if peer_meta is not None:
        head_bits = _bits(meta, label_a) + _bits(peer_meta, label_b)
    else:
        head_bits = _bits(meta)
    cat_hi = meta.get("cat_hi") or []
    if not head_bits and not cat_hi:
        return ""
    bg = f'；后台概况：{_esc("、".join(cat_hi))}' if cat_hi else ""
    return (
        f'<p style="margin:0 0 8px;font-size:12px;line-height:1.5;color:var(--color-text-secondary);">'
        f'<span style="font-weight:600;color:var(--amber-600);">二、线程明细（[K] 采样）：</span>'
        f'{_esc(" · ".join(head_bits)) if head_bits else "—"}{bg}'
        f"（下方方块图：横轴时间 × 纵轴线程）"
        f"</p>"
    )


def _format_abnormal_merged_thread_table(
    ctx: dict[str, Any],
    triggered: list[dict[str, Any]],
    peer_ctx: dict[str, Any],
    peer_triggered: list[dict[str, Any]],
    *,
    label_a: str,
    label_b: str,
) -> str:
    """双机：线程明细仅保留方块图（不再输出总次数/[K] 说明表）。"""
    _, _, meta_a = _collect_abnormal_table_entries(ctx, triggered)
    _, _, meta_b = _collect_abnormal_table_entries(peer_ctx, peer_triggered)
    head = _abnormal_thread_head_html(meta_a, peer_meta=meta_b, label_a=label_a, label_b=label_b)
    heatmap = _format_k_thread_heatmap_block(
        ctx,
        label=label_a or "测试机",
        peer_ctx=peer_ctx,
        peer_label=label_b or "对比机",
    )
    if not head and not heatmap:
        return ""
    return head + heatmap


def _format_abnormal_summary_block(
    ctx: dict[str, Any],
    summary_items: list[dict[str, Any]],
) -> str:
    summary_body: list[str] = []
    for item in summary_items:
        title = str(item.get("title") or item.get("problem") or "总结项")
        label = str(item.get("priority") or "P2").upper()
        p_bg, p_fg = _priority_badge(label)
        left = (
            f'<span style="font-size:11px;font-weight:600;padding:1px 6px;border-radius:4px;'
            f'margin-right:6px;background:{p_bg};color:{p_fg};">{_esc(label)}</span>'
            f"{_esc(title)}"
        )
        phenomenon = "；".join(_abnormal_row_detail_lines(item))
        cause = _summary_specific_cause(item, ctx)
        summary_body.append(
            f'<tr><td class="cause">{left}</td>'
            f'<td class="detail"><div class="snap-compact">'
            f'<div class="snap-line">{_esc(phenomenon)}</div></div></td>'
            f'<td class="reason">{_esc(cause)}</td></tr>'
        )
    if not summary_body:
        return ""
    return (
        '<p style="margin:14px 0 8px;font-size:12px;line-height:1.5;color:var(--color-text-secondary);">'
        '<span style="font-weight:600;color:var(--amber-600);">三、问题总结（规则/后台）：</span>'
        "与上方线程明细区分；末列为具体原因说明</p>"
        '<table class="cause-table methodology-table abnormal-summary-table">'
        "<thead><tr><th>问题</th><th>现象说明</th><th>具体原因</th></tr></thead>"
        f"<tbody>{''.join(summary_body)}</tbody></table>"
    )


def _format_abnormal_situation_media(
    ctx: dict[str, Any],
    triggered: list[dict[str, Any]],
    *,
    peer_ctx: dict[str, Any] | None = None,
    peer_triggered: list[dict[str, Any]] | None = None,
    side: str = "self",
    parts: str = "all",
) -> str:
    """异常问题媒体。

    parts:
      - all: 电流图(第1项) + 线程表 + 问题总结（单机）
      - summary: 仅问题总结（双机分栏用；电流图/线程表由外层单独输出）
    """
    thr_self, core_self, meta = _collect_abnormal_table_entries(ctx, triggered)
    if peer_ctx is not None and parts == "all":
        # 兼容旧调用：双机全量仍按单侧表对齐（新路径走 merged table）
        thr_peer, core_peer, _ = _collect_abnormal_table_entries(peer_ctx, peer_triggered or [])
        if side == "self":
            thr_pri, thr_cmp = thr_self, thr_peer
            core_pri, core_cmp = core_self, core_peer
        else:
            thr_pri, thr_cmp = thr_peer, thr_self
            core_pri, core_cmp = core_peer, core_self
        thr_pri, thr_cmp = _align_abnormal_entries(thr_pri, thr_cmp)
        core_pri, core_cmp = _align_abnormal_entries(core_pri, core_cmp)
        thr_pri, thr_cmp = _apply_abnormal_peer_compare(thr_pri, thr_cmp)
        core_pri, core_cmp = _apply_abnormal_peer_compare(core_pri, core_cmp)
        thread_entries = thr_pri if side == "self" else thr_cmp
        core_entries = core_pri if side == "self" else core_cmp
    else:
        thread_entries = thr_self
        core_entries = core_self

    summary_items = meta.get("summary_items") or []
    if parts == "summary":
        return _format_abnormal_summary_block(ctx, summary_items)

    spike_block = _format_current_spike_abnormal_item(ctx)
    if not thread_entries and not core_entries and not summary_items:
        return spike_block

    thread_head = _abnormal_thread_head_html(meta)
    heatmap = _format_k_thread_heatmap_block(ctx)

    summary_block = _format_abnormal_summary_block(ctx, summary_items)
    network_block = _format_network_analysis_media(ctx)
    if not heatmap and not summary_block and not network_block:
        return spike_block
    return spike_block + thread_head + heatmap + network_block + summary_block



def _format_test_methodology_media(ctx: dict[str, Any]) -> str:
    """测试手法不符不再内嵌亮度/音量卡片，统一走下方「原因 | 说明/快照」表。"""
    return ""


def _format_brightness_section(ctx: dict[str, Any]) -> str:
    """兼容旧调用：整段 section 包装（已迁移至测试手法内嵌）。"""
    inner = _format_brightness_media_block(ctx)
    if not inner:
        return ""
    return f'<div class="section">{inner}</div>'


def _norm_cond_token(text: str) -> str:
    s = str(text or "").strip().lower()
    s = s.replace("wifi", "wi-fi").replace("wlan", "wi-fi")
    s = s.replace("（", "(").replace("）", ")")
    mapping = {
        "开": "on",
        "关": "off",
        "开启": "on",
        "关闭": "off",
        "true": "on",
        "false": "off",
        "1": "on",
        "0": "off",
        "wi-fi": "wifi",
        "wi‑fi": "wifi",
    }
    if s in mapping:
        return mapping[s]
    if s.upper() in ("ON", "OFF"):
        return s.lower()
    return s


def _cond_values_match(required: str, actual: str, tag_id: str = "") -> bool:
    """要求 vs 实际是否视为一致（用于着色）。"""
    req = str(required or "").strip()
    act = str(actual or "").strip()
    if not req or not act or _is_missing_display(req) or _is_missing_display(act):
        return False
    if _norm_cond_token(req) == _norm_cond_token(act):
        return True
    # 网络：WIFI ≈ WiFi
    if tag_id == "wifi":
        rn = _norm_cond_token(req)
        an = _norm_cond_token(act)
        if rn in ("wifi", "wi-fi") and "wifi" in an.replace(" ", ""):
            return True
        if rn in ("数据网络", "data", "cellular") and ("数据" in act or "cellular" in an):
            return True
    # 场景：识别到游戏即视为满足「游戏前台稳定段」
    if tag_id == "scene":
        if "游戏前台" in req and not _is_missing_display(act):
            return True
        if req in act or act in req:
            return True
    # 后台：无异常
    if tag_id == "background":
        if "无异常" in req and act == "未见明显异常":
            return True
    # 亮度：等级精确匹配；nit 允许容差（与 nits_tolerance 对齐）
    if tag_id == "brightness":
        def _num(s: str) -> str | None:
            m = re.search(r"(\d+(?:\.\d+)?)", s.replace(",", ""))
            return m.group(1) if m else None

        rn, an = _num(req), _num(act)
        if rn is not None and an is not None:
            try:
                diff = abs(float(rn) - float(an))
            except ValueError:
                return rn == an
            if "nit" in (req + act).lower():
                return diff <= 20
            return diff < 1e-6
    # 刷新率 Auto：常见 60Hz 视为可接受
    if tag_id == "refresh_rate" and req.lower() == "auto":
        m = re.match(r"^(\d+)\s*hz$", act.lower())
        if m and int(m.group(1)) <= 90:
            return True
    # SIM/数据：左右两段均需一致（SIM侧 / 数据侧）
    if tag_id == "sim_data" and "/" in req and "/" in act:
        rp = [p.strip() for p in req.split("/", 1)]
        ap = [p.strip() for p in act.split("/", 1)]
        if len(rp) == 2 and len(ap) == 2:
            return _cond_values_match(rp[0], ap[0], "data") and _cond_values_match(
                rp[1], ap[1], "sim"
            )
    return False


def _cond_status_class(tag_id: str, ctx: dict[str, Any]) -> str:
    if tag_id == "scene":
        actual = _scene_actual_display(ctx)
        if actual and not _is_missing_display(actual):
            return "color: var(--color-text-success);"
        return "color: var(--color-text-danger);"
    if tag_id == "background":
        actual = _background_actual_display(ctx)
        if actual == "未见明显异常":
            return "color: var(--color-text-success);"
        return "color: var(--color-text-danger);"
    pre = ctx.get("game_precondition") or {}
    tag = _find_tag(_get_path(pre, "test_conditions.tags"), tag_id)
    if not tag:
        return ""
    status = str(tag.get("status", ""))
    if status in ("warn", "bad"):
        return "color: var(--color-text-danger);"
    if status == "ok":
        return "color: var(--color-text-success);"
    return ""


def _format_duration(seconds: int | float | None) -> str:
    try:
        sec = int(seconds or 0)
    except (TypeError, ValueError):
        return "—"
    if sec <= 0:
        return "—"
    mins = sec // 60
    rem = sec % 60
    if mins >= 1:
        return f"{mins}min{rem}s" if rem else f"{mins}min"
    return f"{sec}s"


def _esc(text: Any) -> str:
    return html.escape(str(text if text is not None else ""), quote=True)


def _bump_report_font_sizes(html_text: str, delta: int = 2) -> str:
    """澄清报告全局字号：CSS / 内联 / SVG 的 font-size 一律 +delta（默认加大两号）。"""
    if not html_text or not delta:
        return html_text

    def _css(m: re.Match[str]) -> str:
        try:
            n = float(m.group(2))
        except ValueError:
            return m.group(0)
        bumped = n + delta
        num = str(int(bumped)) if bumped == int(bumped) else f"{bumped:g}"
        return f"{m.group(1)}{num}{m.group(3)}"

    out = re.sub(r"(font-size:\s*)(\d+(?:\.\d+)?)(px)", _css, html_text, flags=re.IGNORECASE)
    out = re.sub(r'(font-size=")(\d+(?:\.\d+)?)(")', _css, out, flags=re.IGNORECASE)
    return out


def _priority_badge(priority: str) -> tuple[str, str]:
    p = (priority or "P2").upper()
    if p == "P0":
        return "var(--red-50)", "var(--red-600)"
    if p == "P1":
        return "var(--amber-50)", "var(--amber-600)"
    return "var(--color-background-secondary)", "var(--color-text-secondary)"


def _fmt_ma_display(val: Any, fallback: str = "—") -> str:
    if val is None or val == "":
        return fallback
    try:
        return f"{float(val):.1f} mA"
    except (TypeError, ValueError):
        return str(val)


def _power_delta_extras_html(power_delta: dict[str, Any] | None) -> str:
    """原因分析开头：整体功耗差闭环 + 电流图差异点汇总。

    不重复第 3 节「器件功耗拆解」的分项明细；此处只保留 I1 与扣器件后的残差。
    """
    if not power_delta:
        return ""
    wf = power_delta.get("waveform_analysis") or {}
    routing = power_delta.get("routing") or {}
    known_sum = power_delta.get("known_delta_sum_ma")
    residual = power_delta.get("residual_after_known_ma")
    unexplained = power_delta.get("unexplained_ma")
    after_known = residual if residual is not None else unexplained
    i1 = power_delta.get("delta_power_ma_i1")
    i1_source = str(power_delta.get("i1_source") or "").strip()
    test_ma = power_delta.get("test_power_ma")
    comp_ma = power_delta.get("competitor_power_ma")
    dual = wf.get("dual_current_summary") if isinstance(wf.get("dual_current_summary"), dict) else {}
    diff_points = [x for x in (wf.get("diff_points") or []) if isinstance(x, dict)]

    # —— 汇总文案（器件分项见第 3 节，此处不展开）——
    if i1 is not None:
        src = f"（{i1_source}）" if i1_source else ""
        headline = f"整体电流差 I1 ≈ {_fmt_ma_display(i1)}{src}"
        if after_known is not None and known_sum is not None:
            headline += f"；差异−器件功耗 {_fmt_ma_display(after_known)}（器件明细见第 3 节）"
        elif after_known is not None:
            headline += f"；差异−器件功耗 {_fmt_ma_display(after_known)}"
        else:
            headline += "；器件拆解暂无量化，残留按 I1 继续分析"
    else:
        headline = "尚未确认整体功耗差 I1（问题单与电流图均缺对齐均值）"

    # 闭环卡片：不展示器件分项/合计（与第 3 节重复）
    cards = [
        ("整体差 I1", _fmt_ma_display(i1), i1_source or "待确认"),
        ("差异−器件功耗", _fmt_ma_display(after_known), routing.get("decision") or "—"),
    ]
    if dual.get("floor_diff_ma") is not None or dual.get("baseline_diff_ma") is not None:
        floor_txt = _fmt_ma_display(dual.get("floor_diff_ma"))
        base_txt = _fmt_ma_display(dual.get("baseline_diff_ma"))
        cards.append(("底电/基线差", f"{floor_txt} / {base_txt}", "电流图"))

    card_html = "".join(
        f'<div style="padding:10px 12px;border-radius:var(--border-radius-md);'
        f'background:var(--color-background-secondary);min-width:0;">'
        f'<p style="margin:0 0 4px;font-size:11px;color:var(--color-text-tertiary);">{_esc(title)}</p>'
        f'<p style="margin:0;font-size:16px;font-weight:600;color:var(--color-text-primary);">{_esc(val)}</p>'
        f'<p style="margin:4px 0 0;font-size:11px;color:var(--color-text-secondary);">{_esc(sub)}</p>'
        f"</div>"
        for title, val, sub in cards
    )

    # 电流图差异点
    points_html = ""
    if diff_points:
        rows = []
        for p in diff_points[:6]:
            kind = str(p.get("kind") or "差异")
            time_txt = str(p.get("time") or "—")
            mean_v = p.get("mean_diff_ma")
            peak_v = p.get("peak_diff_ma")
            mean_txt = _fmt_ma_display(mean_v) if mean_v is not None else "—"
            peak_txt = _fmt_ma_display(peak_v) if peak_v is not None else "—"
            try:
                mean_f = float(mean_v) if mean_v is not None else 0.0
            except (TypeError, ValueError):
                mean_f = 0.0
            tone = "var(--color-text-danger)" if mean_f > 0 else (
                "var(--color-text-success)" if mean_f < 0 else "var(--color-text-primary)"
            )
            procs = "、".join(str(x) for x in (p.get("processes") or [])[:3] if x)
            reasons = "；".join(str(x) for x in (p.get("reasons") or [])[:2] if x)
            evid = p.get("evidence_strength")
            evid_txt = f" · 证据{evid}" if evid else ""
            detail_bits = []
            if procs:
                detail_bits.append(procs)
            if reasons:
                detail_bits.append(reasons)
            detail = " · ".join(detail_bits) if detail_bits else "—"
            rows.append(
                f'<tr>'
                f'<td style="white-space:nowrap;font-weight:600;color:{tone};">{_esc(kind)}</td>'
                f'<td style="white-space:nowrap;">{_esc(time_txt)}</td>'
                f'<td style="font-variant-numeric:tabular-nums;">{_esc(mean_txt)}'
                f'<span style="color:var(--color-text-tertiary);font-size:11px;"> /峰 {_esc(peak_txt)}</span></td>'
                f'<td style="color:var(--color-text-secondary);font-size:12px;">{_esc(detail)}{_esc(evid_txt)}</td>'
                f"</tr>"
            )
        points_html = (
            '<div style="margin-top:12px;">'
            '<p style="margin:0 0 6px;font-size:12px;font-weight:500;color:var(--color-text-secondary);">'
            '<i class="ti ti-chart-arrows" aria-hidden="true"></i> 电流图差异点</p>'
            '<table style="width:100%;border-collapse:collapse;font-size:13px;">'
            '<thead><tr style="background:var(--color-background-secondary);">'
            '<th style="text-align:left;padding:6px 8px;font-weight:500;color:var(--color-text-tertiary);">类型</th>'
            '<th style="text-align:left;padding:6px 8px;font-weight:500;color:var(--color-text-tertiary);">时段</th>'
            '<th style="text-align:left;padding:6px 8px;font-weight:500;color:var(--color-text-tertiary);">均值差/峰</th>'
            '<th style="text-align:left;padding:6px 8px;font-weight:500;color:var(--color-text-tertiary);">关联线索</th>'
            "</tr></thead>"
            f'<tbody>{"".join(rows)}</tbody></table></div>'
        )
    else:
        # 回退：抬高窗摘要
        raised_n = wf.get("raised_window_count")
        if raised_n:
            points_html = (
                '<p style="margin:12px 0 0;font-size:12px;color:var(--color-text-secondary);">'
                f'电流图检出 {_esc(str(raised_n))} 个抬高窗；'
                f'{_esc(str(wf.get("spike_impact_on_avg") or ""))}</p>'
            )

    # 辅助信息：测试机/对比机均值、抬高窗对均值贡献
    aux_bits: list[str] = []
    if test_ma is not None and comp_ma is not None:
        aux_bits.append(
            f"测试机均值 {_fmt_ma_display(test_ma)} · 对比机均值 {_fmt_ma_display(comp_ma)}"
        )
    if wf.get("spike_impact_on_avg"):
        aux_bits.append(str(wf.get("spike_impact_on_avg")))
    if wf.get("dual_summary"):
        aux_bits.append(str(wf.get("dual_summary")))
    # 单机去掉抬高窗后的均值（不是双机差）
    avg_wo = wf.get("avg_without_raised_windows_ma")
    if avg_wo is None and wf.get("source") and "correlate" in str(wf.get("source")):
        avg_wo = wf.get("avg_delta_without_spike_ma")
    if avg_wo is not None:
        aux_bits.append(f"测试机去掉抬高窗后均值 {_fmt_ma_display(avg_wo)}")
    aux_html = (
        f'<p style="margin:8px 0 0;font-size:12px;color:var(--color-text-tertiary);">'
        f'{_esc(" ｜ ".join(aux_bits))}</p>'
        if aux_bits
        else ""
    )

    reason = routing.get("reason") or ""
    reason_html = (
        f'<p style="margin:10px 0 0;font-size:12px;color:var(--color-text-secondary);'
        f'background:var(--color-background-secondary);padding:8px 10px;border-radius:var(--border-radius-md);">'
        f'{_esc(reason)}</p>'
        if reason
        else ""
    )

    return (
        f'<div style="margin-bottom:4px;">'
        f'<p style="margin:0 0 8px;font-size:12px;font-weight:500;color:var(--color-text-secondary);">'
        f'<i class="ti ti-activity" aria-hidden="true"></i> 整体分析汇总 · 功耗差闭环 / 电流图差异</p>'
        f'<p style="margin:0 0 10px;font-size:13px;font-weight:500;color:var(--color-text-primary);">'
        f'{_esc(headline)}</p>'
        f'<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:8px;">'
        f'{card_html}</div>'
        f'{points_html}{aux_html}{reason_html}</div>'
    )


def _ai_insights_section_html(ai_insights: dict[str, Any] | None) -> str:
    if not ai_insights:
        return ""
    summary = ai_insights.get("summary") or ""
    findings = [f for f in (ai_insights.get("findings") or []) if isinstance(f, dict)]
    steps = [str(s) for s in (ai_insights.get("next_steps") or []) if s]
    review = "是" if ai_insights.get("human_review_required") else "否"
    find_html = ""
    if findings:
        find_html = "".join(
            f'<p style="margin:4px 0;font-size:13px;color:var(--color-text-secondary);">'
            f'<span style="font-weight:500;color:var(--color-text-primary);">'
            f'{_esc(f.get("severity") or "")}</span> · {_esc(f.get("title") or "")}'
            f'{" — " + _esc(str(f.get("detail") or "")[:160]) if f.get("detail") else ""}</p>'
            for f in findings[:8]
        )
    steps_html = ""
    if steps:
        steps_html = (
            f'<ul style="margin:6px 0 0;padding-left:18px;font-size:13px;color:var(--color-text-secondary);">'
            f'{"".join(f"<li style=\'margin:3px 0;\">{_esc(s)}</li>" for s in steps[:8])}</ul>'
        )
    return f"""
  <div class="section">
    <p class="section-title"><i class="ti ti-robot" aria-hidden="true"></i>AI 判断与补充建议</p>
    <p style="margin:0 0 8px;font-size:13px;font-weight:500;">{_esc(summary)}</p>
    <p style="margin:0 0 8px;font-size:12px;color:var(--color-text-tertiary);">需人工复核：{_esc(review)}</p>
    {find_html}
    {('<p style="margin:10px 0 0;font-size:12px;font-weight:500;color:var(--color-text-secondary);">建议下一步</p>' + steps_html) if steps_html else ''}
  </div>"""


def _side_labels(meta: dict[str, Any], ctx: dict[str, Any], compare_ctx: dict[str, Any] | None) -> tuple[str, str]:
    """测试机 / 对比机显示名。"""
    test_label = str(
        meta.get("test_device_label")
        or meta.get("primary_label")
        or (ctx.get("summary") or {}).get("analysis_meta", {}).get("device_model")
        or "测试机"
    ).strip() or "测试机"
    test_label = _heatmap_display_label(ctx, test_label)
    if not compare_ctx:
        return test_label, ""
    comp_label = str(
        meta.get("compare_device_label")
        or meta.get("competitor_label")
        or (compare_ctx.get("summary") or {}).get("analysis_meta", {}).get("device_model")
        or "对比机"
    ).strip() or "对比机"
    comp_label = _heatmap_display_label(compare_ctx, comp_label)
    return test_label, comp_label


def _dual_panel_html(label_a: str, html_a: str, label_b: str, html_b: str) -> str:
    """双栏对比容器；任一侧为空则仍占位。"""
    empty = (
        f'<p style="margin:0;font-size:13px;color:var(--color-text-tertiary);">'
        f"{_esc(_MISSING_DISPLAY)}</p>"
    )
    a = (html_a or "").strip() or empty
    b = (html_b or "").strip() or empty
    return (
        '<div class="dual-compare" style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">'
        f'<div class="dual-side"><p class="dual-label">{_esc(label_a)}</p>{a}</div>'
        f'<div class="dual-side"><p class="dual-label">{_esc(label_b)}</p>{b}</div>'
        "</div>"
    )


def _fmt_hz_compact(value: Any) -> str | None:
    try:
        hz = float(value)
    except (TypeError, ValueError):
        return None
    if abs(hz - round(hz)) < 0.05:
        return f"{int(round(hz))}Hz"
    return f"{hz:.1f}Hz"


def _fmt_nits_compact(value: Any) -> str | None:
    if value is None or value == "":
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    # 对比表统一取整，避免 450.4nit 这类噪音
    return str(int(round(f)))


def _fmt_curve_nits_point(curve: Any, nits: Any) -> str | None:
    """单点：曲线值（nit）；缺一侧则只显示另一侧。"""
    nits_s = _fmt_nits_compact(nits)
    curve_s = None
    if curve is not None and curve != "":
        try:
            curve_s = str(int(round(float(curve))))
        except (TypeError, ValueError):
            curve_s = str(curve)
    if curve_s and nits_s:
        return f"{curve_s}（{nits_s}nit）"
    if nits_s:
        return f"{nits_s}nit"
    if curve_s:
        return f"曲线{curve_s}"
    return None


def _brightness_pre_in_game_points(ctx: dict[str, Any]) -> tuple[str | None, str | None]:
    """进游戏前 / 局内亮度点（曲线+nit）。"""
    gb = ctx.get("game_brightness") or {}
    if not isinstance(gb, dict):
        return None, None
    inv = gb.get("brightness_investigation") or {}
    s1 = inv.get("step1_test_setting") if isinstance(inv, dict) else {}
    s4 = inv.get("step4_aal_strategy") if isinstance(inv, dict) else {}
    if not isinstance(s1, dict):
        s1 = {}
    if not isinstance(s4, dict):
        s4 = {}

    # 进游戏前：优先 AAL 起点曲线 + step1/s4 nits
    pre_curve = (
        s4.get("scene_start_bl")
        or s4.get("in_game_bl_from")
        or s4.get("first_bl")
    )
    pre_nits = s4.get("pre_nits")
    if pre_nits is None:
        pre_nits = s1.get("measured_nits")
    ig = gb.get("in_game_brightness") or {}
    hwc = ig.get("hwcomposer") if isinstance(ig, dict) else {}
    if isinstance(hwc, dict):
        base = hwc.get("baseline_before_game") or {}
        if pre_curve is None and base.get("brightness_val") is not None:
            pre_curve = base.get("brightness_val")
    ba = gb.get("brightness_analysis") or {}
    pg = ba.get("pre_game_setting") if isinstance(ba, dict) else {}
    if isinstance(pg, dict) and pre_curve is None:
        pre_curve = pg.get("curve_val")

    # 局内：稳定曲线 / 尾段 + in_game_nits；缺 nits 时从 timeline / 温控命中兜底
    in_curve = (
        s4.get("stable_bl")
        or s4.get("in_game_bl_to")
        or s4.get("last_bl")
        or s4.get("representative_bl")
    )
    in_nits = s4.get("in_game_nits")
    if isinstance(hwc, dict):
        gw = hwc.get("game_window") or {}
        if in_curve is None:
            tail = gw.get("stable_tail") or {}
            plateau = gw.get("stable_plateau") or {}
            # 局内稳定优先尾段（进游戏后稳态）
            in_curve = tail.get("brightness_val") or plateau.get("brightness_val") or gw.get("brightness_val_min")
    if in_nits is None:
        # timeline 末点 nit：如 "2045 351nit → 2923 450nit"
        timeline = str(s4.get("timeline") or "")
        parts = [p.strip() for p in timeline.replace("→", "→").split("→") if p.strip()]
        if parts:
            m = re.search(r"(\d+(?:\.\d+)?)\s*nit", parts[-1], flags=re.IGNORECASE)
            if m:
                in_nits = m.group(1)
            m2 = re.match(r"(?:曲线)?(\d+)", parts[-1])
            if in_curve is None and m2:
                in_curve = m2.group(1)
    if in_nits is None:
        s5 = inv.get("step5_thermal_control") if isinstance(inv, dict) else {}
        if isinstance(s5, dict):
            for h in s5.get("relevant_hits") or []:
                if isinstance(h, dict) and str(h.get("window") or "") in ("T_game", "game_entry", "launch"):
                    if h.get("brightness_nits") is not None:
                        in_nits = h.get("brightness_nits")
                        break

    pre = _fmt_curve_nits_point(pre_curve, pre_nits)
    ing = _fmt_curve_nits_point(in_curve, in_nits)
    return pre, ing


def _brightness_compare_metric_display(ctx: dict[str, Any]) -> str:
    """测试数据对比表亮度：进游戏前 → 局内（曲线/nit）。"""
    pre, ing = _brightness_pre_in_game_points(ctx)
    if pre and ing:
        if pre == ing:
            return pre
        return f"{pre} → {ing}"
    if pre:
        return f"{pre} → —"
    if ing:
        return f"— → {ing}"
    # 兜底：旧逻辑（设置等级）
    return _brightness_actual_display(ctx)


def _refresh_rate_compare_display(ctx: dict[str, Any]) -> str:
    """屏幕刷新率：优先 brightness_investigation.step6 / refresh_rate.investigation。"""
    gb = ctx.get("game_brightness") or {}
    inv = (gb.get("brightness_investigation") or {}) if isinstance(gb, dict) else {}
    s6 = inv.get("step6_refresh_rate") if isinstance(inv, dict) else {}
    if not isinstance(s6, dict):
        s6 = {}
    supported = s6.get("supported_fps") if isinstance(s6.get("supported_fps"), dict) else {}
    actual = s6.get("actual_fps") if isinstance(s6.get("actual_fps"), dict) else {}
    rr = gb.get("refresh_rate") if isinstance(gb, dict) else {}
    rinv = (rr.get("investigation") or {}) if isinstance(rr, dict) else {}
    if not supported and isinstance(rinv, dict):
        supported = rinv.get("supported_fps") if isinstance(rinv.get("supported_fps"), dict) else {}
    if not actual and isinstance(rinv, dict):
        actual = rinv.get("actual_fps") if isinstance(rinv.get("actual_fps"), dict) else {}

    sup = _fmt_hz_compact(supported.get("last_hz") if supported else None)
    act_raw = None
    if actual:
        act_raw = actual.get("avg_hz")
        if act_raw is None:
            act_raw = actual.get("last_hz")
    act = _fmt_hz_compact(act_raw)
    if sup and act:
        return f"{sup}(实际{act})"
    if sup:
        return sup
    if act:
        return act

    mode = None
    if isinstance(rr, dict):
        mode = rr.get("mode") or rr.get("current") or rr.get("value")
        if mode is None:
            tg = rr.get("T_game") if isinstance(rr.get("T_game"), dict) else {}
            mode = tg.get("stable_hz") or tg.get("max_hz")
    if mode is not None:
        hz = _fmt_hz_compact(mode)
        return hz or str(mode)
    fps_stats = _get_path(ctx.get("summary") or {}, "comparison_outputs.frame_rate_stats") or {}
    if isinstance(fps_stats, dict) and fps_stats.get("refresh_hz") is not None:
        return _fmt_hz_compact(fps_stats.get("refresh_hz")) or f"{fps_stats.get('refresh_hz')}Hz"
    return _MISSING_DISPLAY


def _avg_fps_compare_display(ctx: dict[str, Any]) -> str:
    """平均帧率：优先 game_cpu_gpu_ddr.frame_rate 主游戏图层。"""
    fr = _cpu_gpu_ddr_block(ctx).get("frame_rate") or {}
    main = fr.get("main_game_layer") if isinstance(fr, dict) else {}
    avg: Any = None
    if isinstance(main, dict):
        avg = main.get("merged_layer_avg_fps")
        if avg is None:
            avg = main.get("avg_queuebuffer_fps")
    if avg is None and isinstance(fr, dict):
        avg = fr.get("avg_fps") or fr.get("avg_queuebuffer_fps")
    if avg is None:
        stats = _get_path(ctx.get("summary") or {}, "comparison_outputs.frame_rate_stats") or {}
        if isinstance(stats, dict):
            avg = stats.get("avg_fps")
    if avg is None:
        return _MISSING_DISPLAY
    try:
        return f"{float(avg):.1f}"
    except (TypeError, ValueError):
        return str(avg)


def _max_temp_compare_display(ctx: dict[str, Any]) -> str:
    """最高温度：优先 thermal_report.temp_max_c。"""
    th = ctx.get("game_thermal") or {}
    if not isinstance(th, dict):
        return _MISSING_DISPLAY
    tr = th.get("thermal_report") or {}
    tmax = tr.get("temp_max_c") if isinstance(tr, dict) else None
    if tmax is None and isinstance(tr, dict):
        tmax = tr.get("temp_max_all_sensors_c")
    if tmax is None:
        tmax = _get_path(th, "summary.max_temp_c") or _get_path(th, "max_temp_c")
    if tmax is None:
        tmax = _get_path(th, "thermal_summary.max_temp_c")
    if tmax is None:
        temp = th.get("temperature") or {}
        if isinstance(temp, dict):
            tmax = temp.get("max_temp_c") or temp.get("max_c") or temp.get("peak_c")
    if tmax is None:
        return _MISSING_DISPLAY
    try:
        return f"{float(tmax):.1f}℃"
    except (TypeError, ValueError):
        return f"{tmax}℃"


def _extract_compare_metric_rows(ctx: dict[str, Any]) -> list[tuple[str, str]]:
    """抽取可并排对比的关键标量。"""
    rows: list[tuple[str, str]] = []
    gw = (ctx.get("summary") or {}).get("game_window") or (
        (ctx.get("game_time_window") or {}).get("game_window") or {}
    )
    if not gw.get("start"):
        tw = (ctx.get("game_time_window") or {}).get("time_windows") or {}
        if isinstance(tw, dict) and isinstance(tw.get("T_game"), dict):
            gw = dict(tw["T_game"])
    rows.append(
        (
            "游戏",
            _display_or_none(
                gw.get("game_name") or (ctx.get("game_time_window") or {}).get("game_name")
            ),
        )
    )
    if gw.get("duration_seconds") is not None:
        rows.append(("时长", _format_duration(gw.get("duration_seconds"))))
    else:
        rows.append(("时长", _MISSING_DISPLAY))
    rows.append(("亮度", _brightness_compare_metric_display(ctx)))
    rows.append(("音量", _volume_actual_display(ctx)))
    rows.append(("网络", _network_cond_display(ctx)))
    rows.append(("刷新率", _refresh_rate_compare_display(ctx)))
    rows.append(("平均帧率", _avg_fps_compare_display(ctx)))
    rows.append(("最高温度", _max_temp_compare_display(ctx)))
    return rows


def _format_log_metrics_compare_html(
    ctx: dict[str, Any],
    compare_ctx: dict[str, Any],
    label_a: str,
    label_b: str,
) -> str:
    rows_a = dict(_extract_compare_metric_rows(ctx))
    rows_b = dict(_extract_compare_metric_rows(compare_ctx))
    keys = list(rows_a.keys())
    body: list[str] = []
    for k in keys:
        va = rows_a.get(k, _MISSING_DISPLAY)
        vb = rows_b.get(k, _MISSING_DISPLAY)
        same = (not _is_missing_display(va)) and _norm_cond_token(va) == _norm_cond_token(vb)
        cls = " class=\"ok\"" if same else ""
        diff_cls = "" if same else " class=\"bad\""
        body.append(
            "<tr>"
            f"<td>{_esc(k)}</td>"
            f"<td{cls}>{_esc(va)}</td>"
            f"<td{diff_cls}>{_esc(vb)}</td>"
            "</tr>"
        )
    return (
        '<table class="device-table metrics-compare" style="margin-top:12px;">'
        "<thead><tr>"
        f"<th>项目</th><th>{_esc(label_a)}</th><th>{_esc(label_b)}</th>"
        "</tr></thead>"
        f"<tbody>{''.join(body)}</tbody></table>"
    )


def _align_triggered_pair(
    triggered_a: list[dict[str, Any]] | None,
    triggered_b: list[dict[str, Any]] | None,
    *,
    skip_ids: set[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """双机对比：按 rule id 取并集对齐，缺侧补占位（日志未搜到也展示）。"""
    skip = {str(x) for x in (skip_ids or set())}

    def _index(items: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for it in items or []:
            if not isinstance(it, dict):
                continue
            rid = str(it.get("id") or "").strip()
            if not rid or rid in skip:
                continue
            out[rid] = it
        return out

    by_a = _index(triggered_a)
    by_b = _index(triggered_b)
    order = [rid for rid in by_a] + [rid for rid in by_b if rid not in by_a]

    def _pad(own: dict[str, dict[str, Any]], other: dict[str, dict[str, Any]], rid: str) -> dict[str, Any]:
        if rid in own:
            item = dict(own[rid])
            item.pop("_missing", None)
            return item
        tpl = other.get(rid) or {}
        return {
            "id": rid,
            "label": tpl.get("label") or rid,
            "subcategory": tpl.get("subcategory") or "",
            "priority": tpl.get("priority") or "P2",
            "category": tpl.get("category"),
            "confidence": tpl.get("confidence"),
            "detail": "日志未搜到",
            "_missing": True,
        }

    return (
        [_pad(by_a, by_b, rid) for rid in order],
        [_pad(by_b, by_a, rid) for rid in order],
    )


def _format_missing_cause_evidence_html(item: dict[str, Any]) -> str:
    """对比占位：对端有该项、本机日志未搜到。"""
    reason = _esc(
        item.get("subcategory") or item.get("label") or item.get("id") or "对比项"
    )
    label = _esc(item.get("label") or "")
    title = f"{reason}" + (f" — {label}" if label and label != reason else "")
    return (
        f'<div style="margin-top:8px;padding:8px 10px;border:0.5px dashed var(--color-border-tertiary);'
        f'border-radius:var(--border-radius-md);background:var(--color-background-secondary);">'
        f'<p style="margin:0;font-size:13px;"><span style="color:var(--color-text-tertiary);">原因：</span>'
        f"<strong>{title}</strong></p>"
        f'<p style="margin:4px 0 0;font-size:12px;color:var(--color-text-tertiary);">日志未搜到</p>'
        f"</div>"
    )


def _build_cause_category_body(
    cat_id: str,
    cat: dict[str, Any],
    ctx: dict[str, Any],
    *,
    test_method_media: str,
    optimization_media: str,
    peer_ctx: dict[str, Any] | None = None,
    peer_cat: dict[str, Any] | None = None,
    side: str = "self",
    abnormal_parts: str = "all",
) -> str:
    """单侧原因分析正文（媒体 + 明细），供单机或双机复用。"""
    triggered = [x for x in (cat.get("triggered") or []) if isinstance(x, dict)]
    media_block = ""
    if cat_id == "test_methodology":
        media_block = test_method_media
    elif cat_id == "optimization_strategy":
        media_block = optimization_media
    elif cat_id == "abnormal_situation":
        real_triggered = [x for x in triggered if not x.get("_missing")]
        peer_trig = None
        if peer_cat is not None:
            peer_trig = [
                x
                for x in (peer_cat.get("triggered") or [])
                if isinstance(x, dict) and not x.get("_missing")
            ]
        media_block = _format_abnormal_situation_media(
            ctx,
            real_triggered,
            peer_ctx=peer_ctx,
            peer_triggered=peer_trig,
            side=side,
            parts=abnormal_parts,
        )
    elif cat_id == "hardware_difference":
        media_block = _format_hardware_difference_media(ctx)
    real_for_links = [x for x in triggered if not x.get("_missing")]
    cat_evidence = collect_category_evidence(cat_id, real_for_links, ctx)
    # 测试手法 / 功能差异：不展示关联子报告链接
    links_html = (
        ""
        if cat_id in ("hardware_difference", "test_methodology", "feature_difference")
        else format_category_links_html(cat_evidence.get("step_links") or [])
    )
    cause_details_html = ""
    if triggered:
        if cat_id == "test_methodology":
            cause_details_html = format_test_methodology_table_html(triggered, ctx)
        elif cat_id == "feature_difference":
            cause_details_html = format_feature_difference_table_html(triggered, ctx)
        elif cat_id == "abnormal_situation":
            cause_details_html = ""
        else:
            detail_parts: list[str] = []
            for item in triggered:
                rid = str(item.get("id") or "")
                if cat_id == "optimization_strategy" and (
                    rid == "opt_refresh_rate"
                    or "refresh_rate" in rid
                    or rid == "opt_backlight_2_0"
                    or "backlight_2" in rid
                    or rid == "opt_aal_strategy"
                    or "aal" in rid
                    or "thermal" in rid
                    or "perf_lock" in rid
                    or "perflock" in rid
                    or "frame_rate" in rid
                    or "fps" in rid
                ):
                    # 已在软件策略统一媒体区展示，避免重复
                    continue
                if item.get("_missing"):
                    detail_parts.append(_format_missing_cause_evidence_html(item))
                    continue
                ev = collect_cause_evidence(item, ctx)
                detail_parts.append(format_cause_evidence_html(ev))
            cause_details_html = "".join(detail_parts)
    if triggered:
        sub_lines = []
        if cat_id not in (
            "abnormal_situation",
            "test_methodology",
            "optimization_strategy",
            "feature_difference",
        ):
            for item in triggered:
                sub = item.get("subcategory")
                prefix = f"{sub} - " if sub else ""
                suffix = "（日志未搜到）" if item.get("_missing") else ""
                sub_lines.append(
                    f'<p style="margin:3px 0 0;font-size:13px;color:var(--color-text-secondary);">'
                    f'{_esc(prefix)}{_esc(item.get("label", ""))}{_esc(suffix)}</p>'
                )
        return (
            media_block
            + links_html
            + ("\n".join(sub_lines) if sub_lines else "")
            + cause_details_html
        )
    if media_block:
        return media_block + links_html
    return (
        links_html
        + '<p style="margin:3px 0 0;font-size:13px;color:var(--color-text-tertiary);">未发现明显问题</p>'
    )


def render_clarify_report(
    judgment: dict[str, Any],
    ctx: dict[str, Any],
    report_meta: dict[str, Any] | None = None,
    defaults: dict[str, Any] | None = None,
    power_delta: dict[str, Any] | None = None,
    ai_insights: dict[str, Any] | None = None,
    compare_ctx: dict[str, Any] | None = None,
    compare_judgment: dict[str, Any] | None = None,
) -> str:
    meta = dict(report_meta or ctx.get("report_meta") or {})
    ctx = dict(ctx)
    ctx["report_meta"] = meta
    defs = defaults or load_report_defaults()
    report_cfg = defs.get("report") or {}
    pd = power_delta or {}
    dual = isinstance(compare_ctx, dict) and bool(compare_ctx)
    label_a, label_b = _side_labels(meta, ctx, compare_ctx if dual else None)

    summary = ctx.get("summary") or {}
    gw = summary.get("game_window") or (ctx.get("game_time_window") or {}).get("game_window") or {}
    # prefer time_windows.T_game when game_window empty
    if not gw.get("start"):
        tw = (ctx.get("game_time_window") or {}).get("time_windows") or {}
        if isinstance(tw, dict) and isinstance(tw.get("T_game"), dict):
            gw = dict(tw["T_game"])
    game_name = str(
        meta.get("game_title")
        or gw.get("game_name")
        or (ctx.get("game_time_window") or {}).get("game_name")
        or "游戏"
    ).strip()
    # 日志侧常有完整名（PUBG Mobile），优先于 JIRA 简写 PUBG
    log_game = str(
        gw.get("game_name")
        or (ctx.get("game_time_window") or {}).get("game_name")
        or ""
    ).strip()
    if log_game and (not game_name or game_name.casefold() in log_game.casefold() or log_game.casefold().startswith(game_name.casefold())):
        game_name = log_game

    scenario_label = str(
        meta.get("test_case_label")
        or (ctx.get("game_analysis_meta") or {}).get("test_case_label")
        or ""
    ).strip()
    if not scenario_label:
        tc = str(meta.get("test_case") or (ctx.get("game_analysis_meta") or {}).get("test_case") or "").strip().lower()
        if tc == "nps":
            scenario_label = "NPS场景"

    speaker_mode = str(meta.get("speaker_mode") or "").strip()
    if not speaker_mode:
        # 音量通路 device=2 → 外放
        route = ((ctx.get("game_volume") or {}).get("audio_route") or {}).get("tran_aura_volume_change") or {}
        if isinstance(route, dict):
            dom = route.get("dominant_device")
            if dom == 2:
                speaker_mode = "外放"
            else:
                label = str(route.get("dominant_device_label") or "")
                if "外放" in label or "扬声器" in label:
                    speaker_mode = "外放"
                elif "耳机" in label:
                    speaker_mode = "耳机"
                elif "蓝牙" in label:
                    speaker_mode = "蓝牙"

    # 标题：NPS场景PUBG Mobile外放玩游戏功耗
    title_bits = [b for b in (scenario_label, game_name, speaker_mode) if b]
    if title_bits:
        title = f"{''.join(title_bits)}玩游戏功耗"
    else:
        title = f"{game_name}{report_cfg.get('title_suffix', '功耗澄清报告')}"
        if dual:
            title = f"{game_name}功耗对比澄清报告"
    primary = (judgment.get("primary_causes") or [{}])
    priority = str(
        meta.get("priority")
        or (primary[0].get("priority") if primary else None)
        or report_cfg.get("default_priority", "P2")
    )
    badge_bg, badge_fg = _priority_badge(priority)

    raw_jira_key = str(meta.get("jira_key") or "").strip()
    if not raw_jira_key or raw_jira_key == "xxxxxxxx":
        raw_jira_key = ""
    raw_issue_url = str(meta.get("issue_url") or "").strip()
    if raw_jira_key and _JIRA_KEY_RE.match(raw_jira_key):
        if not raw_issue_url or raw_issue_url == "#":
            raw_issue_url = f"{_JIRA_BROWSE_BASE}{raw_jira_key}"
    jira_key = _esc(raw_jira_key or "xxxxxxxx")
    issue_url = _esc(raw_issue_url or "#")
    if raw_jira_key and raw_issue_url and raw_issue_url != "#":
        jira_key_html = (
            f'<a href="{issue_url}" target="_blank" rel="noopener noreferrer" '
            f'style="font-size:13px;font-weight:500;color:var(--blue-600, #2563eb);text-decoration:none;">'
            f"{jira_key}</a>"
        )
    else:
        jira_key_html = f'<span style="font-size:13px;font-weight:500;">{jira_key}</span>'
    if dual:
        # 双机对比优先展示「测试机 / 对比机」，避免 JIRA affect_project 单机型覆盖
        device = _esc(f"{label_a} / {label_b}" if label_a and label_b else (meta.get("device_model") or "xxx / xxx"))
    else:
        device = _esc(meta.get("device_model") or summary.get("analysis_meta", {}).get("device_model") or "xxx / xxx")
    start = _esc(gw.get("start", ""))
    end = _esc(gw.get("end", ""))
    duration = _format_duration(gw.get("duration_seconds"))
    duration_line = f"测试时长 {duration}（{start} → {end}）" if start and end else f"测试时长 {duration}"
    if dual and compare_ctx is not None:
        gw2 = (compare_ctx.get("summary") or {}).get("game_window") or (
            (compare_ctx.get("game_time_window") or {}).get("game_window") or {}
        )
        if not gw2.get("start"):
            tw2 = (compare_ctx.get("game_time_window") or {}).get("time_windows") or {}
            if isinstance(tw2, dict) and isinstance(tw2.get("T_game"), dict):
                gw2 = dict(tw2["T_game"])
        d2 = _format_duration(gw2.get("duration_seconds"))
        duration_line = (
            f"{label_a} {duration}（{_esc(gw.get('start', ''))} → {_esc(gw.get('end', ''))}）；"
            f"{label_b} {d2}（{_esc(gw2.get('start', ''))} → {_esc(gw2.get('end', ''))}）"
        )

    cond_map = (defs.get("test_condition_display") or {})
    cond_items: list[str] = []
    for tag_id, cfg in cond_map.items():
        if not isinstance(cfg, dict):
            continue
        if tag_id == "background":
            continue
        label = _esc(cfg.get("label", tag_id))
        required_raw = _cond_required_display(ctx, tag_id, cfg)
        actual_raw = _cond_display_value(ctx, tag_id)
        required = _esc(required_raw)
        actual = _esc(actual_raw)
        matched = _cond_values_match(required_raw, actual_raw, tag_id)
        pre = ctx.get("game_precondition") or {}
        tags = _get_path(pre, "test_conditions.tags")
        if tag_id == "sim_data":
            data_tag = _find_tag(tags, "data")
            sim_tag = _find_tag(tags, "sim")
            sts = [
                str((data_tag or {}).get("status") or ""),
                str((sim_tag or {}).get("status") or ""),
            ]
            if all(s == "ok" for s in sts if s):
                matched = True
            elif any(s in ("warn", "bad") for s in sts):
                matched = False
            elif any(s == "unknown" for s in sts) or _is_missing_display(actual_raw):
                matched = False
        elif tag_id not in ("scene", "background", "wifi"):
            lookup_id = tag_id
            tag = _find_tag(tags, lookup_id)
            if isinstance(tag, dict):
                st = str(tag.get("status") or "")
                if st == "ok":
                    matched = True
                elif st in ("warn", "bad"):
                    matched = False
                elif st == "unknown" or _is_missing_display(actual_raw):
                    matched = False
        act_cls = "ok" if matched else "bad"
        # 测试场景：左上场景名、左下游戏名；右侧机型仅显示是/否
        if tag_id == "scene":
            scenario_name = _esc(_scene_scenario_name(ctx))
            expected_game = _scene_expected_game_name(ctx)
            game_name = _esc(expected_game)
            yes_a, act_cls = _scene_yes_no(ctx, expected_game=expected_game)
            if dual and compare_ctx is not None:
                yes_b, act2_cls = _scene_yes_no(compare_ctx, expected_game=expected_game)
                cond_items.append(
                    f'<div class="cond-item scene-only dual-cond">'
                    f'<div class="cond-left">'
                    f'<div class="left-top"><span class="label">{scenario_name}</span></div>'
                    f'<span class="v req">{game_name}</span>'
                    f"</div>"
                    f'<div class="cond-right" style="display:flex;flex-direction:column;gap:4px;">'
                    f'<div><span class="side-label">{_esc(label_a)}</span>'
                    f'<span class="v act {act_cls}">{yes_a}</span></div>'
                    f'<div><span class="side-label">{_esc(label_b)}</span>'
                    f'<span class="v act {act2_cls}">{yes_b}</span></div>'
                    f"</div></div>"
                )
            else:
                cond_items.append(
                    f'<div class="cond-item scene-only">'
                    f'<div class="cond-left">'
                    f'<div class="left-top"><span class="label">{scenario_name}</span></div>'
                    f'<span class="v req">{game_name}</span>'
                    f"</div>"
                    f'<div class="cond-right">'
                    f'<span class="side-label">实际</span>'
                    f'<span class="v act {act_cls}">{yes_a}</span>'
                    f"</div></div>"
                )
            continue
        if dual and compare_ctx is not None:
            actual2_raw = _cond_display_value(compare_ctx, tag_id)
            actual2 = _esc(actual2_raw)
            matched2 = _cond_values_match(required_raw, actual2_raw, tag_id)
            act2_cls = "ok" if matched2 else "bad"
            cond_items.append(
                f'<div class="cond-item dual-cond">'
                f'<div class="cond-left">'
                f'<div class="left-top"><span class="label">{label}</span></div>'
                f'<span class="v req">{required}</span>'
                f"</div>"
                f'<div class="cond-right" style="display:flex;flex-direction:column;gap:4px;">'
                f'<div><span class="side-label">{_esc(label_a)}</span>'
                f'<span class="v act {act_cls}">{actual}</span></div>'
                f'<div><span class="side-label">{_esc(label_b)}</span>'
                f'<span class="v act {act2_cls}">{actual2}</span></div>'
                f"</div></div>"
            )
        else:
            cond_items.append(
                f'<div class="cond-item">'
                f'<div class="cond-left">'
                f'<div class="left-top"><span class="label">{label}</span></div>'
                f'<span class="v req">{required}</span>'
                f"</div>"
                f'<div class="cond-right">'
                f'<span class="side-label">实际</span>'
                f'<span class="v act {act_cls}">{actual}</span>'
                f"</div></div>"
            )
    cond_grid = "\n".join(cond_items)
    test_method_media = _format_test_methodology_media(ctx)
    optimization_media = _format_optimization_strategy_media(
        ctx,
        compare_ctx if dual else None,
        label_a=label_a,
        label_b=label_b,
    )
    network_media = _format_network_analysis_media(
        ctx,
        compare_ctx if dual else None,
        label_a=label_a,
        label_b=label_b,
    )
    compare_test_method_media = _format_test_methodology_media(compare_ctx) if dual and compare_ctx else ""
    compare_optimization_media = ""  # 软件策略已统一合并，不再分栏重复

    # Prefer structured power_delta values for KPI cards
    comp_power = _fmt_ma_display(
        pd.get("competitor_power_ma", meta.get("competitor_power_ma")), "xxx"
    )
    test_power = _fmt_ma_display(pd.get("test_power_ma", meta.get("test_power_ma")), "xxx")
    delta_raw = pd.get("delta_power_ma_i1", meta.get("delta_power_ma"))
    delta_power = _fmt_ma_display(delta_raw, "xx")
    adjusted_raw = pd.get("residual_after_known_ma", meta.get("adjusted_delta_ma"))
    adjusted = _fmt_ma_display(adjusted_raw, "xx")
    power_extras = _power_delta_extras_html(pd if pd else None)
    ai_section = _ai_insights_section_html(ai_insights)

    hw_rows_html: list[str] = []
    # Prefer power_delta.known_deltas when present; else fall back to report-defaults hardware_rows
    known_items = pd.get("known_deltas") if isinstance(pd.get("known_deltas"), list) else []
    hw_table_rows: list[dict[str, Any]] = []
    seen_modules: set[str] = set()
    seen_labels: set[str] = set()
    hw_query = meta.get("hardware_power_query") if isinstance(meta.get("hardware_power_query"), dict) else {}
    hw_test_label = str(
        hw_query.get("test_device")
        or meta.get("hardware_test_device")
        or meta.get("test_device_label")
        or "测试机"
    ).strip() or "测试机"
    hw_comp_label = str(
        hw_query.get("compare_device")
        or meta.get("hardware_compare_device")
        or "对比机"
    ).strip() or "对比机"
    hw_source_note = str(meta.get("hardware_power_source") or "").strip()

    def _ma_cell(val: Any, *, delta_fallback: Any = None, emphasize_delta: bool = False) -> tuple[str, str]:
        """返回 (显示文本, css class)。优先绝对值；仅有差值时测试机列显示 +XmA。"""
        if val is not None and val != "":
            try:
                return f"{float(val):g} mA", ""
            except (TypeError, ValueError):
                return str(val), ""
        if delta_fallback is None or delta_fallback == "":
            return "—", "muted"
        try:
            dv = float(delta_fallback)
        except (TypeError, ValueError):
            return "—", "muted"
        if emphasize_delta:
            sign = "+" if dv > 0 else ""
            cls = "bad" if dv > 0 else ("ok" if dv < 0 else "muted")
            return f"{sign}{dv:g} mA", cls
        return f"{abs(dv):g} mA", "bad" if dv > 0 else ("ok" if dv < 0 else "muted")

    def _delta_cell(delta: Any) -> tuple[str, str]:
        if delta is None or delta == "":
            return "—", "muted"
        try:
            dv = float(delta)
        except (TypeError, ValueError):
            return "—", "muted"
        sign = "+" if dv > 0 else ""
        cls = "bad" if dv > 0 else ("ok" if dv < 0 else "muted")
        return f"{sign}{dv:g} mA", cls

    for item in known_items:
        if not isinstance(item, dict):
            continue
        module = str(item.get("module") or "")
        label = str(item.get("label") or item.get("module") or "器件")
        seen_modules.add(module)
        seen_labels.add(label)
        reason = str(item.get("note") or item.get("reason") or "飞书器件功耗台账").strip() or "飞书器件功耗台账"
        optimization = str(item.get("optimization") or item.get("optimization_plan") or "").strip()
        if not optimization:
            optimization = "—"
        test_txt, test_cls = _ma_cell(item.get("test_ma"), delta_fallback=item.get("delta_ma"), emphasize_delta=True)
        comp_txt, comp_cls = _ma_cell(item.get("competitor_ma"))
        delta_txt, delta_cls = _delta_cell(item.get("delta_ma"))
        hw_table_rows.append(
            {
                "label": label,
                "test": test_txt,
                "test_cls": test_cls,
                "competitor": comp_txt,
                "competitor_cls": comp_cls,
                "delta": delta_txt,
                "delta_cls": delta_cls,
                "delta_ma": item.get("delta_ma"),
                "reason": reason,
                "optimization": optimization,
            }
        )

    for row in defs.get("hardware_rows") or []:
        if not isinstance(row, dict):
            continue
        meta_key = str(row.get("meta_key", ""))
        module = str(row.get("id", ""))
        label = str(row.get("label", ""))
        if module in seen_modules or label in seen_labels:
            continue
        raw_delta = meta.get(meta_key)
        test_ma = meta.get(f"{module}_test_ma")
        competitor_ma = meta.get(f"{module}_competitor_ma") or meta.get(f"{module}_compare_ma")
        reason = str(
            meta.get(f"{module}_note")
            or meta.get(f"{module}_reason")
            or row.get("default_reason")
            or ("待仪器对比补充" if raw_delta is None and test_ma is None else "器件功耗台账")
        )
        optimization = str(
            meta.get(f"{module}_optimization")
            or meta.get(f"{module}_fix")
            or row.get("default_optimization")
            or "—"
        )
        test_txt, test_cls = _ma_cell(test_ma, delta_fallback=raw_delta, emphasize_delta=True)
        comp_txt, comp_cls = _ma_cell(competitor_ma)
        delta_txt, delta_cls = _delta_cell(raw_delta)
        hw_table_rows.append(
            {
                "label": label or module or "—",
                "test": test_txt,
                "test_cls": test_cls,
                "competitor": comp_txt,
                "competitor_cls": comp_cls,
                "delta": delta_txt,
                "delta_cls": delta_cls,
                "delta_ma": raw_delta,
                "reason": reason,
                "optimization": optimization,
            }
        )

    if hw_table_rows:
        body_rows: list[str] = []
        delta_sum = 0.0
        delta_sum_ok = False
        for r in hw_table_rows:
            test_cls = f" class=\"{_esc(r['test_cls'])}\"" if r.get("test_cls") else ""
            comp_cls = f" class=\"{_esc(r['competitor_cls'])}\"" if r.get("competitor_cls") else ""
            delta_cls = f" class=\"{_esc(r['delta_cls'])}\"" if r.get("delta_cls") else ""
            body_rows.append(
                "<tr>"
                f"<td class=\"dev\">{_esc(r['label'])}</td>"
                f"<td{test_cls}>{_esc(r['test'])}</td>"
                f"<td{comp_cls}>{_esc(r['competitor'])}</td>"
                f"<td{delta_cls}>{_esc(r['delta'])}</td>"
                f"<td>{_esc(r['reason'])}</td>"
                f"<td>{_esc(r['optimization'])}</td>"
                "</tr>"
            )
            try:
                if r.get("delta_ma") is not None and r.get("delta_ma") != "":
                    delta_sum += float(r["delta_ma"])
                    delta_sum_ok = True
            except (TypeError, ValueError):
                pass
        if delta_sum_ok:
            sum_txt, sum_cls = _delta_cell(delta_sum)
            sum_cls_attr = f" class=\"{_esc(sum_cls)}\"" if sum_cls else ""
            body_rows.append(
                "<tr>"
                '<td class="dev"><strong>合计</strong></td>'
                "<td>—</td><td>—</td>"
                f"<td{sum_cls_attr}><strong>{_esc(sum_txt)}</strong></td>"
                "<td>器件功耗合计（用于 I1 扣减）</td>"
                "<td>—</td>"
                "</tr>"
            )
        caption = ""
        if hw_test_label != "测试机" or hw_comp_label != "对比机" or hw_source_note:
            src = f" · 来源 {hw_source_note}" if hw_source_note else ""
            caption = (
                f'<p style="margin:6px 0 0;font-size:12px;color:var(--color-text-tertiary);">'
                f"台账机型：{_esc(hw_test_label)} vs {_esc(hw_comp_label)}{_esc(src)}"
                f"</p>"
            )
        hw_rows_html.append(
            '<table class="device-table">'
            "<thead><tr>"
            f"<th>器件</th><th>{_esc(hw_test_label)}</th><th>{_esc(hw_comp_label)}</th>"
            "<th>差值</th><th>原因</th><th>优化方案</th>"
            "</tr></thead>"
            f"<tbody>{''.join(body_rows)}</tbody></table>"
            f"{caption}"
        )
    else:
        hw_rows_html.append(
            '<p style="margin:0;font-size:13px;color:var(--color-text-tertiary);">未提供器件功耗台账数据</p>'
        )

    cause_blocks: list[str] = []
    categories = judgment.get("categories") or {}
    compare_categories = (compare_judgment or {}).get("categories") or {} if dual else {}
    ordered = sorted(
        ((k, v) for k, v in categories.items() if isinstance(v, dict)),
        key=lambda x: int(x[1].get("order", 99)),
    )
    for idx, (cat_id, cat) in enumerate(ordered, start=1):
        title_cat = _esc(cat.get("title", ""))
        cat_a = dict(cat)
        if dual and compare_ctx is not None:
            cat_b_raw = compare_categories.get(cat_id) if isinstance(compare_categories, dict) else None
            if not isinstance(cat_b_raw, dict):
                cat_b_raw = {"triggered": [], "title": cat.get("title")}
            cat_b = dict(cat_b_raw)
            # 双侧对比项按 id 对齐；缺侧展示「日志未搜到」
            if cat_id in (
                "optimization_strategy",
                "feature_difference",
                "test_methodology",
                "abnormal_situation",
            ):
                skip_ids = {"opt_refresh_rate"} if cat_id == "optimization_strategy" else None
                aligned_a, aligned_b = _align_triggered_pair(
                    cat_a.get("triggered") or [],
                    cat_b.get("triggered") or [],
                    skip_ids=skip_ids,
                )
                # 刷新率仍只在媒体区展示，但需保留真实命中供媒体逻辑；对齐列表用于明细
                if cat_id == "optimization_strategy":
                    # 把两侧真实的 refresh_rate 命中保留在 triggered 供其他逻辑，明细对齐不含它
                    cat_a["triggered"] = aligned_a + [
                        x
                        for x in (cat.get("triggered") or [])
                        if isinstance(x, dict)
                        and (
                            str(x.get("id") or "") == "opt_refresh_rate"
                            or "refresh_rate" in str(x.get("id") or "")
                        )
                    ]
                    cat_b["triggered"] = aligned_b + [
                        x
                        for x in (cat_b_raw.get("triggered") or [])
                        if isinstance(x, dict)
                        and (
                            str(x.get("id") or "") == "opt_refresh_rate"
                            or "refresh_rate" in str(x.get("id") or "")
                        )
                    ]
                else:
                    cat_a["triggered"] = aligned_a
                    cat_b["triggered"] = aligned_b
            body_a = _build_cause_category_body(
                cat_id,
                cat_a,
                ctx,
                test_method_media=test_method_media,
                optimization_media=optimization_media,
                peer_ctx=compare_ctx,
                peer_cat=cat_b,
                side="self",
                abnormal_parts="summary" if cat_id == "abnormal_situation" else "all",
            )
            if cat_id == "hardware_difference":
                body = body_a
            elif cat_id == "abnormal_situation":
                peer_trig = [
                    x
                    for x in (cat_b.get("triggered") or [])
                    if isinstance(x, dict) and not x.get("_missing")
                ]
                self_trig = [
                    x
                    for x in (cat_a.get("triggered") or [])
                    if isinstance(x, dict) and not x.get("_missing")
                ]
                spike_block = _format_current_spike_abnormal_item(ctx)
                merged_threads = _format_abnormal_merged_thread_table(
                    ctx,
                    self_trig,
                    compare_ctx,
                    peer_trig,
                    label_a=label_a,
                    label_b=label_b,
                )
                body_b = _build_cause_category_body(
                    cat_id,
                    cat_b,
                    compare_ctx,
                    test_method_media=compare_test_method_media,
                    optimization_media=compare_optimization_media,
                    peer_ctx=ctx,
                    peer_cat=cat_a,
                    side="peer",
                    abnormal_parts="summary",
                )
                # 一、电流图；二、线程明细；三、网络/RF（统一双机）；四、问题总结左右分栏
                body = (
                    spike_block
                    + merged_threads
                    + (network_media or "")
                    + _dual_panel_html(label_a, body_a, label_b, body_b)
                )
            elif cat_id == "optimization_strategy":
                # 软件策略：统一单框顺序展示，不再左右分栏重复
                body = optimization_media or body_a
            elif cat_id == "test_methodology":
                # 测试手法：原因 | 机型A | 机型B；隐藏快照与子报告
                body = format_test_methodology_compare_table_html(
                    cat_a.get("triggered") or [],
                    ctx,
                    cat_b.get("triggered") or [],
                    compare_ctx,
                    label_a=label_a,
                    label_b=label_b,
                )
            elif cat_id == "feature_difference":
                # 功能差异：功能 | 机型A | 机型B；与测试手法同款三列表
                body = format_feature_difference_compare_table_html(
                    cat_a.get("triggered") or [],
                    ctx,
                    cat_b.get("triggered") or [],
                    compare_ctx,
                    label_a=label_a,
                    label_b=label_b,
                )
            else:
                body_b = _build_cause_category_body(
                    cat_id,
                    cat_b,
                    compare_ctx,
                    test_method_media=compare_test_method_media,
                    optimization_media=compare_optimization_media,
                    peer_ctx=ctx,
                    peer_cat=cat_a,
                    side="peer",
                )
                body = _dual_panel_html(label_a, body_a, label_b, body_b)
            has_content = bool(
                (cat_a.get("triggered") or [])
                or (cat_b.get("triggered") or [])
                or body_a.strip()
                or (
                    body.strip()
                    and "未发现明显问题" not in body
                    if cat_id in ("abnormal_situation", "test_methodology")
                    else False
                )
            )
        else:
            body_a = _build_cause_category_body(
                cat_id,
                cat_a,
                ctx,
                test_method_media=test_method_media,
                optimization_media=optimization_media,
            )
            body = body_a
            has_content = bool((cat.get("triggered") or []) or (body_a and "未发现明显问题" not in body_a))
        if has_content:
            num_bg = "var(--green-50)"
            num_fg = "var(--green-600)"
        else:
            num_bg = "var(--color-background-secondary)"
            num_fg = "var(--color-text-tertiary)"
        cause_blocks.append(
            f'<div style="display:flex;gap:10px;align-items:flex-start;">'
            f'<span style="background:{num_bg};color:{num_fg};border-radius:50%;'
            f'width:22px;height:22px;min-width:22px;display:flex;align-items:center;'
            f'justify-content:center;font-size:12px;font-weight:500;">{idx}</span>'
            f'<div style="flex:1;min-width:0;"><p style="margin:0;font-size:14px;font-weight:500;">{title_cat}</p>{body}</div></div>'
        )

    metrics_compare_html = ""
    if dual and compare_ctx is not None:
        metrics_compare_html = _format_log_metrics_compare_html(ctx, compare_ctx, label_a, label_b)

    kpi_comp_label = label_b if dual and label_b else "竞品机"
    kpi_test_label = label_a if dual and label_a else "测试机"
    section2_title = "测试数据对比" if dual else "测试数据"

  # Use template CSS from PUBG功耗澄清报告.html
    html_out = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_esc(title)}</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/tabler-icons/3.1.0/tabler-icons.min.css">
<style>
  :root {{
    --color-background-primary: #ffffff;
    --color-background-secondary: #f5f4f0;
    --color-background-tertiary: #ebe9e3;
    --color-text-primary: #2c2c2a;
    --color-text-secondary: #5f5e5a;
    --color-text-tertiary: #888780;
    --color-text-danger: #a32d2d;
    --color-text-success: #3b6d11;
    --color-text-info: #185fa5;
    --color-border-tertiary: rgba(44,44,42,0.15);
    --border-radius-md: 8px;
    --border-radius-lg: 12px;
    --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    --blue-50:#E6F1FB; --blue-600:#185FA5; --blue-800:#0C447C;
    --purple-50:#EEEDFE; --purple-600:#534AB7; --purple-800:#3C3489;
    --coral-50:#FAECE7; --coral-600:#993C1D; --coral-800:#712B13;
    --amber-50:#FAEEDA; --amber-600:#854F0B; --amber-800:#633806;
    --teal-50:#E1F5EE; --teal-600:#0F6E56; --teal-800:#085041;
    --green-50:#EAF3DE; --green-600:#3B6D11; --green-800:#27500A;
    --red-50:#FCEBEB; --red-600:#A32D2D; --red-800:#791F1F;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    font-family: var(--font-sans); color: var(--color-text-primary); margin: 0;
    padding: 1rem 1.25rem 1.5rem; background: var(--color-background-tertiary);
    min-height: 100vh;
  }}
  .report-card {{
    width: 100%; max-width: none; background: var(--color-background-primary);
    border-radius: var(--border-radius-lg); border: 0.5px solid var(--color-border-tertiary);
    overflow: hidden;
  }}
  .section {{ padding: 1rem 1.5rem; border-bottom: 0.5px solid var(--color-border-tertiary); }}
  .section:last-child {{ border-bottom: none; }}
  .section-title {{
    font-size: 18px; font-weight: 700; color: var(--color-text-primary);
    margin: 0 0 10px; display: flex; align-items: center; gap: 8px; line-height: 1.3;
  }}
  .section-title i {{ font-size: 18px; color: var(--color-text-secondary); }}
  .section-title .sec-num {{
    display: inline-flex; align-items: center; justify-content: center;
    width: 26px; height: 26px; border-radius: 50%; flex: none;
    font-size: 14px; font-weight: 700;
    background: var(--blue-50, #eff6ff); color: var(--blue-700, #1d4ed8);
  }}
  .icon-box {{
    width: 28px; height: 28px; border-radius: var(--border-radius-md);
    display: flex; align-items: center; justify-content: center; flex: none;
  }}
  .cond-item {{
    background: var(--color-background-secondary); border-radius: var(--border-radius-md);
    padding: 8px 10px; display: grid; grid-template-columns: 1fr 1fr; gap: 8px;
    align-items: center; min-height: 0;
  }}
  .cond-item.dual-cond {{
    align-items: start; padding: 7px 10px;
  }}
  .cond-item .cond-left,
  .cond-item .cond-right {{
    display: flex; flex-direction: column; gap: 2px; min-width: 0;
    justify-content: center;
  }}
  .cond-item.dual-cond .cond-left,
  .cond-item.dual-cond .cond-right {{
    gap: 2px; justify-content: flex-start;
  }}
  .cond-item .cond-right {{
    border-left: 0.5px solid var(--color-border-tertiary); padding-left: 8px;
  }}
  .cond-item .left-top {{
    display: flex; align-items: baseline; justify-content: space-between; gap: 8px;
  }}
  .cond-item .label {{
    margin: 0; font-size: 12px; font-weight: 500; color: var(--color-text-primary);
    line-height: 1.25;
  }}
  .cond-item .side-label {{
    margin: 0 6px 0 0; font-size: 11px; color: var(--color-text-tertiary); font-weight: 400;
    white-space: nowrap; line-height: 1.25;
  }}
  .cond-item .cond-right > div {{
    display: flex; align-items: baseline; min-width: 0; line-height: 1.25;
  }}
  .cond-item.scene-only.dual-cond .cond-right {{
    display: flex; flex-direction: column; gap: 2px;
  }}
  .cond-item .v {{
    margin: 0; font-size: 14px; font-weight: 600; line-height: 1.25;
    word-break: break-word;
  }}
  .cond-item .v.req {{ color: var(--color-text-success); }}
  .cond-item .v.act.ok {{ color: var(--color-text-success); }}
  .cond-item .v.act.bad {{ color: var(--color-text-danger); }}
  .cond-item.scene-only .cond-left,
  .cond-item.scene-only .cond-right {{
    justify-content: flex-start;
  }}
  .cond-item.scene-only .cond-left .v.req {{
    color: var(--color-text-primary); font-size: 13px;
  }}
  .cond-item.scene-only .cond-right .v {{ font-size: 13px; }}
  .metric-card {{ border-radius: var(--border-radius-md); padding: 10px; text-align: center; }}
  .device-table {{
    width: 100%; border-collapse: collapse; font-size: 13px;
    background: var(--color-background-primary);
  }}
  .device-table th, .device-table td {{
    padding: 10px 12px; text-align: left; vertical-align: top;
    border-bottom: 0.5px solid var(--color-border-tertiary);
  }}
  .device-table th {{
    color: var(--color-text-secondary); font-weight: 500; font-size: 12px;
    background: var(--color-background-secondary);
  }}
  .device-table td.dev {{ font-weight: 500; color: var(--color-text-primary); white-space: nowrap; }}
  .device-table td.bad {{ color: var(--color-text-danger); font-weight: 500; }}
  .device-table td.ok {{ color: var(--color-text-success); font-weight: 500; }}
  .device-table td.muted {{ color: var(--color-text-tertiary); }}
  .device-table tbody tr:last-child td {{ border-bottom: none; }}
  .cause-table {{
    width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 8px;
  }}
  .cause-table th, .cause-table td {{
    padding: 10px 12px; text-align: left; vertical-align: top;
    border-bottom: 0.5px solid var(--color-border-tertiary);
  }}
  .cause-table th {{
    color: var(--color-text-secondary); font-weight: 500; font-size: 12px;
    background: var(--color-background-secondary);
  }}
  .cause-table td.cause {{
    font-weight: 500; color: var(--color-text-primary); width: 22%; min-width: 120px;
  }}
  .cause-table td.count {{
    width: 64px; text-align: center; font-variant-numeric: tabular-nums;
    font-weight: 600; color: var(--color-text-primary); white-space: nowrap;
  }}
  .cause-table td.detail {{
    color: var(--color-text-secondary); font-size: 12px; line-height: 1.45; width: 28%;
  }}
  .cause-table   td.curve {{
    min-width: 280px; width: 42%; padding-top: 6px; padding-bottom: 6px;
  }}
  .abnormal-thread-table-dual td.cause {{
    width: 12%; min-width: 110px;
  }}
  .abnormal-thread-table-dual td.count {{
    width: 56px;
  }}
  .abnormal-thread-table-dual td.detail {{
    width: 18%;
  }}
  .abnormal-thread-table-dual td.curve {{
    min-width: 160px; width: 16%;
  }}
  .thread-round-curve {{ display: block; max-width: 100%; height: auto; }}
  .cause-table td.reason {{
    color: var(--color-text-primary); font-size: 12px; line-height: 1.45; width: 36%;
    font-weight: 500;
  }}
  .abnormal-summary-table td.cause {{ width: 28%; }}
  .abnormal-summary-table td.detail {{ width: 32%; }}
  .abnormal-summary-table .snap-line {{
    color: var(--color-text-secondary); word-break: break-word;
  }}
  .cause-table td.detail ul {{ margin: 0; padding-left: 16px; }}
  .cause-table .snap-compact {{ margin-top: 4px; }}
  .cause-table .snap-line {{
    font-size: 11px; color: var(--color-text-tertiary); word-break: break-all; margin: 2px 0;
  }}
  .abnormal-thread-table .snap-line:first-child {{
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 11px; color: var(--color-text-secondary); white-space: pre-wrap;
  }}
  .thread-round-curve {{ display: block; max-width: 100%; height: auto; }}
  .cause-table .muted {{ color: var(--color-text-tertiary); }}
  .cause-table tbody tr:last-child td {{ border-bottom: none; }}
  .fps-curve-table td.bad {{ color: var(--color-text-danger); font-weight: 500; }}
  .dual-label {{
    font-size: 11px; color: var(--color-text-tertiary); margin: 0 0 8px;
    font-weight: 500;
  }}
  .dual-side {{
    min-width: 0;
    padding: 8px;
    background: var(--color-background-secondary);
    border-radius: var(--border-radius-md);
  }}
  .metrics-compare td.ok {{ color: var(--color-text-success); }}
  .metrics-compare td.bad {{ color: var(--color-text-danger); }}
  a {{ color: var(--color-text-info); text-decoration: none; }}
</style>
</head>
<body>
<div class="report-card">
  <div class="section" style="padding:1.5rem 1.5rem 1.25rem;background:var(--color-background-secondary);">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;">
      <div style="display:flex;align-items:center;gap:12px;">
        <div class="icon-box" style="width:38px;height:38px;background:var(--coral-50);color:var(--coral-600);">
          <i class="ti ti-device-gamepad-2" style="font-size:20px;" aria-hidden="true"></i>
        </div>
        <span style="font-size:17px;font-weight:500;">{_esc(title)}</span>
      </div>
      <span style="background:{badge_bg};color:{badge_fg};font-size:12px;font-weight:500;padding:5px 14px;border-radius:var(--border-radius-md);display:flex;align-items:center;gap:5px;">
        <i class="ti ti-flame" style="font-size:14px;" aria-hidden="true"></i>{_esc(priority)}
      </span>
    </div>
    <div style="display:grid;grid-template-columns:100px 1fr 100px 1fr;gap:10px 0;align-items:center;">
      <div style="display:flex;align-items:center;gap:6px;color:var(--color-text-secondary);font-size:13px;">
        <i class="ti ti-hash" style="font-size:15px;" aria-hidden="true"></i>单号</div>
      {jira_key_html}
      <div style="display:flex;align-items:center;gap:6px;color:var(--color-text-secondary);font-size:13px;">
        <i class="ti ti-device-mobile" style="font-size:15px;" aria-hidden="true"></i>机型</div>
      <span style="font-size:13px;font-weight:500;">{device}</span>
    </div>
  </div>

  <div class="section">
    <p class="section-title"><span class="sec-num">1</span><i class="ti ti-settings" aria-hidden="true"></i>测试条件</p>
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:8px 8px;">
      {cond_grid}
    </div>
    <div style="display:flex;align-items:center;gap:6px;margin-top:8px;font-size:12px;color:var(--color-text-tertiary);">
      <i class="ti ti-clock" style="font-size:14px;" aria-hidden="true"></i>
      <span>{_esc(duration_line)}</span>
    </div>
  </div>

  <div class="section">
    <p class="section-title"><span class="sec-num">2</span><i class="ti ti-chart-bar" aria-hidden="true"></i>{_esc(section2_title)}</p>
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;">
      <div class="metric-card" style="background:var(--color-background-secondary);">
        <p style="font-size:11px;color:var(--color-text-tertiary);margin:0 0 4px;">{_esc(kpi_comp_label)}</p>
        <p style="font-size:16px;font-weight:500;margin:0;">{_esc(comp_power)}</p>
      </div>
      <div class="metric-card" style="background:var(--color-background-secondary);">
        <p style="font-size:11px;color:var(--color-text-tertiary);margin:0 0 4px;">{_esc(kpi_test_label)}</p>
        <p style="font-size:16px;font-weight:500;margin:0;">{_esc(test_power)}</p>
      </div>
      <div class="metric-card" style="background:var(--amber-50);">
        <p style="font-size:11px;margin:0 0 4px;color:var(--amber-600);">差异 I1</p>
        <p style="font-size:16px;font-weight:500;margin:0;color:var(--amber-800);">{_esc(delta_power)}</p>
      </div>
      <div class="metric-card" style="background:var(--teal-50);">
        <p style="font-size:11px;margin:0 0 4px;color:var(--teal-600);">差异−器件功耗</p>
        <p style="font-size:16px;font-weight:500;margin:0;color:var(--teal-800);">{_esc(adjusted)}</p>
      </div>
    </div>
    {metrics_compare_html}
  </div>

  <div class="section">
    <p class="section-title"><span class="sec-num">3</span><i class="ti ti-bolt" aria-hidden="true"></i>器件功耗拆解</p>
    {''.join(hw_rows_html)}
  </div>

  <div class="section">
    <p class="section-title"><span class="sec-num">4</span><i class="ti ti-bulb" aria-hidden="true"></i>原因分析</p>
    {power_extras}
    <div style="display:flex;flex-direction:column;gap:10px;{'margin-top:14px;' if power_extras else ''}">
      {''.join(cause_blocks)}
    </div>
  </div>
  {ai_section}
</div>
</body>
</html>"""
    return _bump_report_font_sizes(html_out, 2)


def analyze_root_cause(
    analysis_dir: Path,
    report_meta: dict[str, Any] | None = None,
    power_delta: dict[str, Any] | None = None,
    ai_insights: dict[str, Any] | None = None,
    compare_analysis_dir: Path | None = None,
) -> dict[str, Any]:
    ctx = load_analysis_bundle(analysis_dir, report_meta)
    judgment = judge_root_causes(ctx)
    compare_ctx: dict[str, Any] | None = None
    compare_judgment: dict[str, Any] | None = None
    if compare_analysis_dir and Path(compare_analysis_dir).is_dir():
        compare_ctx = load_analysis_bundle(Path(compare_analysis_dir), report_meta)
        compare_judgment = judge_root_causes(compare_ctx)
        inject_dual_duration_mismatch(judgment, compare_judgment, ctx, compare_ctx)
    step_htmls = write_step_report_htmls(analysis_dir, ctx)
    html_text = render_clarify_report(
        judgment,
        ctx,
        report_meta,
        power_delta=power_delta,
        ai_insights=ai_insights,
        compare_ctx=compare_ctx,
        compare_judgment=compare_judgment,
    )
    return {
        "judgment": judgment,
        "compare_judgment": compare_judgment,
        "brightness_findings": brightness_findings_summary(ctx),
        "volume_findings": volume_findings_summary(ctx),
        "context_keys": sorted(k for k in ctx.keys() if k != "report_meta"),
        "step_htmls": {k: str(v) for k, v in step_htmls.items()},
        "html": html_text,
        "compare_mode": bool(compare_ctx),
    }


def inject_dual_duration_mismatch(
    judgment: dict[str, Any],
    compare_judgment: dict[str, Any] | None,
    ctx: dict[str, Any],
    compare_ctx: dict[str, Any],
) -> None:
    """双机 T_game 时长不一致时注入 test_methodology finding（原地修改）。"""
    finding = build_dual_duration_mismatch_finding(ctx, compare_ctx)
    if not finding:
        return
    rid = str(finding.get("id") or "log_duration_mismatch")

    def _apply(jdg: dict[str, Any]) -> None:
        cats = jdg.setdefault("categories", {})
        cat = cats.setdefault(
            "test_methodology",
            {
                "order": 1,
                "title": "测试手法不符",
                "triggered_count": 0,
                "findings": [],
                "triggered": [],
            },
        )
        findings = [f for f in (cat.get("findings") or []) if str(f.get("id") or "") != rid]
        triggered = [f for f in (cat.get("triggered") or []) if str(f.get("id") or "") != rid]
        findings.append(dict(finding))
        triggered.append(dict(finding))
        cat["findings"] = findings
        cat["triggered"] = triggered
        cat["triggered_count"] = len(triggered)
        all_findings = [f for f in (jdg.get("findings") or []) if str(f.get("id") or "") != rid]
        all_findings.append(dict(finding))
        jdg["findings"] = all_findings
        triggered_all = [f for f in all_findings if f.get("triggered")]
        jdg["triggered_count"] = len(triggered_all)
        jdg["primary_causes"] = sorted(
            triggered_all,
            key=lambda f: (str(f.get("priority") or "P9"), str(f.get("category_id") or "")),
        )[:5]

    _apply(judgment)
    if isinstance(compare_judgment, dict):
        _apply(compare_judgment)
