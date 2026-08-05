"""游戏场景 CPU/GPU/DDR 五步排查（与 game_cpu_gpu_ddr/SKILL.md §2 对齐）。"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from skill_references import load_analysis_standards, threshold

_POWERHAL_CPU_RE = re.compile(r"libPowerHal: \[recordCPUFreqInfo\] set (?P<body>.+)")
_CLUSTER_RE = re.compile(
    r"cluster\[(?P<cluster>\d+)\]\s+min\((?P<min_source>[^)]*)\):\s*"
    r"(?P<min_value>-?\d+)\s+max\((?P<max_source>[^)]*)\):\s*(?P<max_value>-?\d+)"
)
_PERF_LOCK_RE = re.compile(
    r"\[perfLockAcq\]\s+idx:(?P<idx>\d+)\s+hdl:(?P<hdl>\d+)\s+hint:(?P<hint>-?\d+)\s+"
    r"pid:(?P<pid>\d+)\s+tid:(?P<tid>\d+)\s+duration:(?P<duration>\d+)\s+"
    r"lock_user:(?P<lock_user>[^=]+?)\s+=>\s+ret_hdl:(?P<ret_hdl>\d+)"
)
_DVFSRC_RE = re.compile(r"libPowerHal: \[setDvfsrcDevFreqOpp\] opp:(?P<opp>\d+),\s*freq:(?P<freq>\d+)")
_BUFFER_QUEUE_RE = re.compile(
    r"BufferQueueProducer: \[(?P<layer>.+?)\]\(this:.*?queueBuffer:\s+"
    r"fps=(?P<fps>[-\d.]+)\s+dur=(?P<dur>[-\d.]+)\s+max=(?P<max>[-\d.]+)\s+min=(?P<min>[-\d.]+)"
)
_THERMAL_ENGINE_RE = re.compile(
    r"\[tran_thermal_engine\].*?temp=(?P<temp>[\d.]+)C?.*?"
    r"fgPkg=(?P<fg_pkg>[^,]+).*?fgAct=(?P<fg_act>[^,]+).*?"
    r"limits\{(?P<limits>[^}]+)\}"
)
_LIMIT_KV_RE = re.compile(r"(\w+)=(\d+)")


def _ref_dir(from_file: Path) -> Path:
    return from_file.resolve().parent.parent / "references"


def _hz_label(hz: int) -> str:
    if hz == -1:
        return "不受限制"
    if hz >= 1_000_000:
        return f"{hz / 1_000_000:.2f}GHz"
    if hz >= 1_000:
        return f"{hz / 1_000:.0f}MHz"
    return f"{hz}Hz"


def _freq_ghz(hz: int) -> float:
    return round(hz / 1_000_000_000, 3)


def _parse_clusters(body: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in _CLUSTER_RE.finditer(body):
        out.append(
            {
                "cluster": int(m.group("cluster")),
                "min_source": m.group("min_source"),
                "min_hz": int(m.group("min_value")),
                "min_label": _hz_label(int(m.group("min_value"))),
                "max_source": m.group("max_source"),
                "max_hz": int(m.group("max_value")),
                "max_label": _hz_label(int(m.group("max_value"))),
            }
        )
    return out


def _is_touch_boost_line(line: str) -> bool:
    if "recordCPUFreqInfo" not in line:
        return False
    return "touch_boost" in line or "MTKPOWER_HINT_UX_SCROLLING" in line


def _parse_limits(limits_s: str) -> dict[str, int]:
    return {k: int(v) for k, v in _LIMIT_KV_RE.findall(limits_s)}


def _load_standard_layers(ref_dir: Path) -> list[str]:
    standards = load_analysis_standards(ref_dir)
    raw = standards.get("standard_ui_layers") or ""
    if isinstance(raw, str) and raw.strip():
        return [x.strip() for x in raw.split(",") if x.strip()]
    return [
        "StatusBar",
        "Taskbar",
        "NotificationShade",
        "ColorFade",
        "FramebufferSurface",
        "SmartPanel",
    ]


def _package_from_layer(layer: str) -> str:
    m = re.search(r"\[([^/\]]+)/", layer)
    if m:
        return m.group(1)
    if layer.startswith("com."):
        return layer.split("/")[0].split("#")[0]
    return layer.split("#")[0].split(" ")[0]


def _is_standard_layer(layer: str, standard_layers: list[str], game_package: str) -> bool:
    if game_package and game_package in layer:
        return True
    return any(name in layer for name in standard_layers)


def _fps_distribution(fps_vals: list[float], buckets: list[float]) -> list[dict[str, Any]]:
    if not fps_vals:
        return []
    sorted_b = sorted(buckets)
    counts = Counter()
    for fps in fps_vals:
        placed = False
        for i, upper in enumerate(sorted_b):
            lower = sorted_b[i - 1] if i > 0 else 0.0
            if lower < fps <= upper:
                counts[f"{lower}-{upper}"] += 1
                placed = True
                break
        if not placed:
            counts[f">{sorted_b[-1]}"] += 1
    total = len(fps_vals)
    return [
        {"range": k, "count": v, "pct": round(100.0 * v / total, 1)}
        for k, v in sorted(counts.items(), key=lambda x: x[0])
    ]


def _step1_touch_boost(
    main_files: list[Path],
    start: datetime,
    end: datetime,
    pre_s: int,
    post_s: int,
    *,
    extract_ts: Callable[..., Any],
    iter_lines: Callable[[Path], Any],
    window_for: Callable[..., str | None],
) -> dict[str, Any]:
    events: list[dict[str, Any]] = []

    for path in main_files:
        lines_buf: list[tuple[int, str, datetime | None, str | None]] = []
        for line_no, line in iter_lines(path):
            ts_raw, ts = extract_ts(line)
            if window_for(ts, start, end, pre_s, post_s) != "T_game":
                continue
            lines_buf.append((line_no, line, ts, ts_raw))

        for i, (line_no, line, ts, ts_raw) in enumerate(lines_buf):
            if not _is_touch_boost_line(line):
                continue
            m = _POWERHAL_CPU_RE.search(line)
            clusters = _parse_clusters(m.group("body")) if m else []
            perf_lock = None
            for j in range(i + 1, min(i + 8, len(lines_buf))):
                _, next_line, _, _ = lines_buf[j]
                if "Done for hdl" in next_line:
                    continue
                pm = _PERF_LOCK_RE.search(next_line)
                if pm:
                    dur = int(pm.group("duration"))
                    perf_lock = {
                        "idx": int(pm.group("idx")),
                        "duration_ms": dur,
                        "duration_seconds": round(dur / 1000.0, 1),
                        "lock_user": pm.group("lock_user").strip(),
                        "hint": int(pm.group("hint")),
                        "raw_evidence": lines_buf[j][1].strip()[:280],
                    }
                    break
            events.append(
                {
                    "time": ts_raw,
                    "clusters": clusters,
                    "perf_lock": perf_lock,
                    "raw_evidence": f"{path.name}:{line_no}: {line.strip()[:320]}",
                }
            )

    if not events:
        return {
            "coverage": "missing",
            "event_count": 0,
            "events": [],
            "note": "T_game 内未找到 touch_boost / UX_SCROLLING 滑动提频 recordCPUFreqInfo",
        }

    summary_clusters: dict[int, dict[str, Any]] = {}
    for ev in events:
        for c in ev.get("clusters") or []:
            cid = c["cluster"]
            if cid not in summary_clusters:
                summary_clusters[cid] = c

    return {
        "coverage": "ok",
        "event_count": len(events),
        "events": events[:30],
        "cluster_summary": list(summary_clusters.values()),
        "durations_ms": [e["perf_lock"]["duration_ms"] for e in events if e.get("perf_lock")],
    }


def _step2_ddr(
    main_files: list[Path],
    start: datetime,
    end: datetime,
    pre_s: int,
    post_s: int,
    *,
    extract_ts: Callable[..., Any],
    iter_lines: Callable[[Path], Any],
    window_for: Callable[..., str | None],
) -> dict[str, Any]:
    samples: list[dict[str, Any]] = []
    for path in main_files:
        for line_no, line in iter_lines(path):
            m = _DVFSRC_RE.search(line)
            if not m:
                continue
            ts_raw, ts = extract_ts(line)
            if window_for(ts, start, end, pre_s, post_s) != "T_game":
                continue
            freq = int(m.group("freq"))
            opp = int(m.group("opp"))
            samples.append(
                {
                    "time": ts_raw,
                    "opp": opp,
                    "freq_hz": freq,
                    "freq_ghz": _freq_ghz(freq),
                    "raw_evidence": f"{path.name}:{line_no}: {line.strip()[:280]}",
                }
            )

    if not samples:
        return {"coverage": "missing", "sample_count": 0, "samples": [], "opp_stats": []}

    opp_counter = Counter(s["opp"] for s in samples)
    freq_by_opp: dict[int, list[int]] = defaultdict(list)
    for s in samples:
        freq_by_opp[s["opp"]].append(s["freq_hz"])

    return {
        "coverage": "ok",
        "sample_count": len(samples),
        "samples": samples[-20:],
        "opp_stats": [
            {
                "opp": opp,
                "count": opp_counter[opp],
                "freq_hz_last": freq_by_opp[opp][-1],
                "freq_ghz_last": _freq_ghz(freq_by_opp[opp][-1]),
            }
            for opp in sorted(opp_counter)
        ],
        "freq_ghz_min": _freq_ghz(min(s["freq_hz"] for s in samples)),
        "freq_ghz_max": _freq_ghz(max(s["freq_hz"] for s in samples)),
    }


def _step3_trace(
    trace_path: Path | None,
    ref_dir: Path,
    *,
    perf_html: Path | None = None,
    soc_model: str = "",
    energy_xlsx: Path | None = None,
    vdd_v: float = 4.0,
) -> dict[str, Any]:
    """Delegate to game_trace (prefer MTK perf-statistic.html)."""
    try:
        from game_trace_lib import analyze_game_trace, to_step3_summary
    except ImportError:
        gtrace_scripts = Path(__file__).resolve().parent.parent.parent / "game_trace" / "scripts"
        import sys

        if str(gtrace_scripts) not in sys.path:
            sys.path.insert(0, str(gtrace_scripts))
        from game_trace_lib import analyze_game_trace, to_step3_summary

    standards = load_analysis_standards(ref_dir)
    trace_cfg = standards.get("trace") or {}
    result = analyze_game_trace(
        perf_html=perf_html,
        trace_path=trace_path,
        soc_model=soc_model,
        energy_xlsx=energy_xlsx,
        vdd_v=vdd_v,
    )
    out = to_step3_summary(result)
    out["trace_available"] = bool(
        (perf_html and Path(perf_html).is_file())
        or (trace_path and Path(trace_path).is_file())
        or out.get("perf_html")
    )
    if out.get("status") == "missing" and not out.get("trace_available"):
        out["coverage"] = str(trace_cfg.get("status", "pending"))
        out["note"] = (
            "未提供 perf-statistic.html / trace；"
            "用 MTK 工具转换后传 --perf-html，或放在 log_path/trace 旁"
        )
    return out


def _step4_frame_rate(
    main_files: list[Path],
    start: datetime,
    end: datetime,
    pre_s: int,
    post_s: int,
    game_package: str,
    ref_dir: Path,
    *,
    extract_ts: Callable[..., Any],
    iter_lines: Callable[[Path], Any],
    window_for: Callable[..., str | None],
) -> dict[str, Any]:
    standards = load_analysis_standards(ref_dir)
    fr_cfg = standards.get("frame_rate") or {}
    low_thresh = float(fr_cfg.get("low_fps_exclude_threshold", threshold(standards, "low_fps_exclude_threshold", 5.0)))
    buckets = [float(x) for x in (fr_cfg.get("distribution_buckets") or [5, 15, 30, 45, 60, 90, 120, 999])]
    standard_layers = _load_standard_layers(ref_dir)

    by_layer: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for path in main_files:
        for line_no, line in iter_lines(path):
            m = _BUFFER_QUEUE_RE.search(line)
            if not m:
                continue
            ts_raw, ts = extract_ts(line)
            if window_for(ts, start, end, pre_s, post_s) != "T_game":
                continue
            layer = m.group("layer")
            fps = float(m.group("fps"))
            by_layer[layer].append(
                {
                    "time": ts_raw,
                    "fps": fps,
                    "dur": float(m.group("dur")),
                    "raw_evidence": f"{path.name}:{line_no}: {line.strip()[:240]}",
                }
            )

    if not by_layer:
        return {"coverage": "missing", "layers": [], "game_layer": None}

    layers_out: list[dict[str, Any]] = []
    game_layers: list[dict[str, Any]] = []
    abnormal_layers: list[dict[str, Any]] = []
    excluded_low: list[str] = []

    for layer, samples in by_layer.items():
        fps_vals = [s["fps"] for s in samples]
        if fps_vals and max(fps_vals) <= low_thresh:
            excluded_low.append(layer)
            continue
        pkg = _package_from_layer(layer)
        is_game = bool(game_package and game_package in layer)
        is_std = _is_standard_layer(layer, standard_layers, game_package)
        item = {
            "layer": layer,
            "package": pkg,
            "is_game_layer": is_game,
            "is_standard_layer": is_std,
            "sample_count": len(samples),
            "avg_fps": round(sum(fps_vals) / len(fps_vals), 2),
            "min_fps": round(min(fps_vals), 2),
            "max_fps": round(max(fps_vals), 2),
            "fps_distribution": _fps_distribution(fps_vals, buckets),
            "samples": samples[-10:],
        }
        layers_out.append(item)
        if is_game:
            game_layers.append(item)
        elif not is_std:
            abnormal_layers.append(item)

    game_merged_fps: list[float] = []
    for gl in game_layers:
        for s in by_layer.get(gl["layer"], []):
            game_merged_fps.append(s["fps"])

    game_summary = None
    if game_merged_fps:
        game_summary = {
            "package": game_package,
            "layer_count": len(game_layers),
            "layers": [g["layer"] for g in game_layers],
            "avg_fps": round(sum(game_merged_fps) / len(game_merged_fps), 2),
            "min_fps": round(min(game_merged_fps), 2),
            "max_fps": round(max(game_merged_fps), 2),
            "fps_distribution": _fps_distribution(game_merged_fps, buckets),
            "sample_count": len(game_merged_fps),
        }

    other_layers = [x for x in layers_out if not x.get("is_game_layer")]
    return {
        "coverage": "ok",
        "low_fps_exclude_threshold": low_thresh,
        "excluded_low_fps_layers": excluded_low,
        "game_layer": game_summary,
        "other_layers": {
            "count": len(other_layers),
            "layers": other_layers,
        },
        "abnormal_extra_layers": abnormal_layers,
        "standard_layer_count": sum(1 for x in layers_out if x.get("is_standard_layer")),
        "layers": layers_out,
    }


def _step5_thermal_throttle(
    main_files: list[Path],
    start: datetime,
    end: datetime,
    pre_s: int,
    post_s: int,
    *,
    extract_ts: Callable[..., Any],
    iter_lines: Callable[[Path], Any],
    window_for: Callable[..., str | None],
) -> dict[str, Any]:
    hits: list[dict[str, Any]] = []
    for path in main_files:
        for line_no, line in iter_lines(path):
            if "tran_thermal_engine" not in line:
                continue
            m = _THERMAL_ENGINE_RE.search(line)
            if not m:
                continue
            ts_raw, ts = extract_ts(line)
            w = window_for(ts, start, end, pre_s, post_s) if ts else "other"
            limits = _parse_limits(m.group("limits"))
            c0 = limits.get("cluster0", 0)
            c1 = limits.get("cluster1", 0)
            throttled = c0 > 0 or c1 > 0 or limits.get("cpu", 0) > 0 or limits.get("gpu", 0) > 0
            hits.append(
                {
                    "time": ts_raw,
                    "window": w,
                    "temp_c": float(m.group("temp")),
                    "fg_package": m.group("fg_pkg").strip(),
                    "fg_activity": m.group("fg_act").strip(),
                    "limits": limits,
                    "cluster0_max_hz": c0,
                    "cluster1_max_hz": c1,
                    "cluster0_max_ghz": _freq_ghz(c0) if c0 > 0 else None,
                    "cluster1_max_ghz": _freq_ghz(c1) if c1 > 0 else None,
                    "throttled": throttled,
                    "raw_evidence": f"{path.name}:{line_no}: {line.strip()[:360]}",
                }
            )

    t_game_hits = [h for h in hits if h.get("window") == "T_game"]
    throttled_hits = [h for h in t_game_hits if h.get("throttled")]
    return {
        "coverage": "ok" if hits else "missing",
        "hit_count": len(hits),
        "t_game_hit_count": len(t_game_hits),
        "throttled_in_game": bool(throttled_hits),
        "throttled_hits": throttled_hits,
        "hits": hits[:30],
    }


def build_cpu_gpu_ddr_investigation(
    *,
    lib_file: Path,
    logs: dict[str, list[Path]],
    start: datetime,
    end: datetime,
    pre_s: int,
    post_s: int,
    game_package: str = "",
    trace_path: Path | None = None,
    perf_html: Path | None = None,
    soc_model: str = "",
    energy_xlsx: Path | None = None,
    vdd_v: float = 4.0,
    extract_ts: Callable[..., Any],
    iter_lines: Callable[[Path], Any],
    window_for: Callable[..., str | None],
) -> dict[str, Any]:
    ref_dir = _ref_dir(lib_file)
    main_files = logs.get("main_log", [])

    step1 = _step1_touch_boost(
        main_files, start, end, pre_s, post_s,
        extract_ts=extract_ts, iter_lines=iter_lines, window_for=window_for,
    )
    step2 = _step2_ddr(
        main_files, start, end, pre_s, post_s,
        extract_ts=extract_ts, iter_lines=iter_lines, window_for=window_for,
    )
    step3 = _step3_trace(
        trace_path,
        ref_dir,
        perf_html=perf_html,
        soc_model=soc_model,
        energy_xlsx=energy_xlsx,
        vdd_v=vdd_v,
    )
    step4 = _step4_frame_rate(
        main_files, start, end, pre_s, post_s, game_package, ref_dir,
        extract_ts=extract_ts, iter_lines=iter_lines, window_for=window_for,
    )
    step5 = _step5_thermal_throttle(
        main_files, start, end, pre_s, post_s,
        extract_ts=extract_ts, iter_lines=iter_lines, window_for=window_for,
    )

    warnings: list[str] = []
    if step1.get("coverage") != "ok":
        warnings.append("T_game 未检测到滑动提频 touch_boost 策略")
    if step2.get("coverage") != "ok":
        warnings.append("T_game 未检测到 DDR setDvfsrcDevFreqOpp 变化")
    if step4.get("abnormal_extra_layers"):
        warnings.append(f"检测到 {len(step4['abnormal_extra_layers'])} 个异常多出图层")
    if step5.get("throttled_in_game"):
        warnings.append("测试过程中 tran_thermal_engine 触发 CPU 限频")

    return {
        "flow_version": 1,
        "step1_touch_boost": step1,
        "step2_ddr": step2,
        "step3_trace": step3,
        "step4_frame_rate": step4,
        "step5_thermal_throttle": step5,
        "warnings": warnings,
    }
