"""电流图（pt5）与已有 CPU 分析结果结合：找出高低版本底电差异大的时段并关联 CPU。"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from pt5_reader import find_pt5_for_suffix, load_pt5_series
from utils import extract_suffix, find_test_report

# 看板电流图点数上限（分析仍用 32Hz 全序列，仅展示层降采样）
_MAX_CHART_POINTS = 6000
_DEFAULT_WINDOW_SEC = 10.0
_DEFAULT_WINDOW_STEP_SEC = 2.0
_DEFAULT_TOP_WINDOWS = 3
_DEFAULT_SEGMENT_INTERVAL_SEC = 10.0
_SEGMENT_PROC_COMPARE_LIMIT = 15
_BASELINE_PERCENTILE = 10.0
_BASELINE_TRIM_START_SEC = 10.0
_BASELINE_TRIM_END_SEC = 5.0


def _norm_suffix(suffix: object) -> str:
    return str(suffix or "").strip().lstrip("_")


def _rel_time_to_sec(rel: str) -> float | None:
    """解析 mm:ss 或 mm:ss–mm:ss 相对时间字符串为秒（取区间起点）。"""
    text = str(rel or "").strip()
    if not text:
        return None
    part = re.split(r"[-–—]", text)[0].strip()
    m = re.match(r"^(\d+):(\d{2})$", part)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    m = re.match(r"^(\d+):(\d{2}):(\d{2})$", part)
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
    return None


def _parse_scene_start(iso_str: str | None) -> datetime | None:
    if not iso_str:
        return None
    try:
        return pd.to_datetime(iso_str).to_pydatetime()
    except Exception:
        return None


def _block_relative_sec(item: dict, scene_start: datetime | None) -> float | None:
    """Perf 块相对场景起点的秒数：优先 CPU JSON 的 timestamp，其次 relative_time 字符串。"""
    ts = item.get("timestamp")
    if ts is not None and scene_start is not None:
        try:
            return max(0.0, round(float(ts) - scene_start.timestamp(), 2))
        except (TypeError, ValueError):
            pass
    parsed = _rel_time_to_sec(str(item.get("relative_time") or ""))
    return float(parsed) if parsed is not None else None


def _sec_to_rel_time(sec: float) -> str:
    sec = max(0, int(sec))
    return f"{sec // 60:02d}:{sec % 60:02d}"


def _load_scene_row(folder: str, suffix: str) -> dict[str, Any] | None:
    report = find_test_report(folder)
    if not report:
        return None
    df = pd.read_excel(
        report,
        sheet_name="report",
        usecols=["name", "desc", "starttime", "endtime", "duration_sec", "avg_cur", "avg_cur_4v"],
    )
    suf = _norm_suffix(suffix)
    for _, row in df.iterrows():
        name = str(row.get("name", "")).strip()
        if extract_suffix(name) == suf or name.endswith(f"_{suf}"):
            st = pd.to_datetime(row.get("starttime"))
            en = pd.to_datetime(row.get("endtime"))
            dur = row.get("duration_sec")
            if pd.isna(dur) or not dur:
                dur = (en - st).total_seconds()
            return {
                "name": name,
                "desc": str(row.get("desc", "") or ""),
                "starttime": st.isoformat(sep=" "),
                "endtime": en.isoformat(sep=" "),
                "duration_sec": float(dur),
                "avg_cur": float(row["avg_cur"]) if pd.notna(row.get("avg_cur")) else None,
                "avg_cur_4v": float(row["avg_cur_4v"]) if pd.notna(row.get("avg_cur_4v")) else None,
            }
    return None


def _slice_for_baseline(
    arr: np.ndarray,
    sample_rate_hz: float,
    duration_sec: float,
    *,
    trim_start_sec: float = _BASELINE_TRIM_START_SEC,
    trim_end_sec: float = _BASELINE_TRIM_END_SEC,
) -> np.ndarray:
    """底电统计有效区间：忽略场景开始前 trim_start_sec 与结束前 trim_end_sec。"""
    if arr.size == 0:
        return arr
    start_idx = max(0, int(trim_start_sec * sample_rate_hz))
    end_idx = min(arr.size, max(start_idx, int((duration_sec - trim_end_sec) * sample_rate_hz)))
    if start_idx >= end_idx:
        return np.array([], dtype=float)
    return arr[start_idx:end_idx]


def _rolling_min_mean(arr: np.ndarray, sample_rate_hz: float, window_sec: float) -> float | None:
    """平均底电：在 window_sec 滑动窗口内取均值，再取全场景最小窗口均值（持续底流，非瞬时尖峰）。"""
    if arr.size == 0:
        return None
    win = max(1, int(window_sec * sample_rate_hz))
    if arr.size < win:
        return round(float(arr.mean()), 2)
    kernel = np.ones(win, dtype=float) / win
    rolling = np.convolve(arr, kernel, mode="valid")
    return round(float(rolling.min()), 2)


def _current_level_stats(
    arr: np.ndarray,
    *,
    sample_rate_hz: float = 1.0,
    baseline_window_sec: float = _DEFAULT_WINDOW_SEC,
    baseline_percentile: float = _BASELINE_PERCENTILE,
) -> dict[str, float]:
    """底电(min) / 平均底电(滑动窗口最低均值) / P10 等分位参考。"""
    if arr.size == 0:
        return {}
    avg_baseline = _rolling_min_mean(arr, sample_rate_hz, baseline_window_sec)
    out: dict[str, float] = {
        "min_ma": round(float(arr.min()), 2),
        "p10_ma": round(float(np.percentile(arr, baseline_percentile)), 2),
        "p25_ma": round(float(np.percentile(arr, 25)), 2),
        "median_ma": round(float(np.median(arr)), 2),
    }
    if avg_baseline is not None:
        out["avg_baseline_ma"] = avg_baseline
    # 兼容旧字段名：baseline_ma 仍指 P10
    out["baseline_ma"] = out["p10_ma"]
    return out


def _find_spike_windows(
    diff: np.ndarray,
    *,
    sample_rate_hz: float,
    window_sec: float,
    step_sec: float,
    top_n: int,
) -> list[dict[str, Any]]:
    if diff.size == 0:
        return []
    win = max(1, int(window_sec * sample_rate_hz))
    step = max(1, int(step_sec * sample_rate_hz))
    if diff.size < win:
        return [
            {
                "rank": 1,
                "start_sec": 0.0,
                "end_sec": diff.size / sample_rate_hz,
                "duration_sec": diff.size / sample_rate_hz,
                "mean_diff_ma": float(diff.mean()),
                "max_diff_ma": float(diff.max()),
                "relative_time": f"00:00–{_sec_to_rel_time(diff.size / sample_rate_hz)}",
            }
        ]
    scored: list[tuple[float, int, float, float]] = []
    for i in range(0, diff.size - win + 1, step):
        seg = diff[i : i + win]
        scored.append((float(seg.mean()), i, float(seg.max()), win / sample_rate_hz))
    scored.sort(key=lambda x: x[0], reverse=True)

    windows: list[dict[str, Any]] = []
    used: list[tuple[float, float]] = []
    for mean_diff, start_idx, max_diff, dur in scored:
        start_sec = start_idx / sample_rate_hz
        end_sec = start_sec + dur
        overlap = any(not (end_sec <= s or start_sec >= e) for s, e in used)
        if overlap:
            continue
        used.append((start_sec, end_sec))
        windows.append(
            {
                "rank": len(windows) + 1,
                "start_sec": round(start_sec, 2),
                "end_sec": round(end_sec, 2),
                "duration_sec": round(dur, 2),
                "mean_diff_ma": round(mean_diff, 2),
                "max_diff_ma": round(max_diff, 2),
                "relative_time": f"{_sec_to_rel_time(start_sec)}–{_sec_to_rel_time(end_sec)}",
            }
        )
        if len(windows) >= top_n:
            break
    return windows


def _find_dip_windows(
    diff: np.ndarray,
    *,
    sample_rate_hz: float,
    window_sec: float,
    step_sec: float,
    top_n: int,
) -> list[dict[str, Any]]:
    """差值为负（低功耗瞬时高于高功耗）的时段，按窗口均差从小到大排序。"""
    if diff.size == 0:
        return []
    win = max(1, int(window_sec * sample_rate_hz))
    step = max(1, int(step_sec * sample_rate_hz))
    if diff.size < win:
        if float(diff.min()) >= 0:
            return []
        return [
            {
                "rank": 1,
                "start_sec": 0.0,
                "end_sec": diff.size / sample_rate_hz,
                "duration_sec": diff.size / sample_rate_hz,
                "mean_diff_ma": round(float(diff.mean()), 2),
                "min_diff_ma": round(float(diff.min()), 2),
                "relative_time": f"00:00–{_sec_to_rel_time(diff.size / sample_rate_hz)}",
            }
        ]
    scored: list[tuple[float, int, float, float]] = []
    for i in range(0, diff.size - win + 1, step):
        seg = diff[i : i + win]
        mean_diff = float(seg.mean())
        if mean_diff >= 0:
            continue
        scored.append((mean_diff, i, float(seg.min()), win / sample_rate_hz))
    scored.sort(key=lambda x: x[0])

    windows: list[dict[str, Any]] = []
    used: list[tuple[float, float]] = []
    for mean_diff, start_idx, min_diff, dur in scored:
        start_sec = start_idx / sample_rate_hz
        end_sec = start_sec + dur
        overlap = any(not (end_sec <= s or start_sec >= e) for s, e in used)
        if overlap:
            continue
        used.append((start_sec, end_sec))
        windows.append(
            {
                "rank": len(windows) + 1,
                "start_sec": round(start_sec, 2),
                "end_sec": round(end_sec, 2),
                "duration_sec": round(dur, 2),
                "mean_diff_ma": round(mean_diff, 2),
                "min_diff_ma": round(min_diff, 2),
                "relative_time": f"{_sec_to_rel_time(start_sec)}–{_sec_to_rel_time(end_sec)}",
            }
        )
        if len(windows) >= top_n:
            break
    return windows


def _point_dict(t: float, high: float, low: float, diff: float) -> dict[str, float]:
    return {
        "t_sec": round(float(t), 2),
        "high_ma": round(float(high), 2),
        "low_ma": round(float(low), 2),
        "diff_ma": round(float(diff), 2),
    }


# 高低电流曲线「大形状」差异阈值：不含幅值差，也不抠小抖动
_TREND_DIFF_THRESHOLD = 1.0 / 3.0
# 先压成约 N 段桶均值再相关，只看宏观走势（升降平台），忽略高频毛刺
_TREND_COARSE_POINTS = 24
# 允许时间轴偏移「几秒」再比大形状；偏移后吻合则不算脚本问题
_TREND_MAX_LAG_SEC = 5


def _zscore(arr: np.ndarray) -> np.ndarray:
    """去均值归一化；近似常数序列返回全 0。"""
    x = np.asarray(arr, dtype=float)
    if x.size == 0:
        return x
    std = float(x.std())
    if std < 1e-9:
        return np.zeros_like(x)
    return (x - float(x.mean())) / std


def _coarse_bucket_means(arr: np.ndarray, n_buckets: int) -> np.ndarray:
    """等长分桶取均值，得到宏观包络（大形状）。"""
    x = np.asarray(arr, dtype=float)
    n = len(x)
    if n <= 0:
        return x
    k = max(1, min(int(n_buckets), n))
    # 均匀切桶，避免尾部丢点
    edges = np.linspace(0, n, k + 1, dtype=int)
    out = np.empty(k, dtype=float)
    for i in range(k):
        a, b = int(edges[i]), int(edges[i + 1])
        if b <= a:
            b = min(n, a + 1)
        out[i] = float(np.mean(x[a:b]))
    return out


def _nearly_flat_series(x: np.ndarray) -> bool:
    """粗曲线是否近似平坦（相对均值）。"""
    m = abs(float(np.mean(x)))
    s = float(np.std(x))
    return s < 1e-6 or s < 0.02 * (m + 1.0)


def _macro_corr(a: np.ndarray, b: np.ndarray, coarse_points: int) -> float:
    """对齐后的两段序列：分桶取均值再算大形状相关。"""
    n = min(len(a), len(b))
    if n < 32:
        return 0.0
    k = max(12, min(int(coarse_points), n // 2 if n >= 48 else n))
    ac = _coarse_bucket_means(a[:n], k)
    bc = _coarse_bucket_means(b[:n], k)
    if _nearly_flat_series(ac) and _nearly_flat_series(bc):
        return 1.0
    if _nearly_flat_series(ac) or _nearly_flat_series(bc):
        return 0.0
    c = float(np.corrcoef(_zscore(ac), _zscore(bc))[0, 1])
    if c != c:  # NaN
        return 0.0
    return c


def _compute_trend_compare(
    high: np.ndarray,
    low: np.ndarray,
    *,
    duration_sec: float | None = None,
    threshold: float = _TREND_DIFF_THRESHOLD,
    coarse_points: int = _TREND_COARSE_POINTS,
    max_lag_sec: int = _TREND_MAX_LAG_SEC,
) -> dict[str, Any]:
    """对比高低版电流曲线的大形状走势（统计用）。

    脚本问题**不**由此函数自动判定，仅 Look 人工下拉（is_script_issue）。
    仍计算 ±max_lag_sec 对齐后的相关等字段，供参考；suspect_script_issue 恒为 False。
    """
    n = min(len(high), len(low))
    high = np.asarray(high[:n], dtype=float)
    low = np.asarray(low[:n], dtype=float)
    out: dict[str, Any] = {
        "threshold": round(float(threshold), 4),
        "note": "趋势统计仅供参考；脚本问题请在 Look 人工判定，不作自动标注",
        "suspect_script_issue": False,
        "trend_corr": None,
        "trend_similarity": None,
        "trend_diff_ratio": None,
        "point_count": int(n),
        "coarse_points": int(coarse_points),
        "best_lag_sec": None,
        "max_lag_sec": int(max_lag_sec),
    }
    if n < 32:
        out["reason"] = "点数不足，跳过趋势对比"
        return out

    dur = float(duration_sec) if duration_sec and float(duration_sec) > 1e-6 else float(n)
    samples_per_sec = n / max(dur, 1e-6)
    max_lag = max(0, int(max_lag_sec))
    target = max(12, min(int(coarse_points), n // 2 if n >= 64 else n))

    # 路径 A：按秒对齐后再比大形状（满足「偏移几秒吻合则不算」）
    best_corr = -1.0
    best_lag_sec = 0
    for lag_sec in range(-max_lag, max_lag + 1):
        lag = int(round(lag_sec * samples_per_sec))
        if lag < 0:
            if n + lag < 32:
                continue
            a, b = high[-lag:], low[: n + lag]
        elif lag > 0:
            if n - lag < 32:
                continue
            a, b = high[: n - lag], low[lag:]
        else:
            a, b = high, low
        c = _macro_corr(a, b, target)
        if c > best_corr:
            best_corr = c
            best_lag_sec = lag_sec

    # 路径 B：先粗分桶，再在对应秒数不超过 ±max_lag_sec 的粗段内错位
    hc0 = _coarse_bucket_means(high, target)
    lc0 = _coarse_bucket_means(low, len(hc0))
    bin_sec = dur / max(len(hc0), 1)
    max_lag_bins = 0
    for b in range(1, max(1, len(hc0) // 4) + 1):
        if b * bin_sec <= max_lag + 0.5:
            max_lag_bins = b
        else:
            break
    if not (_nearly_flat_series(hc0) or _nearly_flat_series(lc0)):
        hz = _zscore(hc0)
        lz = _zscore(lc0)
        for lag in range(-max_lag_bins, max_lag_bins + 1):
            if lag < 0:
                a, b = hz[-lag:], lz[: len(lz) + lag]
            elif lag > 0:
                a, b = hz[: len(hz) - lag], lz[lag:]
            else:
                a, b = hz, lz
            if len(a) < 8:
                continue
            c = float(np.corrcoef(a, b)[0, 1])
            if c != c:
                c = 0.0
            lag_sec_approx = int(round(lag * bin_sec))
            if abs(lag_sec_approx) > max_lag and lag != 0:
                continue
            if c > best_corr:
                best_corr = c
                best_lag_sec = lag_sec_approx
    elif _nearly_flat_series(hc0) and _nearly_flat_series(lc0):
        if 1.0 > best_corr:
            best_corr = 1.0
            best_lag_sec = 0
    else:
        # 一边平一边有起伏
        if 0.0 > best_corr:
            best_corr = 0.0

    if best_corr < 0:
        best_corr = 0.0

    h_flat = _nearly_flat_series(hc0)
    l_flat = _nearly_flat_series(lc0)
    sim = max(0.0, best_corr)
    diff_ratio = 1.0 - sim
    # 脚本问题仅由 Look 人工判定；此处不再自动标疑似
    out.update(
        {
            "trend_corr": round(float(best_corr), 4),
            "trend_similarity": round(sim, 4),
            "trend_diff_ratio": round(diff_ratio, 4),
            "suspect_script_issue": False,
            "high_nearly_flat": h_flat,
            "low_nearly_flat": l_flat,
            "best_lag_sec": int(best_lag_sec),
            "coarse_points": int(len(hc0)),
            "note": "趋势统计仅供参考；脚本问题请在 Look 人工判定，不作自动标注",
        }
    )
    return out


def _downsample_series(
    t: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    diff: np.ndarray,
    max_points: int,
) -> list[dict[str, float]]:
    """降采样供看板渲染：点数 ≤ max_points 时原样输出；否则按桶保留 diff 峰/谷，避免尖峰被抽丢。"""
    n = len(t)
    if n <= 0:
        return []
    if n <= max_points:
        return [_point_dict(t[i], high[i], low[i], diff[i]) for i in range(n)]

    # 每桶最多输出 2 点（min/max），桶数 ≈ max_points/2
    n_buckets = max(1, max_points // 2)
    out: list[dict[str, float]] = []
    for b in range(n_buckets):
        start = (b * n) // n_buckets
        end = ((b + 1) * n) // n_buckets
        if start >= end:
            continue
        seg = diff[start:end]
        i_min = start + int(np.argmin(seg))
        i_max = start + int(np.argmax(seg))
        for i in sorted({i_min, i_max}):
            out.append(_point_dict(t[i], high[i], low[i], diff[i]))
    # 保证首尾点在内，便于时间轴对齐
    if out and out[0]["t_sec"] > float(t[0]):
        out.insert(0, _point_dict(t[0], high[0], low[0], diff[0]))
    if out and out[-1]["t_sec"] < float(t[-1]):
        out.append(_point_dict(t[-1], high[-1], low[-1], diff[-1]))
    return out


def _group_process_blocks(
    flat: list, scene_start: datetime | None = None
) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for item in flat or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "separator" or item.get("is_separator"):
            rel_sec = _block_relative_sec(item, scene_start)
            rel_time = str(item.get("relative_time") or "").strip()
            if rel_sec is not None and not rel_time:
                rel_time = _sec_to_rel_time(rel_sec)
            current = {
                "block_num": item.get("block_num"),
                "relative_time": rel_time,
                "relative_sec": rel_sec,
                "perf_start_time": item.get("perf_start_time", ""),
                "title": str(item.get("content") or "").strip(),
                "processes": [],
            }
            blocks.append(current)
        elif item.get("type") == "process" and current is not None:
            current["processes"].append(
                {
                    "name": item.get("进程名", ""),
                    "usage_pct": item.get("使用率(%)", 0),
                    "pid": item.get("PID", ""),
                    "time": item.get("时间", ""),
                }
            )
    return blocks


def _blocks_in_window(blocks: list[dict], start_sec: float, end_sec: float) -> list[dict]:
    picked: list[dict] = []
    for blk in blocks:
        rs = blk.get("relative_sec")
        if rs is None:
            rs = _rel_time_to_sec(str(blk.get("relative_time") or ""))
        if rs is None:
            continue
        rs = float(rs)
        if start_sec <= rs <= end_sec:
            picked.append(blk)
    return picked


def _proc_name(p: dict) -> str:
    return str(p.get("name") or p.get("进程名") or "").strip()


def _proc_usage(p: dict) -> float:
    for key in ("usage_pct", "使用率(%)", "usage"):
        val = p.get(key)
        if val is not None and val != "":
            try:
                return float(val)
            except (TypeError, ValueError):
                pass
    return 0.0


def _compute_diff_segments(
    t: np.ndarray,
    diff: np.ndarray,
    *,
    interval_sec: float = _DEFAULT_SEGMENT_INTERVAL_SEC,
) -> list[dict[str, Any]]:
    """固定间隔分段统计差异曲线（与 look 看板 computeDiffSegments 一致）。"""
    if t.size == 0 or diff.size == 0:
        return []
    n = min(int(t.size), int(diff.size))
    t = t[:n]
    diff = diff[:n]
    t_min = float(t[0])
    t_max = float(t[-1])
    segs: list[dict[str, Any]] = []
    start = t_min
    idx = 0
    prev_mean: float | None = None
    while start < t_max - 0.001:
        end = min(start + interval_sec, t_max)
        mask = (t >= start - 0.001) & (t <= end + 0.001)
        vals = diff[mask]
        mean_diff = max_diff = min_diff = None
        if vals.size:
            mean_diff = round(float(vals.mean()), 2)
            max_diff = round(float(vals.max()), 2)
            min_diff = round(float(vals.min()), 2)
        delta_from_prev = None
        if mean_diff is not None and prev_mean is not None:
            delta_from_prev = round(mean_diff - prev_mean, 2)
        if mean_diff is not None:
            prev_mean = mean_diff
        segs.append(
            {
                "index": idx,
                "start_sec": round(start, 2),
                "end_sec": round(end, 2),
                "duration_sec": round(end - start, 2),
                "mean_diff_ma": mean_diff,
                "max_diff_ma": max_diff,
                "min_diff_ma": min_diff,
                "delta_from_prev_ma": delta_from_prev,
                "relative_time": f"{_sec_to_rel_time(start)}–{_sec_to_rel_time(end)}",
            }
        )
        idx += 1
        start = end
    return segs


def _compute_diff_segments_from_points(
    points: list[dict],
    *,
    interval_sec: float = _DEFAULT_SEGMENT_INTERVAL_SEC,
) -> list[dict[str, Any]]:
    if not points:
        return []
    ts = np.array([float(p.get("t_sec", 0)) for p in points], dtype=float)
    diffs = np.array([float(p.get("diff_ma", 0)) for p in points], dtype=float)
    return _compute_diff_segments(ts, diffs, interval_sec=interval_sec)


def _aggregate_processes_map(blocks: list[dict]) -> dict[str, float]:
    out: dict[str, float] = {}
    for row in _top_processes_from_blocks(blocks, limit=9999):
        out[row["name"]] = float(row["usage_pct"])
    return out


def _build_segment_process_delta_rows(
    cur_hi_blocks: list[dict],
    cur_lo_blocks: list[dict],
    prev_hi_blocks: list[dict],
    prev_lo_blocks: list[dict],
    *,
    limit: int = _SEGMENT_PROC_COMPARE_LIMIT,
) -> list[dict[str, Any]]:
    """本段/上段进程均值对比（与 look 看板 buildSegmentProcessDeltaRows 一致）。"""
    cur_hi = _aggregate_processes_map(cur_hi_blocks)
    cur_lo = _aggregate_processes_map(cur_lo_blocks)
    prev_hi = _aggregate_processes_map(prev_hi_blocks)
    prev_lo = _aggregate_processes_map(prev_lo_blocks)
    names = set(cur_hi) | set(cur_lo) | set(prev_hi) | set(prev_lo)
    rows: list[dict[str, Any]] = []
    for name in names:
        chi = float(cur_hi.get(name, 0.0))
        clo = float(cur_lo.get(name, 0.0))
        phi = float(prev_hi.get(name, 0.0))
        plo = float(prev_lo.get(name, 0.0))
        cur_diff = round(chi - clo, 2)
        prev_diff = round(phi - plo, 2)
        rows.append(
            {
                "process": name,
                "cur_high_pct": chi,
                "cur_low_pct": clo,
                "prev_high_pct": phi,
                "prev_low_pct": plo,
                "delta_high_pct": round(chi - phi, 2),
                "delta_low_pct": round(clo - plo, 2),
                "cur_high_low_diff_pct": cur_diff,
                "prev_high_low_diff_pct": prev_diff,
                "delta_high_low_diff_pct": round(cur_diff - prev_diff, 2),
            }
        )

    def _sort_key(r: dict[str, Any]) -> float:
        for key in ("cur_high_low_diff_pct", "delta_high_pct", "delta_low_pct"):
            val = r.get(key)
            if val is not None:
                return abs(float(val))
        return 0.0

    rows.sort(key=_sort_key, reverse=True)
    return rows[:limit]


def _attach_cpu_to_diff_segments(
    segments: list[dict],
    hi_blocks: list[dict],
    lo_blocks: list[dict],
) -> None:
    for i, seg in enumerate(segments):
        start = float(seg["start_sec"])
        end = float(seg["end_sec"])
        hi_in = _blocks_in_window(hi_blocks, start, end)
        lo_in = _blocks_in_window(lo_blocks, start, end)
        prev_hi: list[dict] = []
        prev_lo: list[dict] = []
        if i > 0:
            prev = segments[i - 1]
            prev_hi = _blocks_in_window(hi_blocks, float(prev["start_sec"]), float(prev["end_sec"]))
            prev_lo = _blocks_in_window(lo_blocks, float(prev["start_sec"]), float(prev["end_sec"]))
        seg["cpu_in_segment"] = {
            "high_block_count": len(hi_in),
            "low_block_count": len(lo_in),
            "high_top_processes": _top_processes_from_blocks(hi_in),
            "low_top_processes": _top_processes_from_blocks(lo_in),
            "process_compare_top": _build_segment_process_delta_rows(
                hi_in, lo_in, prev_hi, prev_lo
            ),
        }


def _cpu_diff_row(item: dict) -> dict[str, Any]:
    return {
        "process": item.get("进程名") or item.get("process") or "",
        "high_pct": item.get("版本1平均值(%)"),
        "low_pct": item.get("版本2平均值(%)"),
        "diff_pct": item.get("差异值(%)"),
        "high_count": item.get("版本1出现次数"),
        "low_count": item.get("版本2出现次数"),
        "trend": item.get("变化趋势") or "",
    }


def _cpu_scene_compare_summary(cpu_data: dict[str, Any], *, limit: int = 25) -> dict[str, Any]:
    """全场景高低版本 CPU 进程对比摘要（来自 cpu_analysis averages_enhanced）。"""
    ae = cpu_data.get("averages_enhanced") or {}
    diff = ae.get("diff") or {}
    diff_data = diff.get("data") or diff.get("top_diffs") or []
    if not isinstance(diff_data, list):
        diff_data = []

    def _rows(items: list, cap: int) -> list[dict[str, Any]]:
        return [_cpu_diff_row(r) for r in items[:cap] if isinstance(r, dict)]

    return {
        "statistics": ae.get("statistics") or {},
        "max_diff_pct": diff.get("max_diff"),
        "top_diff_processes": _rows(diff_data, limit),
        "large_diff_processes": _rows(diff.get("processes_with_large_diff") or [], 15),
        "new_only_in_high": _rows(diff.get("disappeared_processes") or [], 15),
        "new_only_in_low": _rows(diff.get("new_processes_in_scene2") or [], 15),
    }


def _top_processes_from_blocks(blocks: list[dict], limit: int = 8) -> list[dict]:
    agg: dict[str, dict] = {}
    for blk in blocks:
        for p in blk.get("processes") or []:
            name = _proc_name(p)
            if not name:
                continue
            if name not in agg:
                agg[name] = {"name": name, "usage_pct": 0.0, "samples": 0}
            agg[name]["usage_pct"] += _proc_usage(p)
            agg[name]["samples"] += 1
    rows = sorted(agg.values(), key=lambda x: x["usage_pct"], reverse=True)
    for r in rows:
        if r["samples"]:
            r["usage_pct"] = round(r["usage_pct"] / r["samples"], 2)
    return rows[:limit]


def _load_cpu_json(cpu_path: str) -> dict[str, Any]:
    with open(cpu_path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    if isinstance(payload, dict) and isinstance(payload.get("cpu_data"), dict):
        return payload["cpu_data"]
    return payload if isinstance(payload, dict) else {}


def _perf_timeline_entries(blocks: list[dict]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for blk in blocks:
        rs = blk.get("relative_sec")
        if rs is None:
            continue
        out.append(
            {
                "block_num": blk.get("block_num"),
                "relative_time": blk.get("relative_time") or _sec_to_rel_time(rs),
                "relative_sec": rs,
                "perf_start_time": blk.get("perf_start_time", ""),
                "process_count": len(blk.get("processes") or []),
            }
        )
    out.sort(key=lambda x: float(x["relative_sec"]))
    return out


def _attach_cpu_to_windows(
    windows: list[dict],
    cpu_data: dict[str, Any],
    *,
    scene_start_high: datetime | None = None,
    scene_start_low: datetime | None = None,
) -> dict[str, list[dict[str, Any]]]:
    s1 = cpu_data.get("scene1") or {}
    s2 = cpu_data.get("scene2") or {}
    hi_blocks = _group_process_blocks(s1.get("process_data") or [], scene_start_high)
    lo_blocks = _group_process_blocks(s2.get("process_data") or [], scene_start_low)
    diff_rows = (
        ((cpu_data.get("averages_enhanced") or {}).get("diff") or {}).get("data")
        or ((cpu_data.get("averages_enhanced") or {}).get("diff") or {}).get("top_diffs")
        or []
    )
    for win in windows:
        start = float(win["start_sec"])
        end = float(win["end_sec"])
        hi_in = _blocks_in_window(hi_blocks, start, end)
        lo_in = _blocks_in_window(lo_blocks, start, end)
        win["cpu_in_window"] = {
            "high": {
                "block_count": len(hi_in),
                "top_processes": _top_processes_from_blocks(hi_in),
                "blocks": hi_in[:6],
            },
            "low": {
                "block_count": len(lo_in),
                "top_processes": _top_processes_from_blocks(lo_in),
                "blocks": lo_in[:6],
            },
            "scene_diff_top": [
                {
                    "process": r.get("进程名") or r.get("process"),
                    "high_pct": r.get("版本1平均值(%)"),
                    "low_pct": r.get("版本2平均值(%)"),
                    "diff_pct": r.get("差异值(%)"),
                }
                for r in (diff_rows[:15] if isinstance(diff_rows, list) else [])
            ],
        }
    return {
        "high": _perf_timeline_entries(hi_blocks),
        "low": _perf_timeline_entries(lo_blocks),
        "high_blocks": hi_blocks,
        "low_blocks": lo_blocks,
    }


def analyze_scene_current_cpu(
    high_dir: str,
    low_dir: str,
    suffix: str,
    *,
    cpu_json_path: str | None = None,
    window_sec: float = _DEFAULT_WINDOW_SEC,
    step_sec: float = _DEFAULT_WINDOW_STEP_SEC,
    top_windows: int = _DEFAULT_TOP_WINDOWS,
) -> dict[str, Any]:
    """单场景：pt5 底电对比 + 已有 CPU JSON（不重新跑 CPU 分析）。"""
    suf = _norm_suffix(suffix)
    high_meta = os.path.join(high_dir, "meta_report")
    low_meta = os.path.join(low_dir, "meta_report")
    high_pt5 = find_pt5_for_suffix(high_meta, suf)
    low_pt5 = find_pt5_for_suffix(low_meta, suf)
    if not high_pt5:
        return {"success": False, "suffix": suf, "error": f"高功耗 meta_report 未找到场景 {suf} 的 pt5"}
    if not low_pt5:
        return {"success": False, "suffix": suf, "error": f"低功耗 meta_report 未找到场景 {suf} 的 pt5"}

    scene_h = _load_scene_row(high_dir, suf)
    scene_l = _load_scene_row(low_dir, suf)
    if not scene_h:
        return {"success": False, "suffix": suf, "error": f"高功耗 testReport 无场景 {suf}"}

    dur = float(scene_h["duration_sec"])
    cal_h = scene_h.get("avg_cur") or scene_h.get("avg_cur_4v")
    cal_l = (scene_l or {}).get("avg_cur") or (scene_l or {}).get("avg_cur_4v")

    hi = load_pt5_series(high_pt5, dur, calibrate_to_ma=cal_h)
    lo = load_pt5_series(low_pt5, dur, calibrate_to_ma=cal_l)
    rate = float(hi["sample_rate_hz"])
    h = hi["series"]
    l = lo["series"]
    n = min(len(h), len(l))
    if n == 0:
        return {"success": False, "suffix": suf, "error": "pt5 电流序列为空"}
    h = h[:n]
    l = l[:n]
    diff = h - l
    t = np.arange(n, dtype=float) / rate

    windows = _find_spike_windows(
        diff,
        sample_rate_hz=rate,
        window_sec=window_sec,
        step_sec=step_sec,
        top_n=top_windows,
    )
    dip_windows = _find_dip_windows(
        diff,
        sample_rate_hz=rate,
        window_sec=window_sec,
        step_sec=step_sec,
        top_n=top_windows,
    )

    high_stats = _current_level_stats(
        _slice_for_baseline(h, rate, dur),
        sample_rate_hz=rate,
        baseline_window_sec=window_sec,
    )
    low_stats = _current_level_stats(
        _slice_for_baseline(l, rate, dur),
        sample_rate_hz=rate,
        baseline_window_sec=window_sec,
    )

    def _diff(h_key: str, l_key: str) -> float | None:
        hv, lv = high_stats.get(h_key), low_stats.get(l_key)
        if hv is not None and lv is not None:
            return round(float(hv) - float(lv), 2)
        return None

    floor_diff = _diff("min_ma", "min_ma")
    avg_baseline_diff = _diff("avg_baseline_ma", "avg_baseline_ma")
    p10_diff = _diff("baseline_ma", "baseline_ma")

    scene_start_h = _parse_scene_start(scene_h.get("starttime"))
    scene_start_l = _parse_scene_start((scene_l or {}).get("starttime"))

    cpu_path = cpu_json_path or os.path.join(high_dir, f"cpu_analysis_{suf}.json")
    cpu_data: dict[str, Any] = {}
    cpu_source = ""
    perf_timeline: dict[str, list] = {"high": [], "low": []}
    cpu_scene_compare: dict[str, Any] = {}
    if os.path.isfile(cpu_path):
        cpu_data = _load_cpu_json(cpu_path)
        cpu_source = os.path.basename(cpu_path)
        perf_timeline = _attach_cpu_to_windows(
            windows,
            cpu_data,
            scene_start_high=scene_start_h,
            scene_start_low=scene_start_l,
        )
        cpu_scene_compare = _cpu_scene_compare_summary(cpu_data)

    segment_interval_sec = _DEFAULT_SEGMENT_INTERVAL_SEC
    diff_segments = _compute_diff_segments(t, diff, interval_sec=segment_interval_sec)
    if cpu_data:
        hi_blocks = perf_timeline.get("high_blocks") or []
        lo_blocks = perf_timeline.get("low_blocks") or []
        if hi_blocks or lo_blocks:
            _attach_cpu_to_diff_segments(diff_segments, hi_blocks, lo_blocks)

    excel_h = scene_h.get("avg_cur_4v") or scene_h.get("avg_cur")
    excel_l = (scene_l or {}).get("avg_cur_4v") or (scene_l or {}).get("avg_cur")
    excel_diff = None
    if excel_h is not None and excel_l is not None:
        excel_diff = round(float(excel_h) - float(excel_l), 2)

    trend_compare = _compute_trend_compare(h, l, duration_sec=dur)

    return {
        "success": True,
        "suffix": suf,
        "scene_desc": scene_h.get("desc", ""),
        "scene_name": scene_h.get("name", ""),
        "high_pt5": high_pt5,
        "low_pt5": low_pt5,
        "scene_time": {
            "high_start": scene_h.get("starttime"),
            "high_end": scene_h.get("endtime"),
            "low_start": (scene_l or {}).get("starttime"),
            "low_end": (scene_l or {}).get("endtime"),
            "duration_sec": dur,
        },
        "trend_compare": trend_compare,
        "current_summary": {
            "high_avg_ma": round(float(h.mean()), 2),
            "low_avg_ma": round(float(l.mean()), 2),
            "aligned_avg_diff_ma": round(float(diff.mean()), 2),
            "excel_high_avg_ma": excel_h,
            "excel_low_avg_ma": excel_l,
            "excel_avg_diff_ma": excel_diff,
            "max_diff_ma": round(float(diff.max()), 2),
            "min_diff_ma": round(float(diff.min()), 2),
            "high_floor_ma": high_stats.get("min_ma"),
            "low_floor_ma": low_stats.get("min_ma"),
            "floor_diff_ma": floor_diff,
            "high_avg_baseline_ma": high_stats.get("avg_baseline_ma"),
            "low_avg_baseline_ma": low_stats.get("avg_baseline_ma"),
            "avg_baseline_diff_ma": avg_baseline_diff,
            "avg_baseline_window_sec": window_sec,
            "baseline_trim_start_sec": _BASELINE_TRIM_START_SEC,
            "baseline_trim_end_sec": _BASELINE_TRIM_END_SEC,
            "high_baseline_ma": high_stats.get("baseline_ma"),
            "low_baseline_ma": low_stats.get("baseline_ma"),
            "baseline_diff_ma": p10_diff,
            "high_baseline": high_stats,
            "low_baseline": low_stats,
            "baseline_percentile": _BASELINE_PERCENTILE,
        },
        "dip_windows": dip_windows,
        "segment_interval_sec": segment_interval_sec,
        "diff_segments": diff_segments,
        "cpu_scene_compare": cpu_scene_compare,
        "series": {
            "sample_rate_hz": rate,
            "point_count": n,
            "points": _downsample_series(t, h, l, diff, _MAX_CHART_POINTS),
        },
        "spike_windows": windows,
        "perf_timeline": perf_timeline,
        "cpu_source": cpu_source,
        "cpu_loaded": bool(cpu_data),
        "time_axis_note": "横轴为场景内相对时间(mm:ss)，用于对齐 pt5 电流；下方 CPU 时间为高/低版本各自日志时间",
        "analyzed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def enrich_spike_with_perf_timeline(spike: dict[str, Any], bundle_dir: str) -> dict[str, Any]:
    """为 current_cpu_spike JSON 补全/刷新 perf_timeline 与窗口内 Perf+进程汇总（读 cpu_analysis）。"""
    if not isinstance(spike, dict) or not spike.get("success"):
        return spike
    suf = _norm_suffix(spike.get("suffix") or "")
    if not suf:
        return spike
    cpu_path = os.path.join(bundle_dir, f"cpu_analysis_{suf}.json")
    if not os.path.isfile(cpu_path):
        return spike
    cpu_data = _load_cpu_json(cpu_path)
    scene_time = spike.get("scene_time") or {}
    scene_start_h = _parse_scene_start(scene_time.get("high_start"))
    scene_start_l = _parse_scene_start(scene_time.get("low_start"))
    windows = list(spike.get("spike_windows") or [])
    perf_timeline = _attach_cpu_to_windows(
        windows,
        cpu_data,
        scene_start_high=scene_start_h,
        scene_start_low=scene_start_l,
    )
    interval = float(spike.get("segment_interval_sec") or _DEFAULT_SEGMENT_INTERVAL_SEC)
    points = ((spike.get("series") or {}).get("points")) or []
    diff_segments = _compute_diff_segments_from_points(points, interval_sec=interval)
    hi_blocks = perf_timeline.get("high_blocks") or []
    lo_blocks = perf_timeline.get("low_blocks") or []
    if hi_blocks or lo_blocks:
        _attach_cpu_to_diff_segments(diff_segments, hi_blocks, lo_blocks)
    out = dict(spike)
    out["spike_windows"] = windows
    out["perf_timeline"] = perf_timeline
    out["segment_interval_sec"] = interval
    out["diff_segments"] = diff_segments
    out["cpu_scene_compare"] = _cpu_scene_compare_summary(cpu_data)
    out["cpu_loaded"] = True
    out["cpu_source"] = os.path.basename(cpu_path)
    out.setdefault("time_axis_note", "横轴为场景内相对时间(mm:ss)，用于对齐 pt5 电流；下方 CPU 时间为高/低版本各自日志时间")
    return out
