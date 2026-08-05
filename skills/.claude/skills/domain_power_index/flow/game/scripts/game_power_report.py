"""从 game_power_compare_summary.json 生成 HTML 仪表板报告。"""
from __future__ import annotations

import html
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

def _setup_utf8_stdio() -> None:
    for name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

_GTW_SCRIPTS = Path(__file__).resolve().parents[1] / "game_time_window" / "scripts"
if str(_GTW_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_GTW_SCRIPTS))
from game_time_window_lib import load_game_name  # noqa: E402
from brightness_summary_bridge import brightness_kpi_from_stats  # noqa: E402


def _esc(val: Any) -> str:
    return html.escape(str(val) if val is not None else "")


def _fmt_duration(seconds: int) -> str:
    m, s = divmod(max(0, int(seconds)), 60)
    return f"{m}:{s:02d}"


def _priority_class(p: str) -> str:
    p = (p or "").upper()
    if p.startswith("P0"):
        return "p0"
    if p.startswith("P1"):
        return "p1"
    return "p2"


def _tag_class(status: str) -> str:
    return {"ok": "tag-ok", "warn": "tag-warn", "bad": "tag-bad"}.get(status, "tag-unknown")


def _build_suggestions(summary: dict[str, Any]) -> list[dict[str, str]]:
    existing = summary.get("optimization_suggestions") or []
    if existing:
        return existing
    out: list[dict[str, str]] = []
    for item in (summary.get("top_background_packages") or [])[:8]:
        pkg = item.get("package_or_process", "")
        br = item.get("boost_ratio")
        prio = item.get("priority", "P2")
        cats = ", ".join(item.get("categories") or [])
        issue = f"{pkg} 游戏时段高频活动"
        if br:
            issue += f"（boost_ratio={br}）"
        if cats:
            issue += f" [{cats}]"
        out.append(
            {
                "priority": prio,
                "issue": issue,
                "suggestion": "排查后台唤醒/绑定/服务拉起，必要时冻结或延长心跳",
                "benefit": item.get("power_estimate_mws") or "待量化",
            }
        )
    return out


