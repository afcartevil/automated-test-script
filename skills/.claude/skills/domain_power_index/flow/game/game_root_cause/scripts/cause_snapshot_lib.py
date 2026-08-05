"""原因证据快照：从各步骤 JSON 抽取总结与日志 raw_evidence，并生成子报告 HTML。"""

from __future__ import annotations

import html
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


# 规则 id 前缀 / 精确 id → 关联步骤 JSON 键
_RULE_STEP_MAP: dict[str, list[str]] = {
    "log_no_logs": ["summary", "game_time_window"],
    "log_incomplete": ["summary", "game_time_window"],
    "log_no_game_scene": ["game_time_window", "summary"],
    "log_scene_incomplete": ["game_time_window", "summary"],
    "log_duration_short": ["game_time_window", "summary"],
    "log_duration_mismatch": ["game_time_window", "summary"],
    "log_": ["game_time_window", "summary"],
    "precond_": ["game_precondition", "game_brightness", "game_volume"],
    "method_brightness": ["game_brightness", "game_precondition"],
    "method_volume": ["game_volume", "game_precondition"],
    "method_cpu_thermal": ["game_cpu_gpu_ddr", "game_thermal"],
    "method_thermal": ["game_thermal", "game_cpu_gpu_ddr"],
    "scene_background": ["game_background"],
    "scene_network": ["game_network"],
    "scene_app_version": ["summary"],
    "scene_poor_network": ["game_network"],
    "scene_": ["game_time_window", "game_precondition", "game_network", "game_background"],
    "hw_": ["summary"],
    "opt_thermal_backlight": ["game_brightness", "game_thermal"],
    "opt_thermal_freq": ["game_thermal", "game_cpu_gpu_ddr"],
    "opt_thermal": ["game_thermal", "game_cpu_gpu_ddr"],
    "opt_launch_brightness": ["game_brightness"],
    "opt_in_game_brightness": ["game_brightness"],
    "opt_pre_brightness": ["game_brightness"],
    "opt_backlight": ["game_brightness"],
    "opt_aal": ["game_brightness"],
    "opt_refresh": ["game_brightness"],
    "opt_high_fps": ["game_brightness", "game_cpu_gpu_ddr"],
    "opt_frame_rate": ["game_cpu_gpu_ddr", "game_brightness"],
    "opt_sound": ["game_volume"],
    "opt_cpu": ["game_cpu_gpu_ddr", "game_kernel_cpu"],
    "opt_touch_boost": ["game_cpu_gpu_ddr"],
    "opt_ddr": ["game_cpu_gpu_ddr"],
    "opt_boost": ["game_cpu_gpu_ddr"],
    "opt_fps": ["game_cpu_gpu_ddr"],
    "opt_": ["game_brightness", "game_cpu_gpu_ddr", "game_volume"],
    "feat_": ["game_background", "game_brightness", "game_volume", "summary"],
    "abn_freq": ["game_kernel_cpu", "game_cpu_gpu_ddr", "game_thermal"],
    "abn_background": ["game_kernel_cpu", "game_background"],
    "abn_process": ["game_background", "game_kernel_cpu"],
    "abn_cpu": ["game_kernel_cpu", "game_cpu_gpu_ddr"],
    "abn_broadcast": ["game_background"],
    "abn_alarm": ["game_background"],
    "abn_gc": ["game_background"],
    "abn_autostart": ["game_background"],
    "abn_memory": ["game_background"],
    "abn_thermal": ["game_thermal"],
    "abn_weak_rf": ["game_network"],
    "abn_wifi": ["game_network"],
    "abn_cell": ["game_network"],
    "abn_high_data": ["game_network"],
    "abn_": ["game_kernel_cpu", "game_background", "game_thermal", "game_network"],
}

_CATEGORY_STEPS: dict[str, list[str]] = {
    "test_methodology": [
        "game_time_window",
        "game_precondition",
        "game_brightness",
        "game_volume",
        "game_thermal",
        "game_background",
        "game_cpu_gpu_ddr",
    ],
    "hardware_difference": ["summary"],
    "optimization_strategy": ["game_brightness", "game_cpu_gpu_ddr", "game_thermal"],
    "feature_difference": ["game_background", "summary"],
    "abnormal_situation": ["game_kernel_cpu", "game_background", "game_network", "game_cpu_gpu_ddr"],
}

_STEP_META: dict[str, dict[str, str]] = {
    "game_time_window": {"title": "场景识别", "html": "game_time_window_report.html"},
    "game_precondition": {"title": "前置条件", "html": "game_precondition_report.html"},
    "game_brightness": {"title": "亮度/显示", "html": "game_brightness_report.html"},
    "game_volume": {"title": "音量", "html": "game_volume_report.html"},
    "game_cpu_gpu_ddr": {"title": "CPU/GPU/DDR", "html": "game_cpu_gpu_ddr_report.html"},
    "game_kernel_cpu": {"title": "Kernel CPU", "html": "game_kernel_cpu_report.html"},
    "game_background": {"title": "后台应用", "html": "game_background_report.html"},
    "game_network": {"title": "网络/RF", "html": "game_network_report.html"},
    "game_thermal": {"title": "Thermal", "html": "game_thermal_report.html"},
    "game_current_log_correlate": {
        "title": "电流↔日志关联",
        "html": "game_current_log_correlate_report.html",
    },
    "summary": {"title": "数据汇总仪表板", "html": "game_power_report.html"},
}

_EVIDENCE_CAP = 6
_SUMMARY_CAP = 8


def _esc(text: Any) -> str:
    return html.escape("" if text is None else str(text))


def resolve_steps_for_rule(rule_id: str, category_id: str = "") -> list[str]:
    rid = str(rule_id or "")
    # longest prefix / exact first
    candidates = sorted(_RULE_STEP_MAP.keys(), key=len, reverse=True)
    for key in candidates:
        if rid == key or rid.startswith(key):
            return list(_RULE_STEP_MAP[key])
    return list(_CATEGORY_STEPS.get(category_id, ["summary"]))


def _collect_raw_evidence(obj: Any, out: list[str], *, limit: int = 40) -> None:
    if len(out) >= limit or obj is None:
        return
    if isinstance(obj, dict):
        raw = obj.get("raw_evidence")
        if isinstance(raw, str) and raw.strip():
            line = raw.strip()
            if line not in out:
                out.append(line)
        elif isinstance(raw, list):
            for item in raw:
                if len(out) >= limit:
                    break
                if isinstance(item, str) and item.strip():
                    if item.strip() not in out:
                        out.append(item.strip())
                elif isinstance(item, dict):
                    ev = item.get("raw_evidence") or item.get("line") or item.get("text")
                    if isinstance(ev, str) and ev.strip() and ev.strip() not in out:
                        out.append(ev.strip())
        for key, val in obj.items():
            if key == "raw_evidence":
                continue
            # prioritize evidence-ish keys
            if key in ("evidence", "samples", "hits", "abnormal_processes", "top_processes", "notes"):
                _collect_raw_evidence(val, out, limit=limit)
        for key, val in obj.items():
            if key in ("raw_evidence", "evidence", "samples", "hits"):
                continue
            _collect_raw_evidence(val, out, limit=limit)
    elif isinstance(obj, list):
        for item in obj:
            if len(out) >= limit:
                break
            _collect_raw_evidence(item, out, limit=limit)


