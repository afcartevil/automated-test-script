"""game_trace analysis: normalize MTK perf-statistic.html into game_trace.json."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from estimate_cpu_power_lib import EnergyModelError, estimate_cpu_power_from_html
from perf_statistic_html_lib import parse_perf_statistic_html

DEFAULT_THRESHOLDS: dict[str, float] = {
    "fixed_freq_ratio_pct": 75.0,
    "high_freq_peak_ratio_pct": 30.0,
    "high_band_ratio_pct": 40.0,
    "high_band_relative": 0.8,  # freqs >= max*0.8 count as high band
    "raised_floor_mhz": 1000.0,
    "raised_floor_low_band_max_pct": 25.0,
}


def _weighted_avg_mhz(residency: list[dict[str, Any]]) -> float | None:
    if not residency:
        return None
    total = sum(float(r["ratio_pct"]) for r in residency)
    if total <= 0:
        return None
    return round(sum(float(r["freq_mhz"]) * float(r["ratio_pct"]) for r in residency) / total, 1)


def _normalize_cluster(cluster: dict[str, Any], thresholds: dict[str, float]) -> dict[str, Any]:
    residency = list(cluster.get("residency") or [])
    residency_sorted = sorted(residency, key=lambda r: float(r["ratio_pct"]), reverse=True)
    freqs = [int(r["freq_mhz"]) for r in residency]
    max_freq = max(freqs) if freqs else 0
    high_cut = max_freq * float(thresholds["high_band_relative"])
    high_band_pct = round(
        sum(float(r["ratio_pct"]) for r in residency if float(r["freq_mhz"]) >= high_cut),
        2,
    )
    low_band_pct = round(
        sum(
            float(r["ratio_pct"])
            for r in residency
            if float(r["freq_mhz"]) < float(thresholds["raised_floor_mhz"])
        ),
        2,
    )
    peak = residency_sorted[0] if residency_sorted else None
    peak_pct = float(peak["ratio_pct"]) if peak else 0.0
    peak_mhz = float(peak["freq_mhz"]) if peak else 0.0
    fixed = peak_pct >= float(thresholds["fixed_freq_ratio_pct"])
    raised_floor = (
        max_freq > 0
        and low_band_pct <= float(thresholds["raised_floor_low_band_max_pct"])
        and (_weighted_avg_mhz(residency) or 0) >= float(thresholds["raised_floor_mhz"])
    )
    # 仅当「高频带」驻留高，或峰值本身落在高频带且占比高，才算 sustained_high
    peak_is_high = max_freq > 0 and peak_mhz >= high_cut
    sustained_high = high_band_pct >= float(thresholds["high_band_ratio_pct"]) or (
        peak_is_high and peak_pct >= float(thresholds["high_freq_peak_ratio_pct"])
    )
    return {
        "name": f"cluster{cluster['cluster']}",
        "cluster": int(cluster["cluster"]),
        "anchor_cpu": int(cluster["anchor_cpu"]),
        "title": cluster.get("title"),
        "residency": [
            {
                "freq_mhz": int(r["freq_mhz"]),
                "freq_khz": int(r["freq_mhz"]) * 1000,
                "ratio_pct": float(r["ratio_pct"]),
                "ratio": round(float(r["ratio_pct"]) / 100.0, 4),
            }
            for r in residency
        ],
        "top_residency": residency_sorted[:5],
        "weighted_avg_freq_mhz": _weighted_avg_mhz(residency),
        "max_freq_mhz": max_freq or None,
        "high_band_ratio_pct": high_band_pct,
        "low_band_ratio_pct": low_band_pct,
        "peak_freq_mhz": int(peak["freq_mhz"]) if peak else None,
        "peak_ratio_pct": peak_pct if peak else None,
        "flags": {
            "fixed_freq": fixed,
            "raised_floor": raised_floor,
            "sustained_high_freq": sustained_high,
        },
    }


def summarize_limit_policy(clusters: list[dict[str, Any]]) -> dict[str, Any]:
    evidence: list[str] = []
    has_fixed = False
    has_raised = False
    high_clusters: list[str] = []
    for c in clusters:
        flags = c.get("flags") or {}
        name = c["name"]
        if flags.get("fixed_freq"):
            has_fixed = True
            evidence.append(
                f"{name} peak {c.get('peak_freq_mhz')}MHz residency {c.get('peak_ratio_pct')}%"
            )
        if flags.get("raised_floor"):
            has_raised = True
            evidence.append(
                f"{name} weighted avg {c.get('weighted_avg_freq_mhz')}MHz with low-band {c.get('low_band_ratio_pct')}%"
            )
        if flags.get("sustained_high_freq"):
            high_clusters.append(name)
            evidence.append(
                f"{name} high-band residency {c.get('high_band_ratio_pct')}% "
                f"(peak {c.get('peak_freq_mhz')}MHz @ {c.get('peak_ratio_pct')}%)"
            )
    return {
        "has_fixed_freq": has_fixed,
        "has_raised_floor": has_raised,
        "high_freq_clusters": high_clusters,
        "evidence": evidence,
    }


def summarize_findings(
    *,
    cpu_loading: list[dict[str, Any]],
    clusters: list[dict[str, Any]],
    top_processes: list[dict[str, Any]],
    limit_policy: dict[str, Any],
    cpu_power: dict[str, Any] | None = None,
) -> dict[str, Any]:
    avg_loading = None
    if cpu_loading:
        vals = [float(x["loading_pct"]) for x in cpu_loading if x.get("loading_pct") is not None]
        if vals:
            avg_loading = round(sum(vals) / len(vals), 2)
    top_proc = top_processes[0] if top_processes else None
    parts: list[str] = []
    if avg_loading is not None:
        parts.append(f"avg CPU loading {avg_loading}%")
    if limit_policy.get("high_freq_clusters"):
        parts.append("high-freq: " + ",".join(limit_policy["high_freq_clusters"]))
    if limit_policy.get("has_fixed_freq"):
        parts.append("fixed-freq suspected")
    if limit_policy.get("has_raised_floor"):
        parts.append("raised-floor suspected")
    if top_proc:
        parts.append(f"top process {top_proc.get('pname')} loading={top_proc.get('loading')}")
    if cpu_power and cpu_power.get("status") == "ok":
        parts.append(
            f"est CPU {cpu_power.get('est_cpu_power_mW')}mW/"
            f"{cpu_power.get('est_cpu_current_mA')}mA@"
            f"{cpu_power.get('vdd_v')}V ({cpu_power.get('platform')})"
        )
    return {
        "summary": "; ".join(parts) if parts else "parsed perf-statistic.html",
        "avg_cpu_loading_pct": avg_loading,
        "top_process": top_proc,
    }


def analyze_perf_html(
    perf_html: Path | str,
    *,
    thresholds: dict[str, float] | None = None,
    soc_model: str = "",
    window_meta: dict[str, Any] | None = None,
    energy_xlsx: Path | str | None = None,
    vdd_v: float = 4.0,
) -> dict[str, Any]:
    thresholds = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    parsed = parse_perf_statistic_html(perf_html)
    if parsed.get("status") != "ok":
        return {
            "status": "failed",
            "coverage": "failed",
            "skill": "game_trace",
            "source": {
                "perf_html": str(perf_html),
                "format": parsed.get("format"),
                "converter": "mtk_performance_tools",
            },
            "error": parsed.get("error") or "parse_failed",
            "raw": parsed,
        }

    clusters = [_normalize_cluster(c, thresholds) for c in (parsed.get("clusters") or [])]
    limit_policy = summarize_limit_policy(clusters)
    cpu_loading = parsed.get("cpu_loading") or []

    try:
        cpu_power = estimate_cpu_power_from_html(
            cpu_loading=cpu_loading,
            clusters=clusters,
            soc_model=soc_model,
            xlsx=energy_xlsx,
            vdd_v=vdd_v,
        )
    except EnergyModelError as exc:
        cpu_power = {
            "status": "failed",
            "error": str(exc),
            "model": soc_model or None,
        }

    findings = summarize_findings(
        cpu_loading=cpu_loading,
        clusters=clusters,
        top_processes=parsed.get("top_processes") or [],
        limit_policy=limit_policy,
        cpu_power=cpu_power,
    )

    # boost attribution needs main-log correlation; HTML alone cannot confirm trigger.
    boost_attribution = {
        "primary_trigger": None,
        "confidence": "low",
        "note": "perf-statistic.html 为聚合结果，无法单独确认提频触发源；需与 main log touch_boost/perfLockAcq 交叉",
        "evidence": [],
    }

    return {
        "status": "ok",
        "coverage": "full" if clusters else "partial",
        "skill": "game_trace",
        "source": {
            "perf_html": str(Path(perf_html).resolve()),
            "format": "mtk_perf_statistic_bokeh",
            "converter": "mtk_performance_tools",
            "soc_model": soc_model or None,
        },
        "time_window": window_meta
        or {
            "note": "HTML 来自短时 trace 聚合（通常数秒），不必与 T_game 对齐",
            "coverage": "short_trace_sample",
        },
        "thresholds": thresholds,
        "cpu_loading": cpu_loading,
        "cpu_frequency_distribution": {"clusters": clusters},
        "limit_policy": limit_policy,
        "cpu_power": cpu_power,
        "boost_attribution": boost_attribution,
        "threads": parsed.get("threads") or [],
        "top_threads": parsed.get("top_threads") or parsed.get("threads") or [],
        "thread_cluster_stats": parsed.get("thread_cluster_stats") or {},
        "top_processes": parsed.get("top_processes") or [],
        "findings": findings,
        "raw_tables": {
            "figures": parsed.get("figures") or [],
        },
    }


def resolve_perf_html(
    *,
    perf_html: Path | None = None,
    trace_path: Path | None = None,
) -> Path | None:
    """Prefer explicit HTML; if trace_path points to .html use it; else look beside trace."""
    if perf_html and Path(perf_html).is_file():
        return Path(perf_html)
    if not trace_path:
        return None
    tp = Path(trace_path)
    if tp.is_file() and tp.suffix.lower() in {".html", ".htm"}:
        return tp
    if tp.is_file():
        sibling = tp.with_name("perf-statistic.html")
        if sibling.is_file():
            return sibling
        parent_html = tp.parent / "perf-statistic.html"
        if parent_html.is_file():
            return parent_html
        # Common layout: <name>-perfresult/perf-statistic.html next to trace
        for cand in tp.parent.glob("*-perfresult/perf-statistic.html"):
            return cand
    if tp.is_dir():
        direct = tp / "perf-statistic.html"
        if direct.is_file():
            return direct
    return None


def analyze_game_trace(
    *,
    perf_html: Path | None = None,
    trace_path: Path | None = None,
    soc_model: str = "",
    window_meta: dict[str, Any] | None = None,
    thresholds: dict[str, float] | None = None,
    energy_xlsx: Path | str | None = None,
    vdd_v: float = 4.0,
) -> dict[str, Any]:
    html = resolve_perf_html(perf_html=perf_html, trace_path=trace_path)
    if html is None:
        return {
            "status": "missing",
            "coverage": "missing",
            "skill": "game_trace",
            "source": {
                "perf_html": str(perf_html) if perf_html else None,
                "trace_path": str(trace_path) if trace_path else None,
            },
            "note": "未提供 perf-statistic.html；可用 MTK 工具从 trace 转换后传入 --perf-html",
            "limit_policy": {
                "has_fixed_freq": False,
                "has_raised_floor": False,
                "high_freq_clusters": [],
                "evidence": [],
            },
            "cpu_power": {
                "status": "skipped",
                "reason": "perf_html_missing",
            },
            "boost_attribution": {
                "primary_trigger": None,
                "confidence": "low",
                "evidence": [],
            },
        }
    result = analyze_perf_html(
        html,
        thresholds=thresholds,
        soc_model=soc_model,
        window_meta=window_meta,
        energy_xlsx=energy_xlsx,
        vdd_v=vdd_v,
    )
    if trace_path:
        result.setdefault("source", {})["trace_path"] = str(Path(trace_path).resolve())
    return result


def to_step3_summary(trace_result: dict[str, Any]) -> dict[str, Any]:
    """Compact payload for game_cpu_gpu_ddr.step3_trace."""
    status = str(trace_result.get("status") or "pending")
    coverage = str(trace_result.get("coverage") or status)
    limit_policy = trace_result.get("limit_policy") or {}
    findings = trace_result.get("findings") or {}
    clusters = ((trace_result.get("cpu_frequency_distribution") or {}).get("clusters")) or []
    cpu_power = trace_result.get("cpu_power") or {}
    power_summary = None
    if cpu_power.get("status") == "ok":
        power_summary = {
            "status": "ok",
            "model": cpu_power.get("model"),
            "platform": cpu_power.get("platform"),
            "vdd_v": cpu_power.get("vdd_v"),
            "little_cluster_mW": cpu_power.get("little_cluster_mW"),
            "little_cluster_mA": cpu_power.get("little_cluster_mA"),
            "big_cluster_mW": cpu_power.get("big_cluster_mW"),
            "big_cluster_mA": cpu_power.get("big_cluster_mA"),
            "est_cpu_power_mW": cpu_power.get("est_cpu_power_mW"),
            "est_cpu_current_mA": cpu_power.get("est_cpu_current_mA"),
            "freq_match_warnings": len(cpu_power.get("freq_match_warnings") or []),
        }
    elif cpu_power:
        power_summary = {
            "status": cpu_power.get("status"),
            "reason": cpu_power.get("reason"),
            "error": cpu_power.get("error"),
            "note": cpu_power.get("note"),
        }
    return {
        "coverage": coverage,
        "status": status,
        "skill": "game_trace",
        "summary": findings.get("summary"),
        "trace_path": (trace_result.get("source") or {}).get("trace_path"),
        "perf_html": (trace_result.get("source") or {}).get("perf_html"),
        "frequency_distribution": {
            "clusters": [
                {
                    "name": c.get("name"),
                    "cluster": c.get("cluster"),
                    "weighted_avg_freq_mhz": c.get("weighted_avg_freq_mhz"),
                    "peak_freq_mhz": c.get("peak_freq_mhz"),
                    "peak_ratio_pct": c.get("peak_ratio_pct"),
                    "high_band_ratio_pct": c.get("high_band_ratio_pct"),
                    "flags": c.get("flags"),
                }
                for c in clusters
            ]
        },
        "throttle_strategy": {
            "has_fixed_freq": bool(limit_policy.get("has_fixed_freq")),
            "has_raised_floor": bool(limit_policy.get("has_raised_floor")),
            "evidence": list(limit_policy.get("evidence") or []),
        },
        "cpu_power": power_summary,
        "boost_attribution": trace_result.get("boost_attribution"),
        "high_freq_clusters": list(limit_policy.get("high_freq_clusters") or []),
        "cpu_loading": trace_result.get("cpu_loading") or [],
        "top_processes": (trace_result.get("top_processes") or [])[:5],
        "thread_cluster_stats": trace_result.get("thread_cluster_stats") or {},
        "top_threads": (trace_result.get("top_threads") or [])[:15],
        "note": trace_result.get("note"),
    }