def _brightness_overview(brightness_stats: dict[str, Any]) -> dict[str, Any]:
    """步骤 3：kernel LCM 主结论 + hwcomposer 补充 min/max。"""
    baseline = brightness_stats.get("baseline_before_game") or {}
    gw = brightness_stats.get("game_window") or {}
    hwc = brightness_stats.get("hwcomposer") or {}
    hw_gw = hwc.get("game_window") or {}
    hw_base = hwc.get("baseline_before_game") or {}

    lvl_min = gw.get("level_min_raw", gw.get("level_min"))
    lvl_max = gw.get("level_max_raw", gw.get("level_max"))
    pct_min = gw.get("level_min_pct")
    pct_max = gw.get("level_max_pct")
    base_lvl = baseline.get("level")
    base_pct = baseline.get("level_pct")

    hw_min = hw_gw.get("brightness_val_min")
    hw_max = hw_gw.get("brightness_val_max")
    hw_pct_min = hw_gw.get("brightness_val_min_pct") or hw_gw.get("brightness_ratio_min_pct")
    hw_pct_max = hw_gw.get("brightness_val_max_pct") or hw_gw.get("brightness_ratio_max_pct")

    val_parts: list[str] = []
    if lvl_min is not None and lvl_max is not None:
        val_parts.append(f"LCM {lvl_min}~{lvl_max}" if lvl_min != lvl_max else f"LCM {lvl_min}")
    if hw_min is not None and hw_max is not None:
        val_parts.append(
            f"HWC {hw_min}~{hw_max}" if hw_min != hw_max else f"HWC {hw_min}"
        )
    val = " | ".join(val_parts) if val_parts else "N/A"

    sub_parts: list[str] = []
    if lvl_min is not None and lvl_max is not None:
        if pct_min is not None and pct_max is not None and lvl_min != lvl_max:
            sub_parts.append(f"LCM {pct_min}%~{pct_max}%")
        elif pct_min is not None:
            sub_parts.append(f"LCM {pct_min}%")
        if base_lvl is not None:
            sub_parts.append(f"LCM基线 {base_lvl}")
    if hw_min is not None and hw_max is not None:
        if hw_pct_min is not None and hw_pct_max is not None:
            sub_parts.append(f"HWC {hw_pct_min}%~{hw_pct_max}%")
        if hw_base.get("brightness_val") is not None:
            sub_parts.append(f"HWC基线 {hw_base['brightness_val']}")
    sub = " · ".join(sub_parts) if sub_parts else brightness_stats.get("coverage", "missing")

    evidence: list[str] = []
    if baseline.get("raw_evidence"):
        evidence.append(f"[LCM 基线] {baseline['raw_evidence']}")
    min_s = gw.get("level_min_sample") or {}
    max_s = gw.get("level_max_sample") or {}
    if min_s.get("raw_evidence"):
        evidence.append(f"[LCM 最低 {min_s.get('level')}] {min_s['raw_evidence']}")
    if max_s.get("raw_evidence") and max_s.get("raw_evidence") != min_s.get("raw_evidence"):
        evidence.append(f"[LCM 最高 {max_s.get('level')}] {max_s['raw_evidence']}")
    if gw.get("changed") and gw.get("transition_count"):
        evidence.append(f"LCM T_game 有效变光 {gw['transition_count']} 段")

    if hw_base.get("raw_evidence"):
        evidence.append(f"[HWC 基线] {hw_base['raw_evidence']}")
    hw_min_s = hw_gw.get("brightness_val_min_sample") or {}
    hw_max_s = hw_gw.get("brightness_val_max_sample") or {}
    if hw_min_s.get("raw_evidence"):
        evidence.append(
            f"[HWC 最低 val={hw_min_s.get('brightness_val')} ratio={hw_min_s.get('brightness_ratio')}] "
            f"{hw_min_s['raw_evidence']}"
        )
    if hw_max_s.get("raw_evidence") and hw_max_s.get("raw_evidence") != hw_min_s.get("raw_evidence"):
        evidence.append(
            f"[HWC 最高 val={hw_max_s.get('brightness_val')} ratio={hw_max_s.get('brightness_ratio')}] "
            f"{hw_max_s['raw_evidence']}"
        )
    sp = hw_gw.get("stable_plateau") or {}
    if sp.get("brightness_val") is not None:
        evidence.append(
            f"[HWC 开局稳定 {sp.get('duration_seconds')}s] brightness_val={sp['brightness_val']} "
            f"（无采样=未变光，继承基线）"
        )
    for tr in hw_gw.get("transitions") or []:
        evidence.append(
            f"[HWC {tr.get('kind')}] {tr.get('time_start')}→{tr.get('time_end')} "
            f"{tr.get('brightness_val_from')}→{tr.get('brightness_val_to')} · {tr.get('hint')}"
        )
    st = hw_gw.get("stable_tail") or {}
    if st.get("brightness_val") is not None:
        evidence.append(
            f"[HWC 结束前稳定 {st.get('duration_seconds')}s] brightness_val={st['brightness_val']}"
        )
    pg = hw_gw.get("post_game_window") or {}
    if pg.get("first_sample"):
        fs = pg["first_sample"]
        evidence.append(
            f"[HWC T_post 首条] {fs.get('time')} brightness_val={fs.get('brightness_val')} "
            f"{fs.get('raw_evidence', '')}"
        )

    return {"val": val, "sub": sub, "evidence": evidence, "coverage": brightness_stats.get("coverage")}


def _brightness_overview_merged(brightness_stats: dict[str, Any]) -> dict[str, Any]:
    """优先 brightness_analysis 三段结论，回退 LCM/HWC 旧逻辑。"""
    overlay = brightness_kpi_from_stats(brightness_stats)
    if overlay.get("source") == "brightness_analysis":
        legacy = _brightness_overview(brightness_stats)
        evidence = list(overlay.get("evidence") or [])
        for line in legacy.get("evidence") or []:
            if line not in evidence:
                evidence.append(line)
        return {
            "val": overlay.get("val") or legacy.get("val"),
            "sub": overlay.get("sub") or legacy.get("sub"),
            "evidence": evidence,
            "coverage": overlay.get("coverage") or legacy.get("coverage"),
            "warn": overlay.get("warn", False),
        }
    legacy = _brightness_overview(brightness_stats)
    legacy["warn"] = bool(brightness_stats.get("game_window", {}).get("changed"))
    return legacy