def _step_summary_lines(step_key: str, data: Any) -> list[str]:
    if not isinstance(data, dict):
        return []
    lines: list[str] = []
    status = data.get("status")
    if status is not None:
        lines.append(f"status={status}")

    if step_key == "game_time_window":
        lines.append(f"游戏={data.get('game_name')} ({data.get('game_package')})")
        tg = (data.get("time_windows") or {}).get("T_game") or data.get("game_window") or {}
        if isinstance(tg, dict) and tg.get("start"):
            lines.append(f"T_game={tg.get('start')} ~ {tg.get('end')} ({tg.get('duration_seconds')}s)")
    elif step_key == "game_precondition":
        tc = data.get("test_conditions") or {}
        lines.append(f"completeness={tc.get('completeness')}")
        sc = tc.get("scenario") or {}
        if sc:
            lines.append(
                f"场景={sc.get('project')}/{sc.get('label')} mode={sc.get('compare_mode')} "
                f"目标等级={sc.get('target_brightness_level')} 目标nit={sc.get('target_brightness_nits')}"
            )
        tags = tc.get("tags") or []
        if isinstance(tags, list):
            for t in tags:
                if not isinstance(t, dict) or t.get("id") != "brightness":
                    continue
                lines.append(
                    f"亮度比对 measured={t.get('numeric_level') or t.get('numeric_nits')} "
                    f"expected={t.get('expected_level') or t.get('expected_nits')} "
                    f"status={t.get('status')} mode={t.get('compare_mode')}"
                )
            bad = [t for t in tags if isinstance(t, dict) and str(t.get("status")) in ("bad", "warn")]
            for t in bad[:5]:
                lines.append(f"条件异常 {t.get('id')}/{t.get('label')}: {t.get('value')} ({t.get('status')})")
    elif step_key == "game_brightness":
        inv = data.get("brightness_investigation") or {}
        s1 = inv.get("step1_test_setting") or {}
        if s1:
            if s1.get("compare_mode") == "nits":
                lines.append(
                    f"测试亮度(NPS) nits={s1.get('measured_nits')} expected={s1.get('expected_nits')} "
                    f"aligned={s1.get('aligned_with_standard')} source={s1.get('primary_source')}"
                )
            else:
                lines.append(
                    f"测试亮度={s1.get('brightness_level')}/255 expected={s1.get('expected_level')} "
                    f"aligned={s1.get('aligned_with_standard')} source={s1.get('primary_source')}"
                )
        s2 = inv.get("step2_auto_backlight") or {}
        if s2:
            lines.append(f"自动背光={s2.get('enabled') or s2.get('status')}")
        s4 = inv.get("step4_aal_strategy") or {}
        if s4:
            summary = s4.get("report_summary") or s4.get("note")
            if summary:
                lines.append(str(summary))
            elif s4.get("effective") is False:
                lines.append("AAL未生效（main log 无 AALService）")
            else:
                lines.append(f"AAL changes={s4.get('change_count') or s4.get('status')}")
        ba = data.get("brightness_analysis") or {}
        launch = ba.get("launch_window") or {}
        if launch:
            lines.append(f"启动变光 phases={launch.get('phase_count')}")
    elif step_key == "game_volume":
        pre = (data.get("pre_test_volume") or {}).get("baseline") or data.get("pre_test_setting") or {}
        if not pre:
            vf = data.get("volume_investigation") or {}
            pre = (vf.get("step1_test_volume") or {})
        if pre:
            lines.append(
                f"测试音量 index={pre.get('index') or pre.get('volume')} "
                f"device={pre.get('device_label') or pre.get('device')}"
            )
        ing = data.get("in_game_volume") or {}
        if ing:
            lines.append(f"游戏内稳定={ing.get('stable')} range={ing.get('index_min')}~{ing.get('index_max')}")
    elif step_key == "game_cpu_gpu_ddr":
        fps = data.get("frame_rate") or data.get("game_fps") or {}
        if isinstance(fps, dict) and (fps.get("avg") is not None or fps.get("avg_fps") is not None):
            lines.append(f"帧率 avg={fps.get('avg') or fps.get('avg_fps')} min={fps.get('min')} max={fps.get('max')}")
        inv = data.get("investigation") or data
        for key in ("perf_lock", "ddr", "touch_boost", "summary"):
            block = inv.get(key) if isinstance(inv, dict) else None
            if isinstance(block, dict) and block.get("summary"):
                lines.append(str(block.get("summary"))[:160])
        if data.get("notes"):
            for n in (data.get("notes") or [])[:2]:
                lines.append(str(n)[:160])
    elif step_key == "game_kernel_cpu":
        abn = data.get("abnormal_processes") or []
        lines.append(f"异常进程数={len(abn) if isinstance(abn, list) else abn}")
        if isinstance(abn, list):
            for p in abn[:5]:
                if isinstance(p, dict):
                    lines.append(
                        f"{p.get('name')} avg={p.get('avg_usage')}% max={p.get('max_usage')}% "
                        f"count={p.get('occurrence_count')}"
                    )
    elif step_key == "game_background":
        bd = data.get("category_breakdown_T_game") or {}
        if isinstance(bd, dict):
            parts = [f"{k}={v}" for k, v in list(bd.items())[:8] if v]
            if parts:
                lines.append("T_game: " + ", ".join(parts))
        auto = data.get("autostart") or {}
        if isinstance(auto, dict):
            lines.append(f"自启动 starts={auto.get('starts')} frequent={auto.get('frequent')}")
    elif step_key == "game_network":
        rf = data.get("rf_stats") or {}
        lines.append(f"RF level={rf.get('level')} type={rf.get('network_type')} summary={rf.get('summary')}")
        inv = data.get("network_investigation") or {}
        if isinstance(inv, dict):
            s1 = inv.get("step1_wifi_rssi") or {}
            if isinstance(s1, dict) and s1.get("sample_count"):
                lines.append(
                    f"WiFi RSSI avg={s1.get('rssi_dbm_avg')} "
                    f"range={s1.get('rssi_dbm_min')}~{s1.get('rssi_dbm_max')} "
                    f"samples={s1.get('sample_count')}"
                )
            wa = s1.get("wifi_assistant") if isinstance(s1, dict) else None
            if isinstance(wa, dict) and wa.get("coverage") == "ok":
                lines.append(
                    f"WiFi Assistant SSID={wa.get('ssid')} "
                    f"netId={wa.get('network_id')} "
                    f"userIgnored={wa.get('user_ignored')} "
                    f"scored={wa.get('is_scored_current_network')} "
                    f"noCandidate={wa.get('no_candidate_count')} "
                    f"monitorStarts={wa.get('monitor_start_count_t_game')} "
                    f"monitorStops={wa.get('monitor_stop_count_t_game')}"
                )
            gap = None
            if isinstance(s1, dict):
                gap = s1.get("rssi_gap_conclusion")
            if not gap and isinstance(wa, dict):
                gap = wa.get("rssi_gap_conclusion")
            if gap:
                lines.append(f"局内无RSSI原因: {gap}")
            dual = inv.get("dual_channel") or {}
            if isinstance(dual, dict) and dual.get("verdict"):
                lines.append(
                    f"双通道 verdict={dual.get('verdict')} "
                    f"is_dual={dual.get('is_dual_channel')} "
                    f"summary={dual.get('summary')}"
                )
            s2 = inv.get("step2_wifi_scenario") or {}
            if isinstance(s2, dict) and s2.get("coverage") not in (None, "", "missing"):
                lines.append(
                    f"场景切换 cellular_data={s2.get('cellular_data_during_game')} "
                    f"wifi_if_changes={s2.get('wifi_interface_changes')}"
                )
            s3 = inv.get("step3_cellular_signal") or {}
            if isinstance(s3, dict) and s3.get("sample_count"):
                lines.append(
                    f"蜂窝 RSRP avg={s3.get('rsrp_avg')} band_changed={s3.get('band_changed')} "
                    f"bands={s3.get('bands_observed')}"
                )
            s4 = inv.get("step4_ccmni_transfer") or {}
            if isinstance(s4, dict) and (
                s4.get("primary_rx_bytes_delta") is not None
                or s4.get("primary_tx_bytes_delta") is not None
            ):
                lines.append(
                    f"ccmni {s4.get('primary_interface') or '-'} "
                    f"rxΔ={s4.get('primary_rx_bytes_delta')} txΔ={s4.get('primary_tx_bytes_delta')}"
                )
        for note in (rf.get("notes") or data.get("notes") or [])[:3]:
            lines.append(str(note)[:160])
    elif step_key == "game_thermal":
        report = data.get("thermal_report") or {}
        dim = report.get("backlight_dim") or {}
        freq = report.get("freq_throttle") or {}
        if dim.get("report_summary"):
            lines.append(str(dim.get("report_summary")))
        if freq.get("report_summary"):
            lines.append(str(freq.get("report_summary")))
        if not lines:
            temp = (data.get("temperature") or {}).get("T_game") or {}
            lines.append(
                f"T_game temp max={temp.get('max_c')} delta={temp.get('delta_c')} rise={temp.get('rise_detected')}"
            )
            ts = (data.get("thermal_summary") or {}).get("during_game") or {}
            if ts:
                lines.append(
                    f"降背光={ts.get('thermal_backlight')} 限频={ts.get('freq_throttle')}"
                )
    elif step_key == "summary":
        lines.append(f"summary.status={data.get('status')}")
        miss = data.get("missing_logs")
        if miss:
            lines.append(f"missing_logs={miss}")
        gw = data.get("game_window") or {}
        if gw.get("duration_seconds") is not None:
            lines.append(f"duration={gw.get('duration_seconds')}s")

    # generic fallbacks
    if data.get("summary") and isinstance(data.get("summary"), str):
        lines.append(str(data.get("summary"))[:180])
    for note in (data.get("warnings") or [])[:2]:
        lines.append(f"warn: {note}")
    return lines[:_SUMMARY_CAP]


