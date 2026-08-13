"""flow_power_game 步骤 8：CPU（[K]）+ GPU/DDR 频率策略 + perfLockAcq + 图层帧率。

输出 JSON（game_cpu_gpu_ddr.json）:
  kernel_cpu: game_kernel_cpu 全量结果
  frequency: PowerHAL/GPU/DVFSRC/thermalux 统计
  cpu_perf_lock: perfLockAcq 按 idx 策略统计（T_game）
  frame_rate: BufferQueueProducer 各图层 queueBuffer fps（T_game）
  status, notes
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from cpu_gpu_ddr_investigation_lib import build_cpu_gpu_ddr_investigation  # noqa: E402
from game_kernel_cpu_lib import analyze_game_kernel_cpu

_EVIDENCE_CAP = 30
_DEFAULT_BELOW_AVG_MIN_CONSECUTIVE = 3

PERF_LOCK_ACQ_RE = re.compile(
    r"\[perfLockAcq\]\s+idx:(?P<idx>\d+)\s+hdl:(?P<hdl>\d+)\s+hint:(?P<hint>-?\d+)\s+"
    r"pid:(?P<pid>\d+)\s+tid:(?P<tid>\d+)\s+duration:(?P<duration>\d+)\s+"
    r"lock_user:(?P<lock_user>[^=]+?)\s+=>\s+ret_hdl:(?P<ret_hdl>\d+)"
)
BUFFER_QUEUE_RE = re.compile(
    r"BufferQueueProducer: \[(?P<layer>.+?)\]\(this:.*?queueBuffer:\s+"
    r"fps=(?P<fps>[-\d.]+)\s+dur=(?P<dur>[-\d.]+)\s+max=(?P<max>[-\d.]+)\s+min=(?P<min>[-\d.]+)"
)


def _ref_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "references"


def _load_idx_labels() -> dict[str, str]:
    path = _ref_dir() / "keyword-patterns.yaml"
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8", errors="replace")
    labels: dict[str, str] = {}
    in_block = False
    for line in text.splitlines():
        if line.strip() == "perf_lock_idx_labels:":
            in_block = True
            continue
        if in_block:
            if not line.startswith("  "):
                break
            m = re.match(r'\s+"?(\d+)"?:\s*(.+)\s*$', line)
            if m:
                labels[m.group(1)] = m.group(2).strip()
    return labels


def _safe_float(val: str | float | None) -> float:
    try:
        return float(val)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _package_from_layer(layer: str) -> str:
    text = layer.strip()
    m = re.search(r"\[([^/\]]+)/", text)
    if m:
        return m.group(1)
    m = re.match(r"^([\w.]+)/", text)
    if m:
        return m.group(1)
    if text.startswith("com."):
        return text.split("/")[0].split("#")[0]
    return text.split("#")[0]


def _layer_short_label(layer: str) -> str:
    """从完整 layer 名提取短说明，用于同包名区分（如 SurfaceView#537）。"""
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


def _load_below_avg_min_consecutive() -> int:
    path = _ref_dir() / "analysis-standards.yaml"
    if not path.is_file():
        return _DEFAULT_BELOW_AVG_MIN_CONSECUTIVE
    text = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"below_avg_min_consecutive_samples:\s*(\d+)", text)
    return int(m.group(1)) if m else _DEFAULT_BELOW_AVG_MIN_CONSECUTIVE


def _time_to_second_precision(ts: datetime | None = None, raw: str | None = None) -> str:
    if isinstance(ts, datetime):
        return ts.strftime("%m-%d %H:%M:%S")
    text = (raw or "").strip()
    if not text:
        return ""
    dot = text.find(".")
    if dot != -1:
        return text[:dot]
    return text