def _duration_overview(gw: dict[str, Any]) -> dict[str, Any]:
    evidence: list[str] = []
    if gw.get("start_evidence"):
        evidence.append(f"[开始 {gw.get('start', '')}] {gw['start_evidence']}")
    if gw.get("end_evidence"):
        evidence.append(f"[结束 {gw.get('end', '')}] {gw['end_evidence']}")
    if gw.get("end_reason"):
        evidence.append(f"结束判定: {gw['end_reason']}")
    sub = f"{gw.get('start', '')} ~ {gw.get('end', '')}"
    return {"sub": sub, "evidence": evidence}


def _volume_overview(volume_stats: dict[str, Any]) -> dict[str, Any]:
    baseline = volume_stats.get("baseline_before_game") or {}
    gw = volume_stats.get("game_window") or {}
    idx_min = gw.get("index_min")
    idx_max = gw.get("index_max")
    pct_min = gw.get("index_min_pct")
    pct_max = gw.get("index_max_pct")
    base_idx = baseline.get("index")

    if idx_min is not None and idx_max is not None:
        if idx_min == idx_max:
            val = f"{idx_min}"
            sub = f"STREAM_MUSIC 格 · 基线 {base_idx if base_idx is not None else 'N/A'}"
            if pct_min is not None:
                sub += f" ({pct_min}%)"
        else:
            val = f"{idx_min}~{idx_max}"
            sub = "T_game 音量格"
            if pct_min is not None and pct_max is not None:
                sub += f" · {pct_min}%~{pct_max}%"
            if base_idx is not None:
                sub += f" · 基线 {base_idx}"
    elif base_idx is not None:
        val = str(base_idx)
        pct = baseline.get("index_pct")
        sub = "T_game 无新采样，沿用基线"
        if pct is not None:
            sub += f" ({pct}%)"
    else:
        val = "N/A"
        sub = volume_stats.get("coverage", "missing")

    evidence: list[str] = []
    if baseline.get("raw_evidence"):
        evidence.append(f"[基线] {baseline['raw_evidence']}")
    min_s = gw.get("index_min_sample") or {}
    max_s = gw.get("index_max_sample") or {}
    if min_s.get("raw_evidence"):
        evidence.append(f"[最低 index={min_s.get('index')}] {min_s['raw_evidence']}")
    if max_s.get("raw_evidence") and max_s.get("raw_evidence") != min_s.get("raw_evidence"):
        evidence.append(f"[最高 index={max_s.get('index')}] {max_s['raw_evidence']}")
    evidence.extend(gw.get("raw_evidence") or [])

    return {"val": val, "sub": sub, "evidence": evidence[:30], "coverage": volume_stats.get("coverage")}


def _power_buckets(summary: dict[str, Any]) -> list[dict[str, Any]]:
    buckets = summary.get("power_buckets") or {}
    if buckets:
        return [
            {"name": k, **v} if isinstance(v, dict) else {"name": k, "mw": v}
            for k, v in buckets.items()
        ]
    # 占位：按子系统粗略拆分
    ap_mw = 285
    return [
        {"name": "AP (CPU+GPU)", "mw": ap_mw, "pct": 52, "priority": "P0", "color": "#3498db"},
        {"name": "Modem", "mw": 120, "pct": 22, "priority": "P2", "color": "#95a5a6"},
        {"name": "WiFi/BT", "mw": 95, "pct": 17, "priority": "P1", "color": "#2ecc71"},
        {"name": "GPS/Sensor", "mw": 35, "pct": 6, "priority": "P1", "color": "#f39c12"},
        {"name": "Audio", "mw": 15, "pct": 3, "priority": "P2", "color": "#9b59b6"},
    ]


