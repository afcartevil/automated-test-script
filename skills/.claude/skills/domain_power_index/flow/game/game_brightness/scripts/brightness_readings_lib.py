"""统一亮度采样与三阶段分析（测试前末值 / 启动20s / 游戏内变光）。"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

CURVE_SOURCES = frozenset({"hwc_brightness_val", "lcm_backlight_curve", "aal_service_bl"})
LEVEL_SOURCES = frozenset({"brightness_collector", "brightness_synchronizer"})


def _log_files(logs: dict[str, list[Path]], log_names: list[str]) -> list[Path]:
    out: list[Path] = []
    for name in log_names:
        out.extend(logs.get(name, []))
    return out


def _pct(value: int | float, max_v: int) -> float:
    return round(100.0 * float(value) / max_v, 1)


def collect_brightness_readings(
    logs: dict[str, list[Path]],
    patterns_cfg: dict[str, Any],
    extract_ts: Callable[..., Any],
    iter_lines: Callable[[Path], Any],
    *,
    curve_max: int = 4095,
    level_max: int = 255,
) -> list[dict[str, Any]]:
    """扫描 brightness_readings 类别，产出归一化采样列表。"""
    cat = (patterns_cfg.get("categories") or {}).get("brightness_readings") or {}
    readings: list[dict[str, Any]] = []

    for pat in cat.get("patterns") or []:
        if not isinstance(pat, dict) or str(pat.get("status", "active")) != "active":
            continue
        pat_id = str(pat.get("id", ""))
        log_names = pat.get("logs") or []
        keywords = [str(k) for k in (pat.get("keywords") or [])]
        regex_s = str(pat.get("regex") or "").strip()
        if not regex_s:
            continue
        compiled = re.compile(regex_s)
        value_kind = str(pat.get("value_kind") or "")

        for path in _log_files(logs, log_names):
            for line_no, line in iter_lines(path):
                if keywords and not all(kw in line for kw in keywords):
                    continue
                m = compiled.search(line)
                if not m:
                    continue
                ts_raw, dt = extract_ts(line)
                if not dt:
                    continue
                fields = {k: v for k, v in m.groupdict().items() if v is not None}
                entry: dict[str, Any] = {
                    "pattern_id": pat_id,
                    "source": pat_id,
                    "time": ts_raw or str(dt),
                    "dt": dt,
                    "file": path.name,
                    "line": line_no,
                    "raw_evidence": f"{path.name}:{line_no}: {line.strip()[:320]}",
                    "value_kind": value_kind,
                }
                if value_kind == "level_255":
                    try:
                        entry["brightness_level"] = int(fields["level"])
                        entry["brightness_level_pct"] = _pct(entry["brightness_level"], level_max)
                    except (KeyError, TypeError, ValueError):
                        continue
                elif value_kind == "curve_4095":
                    try:
                        curve = int(fields.get("curve") or fields.get("level") or 0)
                    except (TypeError, ValueError):
                        continue
                    entry["curve_val"] = curve
                    entry["curve_pct"] = _pct(curve, curve_max)
                    if fields.get("mapped") is not None:
                        try:
                            entry["mapped_level"] = int(fields["mapped"])
                        except (TypeError, ValueError):
                            pass
                    if fields.get("ratio") is not None:
                        try:
                            ratio = float(fields["ratio"])
                            entry["brightness_ratio"] = ratio
                            entry["brightness_ratio_pct"] = _pct(ratio, 1.0)
                        except (TypeError, ValueError):
                            pass
                else:
                    continue
                readings.append(entry)

    readings.sort(key=lambda r: r.get("dt") or datetime.min)
    return readings


def _last_before(readings: list[dict[str, Any]], boundary: datetime) -> dict[str, Any] | None:
    pre = [r for r in readings if r.get("dt") and r["dt"] < boundary]
    return pre[-1] if pre else None


def _build_pre_game_setting(
    readings: list[dict[str, Any]],
    game_start: datetime,
    *,
    curve_max: int,
    level_max: int,
) -> dict[str, Any]:
    """游戏开始前最后一次亮度读值（多源按时间取最后一条）。"""
    last = _last_before(readings, game_start)
    by_source: dict[str, Any] = {}
    for src in (*CURVE_SOURCES, *LEVEL_SOURCES):
        matched = [r for r in readings if r.get("pattern_id") == src and r.get("dt") and r["dt"] < game_start]
        if matched:
            item = matched[-1]
            by_source[src] = {
                "time": item.get("time"),
                "brightness_level": item.get("brightness_level"),
                "brightness_level_pct": item.get("brightness_level_pct"),
                "curve_val": item.get("curve_val"),
                "curve_pct": item.get("curve_pct"),
                "brightness_ratio": item.get("brightness_ratio"),
                "raw_evidence": item.get("raw_evidence"),
            }

    if not last:
        return {"coverage": "missing", "last": None, "by_source": by_source}

    # 测试设置亮度：优先 BrightnessCollector，备用 BrightnessSynchronizer
    primary = by_source.get("brightness_collector") or by_source.get("brightness_synchronizer")
    if primary:
        summary: dict[str, Any] = {
            "coverage": "ok",
            "time": primary.get("time"),
            "pattern_id": "brightness_collector" if by_source.get("brightness_collector") else "brightness_synchronizer",
            "raw_evidence": primary.get("raw_evidence"),
            "by_source": by_source,
            "brightness_level": primary.get("brightness_level"),
            "brightness_level_pct": primary.get("brightness_level_pct"),
        }
        if last.get("curve_val") is not None:
            summary["curve_val"] = last.get("curve_val")
            summary["curve_pct"] = last.get("curve_pct")
            summary["curve_max"] = curve_max
        return summary

    summary: dict[str, Any] = {
        "coverage": "ok",
        "time": last.get("time"),
        "pattern_id": last.get("pattern_id"),
        "raw_evidence": last.get("raw_evidence"),
        "by_source": by_source,
    }
    if last.get("brightness_level") is not None:
        summary["brightness_level"] = last["brightness_level"]
        summary["brightness_level_pct"] = last.get("brightness_level_pct")
    if last.get("curve_val") is not None:
        summary["curve_val"] = last["curve_val"]
        summary["curve_pct"] = last.get("curve_pct")
        summary["curve_max"] = curve_max
    if last.get("brightness_ratio") is not None:
        summary["brightness_ratio"] = last["brightness_ratio"]
    return summary


def _filter_window(
    readings: list[dict[str, Any]],
    start: datetime,
    end: datetime,
    *,
    curve_only: bool = True,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in readings:
        dt = r.get("dt")
        if not dt or dt < start or dt > end:
            continue
        if curve_only and r.get("curve_val") is None:
            continue
        out.append(r)
    return out


def _collapse_same_timestamp(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for sample in samples:
        if out and out[-1].get("dt") == sample.get("dt"):
            out[-1] = sample
        else:
            out.append(sample)
    return out


def _dedupe_consecutive_curve(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for sample in samples:
        if out and out[-1].get("curve_val") == sample.get("curve_val"):
            continue
        out.append(sample)
    return out


def detect_curve_change_phases(
    samples: list[dict[str, Any]],
    *,
    burst_gap_seconds: float = 2.0,
    min_curve_delta: int = 20,
) -> list[dict[str, Any]]:
    """ms 级连续变化合并为一段：记录 min/max 与时长；多段分别输出。"""
    if len(samples) < 2:
        return []

    collapsed = _dedupe_consecutive_curve(_collapse_same_timestamp(samples))
    if len(collapsed) < 2:
        return []

    phases: list[dict[str, Any]] = []
    i = 0
    n = len(collapsed)
    while i < n - 1:
        j = i + 1
        while j < n:
            gap = (collapsed[j]["dt"] - collapsed[j - 1]["dt"]).total_seconds()
            if gap > burst_gap_seconds:
                break
            j += 1
        block = collapsed[i:j]
        if len(block) >= 2:
            vals = [int(b["curve_val"]) for b in block]
            vmin, vmax = min(vals), max(vals)
            dur = (block[-1]["dt"] - block[0]["dt"]).total_seconds()
            if vmax - vmin >= min_curve_delta or (len(block) >= 3 and dur > 0):
                phases.append(
                    {
                        "phase_type": "burst",
                        "time_start": block[0].get("time"),
                        "time_end": block[-1].get("time"),
                        "duration_seconds": round(dur, 3),
                        "curve_min": vmin,
                        "curve_max": vmax,
                        "curve_delta": vmax - vmin,
                        "sample_count": len(block),
                        "sources": sorted({str(b.get("pattern_id")) for b in block}),
                        "raw_evidence_start": block[0].get("raw_evidence"),
                        "raw_evidence_end": block[-1].get("raw_evidence"),
                    }
                )
        elif i + 1 < n:
            a, b = collapsed[i], collapsed[i + 1]
            gap = (b["dt"] - a["dt"]).total_seconds()
            if gap > burst_gap_seconds:
                delta = abs(int(b["curve_val"]) - int(a["curve_val"]))
                if delta >= min_curve_delta:
                    phases.append(
                        {
                            "phase_type": "step",
                            "time_start": a.get("time"),
                            "time_end": b.get("time"),
                            "duration_seconds": round(gap, 3),
                            "curve_min": min(int(a["curve_val"]), int(b["curve_val"])),
                            "curve_max": max(int(a["curve_val"]), int(b["curve_val"])),
                            "curve_delta": delta,
                            "sample_count": 2,
                            "sources": sorted({str(a.get("pattern_id")), str(b.get("pattern_id"))}),
                            "raw_evidence_start": a.get("raw_evidence"),
                            "raw_evidence_end": b.get("raw_evidence"),
                        }
                    )
        i = j if j > i else i + 1
    return phases


def build_brightness_analysis(
    readings: list[dict[str, Any]],
    game_start: datetime,
    game_end: datetime,
    *,
    launch_window_seconds: int = 20,
    burst_gap_seconds: float = 2.0,
    min_curve_delta: int = 20,
    curve_max: int = 4095,
    level_max: int = 255,
) -> dict[str, Any]:
    launch_end = game_start + timedelta(seconds=launch_window_seconds)
    in_game_start = launch_end

    pre_game = _build_pre_game_setting(
        readings, game_start, curve_max=curve_max, level_max=level_max
    )
    launch_samples = _filter_window(readings, game_start, launch_end)
    in_game_samples = _filter_window(readings, in_game_start, game_end)

    launch_phases = detect_curve_change_phases(
        launch_samples,
        burst_gap_seconds=burst_gap_seconds,
        min_curve_delta=min_curve_delta,
    )
    in_game_phases = detect_curve_change_phases(
        in_game_samples,
        burst_gap_seconds=burst_gap_seconds,
        min_curve_delta=min_curve_delta,
    )

    def _window_stats(samples: list[dict[str, Any]]) -> dict[str, Any]:
        vals = [int(s["curve_val"]) for s in samples if s.get("curve_val") is not None]
        if not vals:
            return {"sample_count": 0, "curve_min": None, "curve_max": None}
        return {
            "sample_count": len(samples),
            "curve_min": min(vals),
            "curve_max": max(vals),
            "curve_min_pct": _pct(min(vals), curve_max),
            "curve_max_pct": _pct(max(vals), curve_max),
        }

    return {
        "curve_max": curve_max,
        "level_max": level_max,
        "pre_game_setting": pre_game,
        "launch_window": {
            "start": str(game_start),
            "end": str(launch_end),
            "window_seconds": launch_window_seconds,
            "stats": _window_stats(launch_samples),
            "phases": launch_phases,
            "phase_count": len(launch_phases),
        },
        "in_game_changes": {
            "start": str(in_game_start),
            "end": str(game_end),
            "stats": _window_stats(in_game_samples),
            "phases": in_game_phases,
            "phase_count": len(in_game_phases),
        },
        "reading_count": len(readings),
    }