def _aal_cause_evidence(finding: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    """AAL/降背光：时间线总结 + main HWC / AAL / sys BrightnessEvent 停止末行快照。"""
    rule_id = str(finding.get("id") or "")
    gb = ctx.get("game_brightness") or {}
    inv = (gb.get("brightness_investigation") or {}) if isinstance(gb, dict) else {}
    s4 = inv.get("step4_aal_strategy") or {}
    summary = str(s4.get("report_summary") or s4.get("note") or "AAL 背光策略").strip()
    timeline = str(s4.get("timeline") or "").strip()
    if timeline and timeline not in summary:
        summary = f"{summary}（{timeline}）" if summary else timeline
    snaps: list[str] = []
    for ev in s4.get("report_evidence") or []:
        line = _display_aal_log_snapshot(str(ev))
        if line and line not in snaps:
            snaps.append(line)
    if not snaps:
        for pt in s4.get("key_points") or []:
            if not isinstance(pt, dict):
                continue
            for key in ("hwc_raw", "aal_raw", "dpc_raw"):
                raw = pt.get(key)
                if not raw:
                    continue
                line = _display_aal_log_snapshot(str(raw))
                if line and line not in snaps:
                    snaps.append(line)
    meta = _STEP_META.get("game_brightness") or {
        "title": "显示/亮度",
        "html": "game_brightness_report.html",
    }
    reason = str(finding.get("label") or rule_id)
    sub = finding.get("subcategory")
    if sub:
        reason = f"{sub} — {reason}"
    return {
        "rule_id": rule_id,
        "reason": reason,
        "priority": finding.get("priority"),
        "category_id": finding.get("category_id"),
        "category_title": finding.get("category_title"),
        "detail": summary,
        "steps": [
            {
                "step": "game_brightness",
                "title": meta["title"],
                "html": meta["html"],
                "summaries": [],
                "snapshots": snaps,
            }
        ],
        "snapshots": snaps,
    }


def _backlight_2_cause_evidence(finding: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    """背光2.0：一句话（实时nits + 下降比例）+ DisplayPowerController 原日志。"""
    rule_id = str(finding.get("id") or "")
    gb = ctx.get("game_brightness") or {}
    inv = (gb.get("brightness_investigation") or {}) if isinstance(gb, dict) else {}
    s3 = inv.get("step3_backlight_2_0") or {}
    summary = str(s3.get("report_summary") or s3.get("note") or "背光2.0").strip()
    # 补强：显式拼 nits / 下降比例
    nits = s3.get("realtime_nits")
    drop = s3.get("drop_ratio_pct")
    exp = s3.get("expected_brightness_drop_pct")
    if nits is not None or drop is not None:
        bits = []
        if nits is not None:
            bits.append(f"实时nits={float(nits):g}")
        if drop is not None:
            bits.append(f"下降比例={float(drop):g}%")
        if exp is not None:
            bits.append(f"期望≈{float(exp):g}%")
        head = "，".join(bits)
        if head and head not in summary:
            summary = f"{summary}（{head}）" if summary else head
    snaps: list[str] = []
    for ev in s3.get("report_evidence") or []:
        line = _display_aal_log_snapshot(str(ev))
        if line and line not in snaps:
            snaps.append(line)
    last = s3.get("last_brightness_event") or {}
    if isinstance(last, dict) and last.get("raw_evidence"):
        line = _display_aal_log_snapshot(str(last.get("raw_evidence")))
        if line and line not in snaps:
            snaps.insert(0, line)
    meta = _STEP_META.get("game_brightness") or {
        "title": "显示/亮度",
        "html": "game_brightness_report.html",
    }
    reason = str(finding.get("label") or rule_id)
    sub = finding.get("subcategory")
    if sub:
        reason = f"{sub} — {reason}"
    return {
        "rule_id": rule_id,
        "reason": reason,
        "priority": finding.get("priority"),
        "category_id": finding.get("category_id"),
        "category_title": finding.get("category_title"),
        "detail": summary,
        "steps": [
            {
                "step": "game_brightness",
                "title": meta["title"],
                "html": meta["html"],
                "summaries": [],
                "snapshots": snaps[:3],
            }
        ],
        "snapshots": snaps[:3],
    }


def _thermal_cause_evidence(finding: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    """thermal降亮度 / 限频：一句话 + 每档一行。"""
    rule_id = str(finding.get("id") or "")
    th = ctx.get("game_thermal") or {}
    report = (th.get("thermal_report") or {}) if isinstance(th, dict) else {}
    if "freq" in rule_id or "throttle" in rule_id:
        block = report.get("freq_throttle") or {}
    else:
        block = report.get("backlight_dim") or {}
    summary = str(block.get("report_summary") or finding.get("label") or "thermal").strip()
    snaps: list[str] = []
    for line in block.get("report_evidence") or []:
        s = str(line).strip()
        if s and s not in snaps:
            snaps.append(s)
    # 补充原始日志（至多每档一行）
    for gear in block.get("gears") or []:
        raw = gear.get("raw_evidence")
        if not raw:
            continue
        disp = _display_aal_log_snapshot(str(raw))  # 去文件名/行号
        if disp and disp not in snaps:
            snaps.append(disp)
    meta = _STEP_META.get("game_thermal") or {"title": "Thermal", "html": "game_thermal_report.html"}
    reason = str(finding.get("label") or rule_id)
    sub = finding.get("subcategory")
    if sub:
        reason = f"{sub} — {reason}"
    return {
        "rule_id": rule_id,
        "reason": reason,
        "priority": finding.get("priority"),
        "category_id": finding.get("category_id"),
        "category_title": finding.get("category_title"),
        "detail": summary,
        "steps": [
            {
                "step": "game_thermal",
                "title": meta["title"],
                "html": meta["html"],
                "summaries": [],
                "snapshots": snaps,
            }
        ],
        "snapshots": snaps,
    }


def _refresh_rate_cause_evidence(finding: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    """屏幕刷新率：一句话总结 + PowerHal/hwcomposer 日志快照。"""
    rule_id = str(finding.get("id") or "")
    gb = ctx.get("game_brightness") or {}
    inv = (gb.get("brightness_investigation") or {}) if isinstance(gb, dict) else {}
    s6 = inv.get("step6_refresh_rate") or {}
    summary = str(s6.get("report_summary") or "屏幕刷新率").strip()
    snaps: list[str] = []
    for ev in s6.get("report_evidence") or []:
        line = _display_aal_log_snapshot(str(ev))
        if line and line not in snaps:
            snaps.append(line)
    for block_key in ("actual_fps", "supported_fps"):
        for it in (s6.get(block_key) or {}).get("samples") or []:
            if not isinstance(it, dict):
                continue
            line = _display_aal_log_snapshot(str(it.get("raw_evidence") or ""))
            if line and line not in snaps:
                snaps.append(line)
            if len(snaps) >= 6:
                break
        if len(snaps) >= 6:
            break
    meta = _STEP_META.get("game_brightness") or {
        "title": "显示/亮度",
        "html": "game_brightness_report.html",
    }
    reason = str(finding.get("label") or rule_id)
    sub = finding.get("subcategory")
    if sub:
        reason = f"{sub} — {reason}"
    return {
        "rule_id": rule_id,
        "reason": reason,
        "priority": finding.get("priority"),
        "category_id": finding.get("category_id"),
        "category_title": finding.get("category_title"),
        "detail": summary,
        "steps": [
            {
                "step": "game_brightness",
                "title": meta["title"],
                "html": meta["html"],
                "summaries": [],
                "snapshots": snaps,
            }
        ],
        "snapshots": snaps,
    }


def collect_cause_evidence(
    finding: dict[str, Any],
    ctx: dict[str, Any],
) -> dict[str, Any]:
    """为单条命中规则收集：原因说明、步骤总结、日志快照、子报告链接。"""
    rule_id = str(finding.get("id") or "")
    if rule_id == "opt_aal_strategy" or rule_id.startswith("opt_aal"):
        return _aal_cause_evidence(finding, ctx)
    if rule_id == "opt_backlight_2_0" or "backlight_2" in rule_id:
        return _backlight_2_cause_evidence(finding, ctx)
    if rule_id == "opt_refresh_rate" or "refresh_rate" in rule_id:
        return _refresh_rate_cause_evidence(finding, ctx)
    if rule_id in ("opt_thermal_backlight_dim", "opt_thermal_freq_throttle") or (
        rule_id.startswith("opt_thermal_") and rule_id != "opt_thermal_triggered"
    ):
        return _thermal_cause_evidence(finding, ctx)
    category_id = str(finding.get("category_id") or "")
    steps = resolve_steps_for_rule(rule_id, category_id)
    # also parse game_* sources mentioned in detail
    detail = str(finding.get("detail") or "")
    for token in detail.replace(";", " ").split():
        if token.startswith("game_") or token.startswith("summary."):
            key = token.split(".", 1)[0]
            if key in _STEP_META and key not in steps:
                steps.append(key)

    step_blocks: list[dict[str, Any]] = []
    all_snapshots: list[str] = []
    for step in steps:
        data = ctx.get(step) if step != "summary" else (ctx.get("summary") or {})
        if not isinstance(data, dict):
            # try loading alias
            continue
        meta = _STEP_META.get(step) or {"title": step, "html": f"{step}_report.html"}
        summaries = _step_summary_lines(step, data)
        evidences: list[str] = []
        _collect_raw_evidence(data, evidences, limit=_EVIDENCE_CAP)
        # keep unique global order
        for ev in evidences:
            if ev not in all_snapshots:
                all_snapshots.append(ev)
        step_blocks.append(
            {
                "step": step,
                "title": meta["title"],
                "html": meta["html"],
                "summaries": summaries,
                "snapshots": evidences[:_EVIDENCE_CAP],
            }
        )

    reason = str(finding.get("label") or rule_id)
    sub = finding.get("subcategory")
    if sub:
        reason = f"{sub} — {reason}"
    human = str(finding.get("detail") or "").strip()
    # prefer short humanized later in renderer; keep raw detail here
    return {
        "rule_id": rule_id,
        "reason": reason,
        "priority": finding.get("priority"),
        "category_id": category_id,
        "category_title": finding.get("category_title"),
        "detail": human,
        "steps": step_blocks,
        "snapshots": all_snapshots[:_EVIDENCE_CAP],
    }


def collect_category_evidence(
    category_id: str,
    triggered: list[dict[str, Any]],
    ctx: dict[str, Any],
) -> dict[str, Any]:
    items = [collect_cause_evidence(f, ctx) for f in triggered if isinstance(f, dict)]
    step_keys: list[str] = []
    for it in items:
        for s in it.get("steps") or []:
            sk = s.get("step")
            if sk and sk not in step_keys:
                step_keys.append(sk)
    if not step_keys:
        step_keys = list(_CATEGORY_STEPS.get(category_id, ["summary"]))
    links = []
    for sk in step_keys:
        meta = _STEP_META.get(sk) or {"title": sk, "html": f"{sk}_report.html"}
        links.append({"step": sk, "title": meta["title"], "html": meta["html"]})
    return {"category_id": category_id, "causes": items, "step_links": links}


def render_step_summary_html(step_key: str, data: dict[str, Any], analysis_dir: Path) -> str:
    meta = _STEP_META.get(step_key) or {"title": step_key, "html": f"{step_key}_report.html"}
    summaries = _step_summary_lines(step_key, data)
    evidences: list[str] = []
    _collect_raw_evidence(data, evidences, limit=20)
    sum_lis = "".join(f"<li>{_esc(s)}</li>" for s in summaries) or "<li>无总结字段</li>"
    ev_pre = "\n".join(_esc(e) for e in evidences[:20]) or "（无 raw_evidence）"
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(meta['title'])} — 步骤摘要</title>
<style>
body{{font-family:"Segoe UI","Microsoft YaHei",sans-serif;margin:24px;background:#f5f7fa;color:#2c3e50;}}
.card{{background:#fff;border-radius:8px;padding:18px 20px;box-shadow:0 1px 3px rgba(0,0,0,.08);max-width:960px;}}
h1{{font-size:18px;margin:0 0 8px;}}
.muted{{color:#7f8c8d;font-size:12px;margin-bottom:14px;}}
h2{{font-size:14px;border-bottom:2px solid #3498db;padding-bottom:4px;}}
pre{{background:#f8fafc;border:1px solid #e8edf2;padding:10px;overflow:auto;font-size:11px;line-height:1.45;white-space:pre-wrap;}}
a{{color:#185fa5;}}
</style>
</head>
<body>
<div class="card">
  <h1>{_esc(meta['title'])}（{_esc(step_key)}）</h1>
  <div class="muted">由 JSON 自动生成的步骤摘要 / 日志快照 · <a href="game_power_clarify_report.html">返回澄清报告</a>
  · <a href="game_power_report.html">汇总仪表板</a></div>
  <h2>总结性结果</h2>
  <ul>{sum_lis}</ul>
  <h2>原始数据快照（日志）</h2>
  <pre>{ev_pre}</pre>
</div>
</body>
</html>
"""


def write_step_report_htmls(analysis_dir: Path, ctx: dict[str, Any]) -> dict[str, Path]:
    """为各分维 JSON 生成轻量 HTML；汇总仪表板若已存在则不覆盖。"""
    analysis_dir = Path(analysis_dir)
    analysis_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    for step_key, meta in _STEP_META.items():
        out = analysis_dir / meta["html"]
        if step_key == "summary":
            # keep existing game_power_report.html produced by game_summary
            if out.is_file():
                written[step_key] = out
                continue
            data = ctx.get("summary") or {}
        else:
            data = ctx.get(step_key) or {}
        if not isinstance(data, dict) or not data:
            # still write a stub so links are not broken
            data = {"status": "missing", "notes": [f"{step_key}.json 不存在或为空"]}
        html_text = render_step_summary_html(step_key, data, analysis_dir)
        out.write_text(html_text, encoding="utf-8")
        written[step_key] = out
    return written


def format_cause_evidence_html(evidence: dict[str, Any], *, compact: bool = False) -> str:
    """单条原因：写明原因 + 快照 + 子报告链接。

    compact=True 时仅保留精简总结与少量快照一行摘要（用于表格单元格）。
    """
    reason = _esc(evidence.get("reason") or "")
    detail = str(evidence.get("detail") or "")
    # strip checkmarks noise for display
    detail_disp = detail.replace("✓", "[命中]").replace("✗", "[未命中]")
    if compact:
        detail_disp = ""
    elif len(detail_disp) > 280:
        detail_disp = detail_disp[:277] + "…"

    snaps = evidence.get("snapshots") or []
    snap_cap = 1 if compact else _EVIDENCE_CAP
    snap_html = ""
    if snaps and not compact:
        snap_body = "".join(
            f'<pre style="margin:0 0 4px;white-space:pre-wrap;word-break:break-all;'
            f'font-size:10px;line-height:1.4;color:var(--color-text-secondary);">{_esc(s)}</pre>'
            for s in snaps[:snap_cap]
        )
        snap_html = (
            f'<div style="margin-top:6px;background:var(--color-background-secondary);'
            f'border-radius:var(--border-radius-md);padding:8px 10px;">'
            f'<p style="margin:0 0 4px;font-size:11px;color:var(--color-text-tertiary);">原始数据快照</p>'
            f"{snap_body}</div>"
        )
    elif snaps and compact:
        # 精简模式：仅在无总结时退化显示 1 条截断快照
        pass

    # step summary chips + links
    link_bits: list[str] = []
    sum_bits: list[str] = []
    sum_limit = 2 if compact else 3
    for st in evidence.get("steps") or []:
        title = _esc(st.get("title") or st.get("step"))
        href = _esc(st.get("html") or "#")
        if not compact:
            link_bits.append(
                f'<a href="{href}" style="font-size:11px;margin-right:8px;">{title}报告</a>'
            )
        for line in (st.get("summaries") or [])[:sum_limit]:
            sum_bits.append(f'<li style="margin:2px 0;">{_esc(line)}</li>')
    links_html = (
        f'<div style="margin-top:6px;">{"".join(link_bits)}</div>' if link_bits else ""
    )
    sum_html = (
        f'<ul style="margin:4px 0 0;padding-left:16px;font-size:12px;color:var(--color-text-secondary);">'
        f'{"".join(sum_bits[: (4 if compact else 6)])}</ul>'
        if sum_bits
        else ""
    )
    if compact and not sum_bits and snaps:
        line = str(snaps[0]).replace("\n", " ").strip()
        if len(line) > 100:
            line = line[:97] + "…"
        snap_html = f'<div class="snap-compact"><div class="snap-line">{_esc(line)}</div></div>'
    if compact:
        # 精简：仅总结 +（必要时）短快照，不含原因标题（表格左列已有）
        parts = [p for p in (sum_html, snap_html) if p]
        return "".join(parts) if parts else '<span class="muted">—</span>'

    return (
        f'<div style="margin-top:8px;padding:8px 10px;border:0.5px solid var(--color-border-tertiary);'
        f'border-radius:var(--border-radius-md);">'
        f'<p style="margin:0;font-size:13px;"><span style="color:var(--color-text-tertiary);">原因：</span>'
        f'<strong>{reason}</strong></p>'
        f'<p style="margin:4px 0 0;font-size:12px;color:var(--color-text-secondary);">{_esc(detail_disp)}</p>'
        f'{sum_html}{snap_html}{links_html}</div>'
    )


def _missing_logs_from_ctx(ctx: dict[str, Any]) -> list[str]:
    summary = ctx.get("summary") or {}
    inv = summary.get("log_inventory") if isinstance(summary, dict) else None
    if isinstance(inv, dict):
        miss = inv.get("missing_for_report") or inv.get("mobile_core_missing")
        if isinstance(miss, list) and miss:
            return [str(x).strip() for x in miss if str(x).strip()]
    miss = summary.get("missing_logs") if isinstance(summary, dict) else None
    if isinstance(miss, list):
        return [str(x).strip() for x in miss if str(x).strip()]
    if isinstance(miss, str) and miss.strip():
        return [miss.strip()]
    return []


def _scene_coverage_missing_from_ctx(ctx: dict[str, Any]) -> list[str]:
    for src in (ctx.get("game_time_window"), ctx.get("summary")):
        if not isinstance(src, dict):
            continue
        inv = src.get("log_inventory") or {}
        if isinstance(inv, dict):
            miss = inv.get("scene_coverage_missing")
            if isinstance(miss, list) and miss:
                return [str(x).strip() for x in miss if str(x).strip()]
        cov = src.get("log_coverage") or {}
        if isinstance(cov, dict):
            out = []
            for key, entry in cov.items():
                if not isinstance(entry, dict):
                    continue
                status = str(entry.get("status") or "").lower()
                if status in ("missing", "no_overlap") or entry.get("covers_t_game") is False:
                    out.append(str(key))
            if out:
                return out
    return []


def _sort_methodology_findings(triggered: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """日志类置顶：无日志 → 日志不全 → 日志无场景 → 场景日志不全 → 其余。"""
    order = {
        "log_no_logs": 0,
        "log_incomplete": 1,
        "log_no_game_scene": 2,
        "log_scene_incomplete": 3,
        "log_duration_short": 4,
        "log_duration_mismatch": 5,
    }
    ranked: list[tuple[int, int, dict[str, Any]]] = []
    for i, item in enumerate(triggered):
        if not isinstance(item, dict):
            continue
        rid = str(item.get("id") or "")
        ranked.append((order.get(rid, 100), i, item))
    ranked.sort(key=lambda x: (x[0], x[1]))
    return [x[2] for x in ranked]


def _display_log_snapshot(line: str) -> str:
    """去掉日志文件名前缀，保留「行号: 时间戳 …」便于表格展示。"""
    s = str(line or "").strip()
    if not s:
        return ""
    m = re.match(r"^[A-Za-z0-9_./\\-]+:(\d+:\s*.+)$", s)
    return m.group(1).strip() if m else s


def _display_aal_log_snapshot(line: str) -> str:
    """AAL 证据：去掉文件名与行号，只保留原始日志行。"""
    s = _display_log_snapshot(line)
    m = re.match(r"^\d+:\s*(.+)$", s)
    return m.group(1).strip() if m else s


def _first_tag_evidence(ctx: dict[str, Any], tag_id: str) -> str:
    pc = ctx.get("game_precondition") or {}
    tags = ((pc.get("test_conditions") or {}).get("tags") or []) if isinstance(pc, dict) else []
    for t in tags:
        if not isinstance(t, dict) or t.get("id") != tag_id:
            continue
        ev = t.get("raw_evidence")
        if isinstance(ev, list) and ev:
            return str(ev[0]).strip()
        if isinstance(ev, str) and ev.strip():
            return ev.strip()
    return ""


def _volume_methodology_snapshot(ctx: dict[str, Any]) -> str:
    vol = ctx.get("game_volume") or {}
    if isinstance(vol, dict):
        s1 = (vol.get("volume_investigation") or {}).get("step1_test_setting") or {}
        raw = s1.get("raw_evidence") if isinstance(s1, dict) else None
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        baseline = ((vol.get("pre_test_volume") or {}).get("baseline") or {})
        raw = baseline.get("raw_evidence") if isinstance(baseline, dict) else None
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return _first_tag_evidence(ctx, "volume")


def _brightness_methodology_snapshots(ctx: dict[str, Any], rule_id: str = "") -> list[str]:
    """亮度说明快照：等级日志 + nits(DPC) 日志，按序去重。"""
    bri = ctx.get("game_brightness") or {}
    if not isinstance(bri, dict):
        return []
    inv = bri.get("brightness_investigation") or {}
    if "thermal" in rule_id:
        s5 = inv.get("step5_thermal_control") or {}
        if isinstance(s5, dict):
            for key in ("raw_evidence", "evidence"):
                raw = s5.get(key)
                if isinstance(raw, str) and raw.strip():
                    return [raw.strip()]
                if isinstance(raw, list) and raw:
                    return [str(raw[0]).strip()]
            hits = s5.get("hits") or s5.get("events") or []
            if isinstance(hits, list) and hits and isinstance(hits[0], dict):
                raw = hits[0].get("raw_evidence")
                if isinstance(raw, str) and raw.strip():
                    return [raw.strip()]
        return []

    s1 = inv.get("step1_test_setting") or {}
    if not isinstance(s1, dict):
        tag_ev = _first_tag_evidence(ctx, "brightness")
        return [tag_ev] if tag_ev else []

    out: list[str] = []

    def _add(raw: Any) -> None:
        if isinstance(raw, str) and raw.strip() and raw.strip() not in out:
            out.append(raw.strip())

    # 1) 等级快照：优先 BrightnessCollector，其次 Synchronizer（只保留一条）
    _add(s1.get("level_evidence"))
    if not out:
        for key in ("brightness_collector_last", "brightness_synchronizer_last"):
            block = s1.get(key) or {}
            if isinstance(block, dict):
                _add(block.get("raw_evidence"))
                if out:
                    break

    # 2) nits 快照：DisplayPowerController
    _add(s1.get("nits_evidence"))
    if not any("DisplayPowerController" in x for x in out):
        dpc = s1.get("display_power_controller_first") or {}
        if isinstance(dpc, dict):
            _add(dpc.get("raw_evidence"))
        raw = s1.get("raw_evidence")
        if isinstance(raw, str) and "DisplayPowerController" in raw:
            _add(raw)

    if not out:
        tag_ev = _first_tag_evidence(ctx, "brightness")
        if tag_ev:
            out.append(tag_ev)
    return out


def _brightness_methodology_snapshot(ctx: dict[str, Any], rule_id: str = "") -> str:
    snaps = _brightness_methodology_snapshots(ctx, rule_id)
    return snaps[0] if snaps else ""

def _brightness_aligned(ctx: dict[str, Any]) -> bool | None:
    bri = ctx.get("game_brightness") or {}
    s1 = ((bri.get("brightness_investigation") or {}).get("step1_test_setting") or {}) if isinstance(bri, dict) else {}
    if isinstance(s1, dict) and s1.get("aligned_with_standard") is not None:
        return bool(s1.get("aligned_with_standard"))
    pc = ctx.get("game_precondition") or {}
    tags = ((pc.get("test_conditions") or {}).get("tags") or []) if isinstance(pc, dict) else []
    for t in tags:
        if isinstance(t, dict) and t.get("id") == "brightness":
            st = str(t.get("status") or "")
            if st == "ok":
                return True
            if st in ("warn", "bad"):
                return False
    return None


def _volume_aligned(ctx: dict[str, Any]) -> bool | None:
    vol = ctx.get("game_volume") or {}
    s1 = ((vol.get("volume_investigation") or {}).get("step1_test_setting") or {}) if isinstance(vol, dict) else {}
    if isinstance(s1, dict) and s1.get("aligned_with_standard") is not None:
        return bool(s1.get("aligned_with_standard"))
    pc = ctx.get("game_precondition") or {}
    tags = ((pc.get("test_conditions") or {}).get("tags") or []) if isinstance(pc, dict) else []
    for t in tags:
        if isinstance(t, dict) and t.get("id") == "volume":
            st = str(t.get("status") or "")
            if st == "ok":
                return True
            if st in ("warn", "bad"):
                return False
            # 有目标与实测时可比较
            exp = t.get("expected_volume_index")
            act = t.get("numeric_volume_index")
            if exp is not None and act is not None:
                try:
                    return int(exp) == int(act)
                except (TypeError, ValueError):
                    pass
    return None


def _game_duration_seconds(ctx: dict[str, Any]) -> float | None:
    """读取 T_game / game_window 时长（秒）。"""
    for src in (ctx.get("game_time_window"), ctx.get("summary"), ctx.get("game_precondition")):
        if not isinstance(src, dict):
            continue
        gw = src.get("game_window")
        if isinstance(gw, dict) and gw.get("duration_seconds") is not None:
            try:
                return float(gw.get("duration_seconds"))
            except (TypeError, ValueError):
                pass
        tw = src.get("time_windows") or {}
        tg = tw.get("T_game") if isinstance(tw, dict) else None
        if isinstance(tg, dict) and tg.get("duration_seconds") is not None:
            try:
                return float(tg.get("duration_seconds"))
            except (TypeError, ValueError):
                pass
    return None


def _dual_duration_tolerance_seconds(ctx_a: dict[str, Any] | None = None) -> float:
    """双机时长容差（秒），优先读规则 thresholds。"""
    try:
        rules_path = Path(__file__).resolve().parent.parent / "references" / "cause-judgment-rules.yaml"
        if rules_path.is_file():
            from skill_references import load_reference_yaml  # noqa: WPS433

            doc = load_reference_yaml(rules_path)
            thr = (doc or {}).get("thresholds") or {}
            val = thr.get("dual_duration_tolerance_seconds")
            if val is not None:
                return float(val)
    except Exception:
        pass
    # 无 skill_references 时直接解析 YAML 中的阈值行
    try:
        rules_path = Path(__file__).resolve().parent.parent / "references" / "cause-judgment-rules.yaml"
        text = rules_path.read_text(encoding="utf-8")
        m = re.search(r"dual_duration_tolerance_seconds:\s*(\d+(?:\.\d+)?)", text)
        if m:
            return float(m.group(1))
    except Exception:
        pass
    meta = ((ctx_a or {}).get("report_meta") or {}) if isinstance(ctx_a, dict) else {}
    try:
        if meta.get("dual_duration_tolerance_seconds") is not None:
            return float(meta.get("dual_duration_tolerance_seconds"))
    except (TypeError, ValueError):
        pass
    return 60.0


def build_dual_duration_mismatch_finding(
    ctx_a: dict[str, Any],
    ctx_b: dict[str, Any],
    *,
    tolerance_seconds: float | None = None,
) -> dict[str, Any] | None:
    """双机 T_game 时长差超容差时返回 finding；否则 None。"""
    da = _game_duration_seconds(ctx_a)
    db = _game_duration_seconds(ctx_b)
    if da is None or db is None:
        return None
    tol = float(tolerance_seconds if tolerance_seconds is not None else _dual_duration_tolerance_seconds(ctx_a))
    diff = abs(da - db)
    if diff <= tol:
        return None
    return {
        "id": "log_duration_mismatch",
        "category_id": "test_methodology",
        "category_title": "测试手法不符",
        "subcategory": "日志不全",
        "label": "双机游戏场景测试时长不一致",
        "flow_step": 2,
        "priority": "P1",
        "triggered": True,
        "check_type": "dual_duration",
        "_match_ok": False,
        "_duration_a": da,
        "_duration_b": db,
        "_duration_diff": diff,
        "_duration_tolerance": tol,
        "detail": f"T_game 时长 {da:.0f}s vs {db:.0f}s（差 {diff:.0f}s，容差 {tol:.0f}s）",
    }


def _ensure_dual_duration_methodology_rows(
    rows_a: list[dict[str, Any]],
    rows_b: list[dict[str, Any]],
    ctx_a: dict[str, Any],
    ctx_b: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """向双机测试手法表注入「时长不一致」行。"""
    finding = build_dual_duration_mismatch_finding(ctx_a, ctx_b)
    if not finding:
        return rows_a, rows_b
    rid = "log_duration_mismatch"
    out_a = [dict(x) for x in rows_a if isinstance(x, dict) and str(x.get("id") or "") != rid]
    out_b = [dict(x) for x in rows_b if isinstance(x, dict) and str(x.get("id") or "") != rid]
    item_a = dict(finding)
    item_b = dict(finding)
    # 各侧说明用本机时长
    item_a["_side_duration"] = finding.get("_duration_a")
    item_b["_side_duration"] = finding.get("_duration_b")
    out_a.append(item_a)
    out_b.append(item_b)
    return out_a, out_b


def _ensure_brightness_volume_methodology_rows(
    triggered: list[dict[str, Any]],
    ctx: dict[str, Any],
) -> list[dict[str, Any]]:
    """测试手法表始终纳入亮度/音量行；相符时原因改为「亮度相同/音量相同」。"""
    rows = [dict(x) for x in triggered if isinstance(x, dict)]
    by_id = {str(x.get("id") or ""): x for x in rows}

    def _upsert(rule_id: str, *, aligned: bool | None, has_evidence: bool, mismatch_label: str, match_label: str) -> None:
        if not has_evidence and rule_id not in by_id:
            return
        item = by_id.get(rule_id) or {
            "id": rule_id,
            "category_id": "test_methodology",
            "triggered": True,
            "priority": "P1",
        }
        if aligned is True:
            item["label"] = match_label
            item["_match_ok"] = True
        else:
            item["label"] = mismatch_label
            item["_match_ok"] = False
        by_id[rule_id] = item

    bri_snap = _brightness_methodology_snapshot(ctx, "method_brightness_testcase")
    vol_snap = _volume_methodology_snapshot(ctx)
    _upsert(
        "method_brightness_testcase",
        aligned=_brightness_aligned(ctx),
        has_evidence=bool(bri_snap),
        mismatch_label="亮度大小不符",
        match_label="亮度相同",
    )
    _upsert(
        "method_volume_size",
        aligned=_volume_aligned(ctx),
        has_evidence=bool(vol_snap),
        mismatch_label="音量大小不符",
        match_label="音量相同",
    )

    # 保持原排序，亮度/音量若新建则插入日志类之后
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in _sort_methodology_findings(list(by_id.values())):
        rid = str(item.get("id") or "")
        if rid in seen:
            continue
        seen.add(rid)
        out.append(item)
    return out


def _methodology_cause_label(rule_id: str, item: dict[str, Any]) -> str:
    if item.get("_match_ok") is True:
        if rule_id.startswith("method_brightness"):
            return "亮度相同"
        if rule_id.startswith("method_volume"):
            return "音量相同"
    if item.get("label"):
        # 动态标签优先（已在 ensure 中改写）
        lab = str(item.get("label"))
        if lab in ("亮度相同", "音量相同", "亮度大小不符", "音量大小不符"):
            return lab
    return _METHODOLOGY_CAUSE_LABELS.get(rule_id) or str(item.get("label") or rule_id or "原因")


def _thermal_methodology_snapshot(ctx: dict[str, Any]) -> str:
    """优先取 tran_thermal_engine 且体现策略变化的行（gameMode / limits）。"""
    th = ctx.get("game_thermal") or {}
    if not isinstance(th, dict):
        return ""
    inv = th.get("thermal_investigation") or {}
    s1 = inv.get("step1_thermal_info") or {}
    events = s1.get("engine_events") if isinstance(s1, dict) else None
    if isinstance(events, list):
        # 优先 gameMode=1 的证据行
        for e in reversed(events):
            if not isinstance(e, dict):
                continue
            raw = e.get("raw_evidence")
            if not isinstance(raw, str) or not raw.strip():
                continue
            if e.get("game_mode") == 1 or "gameMode=1" in raw:
                return raw.strip()
        for e in reversed(events):
            if isinstance(e, dict) and isinstance(e.get("raw_evidence"), str):
                return str(e.get("raw_evidence")).strip()
    for path in (
        ("thermal_summary", "during_game"),
        ("temperature", "T_game"),
    ):
        node: Any = th
        for key in path:
            node = (node or {}).get(key) if isinstance(node, dict) else None
        if isinstance(node, dict):
            raw = node.get("raw_evidence")
            if isinstance(raw, str) and raw.strip():
                return raw.strip()
            if isinstance(raw, list) and raw:
                return str(raw[0]).strip()
    evidences: list[str] = []
    _collect_raw_evidence(th, evidences, limit=1)
    return evidences[0] if evidences else ""


def _download_methodology_snapshot(ctx: dict[str, Any]) -> str:
    snaps = _download_methodology_snapshots(ctx)
    return snaps[0] if snaps else ""


def _parse_mmdd_time(text: Any) -> datetime | None:
    s = str(text or "").strip()
    if not s:
        return None
    for fmt in ("%m-%d %H:%M:%S.%f", "%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s[:26], fmt)
        except ValueError:
            continue
    return None


def _fmt_brief_duration(seconds: float | None) -> str | None:
    if seconds is None:
        return None
    try:
        sec = float(seconds)
    except (TypeError, ValueError):
        return None
    if sec < 0:
        return None
    if sec < 60:
        return f"{sec:.0f}s" if sec >= 10 else f"{sec:.1f}s"
    mins = int(sec // 60)
    rem = int(round(sec % 60))
    return f"{mins}min{rem:02d}s" if rem else f"{mins}min"


def _game_identity(ctx: dict[str, Any]) -> tuple[str | None, str | None]:
    tw = ctx.get("game_time_window") or {}
    gw = tw.get("game_window") if isinstance(tw, dict) else {}
    if not isinstance(gw, dict) or not gw:
        gw = ((ctx.get("summary") or {}).get("game_window") or {}) if isinstance(ctx.get("summary"), dict) else {}
    name = None
    if isinstance(tw, dict):
        name = str(tw.get("game_name") or "").strip() or None
    if not name and isinstance(gw, dict):
        name = str(gw.get("game_name") or "").strip() or None
    pkg = str(gw.get("package") or "").strip() or None
    if not pkg and isinstance(ctx.get("summary"), dict):
        pkg = str(((ctx.get("summary") or {}).get("analysis_meta") or {}).get("game_package") or "").strip() or None
    meta = ctx.get("report_meta") or ctx.get("game_analysis_meta") or {}
    if isinstance(meta, dict):
        if not name:
            name = str(meta.get("game_title") or meta.get("game_name") or "").strip() or None
        if not pkg:
            pkg = str(meta.get("game_package") or "").strip() or None
    return name, pkg


def _download_event_rows(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    bg = ctx.get("game_background") or {}
    if not isinstance(bg, dict):
        return []
    s3 = ((bg.get("background_investigation") or {}).get("step3_background_download") or {})
    if not isinstance(s3, dict):
        return []
    rows: list[dict[str, Any]] = []
    for key in ("t_game_downloads", "t_game_gcloud", "downloads"):
        for item in s3.get(key) or []:
            if isinstance(item, dict):
                rows.append(item)
    return rows


def _download_methodology_snapshots(ctx: dict[str, Any], *, limit: int = 3) -> list[str]:
    out: list[str] = []
    for row in _download_event_rows(ctx):
        raw = row.get("raw_evidence") or row.get("line")
        if isinstance(raw, str) and raw.strip() and raw.strip() not in out:
            out.append(raw.strip())
        if len(out) >= limit:
            break
    if out:
        return out
    bg = ctx.get("game_background") or {}
    if isinstance(bg, dict):
        s3 = ((bg.get("background_investigation") or {}).get("step3_background_download") or {})
        note = s3.get("note") if isinstance(s3, dict) else None
        if isinstance(note, str) and note.strip():
            return [note.strip()]
    return []


def _background_download_brief(ctx: dict[str, Any]) -> str:
    """后台下载：应用 + 持续时长（优先 T_game 事件首末）。"""
    bg = ctx.get("game_background") or {}
    s3 = ((bg.get("background_investigation") or {}).get("step3_background_download") or {}) if isinstance(bg, dict) else {}
    if not isinstance(s3, dict):
        return "检测到后台下载行为"

    rows = _download_event_rows(ctx)
    pkgs: list[str] = []
    for row in rows:
        pkg = str(row.get("package") or row.get("pkg") or "").strip()
        if pkg and pkg not in pkgs:
            pkgs.append(pkg)
    game_name, game_pkg = _game_identity(ctx)
    is_gcloud = bool(s3.get("gcloud_tencent_download_during_game") or s3.get("t_game_gcloud_count"))
    if not pkgs and game_pkg and is_gcloud:
        pkgs = [game_pkg]

    app_label = ""
    if game_name and pkgs:
        app_label = f"{game_name}（{pkgs[0]}）"
    elif pkgs:
        app_label = pkgs[0]
    elif game_name:
        app_label = game_name
    elif is_gcloud:
        app_label = "腾讯游戏 GCloud"
    else:
        app_label = "未知应用"

    kind = " · GCloud下载" if is_gcloud else " · 后台下载"
    hit_n = s3.get("t_game_gcloud_count") if is_gcloud else s3.get("t_game_download_count")
    if hit_n is None:
        hit_n = s3.get("gcloud_count") if is_gcloud else s3.get("download_count")

    times = [_parse_mmdd_time(r.get("time")) for r in rows]
    times = [t for t in times if t is not None]
    dur_s = None
    if len(times) >= 2:
        dur_s = max((times[-1] - times[0]).total_seconds(), 0.0)
    dur_txt = _fmt_brief_duration(dur_s)

    bits = [f"{app_label}{kind}"]
    if dur_txt:
        bits.append(f"持续约{dur_txt}")
    if hit_n:
        bits.append(f"T_game命中{hit_n}次")
    return " · ".join(bits)


def _cpu_thermal_throttle_snapshot(ctx: dict[str, Any]) -> str:
    cpu = ctx.get("game_cpu_gpu_ddr") or {}
    if isinstance(cpu, dict):
        s5 = ((cpu.get("cpu_gpu_ddr_investigation") or {}).get("step5_thermal_throttle") or {})
        if isinstance(s5, dict):
            hits = s5.get("throttled_hits") or s5.get("hits") or []
            if isinstance(hits, list) and hits and isinstance(hits[0], dict):
                raw = hits[0].get("raw_evidence")
                if isinstance(raw, str) and raw.strip():
                    return raw.strip()
    return _thermal_methodology_snapshot(ctx)


_METHODOLOGY_CAUSE_LABELS: dict[str, str] = {
    "log_incomplete": "监测日志不完整",
    "log_no_logs": "无日志",
    "log_no_game_scene": "日志中不包含测试场景时间段",
    "log_scene_incomplete": "场景时段日志覆盖不全",
    "log_duration_short": "测试场景时长小于3min",
    "log_duration_mismatch": "双机游戏场景测试时长不一致",
    "method_brightness_testcase": "亮度大小不符",
    "method_brightness_thermal_dim": "触发温控降背光",
    "method_volume_size": "音量大小不符",
    "method_volume_channel": "音量通道不符",
    "method_cpu_thermal_throttle": "thermal导致的限频",
    "method_background_download": "后台下载行为",
    "precond_mismatch": "前置条件与测试用例标准不相符",
    "precond_auto_brightness_on": "自动背光被打开",
    "precond_network_wifi_uses_data": "WiFi场景使用数据",
    "precond_network_data_uses_wifi": "数据场景使用WiFi",
}


def _methodology_detail_text(rule_id: str, label: str, ctx: dict[str, Any]) -> str:
    """统一「说明/快照」：优先原始日志行，与日志不全同风格。"""
    if rule_id == "log_incomplete" or "监测日志不完整" in label or label == "日志不全":
        missing = _missing_logs_from_ctx(ctx)
        return "、".join(missing) if missing else "（未列出缺失日志名）"

    if rule_id == "log_no_logs" or label == "无日志":
        return "无 mobile 核心日志（kernel/main/sys/radio/event）且无 bugreport"

    if rule_id == "log_no_game_scene" or "不包含测试场景" in label or label == "日志无场景":
        tw = ctx.get("game_time_window") or {}
        status = tw.get("status") or (ctx.get("summary") or {}).get("status") or "—"
        return f"场景识别未得到满足要求的测试窗口（status={status}）"

    if rule_id == "log_scene_incomplete" or "场景时段日志覆盖不全" in label or label == "场景日志不全":
        missing = _scene_coverage_missing_from_ctx(ctx)
        return (
            "T_game 时段缺少覆盖：" + "、".join(missing)
            if missing
            else "T_game 时段存在日志覆盖缺口"
        )

    if rule_id == "log_duration_short" or "小于3min" in label:
        gw = (ctx.get("game_time_window") or {}).get("game_window") or {}
        if not gw:
            gw = (ctx.get("summary") or {}).get("game_window") or {}
        dur = gw.get("duration_seconds") if isinstance(gw, dict) else None
        return f"游戏场景时长 {dur}s（阈值 180s）" if dur is not None else "游戏场景时长不足 3min"

    if rule_id == "log_duration_mismatch" or "双机游戏场景测试时长不一致" in label:
        dur = _game_duration_seconds(ctx)
        if dur is not None:
            return f"T_game 时长 {dur:.0f}s（双机不一致）"
        return "双机 T_game 时长不一致"

    raw = ""
    raw_lines: list[str] = []
    if rule_id.startswith("method_volume"):
        raw = _volume_methodology_snapshot(ctx)
    elif rule_id.startswith("method_brightness"):
        raw_lines = _brightness_methodology_snapshots(ctx, rule_id)
        raw = raw_lines[0] if raw_lines else ""
    elif rule_id == "method_cpu_thermal_throttle":
        raw = _cpu_thermal_throttle_snapshot(ctx)
    elif rule_id == "method_background_download":
        raw = _download_methodology_snapshot(ctx)
    elif rule_id.startswith("precond_"):
        if "brightness" in rule_id or rule_id == "precond_auto_brightness_on":
            raw_lines = _brightness_methodology_snapshots(ctx)
            raw = raw_lines[0] if raw_lines else ""
        elif "volume" in rule_id:
            raw = _volume_methodology_snapshot(ctx)
        else:
            raw = _first_tag_evidence(ctx, "brightness") or _first_tag_evidence(ctx, "volume")

    if raw or raw_lines:
        # 亮度：说明中带上等级 + nits，并同时保留等级日志与 DPC nits 日志
        if rule_id.startswith("method_brightness") and "thermal" not in rule_id:
            bri = ctx.get("game_brightness") or {}
            s1 = ((bri.get("brightness_investigation") or {}).get("step1_test_setting") or {}) if isinstance(bri, dict) else {}
            level = s1.get("brightness_level") if isinstance(s1, dict) else None
            nits = s1.get("measured_nits") if isinstance(s1, dict) else None
            head_bits: list[str] = []
            if level is not None:
                head_bits.append(f"等级={level}")
            if nits is not None:
                try:
                    head_bits.append(f"nits={float(nits):g}")
                except (TypeError, ValueError):
                    head_bits.append(f"nits={nits}")
            snaps = raw_lines or ([raw] if raw else [])
            body = "\n".join(_display_log_snapshot(s) for s in snaps if s)
            if head_bits:
                return " · ".join(head_bits) + "\n" + body
            return body or "—"
        return _display_log_snapshot(raw) if raw else "—"

    # 兜底：从关联步骤抽一条 raw_evidence
    ev = collect_cause_evidence({"id": rule_id, "label": label, "category_id": "test_methodology"}, ctx)
    snaps = ev.get("snapshots") or []
    if snaps:
        return _display_log_snapshot(str(snaps[0]))
    return "—"


def _feature_difference_detail_text(item: dict[str, Any], ctx: dict[str, Any]) -> str:
    """功能差异：一句话 +（可选）一条相关日志。"""
    summary, snaps = _feature_difference_summary_and_snaps(item, ctx)
    if snaps:
        return f"{summary}\n{snaps[0]}"
    return summary


def _feature_difference_summary_and_snaps(
    item: dict[str, Any],
    ctx: dict[str, Any],
) -> tuple[str, list[str]]:
    """返回 (单元格说明, 日志快照列表)。"""
    if item.get("_missing"):
        return "日志未搜到", []
    label = str(item.get("label") or item.get("id") or "功能")
    detail = str(item.get("detail") or "")
    sample = ""
    matched = ""
    if " || " in detail:
        matched, sample = detail.split(" || ", 1)
    elif detail.startswith("命中关键词"):
        matched = detail
    else:
        matched = f"日志命中「{label}」相关特征"

    if not sample.strip():
        kws: list[str] = []
        if "命中关键词：" in matched:
            kws = [
                x.strip()
                for x in matched.split("命中关键词：", 1)[-1].replace("、", ",").split(",")
                if x.strip()
            ]
        texts: list[str] = []
        for key, val in ctx.items():
            if key.startswith("game_") or key == "summary":
                _collect_raw_from_ctx(val, texts, limit=80)
        for line in texts:
            if kws and any(kw in line for kw in kws):
                sample = line
                break
            if not kws and label and label in line:
                sample = line
                break

    summary = matched if matched.startswith("命中") else f"日志命中「{label}」相关特征"
    snaps: list[str] = []
    if sample.strip():
        disp = _display_aal_log_snapshot(sample.strip())
        if disp:
            snaps.append(disp)
    return summary, snaps


def _collect_raw_from_ctx(obj: Any, out: list[str], *, limit: int = 40) -> None:
    if len(out) >= limit:
        return
    if isinstance(obj, dict):
        raw = obj.get("raw_evidence")
        if isinstance(raw, str) and raw.strip():
            out.append(raw.strip())
        elif isinstance(raw, list):
            for item in raw:
                if len(out) >= limit:
                    return
                if isinstance(item, str) and item.strip():
                    out.append(item.strip())
        for key, val in obj.items():
            if key == "raw_evidence":
                continue
            _collect_raw_from_ctx(val, out, limit=limit)
            if len(out) >= limit:
                return
    elif isinstance(obj, list):
        for item in obj:
            _collect_raw_from_ctx(item, out, limit=limit)
            if len(out) >= limit:
                return


def format_feature_difference_table_html(
    triggered: list[dict[str, Any]],
    ctx: dict[str, Any],
) -> str:
    """功能差异：两列表格（功能 | 说明）；快照默认折叠。"""
    rows = [x for x in triggered if isinstance(x, dict)]
    if not rows:
        return '<p style="margin:3px 0 0;font-size:13px;color:var(--color-text-tertiary);">未发现明显问题</p>'

    body: list[str] = []
    for item in rows:
        label = str(item.get("label") or item.get("id") or "功能")
        summary, snaps = _feature_difference_summary_and_snaps(item, ctx)
        snap_html = _methodology_snap_details_html(label_a="本机", snaps_a=snaps)
        body.append(
            f'<tr><td class="cause">{_esc(label)}</td>'
            f'<td class="detail">{_esc(summary)}'
            f'{f"<div style=\"margin-top:4px;\">{snap_html}</div>" if snap_html else ""}'
            f"</td></tr>"
        )

    return (
        '<table class="cause-table methodology-table">'
        "<thead><tr><th>功能</th><th>说明</th></tr></thead>"
        f"<tbody>{''.join(body)}</tbody></table>"
    )


def format_feature_difference_compare_table_html(
    triggered_a: list[dict[str, Any]],
    ctx_a: dict[str, Any],
    triggered_b: list[dict[str, Any]],
    ctx_b: dict[str, Any],
    *,
    label_a: str = "测试机",
    label_b: str = "对比机",
) -> str:
    """双机功能差异：功能 | 机型A | 机型B；每行下方折叠日志快照。"""
    rows_a = [x for x in triggered_a if isinstance(x, dict)]
    rows_b = [x for x in triggered_b if isinstance(x, dict)]
    by_a = {str(x.get("id") or ""): x for x in rows_a if str(x.get("id") or "")}
    by_b = {str(x.get("id") or ""): x for x in rows_b if str(x.get("id") or "")}
    ordered_ids: list[str] = []
    seen: set[str] = set()
    for item in rows_a + rows_b:
        rid = str(item.get("id") or "")
        if not rid or rid in seen:
            continue
        seen.add(rid)
        ordered_ids.append(rid)
    if not ordered_ids:
        return '<p style="margin:3px 0 0;font-size:13px;color:var(--color-text-tertiary);">未发现明显问题</p>'

    body: list[str] = []
    for rid in ordered_ids:
        ia = by_a.get(rid)
        ib = by_b.get(rid)
        if ia is None and ib is None:
            continue
        if ia is None:
            ia = dict(ib or {})
            ia["_missing"] = True
        if ib is None:
            ib = dict(ia or {})
            ib["_missing"] = True
        feature = str(
            (ia.get("label") if not ia.get("_missing") else None)
            or (ib.get("label") if not ib.get("_missing") else None)
            or ia.get("label")
            or ib.get("label")
            or rid
            or "功能"
        )
        sa, snaps_a = _feature_difference_summary_and_snaps(ia, ctx_a)
        sb, snaps_b = _feature_difference_summary_and_snaps(ib, ctx_b)
        snap_html = _methodology_snap_details_html(
            label_a=label_a,
            snaps_a=snaps_a,
            label_b=label_b,
            snaps_b=snaps_b,
        )
        body.append(
            f"<tr>"
            f'<td class="cause">{_esc(feature)}</td>'
            f'<td class="detail">{_esc(sa)}</td>'
            f'<td class="detail">{_esc(sb)}</td>'
            f"</tr>"
        )
        if snap_html:
            body.append(
                f'<tr class="methodology-snap-row">'
                f'<td colspan="3" style="padding-top:0;border-bottom:0.5px solid var(--color-border-tertiary);">'
                f"{snap_html}</td></tr>"
            )

    return (
        '<table class="cause-table methodology-table methodology-compare">'
        "<thead><tr>"
        f"<th>功能</th><th>{_esc(label_a)}</th><th>{_esc(label_b)}</th>"
        "</tr></thead>"
        f"<tbody>{''.join(body)}</tbody></table>"
    )


def _methodology_plain_summary(rule_id: str, label: str, ctx: dict[str, Any], *, item: dict[str, Any] | None = None) -> str:
    """测试手法单元格：最简中文结论，不含日志快照。"""
    it = item or {}
    if it.get("_missing"):
        return "日志未搜到"
    if it.get("_match_ok") is True:
        if rule_id.startswith("method_brightness"):
            return "亮度与用例相符"
        if rule_id.startswith("method_volume"):
            return "音量与用例相符"
        return "相符"

    if rule_id == "log_incomplete" or "监测日志不完整" in label or label == "日志不全":
        missing = _missing_logs_from_ctx(ctx)
        return ("缺少：" + "、".join(missing[:6])) if missing else "监测日志不完整"

    if rule_id == "log_no_logs" or label == "无日志":
        return "无核心日志"

    if rule_id == "log_no_game_scene" or "不包含测试场景" in label:
        return "未识别到有效游戏场景时段"

    if rule_id == "log_scene_incomplete" or "场景时段日志覆盖不全" in label:
        missing = _scene_coverage_missing_from_ctx(ctx)
        return ("场景日志缺：" + "、".join(missing[:4])) if missing else "场景时段日志覆盖不全"

    if rule_id == "log_duration_short" or "小于3min" in label:
        gw = (ctx.get("game_time_window") or {}).get("game_window") or {}
        if not gw:
            gw = (ctx.get("summary") or {}).get("game_window") or {}
        dur = gw.get("duration_seconds") if isinstance(gw, dict) else None
        if dur is not None:
            try:
                return f"时长 {float(dur):.0f}s（不足3min）"
            except (TypeError, ValueError):
                return f"时长 {dur}s（不足3min）"
        return "场景时长不足3min"

    if rule_id == "log_duration_mismatch" or "双机游戏场景测试时长不一致" in label:
        side = it.get("_side_duration")
        if side is None:
            side = _game_duration_seconds(ctx)
        if side is not None:
            try:
                return f"T_game 时长 {float(side):.0f}s"
            except (TypeError, ValueError):
                return f"T_game 时长 {side}s"
        detail = str(it.get("detail") or "").strip()
        return detail or "双机 T_game 时长不一致"

    if rule_id.startswith("method_brightness") and "thermal" not in rule_id:
        bri = ctx.get("game_brightness") or {}
        s1 = ((bri.get("brightness_investigation") or {}).get("step1_test_setting") or {}) if isinstance(bri, dict) else {}
        level = s1.get("brightness_level") if isinstance(s1, dict) else None
        nits = s1.get("measured_nits") if isinstance(s1, dict) else None
        expected = s1.get("expected_level") if isinstance(s1, dict) else None
        bits: list[str] = []
        if level is not None:
            bits.append(f"等级{level}")
        if nits is not None:
            try:
                nf = float(nits)
                bits.append(f"{int(round(nf))}nit" if abs(nf - round(nf)) < 0.05 else f"{nf:.1f}nit")
            except (TypeError, ValueError):
                bits.append(f"{nits}nit")
        if expected is not None:
            bits.append(f"目标{expected}")
        return "，".join(bits) if bits else "亮度与用例不符"

    if rule_id == "method_brightness_thermal_dim":
        bri = ctx.get("game_brightness") or {}
        s5 = ((bri.get("brightness_investigation") or {}).get("step5_thermal_control") or {}) if isinstance(bri, dict) else {}
        if isinstance(s5, dict) and (s5.get("triggered") or s5.get("relevant_hits")):
            hits = [h for h in (s5.get("relevant_hits") or []) if isinstance(h, dict)]
            nits = next((h.get("brightness_nits") for h in hits if h.get("brightness_nits") is not None), None)
            if nits is not None:
                try:
                    return f"已触发温控降背光（{float(nits):g}nit）"
                except (TypeError, ValueError):
                    return f"已触发温控降背光（{nits}nit）"
            return "已触发温控降背光"
        return "未见温控降背光"

    if rule_id.startswith("method_volume"):
        vol = ctx.get("game_volume") or {}
        s1 = ((vol.get("volume_investigation") or {}).get("step1_test_setting") or {}) if isinstance(vol, dict) else {}
        idx = s1.get("index") if isinstance(s1, dict) else None
        if idx is None:
            base = ((vol.get("pre_test_volume") or {}).get("baseline") or {}) if isinstance(vol, dict) else {}
            idx = base.get("index") if isinstance(base, dict) else None
        expected = s1.get("expected_index") if isinstance(s1, dict) else None
        bits = []
        if idx is not None:
            bits.append(f"档位{idx}")
        if expected is not None:
            bits.append(f"目标{expected}")
        if rule_id == "method_volume_channel":
            return "音量通道不符" + (f"（{'，'.join(bits)}）" if bits else "")
        return "，".join(bits) if bits else "音量与用例不符"

    if rule_id == "method_cpu_thermal_throttle":
        th = ctx.get("game_thermal") or {}
        during = ((th.get("thermal_summary") or {}).get("during_game") or {}) if isinstance(th, dict) else {}
        if during.get("freq_throttle"):
            tr = th.get("thermal_report") or {}
            tmax = tr.get("temp_max_c") if isinstance(tr, dict) else None
            if tmax is not None:
                try:
                    return f"已触发温控限频（最高约{float(tmax):.1f}℃）"
                except (TypeError, ValueError):
                    return f"已触发温控限频（最高约{tmax}℃）"
            return "已触发温控限频"
        return "未见温控限频"

    if rule_id == "method_background_download":
        return _background_download_brief(ctx)

    if rule_id == "precond_auto_brightness_on":
        return "自动背光处于开启"
    if rule_id == "precond_network_wifi_uses_data":
        return "WiFi场景实际走了数据网络"
    if rule_id == "precond_network_data_uses_wifi":
        return "数据场景实际走了WiFi"

    if rule_id == "precond_mismatch" or "前置条件" in label:
        pc = ctx.get("game_precondition") or {}
        tags = ((pc.get("test_conditions") or {}).get("tags") or []) if isinstance(pc, dict) else []
        bad: list[str] = []
        for t in tags:
            if not isinstance(t, dict):
                continue
            st = str(t.get("status") or "")
            if st in ("warn", "bad"):
                name = str(t.get("label") or t.get("id") or "").strip()
                if name:
                    bad.append(name)
        if bad:
            return "未对齐：" + "、".join(bad[:4])
        detail = str(it.get("detail") or "").strip()
        if detail and "BrightnessEvent" not in detail and len(detail) < 80:
            return detail
        return "前置条件与用例标准不相符"

    # 兜底：用 detail 首句，去掉日志味
    detail = str(it.get("detail") or "").strip()
    if detail:
        first = detail.split("\n", 1)[0].strip()
        first = first.replace("✓", "").replace("✗", "").strip()
        if first and "BrightnessEvent" not in first and "raw_evidence" not in first and len(first) <= 60:
            return first
    return str(label or "已命中").strip() or "已命中"


def _methodology_snapshot_lines(
    rule_id: str,
    label: str,
    ctx: dict[str, Any],
    *,
    item: dict[str, Any] | None = None,
    limit: int = 3,
) -> list[str]:
    """测试手法日志快照（仅原始行，不含说明摘要）。"""
    it = item or {}
    if it.get("_missing"):
        return []

    raw_lines: list[str] = []
    if rule_id in ("log_incomplete", "log_no_logs", "log_no_game_scene", "log_scene_incomplete"):
        raw_lines = _log_inventory_methodology_snapshots(ctx, rule_id=rule_id, limit=limit)
    elif rule_id.startswith("method_volume"):
        raw = _volume_methodology_snapshot(ctx)
        if raw:
            raw_lines = [raw]
    elif rule_id.startswith("method_brightness"):
        raw_lines = _brightness_methodology_snapshots(ctx, rule_id)
    elif rule_id == "method_cpu_thermal_throttle":
        raw = _cpu_thermal_throttle_snapshot(ctx)
        if raw:
            raw_lines = [raw]
    elif rule_id == "method_background_download":
        raw_lines = _download_methodology_snapshots(ctx, limit=limit)
    elif rule_id.startswith("precond_"):
        if "brightness" in rule_id or rule_id == "precond_auto_brightness_on" or rule_id == "precond_mismatch":
            raw_lines = _brightness_methodology_snapshots(ctx)
            if not raw_lines:
                tag_ev = _first_tag_evidence(ctx, "brightness")
                if tag_ev:
                    raw_lines = [tag_ev]
        elif "volume" in rule_id:
            raw = _volume_methodology_snapshot(ctx)
            if raw:
                raw_lines = [raw]
        else:
            for tag_id in ("brightness", "volume", "wifi", "network"):
                tag_ev = _first_tag_evidence(ctx, tag_id)
                if tag_ev:
                    raw_lines = [tag_ev]
                    break

    if not raw_lines:
        # 兜底：从关联步骤抽 raw_evidence
        ev = collect_cause_evidence(
            {"id": rule_id, "label": label, "category_id": "test_methodology"},
            ctx,
        )
        for s in ev.get("snapshots") or []:
            if not s or not str(s).strip():
                continue
            # 日志不全类：过滤显示相关噪声
            if rule_id.startswith("log_") and _is_display_related_snapshot(str(s)):
                continue
            raw_lines.append(str(s).strip())
            if len(raw_lines) >= limit:
                break

    out: list[str] = []
    for line in raw_lines[:limit]:
        if rule_id.startswith("log_") and _is_display_related_snapshot(str(line)):
            continue
        disp = _display_log_snapshot(str(line))
        if disp and disp not in out:
            out.append(disp)
    return out


def _is_display_related_snapshot(line: str) -> bool:
    s = str(line or "").lower()
    markers = (
        "displaypowercontroller",
        "brightnessevent",
        "hwc_log",
        "transsionaal",
        "aal_",
        "backlight",
        "nits=",
        "brightness=",
        "autobacklight",
    )
    return any(m in s for m in markers)


def _log_inventory_methodology_snapshots(
    ctx: dict[str, Any],
    *,
    rule_id: str = "log_incomplete",
    limit: int = 3,
) -> list[str]:
    """监测日志不全：只展示清单/路径证据，不含显示类日志。"""
    out: list[str] = []
    inv: dict[str, Any] = {}
    for src_name in ("summary", "game_time_window"):
        src = ctx.get(src_name) or {}
        if isinstance(src, dict) and isinstance(src.get("log_inventory"), dict):
            inv = src["log_inventory"]
            break
    if inv:
        miss = [str(x) for x in (inv.get("missing_for_report") or []) if str(x).strip()]
        if miss:
            out.append("缺失：" + "、".join(miss[:8]))
        elif inv.get("incomplete"):
            out.append("监测日志不完整（见 log_inventory）")
        br = str(inv.get("bugreport") or "")
        if br:
            out.append(f"bugreport={br}")
        files = inv.get("bugreport_files") or []
        if isinstance(files, list) and files:
            out.append(f"bugreport文件：{Path(str(files[0])).name}")
        core_miss = [str(x) for x in (inv.get("mobile_core_missing") or []) if str(x).strip()]
        if core_miss and rule_id in ("log_incomplete", "log_no_logs"):
            out.append("核心缺失：" + "、".join(core_miss[:5]))
        scene_miss = [str(x) for x in (inv.get("scene_coverage_missing") or []) if str(x).strip()]
        if scene_miss and rule_id in ("log_scene_incomplete", "log_no_game_scene"):
            out.append("场景覆盖缺：" + "、".join(scene_miss[:5]))

    # 补充：log_availability 中 missing 项
    summary = ctx.get("summary") or {}
    avail = summary.get("log_availability") if isinstance(summary, dict) else None
    if isinstance(avail, dict) and len(out) < limit:
        bad = [
            f"{k}={v}"
            for k, v in avail.items()
            if str(v).lower() in ("missing", "absent", "none", "false", "0")
        ]
        if bad:
            line = "可用性：" + "、".join(bad[:6])
            if line not in out:
                out.append(line)

    # 最后兜底：从 summary/time_window 抽非显示 raw_evidence
    if len(out) < limit:
        for src_name in ("game_time_window", "summary"):
            data = ctx.get(src_name) or {}
            if not isinstance(data, dict):
                continue
            tmp: list[str] = []
            _collect_raw_evidence(data, tmp, limit=12)
            for line in tmp:
                if _is_display_related_snapshot(line):
                    continue
                # 跳过仅有 file:lineno 无正文的噪声
                s = str(line).strip()
                if re.fullmatch(r"[\w.\-]+\.(?:txt|curf|log):\d+\s*", s):
                    continue
                if s and s not in out:
                    out.append(s)
                if len(out) >= limit:
                    break
            if len(out) >= limit:
                break
    return out[:limit]


def _methodology_snap_details_html(
    *,
    label_a: str,
    snaps_a: list[str],
    label_b: str | None = None,
    snaps_b: list[str] | None = None,
) -> str:
    """每条原因下方默认折叠的日志快照。"""
    snaps_b = snaps_b or []
    if not snaps_a and not snaps_b:
        return ""
    n_a, n_b = len(snaps_a), len(snaps_b)

    def _block(title: str, snaps: list[str]) -> str:
        if not snaps:
            return (
                f'<div><p style="margin:0 0 4px;font-size:11px;font-weight:600;'
                f'color:var(--color-text-secondary);">{_esc(title)}</p>'
                f'<p style="margin:0;font-size:11px;color:var(--color-text-tertiary);">无快照</p></div>'
            )
        body = "".join(
            f'<pre style="margin:0 0 4px;white-space:pre-wrap;word-break:break-all;'
            f'font-size:10px;line-height:1.4;color:var(--color-text-secondary);">{_esc(s)}</pre>'
            for s in snaps[:4]
        )
        return (
            f'<div><p style="margin:0 0 4px;font-size:11px;font-weight:600;'
            f'color:var(--color-text-secondary);">{_esc(title)}（{len(snaps)}）</p>{body}</div>'
        )

    if label_b is not None:
        summary = f"日志快照（{_esc(label_a)} {n_a} · {_esc(label_b)} {n_b}）· 默认隐藏，点击展开"
        inner = (
            f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:6px;">'
            f'{_block(label_a, snaps_a)}{_block(label_b, snaps_b)}</div>'
        )
    else:
        summary = f"日志快照（{n_a}）· 默认隐藏，点击展开"
        inner = f'<div style="margin-top:6px;">{_block(label_a, snaps_a)}</div>'

    return (
        f'<details style="margin:2px 0 6px;">'
        f'<summary style="cursor:pointer;font-size:11px;color:var(--color-text-tertiary);">{summary}</summary>'
        f'<div style="margin-top:6px;padding:8px 10px;background:var(--color-background-secondary);'
        f'border-radius:var(--border-radius-md);">{inner}</div></details>'
    )


def format_test_methodology_table_html(
    triggered: list[dict[str, Any]],
    ctx: dict[str, Any],
) -> str:
    """测试手法不符：两列表格（原因 | 简要说明）；快照默认折叠在每行下方。"""
    rows = _ensure_brightness_volume_methodology_rows(triggered, ctx)
    if not rows:
        return '<p style="margin:3px 0 0;font-size:13px;color:var(--color-text-tertiary);">未发现明显问题</p>'

    body: list[str] = []
    for item in rows:
        rule_id = str(item.get("id") or "")
        label = _methodology_cause_label(rule_id, item)
        right = _methodology_plain_summary(rule_id, label, ctx, item=item)
        snaps = _methodology_snapshot_lines(rule_id, label, ctx, item=item)
        snap_html = _methodology_snap_details_html(label_a="本机", snaps_a=snaps)
        body.append(
            f'<tr><td class="cause">{_esc(label)}</td>'
            f'<td class="detail">{_esc(right)}'
            f'{f"<div style=\"margin-top:4px;\">{snap_html}</div>" if snap_html else ""}'
            f"</td></tr>"
        )

    return (
        '<table class="cause-table methodology-table">'
        "<thead><tr><th>原因</th><th>说明</th></tr></thead>"
        f"<tbody>{''.join(body)}</tbody></table>"
    )


def format_test_methodology_compare_table_html(
    triggered_a: list[dict[str, Any]],
    ctx_a: dict[str, Any],
    triggered_b: list[dict[str, Any]],
    ctx_b: dict[str, Any],
    *,
    label_a: str = "测试机",
    label_b: str = "对比机",
) -> str:
    """双机测试手法：原因 | 机型A | 机型B；每行下方折叠日志快照。"""
    rows_a = _ensure_brightness_volume_methodology_rows(triggered_a, ctx_a)
    rows_b = _ensure_brightness_volume_methodology_rows(triggered_b, ctx_b)
    rows_a, rows_b = _ensure_dual_duration_methodology_rows(rows_a, rows_b, ctx_a, ctx_b)
    by_a = {str(x.get("id") or ""): x for x in rows_a if str(x.get("id") or "")}
    by_b = {str(x.get("id") or ""): x for x in rows_b if str(x.get("id") or "")}
    ordered_ids: list[str] = []
    seen: set[str] = set()
    for item in _sort_methodology_findings(rows_a + rows_b):
        rid = str(item.get("id") or "")
        if not rid or rid in seen:
            continue
        seen.add(rid)
        ordered_ids.append(rid)
    if not ordered_ids:
        return '<p style="margin:3px 0 0;font-size:13px;color:var(--color-text-tertiary);">未发现明显问题</p>'

    body: list[str] = []
    for rid in ordered_ids:
        ia = by_a.get(rid) or {"id": rid, "_missing": True, "label": _METHODOLOGY_CAUSE_LABELS.get(rid, rid)}
        ib = by_b.get(rid) or {"id": rid, "_missing": True, "label": _METHODOLOGY_CAUSE_LABELS.get(rid, rid)}
        if rid not in by_a:
            ia = dict(ib)
            ia["_missing"] = True
        if rid not in by_b:
            ib = dict(ia)
            ib["_missing"] = True
        cause = _methodology_cause_label(rid, ia if not ia.get("_missing") else ib)
        if ia.get("_match_ok") is True and ib.get("_match_ok") is True:
            cause = _methodology_cause_label(rid, ia)
        elif ia.get("_match_ok") is False or ib.get("_match_ok") is False:
            cause = _methodology_cause_label(
                rid,
                ia if ia.get("_match_ok") is False else ib,
            )
        sa = _methodology_plain_summary(rid, cause, ctx_a, item=ia)
        sb = _methodology_plain_summary(rid, cause, ctx_b, item=ib)
        snaps_a = _methodology_snapshot_lines(rid, cause, ctx_a, item=ia)
        snaps_b = _methodology_snapshot_lines(rid, cause, ctx_b, item=ib)
        snap_html = _methodology_snap_details_html(
            label_a=label_a,
            snaps_a=snaps_a,
            label_b=label_b,
            snaps_b=snaps_b,
        )
        body.append(
            f'<tr>'
            f'<td class="cause">{_esc(cause)}</td>'
            f'<td class="detail">{_esc(sa)}</td>'
            f'<td class="detail">{_esc(sb)}</td>'
            f"</tr>"
        )
        if snap_html:
            body.append(
                f'<tr class="methodology-snap-row">'
                f'<td colspan="3" style="padding-top:0;border-bottom:0.5px solid var(--color-border-tertiary);">'
                f"{snap_html}</td></tr>"
            )

    return (
        '<table class="cause-table methodology-table methodology-compare">'
        "<thead><tr>"
        f"<th>原因</th><th>{_esc(label_a)}</th><th>{_esc(label_b)}</th>"
        "</tr></thead>"
        f"<tbody>{''.join(body)}</tbody></table>"
    )


def format_category_links_html(step_links: list[dict[str, Any]]) -> str:
    if not step_links:
        return ""
    bits = []
    for link in step_links:
        bits.append(
            f'<a href="{_esc(link.get("html"))}" style="font-size:11px;margin-right:10px;">'
            f'{_esc(link.get("title"))}报告</a>'
        )
    return (
        '<div style="margin:6px 0 8px;font-size:11px;color:var(--color-text-tertiary);">'
        f'关联子报告：{"".join(bits)}</div>'
    )