def _cpu_samples_t_game(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """报告展示仅保留 T_game 时段采样（兼容旧版 summary 含 T_pre/T_post）。"""
    out = [dict(s) for s in samples if s.get("window") == "T_game"]
    for idx, sample in enumerate(out, start=1):
        sample["round"] = idx
    return out


_FINDING_TYPE_LABEL = {
    "spike": "CPU突增",
    "single_shot": "单次高占用",
    "persistent_non_baseline": "持续非基线",
}


def _format_thread_line(thread: dict[str, Any], flagged: bool) -> str:
    text = f"{thread.get('usage')}% pid={thread.get('pid')} {thread.get('name')}"
    if flagged:
        return f'<span style="color:var(--danger);font-weight:600;">{_esc(text)}</span>'
    return _esc(text)


def generate_report(summary: dict[str, Any], out_path: Path) -> Path:
    gw = summary.get("game_window") or {}
    meta = summary.get("analysis_meta") or {}
    cmp_out = summary.get("comparison_outputs") or {}
    ps = summary.get("power_summary") or {}
    tc = summary.get("test_conditions") or {}
    tags = tc.get("tags") or []
    cpu_samples = _cpu_samples_t_game(cmp_out.get("cpu_samples") or [])
    cpu_inv = cmp_out.get("cpu_thread_investigation") or {}
    cpu_findings = cpu_inv.get("findings") or []
    flagged_by_round: dict[str, set[str]] = {}
    for item in cpu_findings:
        rnd = str(item.get("round", ""))
        name = str(item.get("name", ""))
        if rnd and name:
            flagged_by_round.setdefault(rnd, set()).add(name)
    cpu_stats = cmp_out.get("cpu_core_usage_stats") or {}
    cpu_trend = cmp_out.get("cpu_usage_trend") or {}
    fps_stats = cmp_out.get("frame_rate_stats") or {}
    brightness_stats = cmp_out.get("brightness_stats") or {}
    volume_stats = cmp_out.get("volume_stats") or {}
    thermal = (summary.get("mtk_specific") or {}).get("thermal") or {}
    br_overview = _brightness_overview_merged(brightness_stats)
    vol_overview = _volume_overview(volume_stats)
    dur_overview = _duration_overview(gw)

    game_name = (
        gw.get("game_name")
        or load_game_name(str(gw.get("package") or meta.get("game_package") or ""))
        or meta.get("game_package")
        or "未知游戏"
    )
    duration = gw.get("duration_seconds") or 0
    extra_mw = ps.get("delta_power_estimate_mw")
    battery_min = ps.get("battery_impact_estimate_min")

    avg_fps = 0.0
    main_layer = fps_stats.get("main_app_layer") or {}
    if isinstance(main_layer, dict) and main_layer.get("avg_fps"):
        avg_fps = main_layer["avg_fps"]
    else:
        for key in ("system_layers", "composition_layers", "unknown_layers"):
            layers = fps_stats.get(key) or []
            if isinstance(layers, list) and layers:
                avg_fps = layers[0].get("avg_fps", 0)
                break

    max_temp = thermal.get("max_cpu_temp_celsius")

    suggestions = _build_suggestions(summary)
    buckets = _power_buckets(summary)

    tag_html = []
    for t in tags:
        tag_html.append(
            f'<button type="button" class="cond-tag {_tag_class(t.get("status", ""))}" '
            f'data-tag-id="{_esc(t.get("id", ""))}" '
            f'onclick="showEvidence(\'{_esc(t.get("id", ""))}\')">'
            f'{_esc(t.get("label", ""))}</button>'
        )

    bucket_html = []
    max_mw = max((b.get("mw") or 0) for b in buckets) or 1
    for b in buckets:
        w = int(100 * (b.get("mw") or 0) / max_mw)
        bucket_html.append(
            f'<div class="bucket-row">'
            f'<div class="bucket-label">{_esc(b.get("name"))} '
            f'<span class="bucket-prio">{_esc(b.get("priority", ""))}</span></div>'
            f'<div class="bucket-bar-wrap"><div class="bucket-bar" style="width:{w}%;background:{_esc(b.get("color", "#3498db"))}">'
            f'{b.get("mw", 0)}mW ({b.get("pct", 0)}%)</div></div></div>'
        )

    sug_rows = []
    for s in suggestions:
        sug_rows.append(
            "<tr>"
            f'<td><span class="prio-badge {_priority_class(s.get("priority", ""))}">{_esc(s.get("priority", ""))}</span></td>'
            f"<td>{_esc(s.get('issue', ''))}</td>"
            f"<td>{_esc(s.get('suggestion', ''))}</td>"
            f"<td>{_esc(s.get('benefit', ''))}</td>"
            "</tr>"
        )

    cpu_evidence_map: dict[str, str] = {}
    inv_evidence_map: dict[str, str] = {}

    inv_rows: list[str] = []
    for idx, item in enumerate(cpu_findings):
        fkey = f"inv{idx}"
        logs_blob = item.get("correlated_logs") or {}
        parts: list[str] = []
        for src in ("events", "main_log", "sys_log", "kernel_log"):
            lines = logs_blob.get(src) or []
            if lines:
                parts.append(f"=== {src} (±{cpu_inv.get('thresholds', {}).get('log_correlation_seconds', 10)}s) ===")
                parts.extend(lines)
        inv_evidence_map[fkey] = "\n\n".join(parts) if parts else "（该时段未匹配到 events/main/sys/kernel 相关行）"
        ftype = _FINDING_TYPE_LABEL.get(str(item.get("finding_type")), item.get("finding_type"))
        inv_rows.append(
            "<tr>"
            f'<td><span class="prio-badge {_priority_class(item.get("priority", "P2"))}">{_esc(item.get("priority", ""))}</span></td>'
            f"<td>{_esc(ftype)}</td>"
            f"<td>{_esc(item.get('name', ''))}</td>"
            f"<td>{_esc(item.get('pid', ''))}</td>"
            f"<td>{_esc(item.get('time', ''))}</td>"
            f"<td>{_esc(item.get('detail', ''))}</td>"
            f"<td>{_esc(item.get('owner_hint', '') or '（未解析到归属，建议按 PID 查 sys Start proc）')}</td>"
            f'<td><button type="button" class="link-btn" onclick="showInvEvidence(\'{fkey}\')">关联日志</button></td>'
            "</tr>"
        )

    cpu_rows = []
    for sample in cpu_samples:
        cpus = sample.get("cpus_usage") or []
        cpu_cells = "".join(f"<td>{c}%</td>" for c in cpus)
        while len(cpus) < 8:
            cpu_cells += "<td>-</td>"
            cpus.append(-1)
        total = sample.get("total") or {}
        agg = sample.get("aggregate_usage_pct", "")
        threads = sample.get("threads") or []
        round_key = str(sample.get("round", len(cpu_rows) + 1))
        flagged_names = flagged_by_round.get(round_key, set())
        thread_lines = "<br>".join(
            _format_thread_line(t, t.get("name") in flagged_names) for t in threads[:15]
        )
        if len(threads) > 15:
            thread_lines += f"<br>…共 {len(threads)} 线程"
        raw = sample.get("raw_evidence", "")
        cpu_evidence_map[round_key] = raw
        cpu_rows.append(
            "<tr>"
            f"<td>{sample.get('round', '')}</td>"
            f"<td>{_esc(sample.get('time', ''))}</td>"
            f"<td>{_esc(sample.get('window', ''))}</td>"
            f"<td>{_esc(sample.get('phase', '') or '-')}</td>"
            f"<td>{_esc(agg)}</td>"
            f"{cpu_cells}"
            f"<td>user={total.get('user', '-')} sys={total.get('system', '-')} idle={total.get('idle', '-')}</td>"
            f'<td class="thread-cell">{thread_lines}</td>'
            f'<td><button type="button" class="link-btn" onclick="showCpuEvidence(\'{round_key}\')">原始行</button></td>'
            "</tr>"
        )

    core_chart_labels = [f"CPU{i}" for i in range(8)]
    core_avgs = [c.get("avg_usage", 0) for c in (cpu_stats.get("cores") or [])[:8]]
    while len(core_avgs) < 8:
        core_avgs.append(0)

    evidence_json = json.dumps(
        {t["id"]: t.get("raw_evidence", []) for t in tags if t.get("id")},
        ensure_ascii=False,
    )
    overview_evidence_json = json.dumps(
        {
            "duration": dur_overview.get("evidence", []),
            "brightness": br_overview.get("evidence", []),
            "volume": vol_overview.get("evidence", []),
        },
        ensure_ascii=False,
    )
    cpu_evidence_json = json.dumps(cpu_evidence_map, ensure_ascii=False)
    inv_evidence_json = json.dumps(inv_evidence_map, ensure_ascii=False)
    inv_thr = cpu_inv.get("thresholds") or {}
    inv_summary = cpu_inv.get("summary") or {}
    br_warn = "warn" if br_overview.get("warn") else ""

    gen_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html_doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>游戏功耗分析仪表板 - {_esc(game_name)}</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/echarts/5.4.3/echarts.min.js"></script>
<style>
:root {{
  --bg:#f5f7fa;--card:#fff;--primary:#2c3e50;--accent:#3498db;
  --danger:#e74c3c;--warn:#f39c12;--ok:#2ecc71;--muted:#7f8c8d;--border:#e0e6ed;
}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Segoe UI',sans-serif;background:var(--bg);color:var(--primary);padding:24px}}
h1{{font-size:22px;margin-bottom:4px}}
.sub{{color:var(--muted);font-size:13px;margin-bottom:20px}}
.dashboard{{max-width:1280px;margin:0 auto}}
.card{{background:var(--card);border-radius:10px;box-shadow:0 2px 8px rgba(0,0,0,.06);padding:20px;margin-bottom:20px}}
.card h2{{font-size:16px;border-bottom:2px solid var(--accent);padding-bottom:8px;margin-bottom:16px}}
.stat-row{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px}}
.stat{{background:#fafbfc;border:1px solid var(--border);border-radius:8px;padding:14px;text-align:center}}
.stat .val{{font-size:22px;font-weight:700;color:var(--accent)}}
.stat .val.danger{{color:var(--danger)}}
.stat .label{{font-size:12px;color:var(--muted);margin-top:4px}}
.stat .subval{{font-size:11px;color:var(--muted);margin-top:6px;line-height:1.35}}
.stat.clickable{{cursor:pointer}}
.stat.clickable:hover{{border-color:var(--accent);box-shadow:0 0 0 1px var(--accent)}}
.stat .val.warn{{color:var(--warn)}}
.cond-tags{{display:flex;flex-wrap:wrap;gap:8px}}
.cond-tag{{border:none;border-radius:20px;padding:8px 14px;font-size:12px;cursor:pointer;font-weight:600}}
.tag-ok{{background:#e8f8f0;color:#1e8449}}
.tag-warn{{background:#fef5e7;color:#b7950b}}
.tag-bad{{background:#fdedec;color:#c0392b}}
.tag-unknown{{background:#ecf0f1;color:#566573}}
.bucket-row{{margin-bottom:10px}}
.bucket-label{{font-size:13px;margin-bottom:4px}}
.bucket-prio{{font-size:11px;color:var(--muted);margin-left:6px}}
.bucket-bar-wrap{{background:#ecf0f1;border-radius:6px;height:28px;overflow:hidden}}
.bucket-bar{{height:100%;line-height:28px;padding:0 10px;font-size:12px;color:#fff;font-weight:600;min-width:80px}}
table{{width:100%;border-collapse:collapse;font-size:12px}}
th{{background:var(--primary);color:#fff;padding:8px;text-align:left}}
td{{padding:8px;border-bottom:1px solid var(--border);vertical-align:top}}
tr:hover td{{background:#f8f9fa}}
.table-scroll{{overflow-x:auto}}
.prio-badge{{display:inline-block;padding:2px 8px;border-radius:4px;font-weight:700;font-size:11px;color:#fff}}
.p0{{background:var(--danger)}}.p1{{background:var(--warn)}}.p2{{background:var(--ok)}}
.thread-cell{{font-size:11px;max-width:280px}}
.link-btn{{background:none;border:none;color:var(--accent);cursor:pointer;text-decoration:underline;font-size:12px}}
#chart-cores{{width:100%;height:300px}}
.modal{{display:none;position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:1000;align-items:center;justify-content:center}}
.modal.open{{display:flex}}
.modal-box{{background:#fff;border-radius:10px;max-width:900px;width:92%;max-height:80vh;overflow:hidden;display:flex;flex-direction:column}}
.modal-head{{padding:14px 18px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center}}
.modal-body{{padding:14px 18px;overflow:auto;font-family:Consolas,monospace;font-size:12px;white-space:pre-wrap;line-height:1.5}}
.modal-close{{border:none;background:none;font-size:20px;cursor:pointer;color:var(--muted)}}
.no-data{{color:var(--muted);font-style:italic;padding:20px;text-align:center}}
</style>
</head>
<body>
<div class="dashboard">
  <h1>游戏功耗分析仪表板</h1>
  <p class="sub">生成时间：{gen_time} · 日志：{_esc(summary.get("log_path", ""))}</p>

  <div class="card">
    <h2>概览 KPI</h2>
    <div class="stat-row">
      <div class="stat"><div class="val">{_esc(game_name)}</div><div class="label">游戏</div></div>
      <div class="stat clickable" onclick="showOverviewEvidence('duration')" title="点击查看游戏窗起止原始日志">
        <div class="val">{_fmt_duration(duration)}</div>
        <div class="label">运行时长</div>
        <div class="subval">{_esc(dur_overview.get("sub", ""))}</div>
      </div>
      <div class="stat"><div class="val">{_esc(extra_mw if extra_mw is not None else "N/A")}{"" if extra_mw is None else "mW"}</div><div class="label">额外功耗</div></div>
      <div class="stat"><div class="val danger">{_esc(battery_min if battery_min is not None else "N/A")}{"" if battery_min is None else "min"}</div><div class="label">预估续航减少</div></div>
      <div class="stat"><div class="val">{avg_fps or "N/A"}{"" if not avg_fps else "fps"}</div><div class="label">平均帧率</div></div>
      <div class="stat"><div class="val">{_esc(max_temp if max_temp is not None else "N/A")}{"" if max_temp is None else "°C"}</div><div class="label">最高 CPU 温度</div></div>
      <div class="stat"><div class="val">{cpu_trend.get("avg_total_usage", "N/A")}%</div><div class="label">CPU 平均占用</div></div>
      <div class="stat"><div class="val">{cpu_stats.get("total_samples", 0)}</div><div class="label">[K] CPU 采样轮次</div></div>
      <div class="stat clickable" onclick="showOverviewEvidence('brightness')" title="点击查看 LCM 背光原始日志">
        <div class="val {br_warn}">{_esc(br_overview.get("val", "N/A"))}</div>
        <div class="label">亮度（测试前/启动/游戏内）</div>
        <div class="subval">{_esc(br_overview.get("sub", ""))}</div>
      </div>
      <div class="stat clickable" onclick="showOverviewEvidence('volume')" title="点击查看音量原始日志">
        <div class="val">{_esc(vol_overview.get("val", "N/A"))}</div>
        <div class="label">音量 STREAM_MUSIC (min~max)</div>
        <div class="subval">{_esc(vol_overview.get("sub", ""))}</div>
      </div>
    </div>
  </div>

  <div class="card">
    <h2>测试前置条件 <span style="font-size:12px;color:var(--muted)">（点击标签查看原始日志）</span></h2>
    <div class="cond-tags">{"".join(tag_html) if tag_html else '<span class="no-data">无探测数据</span>'}</div>
    <p style="margin-top:10px;font-size:12px;color:var(--muted)">完整性：{tc.get("completeness", "unknown")} · 缺失：{", ".join(tc.get("missing_items") or []) or "无"}</p>
  </div>

  <div class="card">
    <h2>功耗归因（估算）</h2>
    {"".join(bucket_html)}
  </div>

  <div class="card">
    <h2>优化建议</h2>
    <div class="table-scroll">
      <table>
        <thead><tr><th>优先级</th><th>问题</th><th>建议</th><th>预期收益</th></tr></thead>
        <tbody>{"".join(sug_rows) if sug_rows else '<tr><td colspan="4" class="no-data">暂无建议</td></tr>'}</tbody>
      </table>
    </div>
  </div>

  <div class="card">
    <h2>CPU 核心平均占用（T_game stable）</h2>
    <div id="chart-cores"></div>
  </div>

  <div class="card">
    <h2>[K] 线程异常排查（突增≥{inv_thr.get("spike_usage_pp", 10)}pp / 单次&gt;{inv_thr.get("single_shot_min_usage_pct", 10)}% / 非基线多轮）</h2>
    <p style="font-size:12px;color:var(--muted);margin-bottom:12px;">
      突增 {inv_summary.get("spike", 0)} · 单次高占用 {inv_summary.get("single_shot", 0)} · 持续非基线 {inv_summary.get("persistent_non_baseline", 0)}
      （白名单：baseline-processes.yaml + 游戏包名/子进程；游戏线程如 ds:UnityKillsMe 主界面→对局 CPU 上升属正常）
    </p>
    <div class="table-scroll">
      <table>
        <thead><tr>
          <th>优先级</th><th>类型</th><th>进程/线程</th><th>PID</th><th>时间</th><th>说明</th><th>归属线索</th><th>日志</th>
        </tr></thead>
        <tbody>{"".join(inv_rows) if inv_rows else '<tr><td colspan="8" class="no-data">未检出需排查的线程（或均为基线/游戏进程）</td></tr>'}</tbody>
      </table>
    </div>
  </div>

  <div class="card">
    <h2>[K] CPU 每轮采样（T_game {_esc(gw.get("start", ""))} ~ {_esc(gw.get("end", ""))}，共 {len(cpu_samples)} 轮）</h2>
    <div class="table-scroll">
      <table>
        <thead><tr>
          <th>#</th><th>时间</th><th>窗口</th><th>阶段</th><th>总占用%</th>
          <th>C0</th><th>C1</th><th>C2</th><th>C3</th><th>C4</th><th>C5</th><th>C6</th><th>C7</th>
          <th>user/sys/idle</th><th>Top 线程</th><th>证据</th>
        </tr></thead>
        <tbody>{"".join(cpu_rows) if cpu_rows else '<tr><td colspan="16" class="no-data">无 CPU 采样</td></tr>'}</tbody>
      </table>
    </div>
  </div>
</div>

<div class="modal" id="modal" onclick="if(event.target===this)closeModal()">
  <div class="modal-box">
    <div class="modal-head"><strong id="modal-title">原始日志</strong><button class="modal-close" onclick="closeModal()">×</button></div>
    <div class="modal-body" id="modal-body"></div>
  </div>
</div>

<script>
const EVIDENCE = {evidence_json};
const OVERVIEW_EVIDENCE = {overview_evidence_json};
const CPU_EVIDENCE = {cpu_evidence_json};
const INV_EVIDENCE = {inv_evidence_json};

function showInvEvidence(key) {{
  document.getElementById('modal-title').textContent = '线程排查 · 关联日志 ' + key;
  document.getElementById('modal-body').textContent = INV_EVIDENCE[key] || '（无数据）';
  document.getElementById('modal').classList.add('open');
}}

function showOverviewEvidence(kind) {{
  const lines = OVERVIEW_EVIDENCE[kind] || [];
  const titles = {{
    duration: '运行时长（游戏窗起止）',
    brightness: '亮度（测试前末值 / 启动20s / 游戏内变光）',
    volume: '音量（STREAM_MUSIC）'
  }};
  const title = titles[kind] || kind;
  document.getElementById('modal-title').textContent = '概览 · ' + title;
  document.getElementById('modal-body').textContent = lines.length ? lines.join(String.fromCharCode(10, 10)) : '（无原始日志行）';
  document.getElementById('modal').classList.add('open');
}}

function showEvidence(tagId) {{
  const lines = EVIDENCE[tagId] || [];
  document.getElementById('modal-title').textContent = '前置条件原始日志 · ' + tagId;
  document.getElementById('modal-body').textContent = lines.length ? lines.join(String.fromCharCode(10, 10)) : '（无原始日志行）';
  document.getElementById('modal').classList.add('open');
}}

function showCpuEvidence(roundKey) {{
  document.getElementById('modal-title').textContent = 'CPU 采样原始证据 · 第 ' + roundKey + ' 轮';
  document.getElementById('modal-body').textContent = CPU_EVIDENCE[roundKey] || '（无）';
  document.getElementById('modal').classList.add('open');
}}

function closeModal() {{
  document.getElementById('modal').classList.remove('open');
}}

(function(){{
  var c = echarts.init(document.getElementById('chart-cores'));
  c.setOption({{
    title: {{ text: '8 核平均占用 %', textStyle: {{ fontSize: 14 }} }},
    tooltip: {{}},
    xAxis: {{ type: 'category', data: {json.dumps(core_chart_labels, ensure_ascii=False)} }},
    yAxis: {{ type: 'value', max: 100 }},
    series: [{{ type: 'bar', data: {json.dumps(core_avgs)}, itemStyle: {{ color: '#3498db' }} }}]
  }});
  window.addEventListener('resize', function(){{ c.resize(); }});
}})();
</script>
</body>
</html>"""

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_doc, encoding="utf-8")
    return out_path


def main() -> int:
    _setup_utf8_stdio()
    import argparse

    parser = argparse.ArgumentParser(description="生成游戏功耗 HTML 仪表板")
    parser.add_argument("summary_json", help="game_power_compare_summary.json 路径")
    parser.add_argument("--output", default="", help="输出 HTML 路径")
    args = parser.parse_args()
    summary_path = Path(args.summary_json)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    out = Path(args.output) if args.output else summary_path.parent / "game_power_report.html"
    generate_report(summary, out)
    print(f"已输出: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
