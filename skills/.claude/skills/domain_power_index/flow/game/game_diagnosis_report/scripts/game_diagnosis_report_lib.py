"""步骤 12 之后：确认功耗差 + 初步诊断 + AI 建议，合并写入澄清报告。"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_SCRIPT_DIR = Path(__file__).resolve().parent
_GAME_SCRIPTS = _SCRIPT_DIR.parent.parent / "scripts"
_ROOT_CAUSE_SCRIPTS = _SCRIPT_DIR.parent.parent / "game_root_cause" / "scripts"

for p in (_GAME_SCRIPTS, _ROOT_CAUSE_SCRIPTS, _SCRIPT_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from game_ai_insights_lib import synthesize_ai_insights  # noqa: E402
from game_power_delta_lib import analyze_power_delta  # noqa: E402
from cause_snapshot_lib import write_step_report_htmls  # noqa: E402
from game_root_cause_lib import (  # noqa: E402
    inject_dual_duration_mismatch,
    judge_root_causes,
    load_analysis_bundle,
    render_clarify_report,
)
from game_skill_debug import log_skill_end, log_skill_start  # noqa: E402


def _as_float(val: Any) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _proc_name(item: dict[str, Any]) -> str:
    return str(
        item.get("name")
        or item.get("thread")
        or item.get("process")
        or item.get("comm")
        or item.get("label")
        or ""
    ).strip()


def _enrich_meta_from_current_charts(analysis_dir: Path, meta: dict[str, Any]) -> dict[str, Any]:
    """用双机电流图 / correlate 补齐 I1 与差异点（问题单功耗字段缺失时）。"""
    out = dict(meta)
    spike_path = analysis_dir / "game_current_cpu_spike.json"
    corr_path = analysis_dir / "game_current_log_correlate.json"
    spike: dict[str, Any] = {}
    corr: dict[str, Any] = {}
    if spike_path.is_file():
        try:
            loaded = json.loads(spike_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                spike = loaded
        except (OSError, json.JSONDecodeError):
            spike = {}
    if corr_path.is_file():
        try:
            loaded = json.loads(corr_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                corr = loaded
        except (OSError, json.JSONDecodeError):
            corr = {}

    cs = spike.get("current_summary") if isinstance(spike.get("current_summary"), dict) else {}
    if cs:
        out.setdefault("dual_current_summary", dict(cs))
        if out.get("test_power_ma") in (None, "") and cs.get("high_avg_ma") is not None:
            out["test_power_ma"] = cs.get("high_avg_ma")
            out.setdefault("test_power_source", "current_cpu_spike.high_avg_ma")
        if out.get("competitor_power_ma") in (None, "") and cs.get("low_avg_ma") is not None:
            out["competitor_power_ma"] = cs.get("low_avg_ma")
            out.setdefault("competitor_power_source", "current_cpu_spike.low_avg_ma")
        if out.get("delta_power_ma") in (None, "") and cs.get("aligned_avg_diff_ma") is not None:
            out["delta_power_ma"] = cs.get("aligned_avg_diff_ma")
            out["i1_source"] = "双机电流图对齐均值差"
        elif out.get("delta_power_ma") in (None, "") and cs.get("floor_diff_ma") is not None:
            out["delta_power_ma"] = cs.get("floor_diff_ma")
            out["i1_source"] = "双机电流图底电差"

    diff_points: list[dict[str, Any]] = []
    trends = spike.get("trend_correlations")
    if isinstance(trends, list):
        for seg in trends[:8]:
            if not isinstance(seg, dict):
                continue
            procs = []
            for p in (seg.get("matched_processes") or [])[:3]:
                if isinstance(p, dict):
                    name = _proc_name(p)
                    if name:
                        procs.append(name)
            reasons = [str(x) for x in (seg.get("possible_reasons") or [])[:2] if x]
            diff_points.append(
                {
                    "kind": seg.get("stage_label") or seg.get("trend_type") or "差异段",
                    "trend_type": seg.get("trend_type"),
                    "time": seg.get("relative_time")
                    or (
                        f"{seg.get('start_sec')}–{seg.get('end_sec')}s"
                        if seg.get("start_sec") is not None
                        else ""
                    ),
                    "duration_sec": seg.get("duration_sec"),
                    "mean_diff_ma": seg.get("mean_diff_ma"),
                    "peak_diff_ma": seg.get("peak_diff_ma"),
                    "evidence_strength": seg.get("evidence_strength"),
                    "processes": procs,
                    "reasons": reasons,
                    "source": "current_cpu_spike.trend_correlations",
                }
            )
    if not diff_points:
        for win in (corr.get("raised_windows") or [])[:6]:
            if not isinstance(win, dict):
                continue
            start = win.get("start_sec")
            end = win.get("end_sec")
            time_txt = ""
            if start is not None and end is not None:
                time_txt = f"{float(start):.0f}–{float(end):.0f}s"
            cause = win.get("primary_cause") or win.get("label") or "抬高窗"
            diff_points.append(
                {
                    "kind": "抬高",
                    "trend_type": "rise",
                    "time": time_txt,
                    "duration_sec": win.get("duration_sec"),
                    "mean_diff_ma": win.get("mean_raise_ma"),
                    "peak_diff_ma": win.get("peak_ma"),
                    "evidence_strength": None,
                    "processes": [],
                    "reasons": [str(cause)] if cause else [],
                    "source": "game_current_log_correlate.raised_windows",
                }
            )
    if diff_points:
        out["current_diff_points"] = diff_points

    wf = out.get("waveform_analysis")
    if not isinstance(wf, dict):
        wf = {}
    else:
        wf = dict(wf)
    if corr:
        corr_wf = corr.get("waveform_analysis") if isinstance(corr.get("waveform_analysis"), dict) else {}
        for k, v in corr_wf.items():
            if wf.get(k) in (None, "") and v not in (None, ""):
                wf[k] = v
        if wf.get("avg_without_raised_windows_ma") is None:
            wf["avg_without_raised_windows_ma"] = corr.get("avg_without_raised_windows_ma")
        if wf.get("raised_window_count") is None:
            wf["raised_window_count"] = len(corr.get("raised_windows") or [])
        if not wf.get("source"):
            wf["source"] = "game_current_log_correlate"
        if not wf.get("conclusion") and corr.get("summary"):
            wf["conclusion"] = corr.get("summary")
        if wf.get("has_abnormal_spike") is None and corr.get("raised_windows"):
            wf["has_abnormal_spike"] = True
        if not wf.get("spike_impact_on_avg") and corr.get("raise_contribution_to_avg_ma") is not None:
            contrib = _as_float(corr.get("raise_contribution_to_avg_ma"))
            if contrib is not None:
                wf["spike_impact_on_avg"] = f"Top抬高窗口合计抬高整段均值约 {contrib:.1f} mA"
    if cs:
        bits = []
        if cs.get("aligned_avg_diff_ma") is not None:
            bits.append(f"双机对齐均值差 {float(cs['aligned_avg_diff_ma']):.1f} mA")
        if cs.get("floor_diff_ma") is not None:
            bits.append(f"底电差 {float(cs['floor_diff_ma']):.1f} mA")
        if cs.get("baseline_diff_ma") is not None:
            bits.append(f"基线差 {float(cs['baseline_diff_ma']):.1f} mA")
        if bits and not wf.get("dual_summary"):
            wf["dual_summary"] = "；".join(bits)
        wf["dual_current_summary"] = dict(cs)
        if not wf.get("source"):
            wf["source"] = "game_current_cpu_spike"
        elif "cpu_spike" not in str(wf.get("source")):
            wf["source"] = f"{wf.get('source')}+game_current_cpu_spike"
    if diff_points:
        wf["diff_points"] = diff_points
    if wf:
        out["waveform_analysis"] = wf
    return out


def _enrich_meta_from_hardware_power(analysis_dir: Path, meta: dict[str, Any]) -> dict[str, Any]:
    """从 game_power_model.hardware_power.known_deltas 灌入器件功耗差。

    飞书台账行（含 test_ma/competitor_ma）优先覆盖同 module 的 CLI 默认差值，
    保证「器件功耗拆解」与「差异−器件功耗」使用最新台账。
    """
    out = dict(meta)
    path = analysis_dir / "game_power_model.json"
    if not path.is_file():
        return out
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return out
    if not isinstance(data, dict):
        return out
    hw = data.get("hardware_power") if isinstance(data.get("hardware_power"), dict) else {}
    rows = hw.get("known_deltas") if isinstance(hw.get("known_deltas"), list) else []
    if not rows:
        return out

    alt_keys = {
        "screen": "screen_delta_ma",
        "speaker": "speaker_delta_ma",
        "cpu": "cpu_delta_ma",
        "rf": "rf_delta_ma",
        "other_hw": "other_hw_delta_ma",
    }

    existing = out.get("known_deltas")
    if not isinstance(existing, list):
        existing = []
    # 先保留非器件 module（如 other_sw），器件行以飞书为准替换
    device_modules = set(alt_keys.keys())
    merged = [
        x
        for x in existing
        if isinstance(x, dict) and str(x.get("module") or "") not in device_modules
    ]
    seen_modules = {
        str(x.get("module") or "")
        for x in merged
        if isinstance(x, dict) and x.get("module")
    }
    for row in rows:
        if not isinstance(row, dict):
            continue
        module = str(row.get("module") or "")
        if not module or module in seen_modules:
            continue
        key = alt_keys.get(module, f"{module}_delta_ma")
        # 飞书行带绝对功耗时，始终覆盖 flat 差值
        has_abs = row.get("test_ma") is not None or row.get("competitor_ma") is not None
        if not has_abs and out.get(key) not in (None, ""):
            # 仅有 delta、且 CLI 已显式给值时保留 CLI
            continue
        merged.append(dict(row))
        seen_modules.add(module)
        if row.get("delta_ma") is not None:
            out[key] = row.get("delta_ma")
        if row.get("test_ma") is not None:
            out[f"{module}_test_ma"] = row.get("test_ma")
        if row.get("competitor_ma") is not None:
            out[f"{module}_competitor_ma"] = row.get("competitor_ma")
    if merged:
        out["known_deltas"] = merged
        out["hardware_power_source"] = hw.get("source") or "game_power_model"
        out["hardware_power_query"] = hw.get("query") or {}
        # 清除旧的「去掉已知差」外部覆盖，统一按 I1−器件合计重算
        if out.get("adjusted_delta_ma") is not None and has_abs_any(rows):
            out.pop("adjusted_delta_ma", None)
    return out


def has_abs_any(rows: list[Any]) -> bool:
    for row in rows:
        if isinstance(row, dict) and (
            row.get("test_ma") is not None or row.get("competitor_ma") is not None
        ):
            return True
    return False


def build_preliminary_diagnosis(judgment: dict[str, Any]) -> dict[str, Any]:
    """按四类重点输出初步诊断结构（JSON；HTML 由澄清报告「原因分析」展示）。"""
    focus_ids = (
        "test_methodology",
        "optimization_strategy",
        "feature_difference",
        "abnormal_situation",
        "hardware_difference",
    )
    categories = judgment.get("categories") or {}
    sections: list[dict[str, Any]] = []
    for cid in focus_ids:
        cat = categories.get(cid) or {}
        if not isinstance(cat, dict):
            continue
        triggered = [x for x in (cat.get("triggered") or []) if isinstance(x, dict)]
        sections.append(
            {
                "category_id": cid,
                "title": cat.get("title") or cid,
                "order": cat.get("order"),
                "triggered_count": len(triggered),
                "items": [
                    {
                        "id": x.get("id"),
                        "priority": x.get("priority"),
                        "subcategory": x.get("subcategory"),
                        "label": x.get("label"),
                        "detail": x.get("detail"),
                        "confidence": x.get("confidence"),
                    }
                    for x in triggered
                ],
            }
        )
    return {
        "status": judgment.get("status", "ok"),
        "triggered_count": judgment.get("triggered_count", 0),
        "total_rules": judgment.get("total_rules", 0),
        "primary_causes": judgment.get("primary_causes") or [],
        "sections": sections,
        "focus": {
            "test_methodology": "测试手法不符",
            "optimization_strategy": "软件策略差异",
            "feature_difference": "功能差异",
            "abnormal_situation": "异常问题",
        },
    }


def analyze_diagnosis_report(
    analysis_dir: Path,
    report_meta: dict[str, Any] | None = None,
    external_ai: dict[str, Any] | None = None,
    compare_analysis_dir: Path | None = None,
) -> dict[str, Any]:
    meta = dict(report_meta or {})
    analysis_dir = Path(analysis_dir)
    # 步骤 13 产物：自动灌入 waveform_analysis（CLI 显式值优先）
    corr_path = analysis_dir / "game_current_log_correlate.json"
    if corr_path.is_file():
        try:
            corr = json.loads(corr_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            corr = {}
        if isinstance(corr, dict):
            wf = corr.get("waveform_analysis")
            if isinstance(wf, dict):
                existing = meta.get("waveform_analysis")
                if not isinstance(existing, dict):
                    meta["waveform_analysis"] = dict(wf)
                else:
                    merged = dict(wf)
                    merged.update({k: v for k, v in existing.items() if v not in (None, "")})
                    meta["waveform_analysis"] = merged
            if meta.get("has_abnormal_current_spike") is None and isinstance(wf, dict):
                if wf.get("has_abnormal_spike") is not None:
                    meta["has_abnormal_current_spike"] = wf.get("has_abnormal_spike")
            if not meta.get("spike_impact_on_avg") and isinstance(wf, dict):
                meta["spike_impact_on_avg"] = wf.get("spike_impact_on_avg") or ""
            if meta.get("avg_delta_without_spike_ma") is None and isinstance(wf, dict):
                meta["avg_delta_without_spike_ma"] = wf.get("avg_delta_without_spike_ma")
            if not meta.get("waveform_conclusion") and isinstance(wf, dict):
                meta["waveform_conclusion"] = wf.get("conclusion") or ""
            meta.setdefault("current_log_correlate", {
                "status": corr.get("status"),
                "raised_window_count": len(corr.get("raised_windows") or []),
                "summary": corr.get("summary") or corr.get("message") or "",
                "primary_cause_counts": corr.get("primary_cause_counts") or {},
            })

    meta = _enrich_meta_from_current_charts(analysis_dir, meta)
    meta = _enrich_meta_from_hardware_power(analysis_dir, meta)

    ctx = load_analysis_bundle(analysis_dir, meta)
    # load_analysis_bundle 与 meta 共享同一 dict；再显式对齐一次，避免后续漏补
    meta = ctx.get("report_meta") if isinstance(ctx.get("report_meta"), dict) else meta

    log_skill_start("game_power_delta", inputs={"meta_keys": sorted(meta.keys())})
    power_delta = analyze_power_delta(meta)
    log_skill_end("game_power_delta", power_delta, ok=True)

    judgment = judge_root_causes(ctx)

    compare_ctx: dict[str, Any] | None = None
    compare_judgment: dict[str, Any] | None = None
    if compare_analysis_dir and Path(compare_analysis_dir).is_dir():
        compare_ctx = load_analysis_bundle(Path(compare_analysis_dir), meta)
        compare_judgment = judge_root_causes(compare_ctx)
        inject_dual_duration_mismatch(judgment, compare_judgment, ctx, compare_ctx)

    diagnosis = build_preliminary_diagnosis(judgment)

    log_skill_start(
        "game_ai_insights",
        inputs={
            "triggered_count": judgment.get("triggered_count"),
            "route": (power_delta.get("routing") or {}).get("decision"),
            "compare_mode": bool(compare_ctx),
        },
    )
    ai_insights = synthesize_ai_insights(
        power_delta=power_delta,
        judgment=judgment,
        ctx=ctx,
        external_ai=external_ai,
    )
    log_skill_end("game_ai_insights", ai_insights, ok=True)

    step_htmls = write_step_report_htmls(analysis_dir, ctx)
    # 唯一 HTML：澄清报告（含功耗差确认 / 原因+快照 / AI / 子报告链接）
    html_text = render_clarify_report(
        judgment,
        ctx,
        meta,
        power_delta=power_delta,
        ai_insights=ai_insights,
        compare_ctx=compare_ctx,
        compare_judgment=compare_judgment,
    )
    return {
        "status": "ok",
        "compare_mode": bool(compare_ctx),
        "power_delta": power_delta,
        "diagnosis": diagnosis,
        "judgment": judgment,
        "compare_judgment": compare_judgment,
        "ai_insights": ai_insights,
        "step_htmls": {k: str(v) for k, v in step_htmls.items()},
        "html": html_text,
    }


def write_diagnosis_outputs(
    analysis_dir: Path,
    result: dict[str, Any],
    *,
    html_name: str = "game_power_clarify_report.html",
) -> dict[str, Path]:
    analysis_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "power_delta": analysis_dir / "game_power_delta.json",
        "diagnosis": analysis_dir / "game_preliminary_diagnosis.json",
        "ai": analysis_dir / "game_ai_insights.json",
        "bundle": analysis_dir / "game_diagnosis_report.json",
        "root_cause": analysis_dir / "game_root_cause.json",
        "html": analysis_dir / html_name,
    }
    paths["power_delta"].write_text(
        json.dumps(result["power_delta"], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    paths["diagnosis"].write_text(
        json.dumps(result["diagnosis"], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    paths["ai"].write_text(
        json.dumps(result["ai_insights"], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    judgment = result.get("judgment") or {}
    root_payload = {
        "status": judgment.get("status", result.get("status")),
        "triggered_count": judgment.get("triggered_count", 0),
        "primary_causes": judgment.get("primary_causes", []),
        "categories": judgment.get("categories", {}),
        "findings": judgment.get("findings", []),
        "power_delta": result.get("power_delta"),
        "ai_insights": result.get("ai_insights"),
        "html_output": str(paths["html"]),
    }
    paths["root_cause"].write_text(
        json.dumps(root_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    bundle = {
        "status": result.get("status"),
        "power_delta": result.get("power_delta"),
        "diagnosis": {
            "triggered_count": result["diagnosis"].get("triggered_count"),
            "total_rules": result["diagnosis"].get("total_rules"),
            "primary_causes": result["diagnosis"].get("primary_causes"),
            "sections": result["diagnosis"].get("sections"),
        },
        "ai_insights": result.get("ai_insights"),
        "step_htmls": result.get("step_htmls") or {},
        "html_output": str(paths["html"]),
        "note": "澄清报告含原因说明、日志快照与子 skill HTML 链接；步骤摘要 HTML 与 JSON 同目录",
    }
    paths["bundle"].write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["html"].write_text(result["html"], encoding="utf-8")

    # 去掉旧的重复统一诊断 HTML
    legacy = analysis_dir / "game_diagnosis_report.html"
    if legacy.is_file() and legacy.resolve() != paths["html"].resolve():
        try:
            legacy.unlink()
        except OSError:
            pass
    return paths
