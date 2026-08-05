"""从 game_network_cap 解析结果提炼影响功耗的因素。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_GAME_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if str(_GAME_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_GAME_SCRIPTS))

from skill_references import load_analysis_standards, threshold  # noqa: E402


def _ref_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "references"


def _f(val: Any, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def extract_power_impact(
    cap_result: dict[str, Any],
    *,
    window_duration_s: float | None = None,
) -> dict[str, Any]:
    """基于重叠 cap 深解析结果，输出功耗相关因子与结论。"""
    standards = load_analysis_standards(_ref_dir(), "power-impact-rules.yaml")
    high_pps = float(threshold(standards, "high_packet_rate_pps", 200))
    high_bps = float(threshold(standards, "high_byte_rate_bps", 200000))
    min_cov = float(threshold(standards, "min_coverage_ratio", 0.5))
    noise_ratio = float(threshold(standards, "iface_noise_ratio", 0.01))

    status = str(cap_result.get("status") or "")
    if status in {"skipped", "missing", "no_overlap", "blocked"}:
        return {
            "coverage": status,
            "has_impact": False,
            "level": "none",
            "summary": f"未启用抓包功耗分析（status={status}）",
            "factors": [],
            "evidence": list(cap_result.get("errors") or [])[:5],
        }

    files = [f for f in (cap_result.get("files") or []) if isinstance(f, dict)]
    dual = cap_result.get("dual_channel") if isinstance(cap_result.get("dual_channel"), dict) else {}
    win = cap_result.get("window") if isinstance(cap_result.get("window"), dict) else {}

    factors: list[dict[str, Any]] = []
    evidence: list[str] = []

    # 1) 双通道 / 多接口
    verdict = str(dual.get("verdict") or "")
    if verdict == "yes":
        factors.append(
            {
                "id": "dual_channel",
                "title": "双通道数传",
                "severity": "high",
                "power_hint": "WiFi+蜂窝同时活跃时，modem/WiFi 射频与协议栈功耗易叠加抬升",
                "detail": dual.get("summary"),
            }
        )
    elif verdict in {"suspect_multi_iface", "suspect_multi_ip"}:
        factors.append(
            {
                "id": "multi_path_suspect",
                "title": "多接口/多地址疑似",
                "severity": "medium",
                "power_hint": "多网卡或地址族并存可能导致路径切换/并发探测，增加待机与数传功耗",
                "detail": dual.get("summary"),
            }
        )
    elif verdict == "no":
        factors.append(
            {
                "id": "single_path",
                "title": "单通道数传",
                "severity": "info",
                "power_hint": "抓包侧未见 WiFi+蜂窝双通道并发，射频抬升需结合 RSSI/RSRP 另判",
                "detail": dual.get("summary"),
            }
        )

    for ev in dual.get("evidence") or []:
        if ev:
            evidence.append(str(ev))

    # 2) 吞吐 / 包速率（优先用窗口内 interface_traffic 包数）
    win_pkts = _f(dual.get("packet_count_in_window"))
    overlap_s = 0.0
    byte_rates: list[float] = []
    for f in files:
        ov = _f(f.get("overlap_with_window_seconds"))
        overlap_s += ov
        if f.get("data_byte_rate") is not None:
            byte_rates.append(_f(f.get("data_byte_rate")))
        it = f.get("interface_traffic") if isinstance(f.get("interface_traffic"), dict) else {}
        if not win_pkts and it.get("packet_count_in_window"):
            win_pkts += _f(it.get("packet_count_in_window"))

    # 窗口时长：包速率用重叠时长更贴近活跃抓包段；覆盖率仍用整段 T_game
    dur_for_rate = overlap_s if overlap_s > 0 else None
    t_game_dur = window_duration_s
    if dur_for_rate is None and t_game_dur and t_game_dur > 0:
        dur_for_rate = t_game_dur

    pps = (win_pkts / dur_for_rate) if (dur_for_rate and dur_for_rate > 0 and win_pkts > 0) else None
    avg_bps = (sum(byte_rates) / len(byte_rates)) if byte_rates else None

    if pps is not None and pps >= high_pps:
        factors.append(
            {
                "id": "high_packet_rate",
                "title": "局内高包速率",
                "severity": "high",
                "power_hint": "高频收发包会抬升 WiFi/modem 与 CPU softirq，平均电流易升高",
                "detail": f"重叠段约 {pps:.1f} pkt/s（阈值 {high_pps:g}）",
                "metric": {
                    "pps": round(pps, 2),
                    "packets": win_pkts,
                    "duration_s": round(dur_for_rate or 0, 1),
                },
            }
        )
    elif pps is not None:
        factors.append(
            {
                "id": "packet_rate_normal",
                "title": "局内包速率正常",
                "severity": "info",
                "power_hint": "包速率未超阈值，数传活跃度本身不太像主因",
                "detail": f"约 {pps:.1f} pkt/s",
                "metric": {"pps": round(pps, 2)},
            }
        )

    if avg_bps is not None and avg_bps >= high_bps:
        factors.append(
            {
                "id": "high_throughput",
                "title": "高吞吐数传",
                "severity": "medium",
                "power_hint": "高字节率对应射频/基带持续工作，可能抬升局内平均功耗",
                "detail": f"capinfos 数据字节率均值约 {avg_bps/1024:.1f} KB/s（阈值 {high_bps/1024:g} KB/s）",
                "metric": {"byte_rate_bps": round(avg_bps, 1)},
            }
        )

    # 3) 接口噪声外的主接口数量
    iface_counts = dual.get("interface_index_counts") if isinstance(dual.get("interface_index_counts"), dict) else {}
    if iface_counts and win_pkts > 0:
        significant = {
            k: v
            for k, v in iface_counts.items()
            if _f(v) / win_pkts >= noise_ratio
        }
        if len(significant) >= 2:
            factors.append(
                {
                    "id": "multi_iface_significant",
                    "title": "多网卡显著分流",
                    "severity": "medium",
                    "power_hint": "多个接口均有可观流量，存在并发或频繁切换的功耗风险",
                    "detail": "显著接口: "
                    + ", ".join(f"{k}×{int(v)}" for k, v in sorted(significant.items(), key=lambda kv: -_f(kv[1]))),
                }
            )

    # 4) 抓包覆盖缺口
    if t_game_dur and t_game_dur > 0 and overlap_s >= 0:
        cov = overlap_s / t_game_dur
        if cov < min_cov:
            factors.append(
                {
                    "id": "cap_coverage_gap",
                    "title": "抓包未覆盖完整 T_game",
                    "severity": "info",
                    "power_hint": "后半段无 cap 时，抓包结论不能外推整局；需结合 main/radio 证据",
                    "detail": f"重叠约 {overlap_s:.0f}s / T_game {t_game_dur:.0f}s（覆盖 {cov*100:.0f}%）",
                    "metric": {"overlap_s": round(overlap_s, 1), "coverage_ratio": round(cov, 3)},
                }
            )

    # 汇总 level
    severities = {f.get("severity") for f in factors}
    if "high" in severities:
        level = "suspect"
    elif "medium" in severities:
        level = "observe"
    else:
        level = "info"

    impact_factors = [f for f in factors if f.get("severity") in {"high", "medium"}]
    has_impact = bool(impact_factors)

    if has_impact:
        titles = "；".join(str(f.get("title")) for f in impact_factors[:3])
        summary = f"抓包功耗相关：{titles}"
    elif factors:
        summary = "抓包已分析：未见明确双通道/高吞吐抬升证据"
    else:
        summary = "抓包结果缺少可用于功耗判定的有效字段"

    # 报告用精简行
    report_rows: list[tuple[str, str]] = [
        ("抓包状态", status or "—"),
        ("重叠 cap 数", str(cap_result.get("overlapping_cap_count") or len(files))),
        ("双通道判定", f"{verdict or '—'}（{dual.get('summary') or ''}）".rstrip("（）")),
    ]
    if pps is not None:
        report_rows.append(("局内包速率", f"{pps:.1f} pkt/s"))
    if avg_bps is not None:
        report_rows.append(("数据字节率", f"{avg_bps/1024:.1f} KB/s"))
    for f in impact_factors:
        report_rows.append((str(f.get("title")), str(f.get("power_hint") or f.get("detail") or "—")))

    return {
        "coverage": "ok" if files else status or "missing",
        "has_impact": has_impact,
        "level": level,
        "summary": summary,
        "factors": factors,
        "impact_factors": impact_factors,
        "evidence": evidence[:12],
        "metrics": {
            "window_packets": win_pkts,
            "overlap_seconds": round(overlap_s, 1) if overlap_s else None,
            "packet_rate_pps": round(pps, 2) if pps is not None else None,
            "avg_byte_rate_bps": round(avg_bps, 1) if avg_bps is not None else None,
            "dual_verdict": verdict or None,
        },
        "report_rows": [{"label": a, "value": b} for a, b in report_rows],
        "window": win,
        "thresholds": {
            "high_packet_rate_pps": high_pps,
            "high_byte_rate_bps": high_bps,
            "min_coverage_ratio": min_cov,
        },
    }