def _build_fps_timeline(
    samples: list[dict[str, Any]],
    *,
    max_points: int = 360,
) -> list[dict[str, Any]]:
    """按时间序列化 fps 曲线点（不含 datetime，便于写 JSON）。"""
    ordered = _sort_samples_by_time(samples)
    points: list[dict[str, Any]] = []
    for s in ordered:
        fps = s.get("fps")
        if fps is None:
            continue
        points.append(
            {
                "time": _time_to_second_precision(s.get("ts"), s.get("time")),
                "time_raw": str(s.get("time") or ""),
                "fps": round(float(fps), 2),
            }
        )
    if len(points) <= max_points or max_points <= 2:
        return points
    last_i = len(points) - 1
    dedup: list[dict[str, Any]] = []
    prev_idx = -1
    for i in range(max_points):
        idx = int(round(i * last_i / (max_points - 1)))
        if idx == prev_idx:
            continue
        dedup.append(points[idx])
        prev_idx = idx
    return dedup


def _build_fps_curve_table(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按秒聚合：时间 | avg/min/max fps | 采样数（曲线表）。"""
    buckets: dict[str, list[float]] = {}
    order: list[str] = []
    for p in points:
        t = str(p.get("time") or "").strip() or "—"
        if t not in buckets:
            buckets[t] = []
            order.append(t)
        try:
            buckets[t].append(float(p["fps"]))
        except (TypeError, ValueError, KeyError):
            continue
    rows: list[dict[str, Any]] = []
    for t in order:
        vals = buckets.get(t) or []
        if not vals:
            continue
        rows.append(
            {
                "time": t,
                "avg_fps": round(sum(vals) / len(vals), 2),
                "min_fps": round(min(vals), 2),
                "max_fps": round(max(vals), 2),
                "sample_count": len(vals),
            }
        )
    return rows


def _sort_samples_by_time(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def _key(s: dict[str, Any]) -> tuple[int, str]:
        ts = s.get("ts")
        if isinstance(ts, datetime):
            return (0, ts.isoformat())
        return (1, str(s.get("time") or ""))

    return sorted(samples, key=_key)


def _period_duration_seconds(run: list[dict[str, Any]]) -> int | None:
    t0 = run[0].get("ts")
    t1 = run[-1].get("ts")
    if not isinstance(t0, datetime) or not isinstance(t1, datetime):
        return None
    t0s = t0.replace(microsecond=0)
    t1s = t1.replace(microsecond=0)
    tail_s = int(round(float(run[-1].get("dur") or 1000.0) / 1000.0))
    return max(0, int((t1s - t0s).total_seconds()) + tail_s)


def _find_below_avg_fps_periods(
    samples: list[dict[str, Any]],
    min_consecutive: int = 3,
) -> tuple[float, list[dict[str, Any]]]:
    """找出连续低于图层平均 fps 的时段（含 min_consecutive 次采样）。"""
    ordered = _sort_samples_by_time(samples)
    if len(ordered) < min_consecutive:
        return 0.0, []

    fps_vals = [float(s["fps"]) for s in ordered if s.get("fps") is not None]
    if not fps_vals:
        return 0.0, []
    layer_avg = sum(fps_vals) / len(fps_vals)

    periods: list[dict[str, Any]] = []
    i = 0
    while i < len(ordered):
        fps = ordered[i].get("fps")
        if fps is None or float(fps) >= layer_avg:
            i += 1
            continue
        run_start = i
        while i < len(ordered):
            fv = ordered[i].get("fps")
            if fv is None or float(fv) >= layer_avg:
                break
            i += 1
        run = ordered[run_start:i]
        if len(run) < min_consecutive:
            continue
        run_fps = [float(s["fps"]) for s in run]
        period_avg = sum(run_fps) / len(run_fps)
        dur_s = _period_duration_seconds(run)
        periods.append(
            {
                "start": _time_to_second_precision(run[0].get("ts"), run[0].get("time")),
                "end": _time_to_second_precision(run[-1].get("ts"), run[-1].get("time")),
                "duration_seconds": dur_s,
                "sample_count": len(run),
                "avg_fps": round(period_avg, 2),
                "min_fps": round(min(run_fps), 2),
                "max_fps": round(max(run_fps), 2),
                "layer_avg_fps": round(layer_avg, 2),
            }
        )
    return round(layer_avg, 2), periods


def _summarize_below_avg_periods(periods: list[dict[str, Any]]) -> dict[str, Any]:
    total_dur = sum(float(p.get("duration_seconds") or 0) for p in periods)
    if not periods:
        return {
            "period_count": 0,
            "total_duration_seconds": 0,
            "weighted_avg_fps": None,
        }
    weighted = 0.0
    weight = 0.0
    for p in periods:
        d = int(p.get("duration_seconds") or 0)
        if d > 0:
            weighted += float(p.get("avg_fps") or 0) * d
            weight += d
    return {
        "period_count": len(periods),
        "total_duration_seconds": int(total_dur),
        "weighted_avg_fps": round(weighted / weight, 2) if weight > 0 else None,
    }


def _evidence(path: Path, line_no: int, line: str) -> str:
    return f"{path.name}:{line_no}: {line.rstrip()[:240]}"


def analyze_perf_lock_acq(
    logs: dict[str, list[Path]],
    start: datetime,
    end: datetime,
    pre_s: int,
    post_s: int,
    extract_ts: Callable[..., Any],
    iter_lines: Callable[[Path], Any],
    window_for: Callable[..., str | None],
) -> dict[str, Any]:
    """T_game 内 perfLockAcq 按 idx 策略聚合。"""
    idx_labels = _load_idx_labels()
    files = logs.get("main_log", []) + logs.get("sys_log", [])
    by_idx: dict[int, list[dict[str, Any]]] = defaultdict(list)
    evidence: list[str] = []
    total_t_game = 0

    for path in files:
        for line_no, line in iter_lines(path):
            if "perfLockAcq" not in line or "Done for hdl" in line:
                continue
            m = PERF_LOCK_ACQ_RE.search(line)
            if not m:
                continue
            _, ts = extract_ts(line)
            w = window_for(ts, start, end, pre_s, post_s)
            if w != "T_game":
                continue
            total_t_game += 1
            item = {
                "idx": int(m.group("idx")),
                "hdl": int(m.group("hdl")),
                "hint": int(m.group("hint")),
                "pid": int(m.group("pid")),
                "tid": int(m.group("tid")),
                "duration_ms": int(m.group("duration")),
                "lock_user": m.group("lock_user").strip(),
                "ret_hdl": int(m.group("ret_hdl")),
                "raw_evidence": _evidence(path, line_no, line),
            }
            by_idx[item["idx"]].append(item)
            if len(evidence) < _EVIDENCE_CAP:
                evidence.append(item["raw_evidence"])

    if not files:
        return {
            "coverage": "missing",
            "window": "T_game",
            "notes": ["main/sys 日志缺失，无法分析 perfLockAcq"],
            "by_strategy_idx": [],
        }
    if not by_idx:
        return {
            "coverage": "partial",
            "window": "T_game",
            "total_acquire_count": 0,
            "notes": ["T_game 内未匹配到 perfLockAcq 记录"],
            "by_strategy_idx": [],
            "raw_evidence": evidence,
        }

    strategies: list[dict[str, Any]] = []
    for idx in sorted(by_idx):
        rows = by_idx[idx]
        users = Counter(r["lock_user"] for r in rows if r.get("lock_user"))
        durations = [int(r["duration_ms"]) for r in rows]
        hints = sorted({int(r["hint"]) for r in rows})
        strategies.append(
            {
                "idx": idx,
                "label": idx_labels.get(str(idx), ""),
                "acquire_count": len(rows),
                "top_lock_user": users.most_common(1)[0][0] if users else "",
                "lock_users": dict(users.most_common(8)),
                "hint_values": hints,
                "duration_ms": {
                    "min": min(durations) if durations else None,
                    "max": max(durations) if durations else None,
                },
                "sample": rows[-1],
            }
        )
    strategies.sort(key=lambda x: int(x.get("acquire_count") or 0), reverse=True)

    return {
        "coverage": "ok",
        "window": "T_game",
        "total_acquire_count": total_t_game,
        "strategy_count": len(strategies),
        "by_strategy_idx": strategies,
        "raw_evidence": evidence,
        "notes": [f"T_game perfLockAcq 共 {total_t_game} 次，{len(strategies)} 种 idx 策略"],
    }


def analyze_frame_rate_layers(
    logs: dict[str, list[Path]],
    start: datetime,
    end: datetime,
    pre_s: int,
    post_s: int,
    game_package: str,
    extract_ts: Callable[..., Any],
    iter_lines: Callable[[Path], Any],
    window_for: Callable[..., str | None],
) -> dict[str, Any]:
    """T_game 内各 BufferQueueProducer 图层 queueBuffer fps 统计。"""
    min_consecutive = _load_below_avg_min_consecutive()
    files = logs.get("main_log", []) + logs.get("sys_log", [])
    by_layer: dict[str, list[dict[str, Any]]] = defaultdict(list)
    layer_last_evidence: dict[str, str] = {}
    evidence: list[str] = []

    for path in files:
        for line_no, line in iter_lines(path):
            m = BUFFER_QUEUE_RE.search(line)
            if not m:
                continue
            ts_raw, ts = extract_ts(line)
            w = window_for(ts, start, end, pre_s, post_s)
            if w != "T_game":
                continue
            layer = m.group("layer")
            sample = {
                "time": ts_raw or "",
                "ts": ts,
                "fps": _safe_float(m.group("fps")),
                "dur": _safe_float(m.group("dur")),
                "frame_interval_max_ms": _safe_float(m.group("max")),
                "frame_interval_min_ms": _safe_float(m.group("min")),
            }
            by_layer[layer].append(sample)
            ev = _evidence(path, line_no, line)
            layer_last_evidence[layer] = ev
            if len(evidence) < _EVIDENCE_CAP:
                evidence.append(ev)

    if not files:
        return {
            "coverage": "missing",
            "window": "T_game",
            "notes": ["main/sys 日志缺失，无法分析 BufferQueueProducer"],
            "layers": [],
        }
    if not by_layer:
        return {
            "coverage": "partial",
            "window": "T_game",
            "layer_count": 0,
            "notes": ["T_game 内未匹配到 BufferQueueProducer queueBuffer 记录"],
            "layers": [],
            "raw_evidence": evidence,
        }

    layers: list[dict[str, Any]] = []
    game_merged_samples: list[dict[str, Any]] = []
    for layer, samples in by_layer.items():
        fps_vals = [s["fps"] for s in samples if s.get("fps") is not None]
        if not fps_vals:
            continue
        pkg = _package_from_layer(layer)
        interval_max = [s["frame_interval_max_ms"] for s in samples if s.get("frame_interval_max_ms")]
        interval_min = [s["frame_interval_min_ms"] for s in samples if s.get("frame_interval_min_ms")]
        is_game = bool(game_package and game_package in layer)
        _, below_periods = _find_below_avg_fps_periods(samples, min_consecutive)
        below_summary = _summarize_below_avg_periods(below_periods)
        timeline = _build_fps_timeline(samples)
        avg = round(sum(fps_vals) / len(fps_vals), 2)
        mn = round(min(fps_vals), 2)
        mx = round(max(fps_vals), 2)
        fluct_pct = round((mx - mn) / avg * 100.0, 2) if avg > 0 else None
        keep_timeline = avg >= 10.0
        if is_game:
            game_merged_samples.extend(samples)
        layers.append(
            {
                "package": pkg,
                "layer": layer,
                "layer_short": _layer_short_label(layer),
                "is_game_layer": is_game,
                "sample_count": len(samples),
                "avg_queuebuffer_fps": avg,
                "min_queuebuffer_fps": mn,
                "max_queuebuffer_fps": mx,
                "fps_fluctuation_pct": fluct_pct,
                "frame_interval_ms": {
                    "min": round(min(interval_min), 2) if interval_min else None,
                    "max": round(max(interval_max), 2) if interval_max else None,
                },
                "below_avg_fps_periods": below_periods,
                "below_avg_fps_summary": below_summary,
                "fps_timeline": timeline if keep_timeline else [],
                "fps_curve_table": _build_fps_curve_table(timeline) if keep_timeline else [],
                "raw_evidence": layer_last_evidence.get(layer),
            }
        )

    def _sort_key(item: dict[str, Any]) -> tuple[int, int]:
        game_first = 0 if item.get("is_game_layer") else 1
        return (game_first, -int(item.get("sample_count") or 0))

    layers.sort(key=_sort_key)

    main_game = next((x for x in layers if x.get("is_game_layer")), None)
    game_avg, game_below_periods = _find_below_avg_fps_periods(
        game_merged_samples,
        min_consecutive,
    )
    game_below_summary = _summarize_below_avg_periods(game_below_periods)
    game_timeline = _build_fps_timeline(game_merged_samples)
    game_curve_table = _build_fps_curve_table(game_timeline)
    if main_game:
        main_game = dict(main_game)
        main_game["below_avg_fps_periods_merged"] = game_below_periods
        main_game["below_avg_fps_summary_merged"] = game_below_summary
        main_game["merged_layer_avg_fps"] = game_avg
        main_game["fps_timeline"] = game_timeline
        main_game["fps_curve_table"] = game_curve_table

    notes = [f"T_game 捕获 {len(layers)} 个图层 queueBuffer 采样"]
    if game_below_periods:
        notes.append(
            f"游戏图层低于均值（连续≥{min_consecutive}次）共 {game_below_summary['period_count']} 段，"
            f"合计约 {game_below_summary['total_duration_seconds']}s"
        )

    return {
        "coverage": "ok",
        "window": "T_game",
        "layer_count": len(layers),
        "main_game_layer": main_game,
        "game_below_avg_fps": {
            "min_consecutive_samples": min_consecutive,
            "layer_avg_fps": game_avg,
            "periods": game_below_periods,
            "summary": game_below_summary,
        },
        "fps_timeline": game_timeline,
        "fps_curve_table": game_curve_table,
        "layers": layers,
        "raw_evidence": evidence,
        "notes": notes,
    }


def analyze_frequency(
    logs: dict[str, list[Path]],
    start: datetime,
    end: datetime,
    pre_s: int,
    post_s: int,
    game_package: str,
    add_event: Callable[..., None],
    extract_ts: Callable[..., Any],
    iter_lines: Callable[[Path], Any],
    window_for: Callable[..., str | None],
    parse_main_sys: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    main_summary = parse_main_sys(
        logs.get("main_log", []) + logs.get("sys_log", []),
        events,
        start,
        end,
        pre_s,
        post_s,
        game_package,
    )
    game_events = [e for e in events if e.get("window") == "T_game"]
    by_cat = Counter(e.get("category", "") for e in game_events)

    notes: list[str] = []
    if not logs.get("main_log") and not logs.get("sys_log"):
        notes.append("main/sys 日志缺失，无法分析 PowerHAL/GPU/DDR 频率策略")
    else:
        notes.append(f"T_game PowerHAL 相关事件 {len(game_events)} 条")
        if by_cat.get("powerhal_cpu_freq"):
            notes.append(f"CPU cluster 约束记录 {by_cat['powerhal_cpu_freq']} 条")
        if by_cat.get("gpu_freq_policy"):
            notes.append(f"GPU 频率策略记录 {by_cat['gpu_freq_policy']} 条")
        if by_cat.get("dvfsrc_opp"):
            notes.append(f"DVFSRC opp 记录 {by_cat['dvfsrc_opp']} 条")

    gpu = main_summary.get("gpu_policy") or {}
    dvfsrc = main_summary.get("dvfsrc") or {}
    top_dvfsrc = dvfsrc.most_common(5) if hasattr(dvfsrc, "most_common") else []

    return {
        "cpu_frequency_stats": {
            "cluster_constraints": main_summary.get("cluster_constraints", {}),
            "powerhal_event_count": main_summary.get("powerhal_event_count", 0),
            "gpu_frequency_policy": gpu,
            "dvfsrc_opp_stats": [{"key": k, "count": c} for k, c in top_dvfsrc],
            "thermalux_requests": dict(main_summary.get("thermalux_requests", {})),
        },
        "t_game_event_counts": dict(by_cat),
        "notes": notes,
        "log_availability": {
            "main_log": bool(logs.get("main_log")),
            "sys_log": bool(logs.get("sys_log")),
        },
    }


def analyze_game_cpu_gpu_ddr(
    log_path: Path,
    start: datetime,
    end: datetime,
    *,
    game_package: str = "",
    pre_minutes: int = 5,
    post_minutes: int = 3,
    startup_seconds: int = 60,
    exit_seconds: int = 30,
    soc_model: str = "",
    trace_path: Path | None = None,
    perf_html: Path | None = None,
    discover_logs: Callable[..., dict[str, list[Path]]],
    extract_ts: Callable[..., Any],
    window_for: Callable[..., str | None],
    iter_lines: Callable[[Path], Any],
    fmt_time: Callable[[datetime | None], str],
    add_event: Callable[..., None],
    parse_kernel: Callable[..., dict[str, Any]],
    analyze_kernel_samples: Callable[..., dict[str, Any]],
    load_baseline_processes: Callable[[Path], dict[str, Any]],
    load_baseline_cpu_cores: Callable[[Path], dict[str, Any]],
    serialize_cpu_samples: Callable[..., list[dict[str, Any]]],
    parse_main_sys: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    pre_s = max(0, pre_minutes) * 60
    post_s = max(0, post_minutes) * 60
    logs = discover_logs(log_path)
    pkg = game_package.strip()

    kernel_result = analyze_game_kernel_cpu(
        log_path,
        start,
        end,
        game_package=pkg,
        soc_model=soc_model,
        pre_minutes=pre_minutes,
        post_minutes=post_minutes,
        startup_seconds=startup_seconds,
        exit_seconds=exit_seconds,
        discover_logs=discover_logs,
        parse_kernel=parse_kernel,
        analyze_kernel_samples=analyze_kernel_samples,
        serialize_cpu_samples=serialize_cpu_samples,
        load_baseline_processes=load_baseline_processes,
        load_baseline_cpu_cores=load_baseline_cpu_cores,
        add_event=add_event,
        fmt_time=fmt_time,
        extract_ts=extract_ts,
        iter_lines=iter_lines,
    )

    freq_result = analyze_frequency(
        logs,
        start,
        end,
        pre_s,
        post_s,
        pkg,
        add_event,
        extract_ts,
        iter_lines,
        window_for,
        parse_main_sys,
    )

    perf_lock = analyze_perf_lock_acq(
        logs,
        start,
        end,
        pre_s,
        post_s,
        extract_ts,
        iter_lines,
        window_for,
    )
    frame_rate = analyze_frame_rate_layers(
        logs,
        start,
        end,
        pre_s,
        post_s,
        pkg,
        extract_ts,
        iter_lines,
        window_for,
    )

    cpu_gpu_ddr_investigation = build_cpu_gpu_ddr_investigation(
        lib_file=Path(__file__),
        logs=logs,
        start=start,
        end=end,
        pre_s=pre_s,
        post_s=post_s,
        game_package=pkg,
        trace_path=trace_path,
        perf_html=perf_html,
        soc_model=soc_model,
        extract_ts=extract_ts,
        iter_lines=iter_lines,
        window_for=window_for,
    )

    notes = list(kernel_result.get("notes") or [])
    notes.extend(freq_result.get("notes") or [])
    notes.extend(perf_lock.get("notes") or [])
    notes.extend(frame_rate.get("notes") or [])
    notes.extend(cpu_gpu_ddr_investigation.get("warnings") or [])
    status = kernel_result.get("status", "partial")
    if status == "ok" and not logs.get("kernel_log"):
        status = "partial"

    return {
        "status": status,
        "log_path": str(log_path),
        "game_window": kernel_result.get("game_window"),
        "kernel_cpu": kernel_result,
        "frequency": freq_result,
        "cpu_perf_lock": perf_lock,
        "frame_rate": frame_rate,
        "cpu_gpu_ddr_investigation": cpu_gpu_ddr_investigation,
        "notes": notes,
    }
