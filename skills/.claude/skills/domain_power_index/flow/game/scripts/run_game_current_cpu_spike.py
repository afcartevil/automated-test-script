#!/usr/bin/env python3
"""游戏 flow 步骤 13b：接入 DOU current_cpu_spike（不修改 DOU 原脚本）。

做法：
1. 若有两份 pt5：在 analysis 下搭临时 DOU 目录布局（meta_report + testReport.xlsx + pt5），
   再调用原版 `run_current_cpu_spike.py <high> <low> --suffix 1`
2. 曲线图完全在 game wrapper 侧生成：
   - 单份 pt5：只展示单机电流曲线
   - 两份 pt5：同图展示双曲线 + 差值曲线 + 趋势柱状图
   - 间隔支持 1s / 5s / 10s 切换
"""

from __future__ import annotations

import argparse
import html
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

_SCRIPT_DIR = Path(__file__).resolve().parent
_GAME = _SCRIPT_DIR.parent
_CORR_SCRIPTS = _GAME / "game_current_log_correlate" / "scripts"
_DOU_TOOL = _GAME.parent / "dou_2" / "tool1_2" / "run_current_cpu_spike.py"
_SCENE_SUFFIX = "1"
_BUCKET_OPTIONS = (1, 5, 10)
for p in (_SCRIPT_DIR, _CORR_SCRIPTS):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from game_log_paths import add_log_path_argument, resolve_log_path  # noqa: E402
from game_skill_debug import add_debug_log_arguments, debug_begin, debug_end  # noqa: E402
from pt5_series_loader import find_pt5_candidates, load_current_series  # noqa: E402


def _setup_utf8_stdio() -> None:
    for name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _esc(v: Any) -> str:
    return html.escape("" if v is None else str(v), quote=True)


def _load_duration_sec(analysis_dir: Path) -> float:
    win_path = analysis_dir / "game_time_window.json"
    if not win_path.is_file():
        return 0.0
    try:
        data = json.loads(win_path.read_text(encoding="utf-8"))
    except Exception:
        return 0.0
    for key in ("duration_sec", "t_game_duration_sec"):
        try:
            v = float(data.get(key) or 0)
            if v > 0:
                return v
        except (TypeError, ValueError):
            pass
    window = data.get("window") or data.get("T_game") or data.get("t_game") or {}
    if isinstance(window, dict):
        try:
            v = float(window.get("duration_sec") or 0)
            if v > 0:
                return v
        except (TypeError, ValueError):
            pass
        start = window.get("start") or window.get("start_iso")
        end = window.get("end") or window.get("end_iso")
        if start and end:
            try:
                import pandas as pd

                return max(0.0, float((pd.to_datetime(end) - pd.to_datetime(start)).total_seconds()))
            except Exception:
                return 0.0
    return 0.0


def resolve_pt5_pair(
    *,
    pt5: str,
    pt5_compare: str,
    pt5_dir: str,
    search_dirs: list[Path],
    jira_key: str,
) -> tuple[Path | None, Path | None]:
    test = Path(pt5).expanduser() if pt5.strip() else None
    other = Path(pt5_compare).expanduser() if pt5_compare.strip() else None
    if test and test.is_file() and other and other.is_file():
        return test.resolve(), other.resolve()

    dirs: list[Path] = []
    if pt5_dir.strip():
        dirs.append(Path(pt5_dir).expanduser())
    dirs.extend(search_dirs)
    candidates = find_pt5_candidates(explicit=None, search_dirs=dirs, jira_key=jira_key)
    uniq: list[Path] = []
    seen: set[str] = set()
    for p in candidates:
        key = str(p.resolve()).lower()
        if key in seen or not p.is_file():
            continue
        seen.add(key)
        uniq.append(p.resolve())
    if test and test.is_file():
        test_r = test.resolve()
        rest = [p for p in uniq if p != test_r]
        return test_r, (rest[0] if rest else (other.resolve() if other and other.is_file() else None))
    if other and other.is_file() and len(uniq) >= 1:
        o = other.resolve()
        rest = [p for p in uniq if p != o]
        return (rest[0] if rest else None), o
    if len(uniq) >= 2:
        return uniq[0], uniq[1]
    if len(uniq) == 1:
        return uniq[0], None
    return None, None


def _link_or_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() or dst.is_symlink():
        dst.unlink()
    try:
        os.link(src, dst)
    except OSError:
        try:
            os.symlink(src, dst)
        except OSError:
            shutil.copy2(src, dst)


def _write_test_report(
    meta_dir: Path,
    *,
    duration_sec: float,
    desc: str,
    avg_cur: float | None = None,
) -> Path:
    import pandas as pd

    meta_dir.mkdir(parents=True, exist_ok=True)
    start = datetime.now().replace(microsecond=0)
    end = start + timedelta(seconds=max(duration_sec, 1.0))
    row = {
        "name": f"game_scene_{_SCENE_SUFFIX}",
        "desc": desc,
        "starttime": start,
        "endtime": end,
        "duration_sec": float(duration_sec),
        "avg_cur": avg_cur,
        "avg_cur_4v": avg_cur,
    }
    path = meta_dir / "testReport.xlsx"
    pd.DataFrame([row]).to_excel(path, sheet_name="report", index=False)
    return path


def _build_dou_stage(
    stage_root: Path,
    *,
    high_pt5: Path,
    low_pt5: Path,
    duration_sec: float,
    high_label: str,
    low_label: str,
) -> tuple[Path, Path]:
    high_dir = stage_root / "high"
    low_dir = stage_root / "low"
    high_meta = high_dir / "meta_report"
    low_meta = low_dir / "meta_report"
    high_meta.mkdir(parents=True, exist_ok=True)
    low_meta.mkdir(parents=True, exist_ok=True)
    _link_or_copy(high_pt5, high_meta / f"dou3_{_SCENE_SUFFIX}.pt5")
    _link_or_copy(low_pt5, low_meta / f"dou3_{_SCENE_SUFFIX}.pt5")
    _write_test_report(high_meta, duration_sec=duration_sec, desc=f"game/{high_label}")
    _write_test_report(low_meta, duration_sec=duration_sec, desc=f"game/{low_label}")
    return high_dir, low_dir


def _to_1s_series(series: dict[str, Any]) -> dict[str, Any]:
    t_vals = [float(x) for x in list(series.get("t_sec") or [])]
    cur_vals = [float(x) for x in list(series.get("current_ma") or [])]
    if not t_vals or not cur_vals:
        return {"t_sec": [], "current_ma": []}
    n = min(len(t_vals), len(cur_vals))
    if n <= 0:
        return {"t_sec": [], "current_ma": []}
    end_sec = int(math.floor(max(t_vals[:n])))
    sums = [0.0] * (end_sec + 1)
    counts = [0] * (end_sec + 1)
    for idx in range(n):
        sec = int(math.floor(t_vals[idx]))
        if 0 <= sec <= end_sec:
            sums[sec] += cur_vals[idx]
            counts[sec] += 1
    out_t: list[int] = []
    out_cur: list[float] = []
    for sec, cnt in enumerate(counts):
        if cnt <= 0:
            continue
        out_t.append(sec)
        out_cur.append(round(sums[sec] / cnt, 2))
    return {"t_sec": out_t, "current_ma": out_cur}


def _align_series(
    high_series: dict[str, Any],
    low_series: dict[str, Any] | None,
) -> dict[str, Any]:
    high_1s = _to_1s_series(high_series)
    low_1s = _to_1s_series(low_series) if low_series else None
    high_vals = list(high_1s.get("current_ma") or [])
    if not low_1s:
        return {
            "mode": "single",
            "t_sec": list(high_1s.get("t_sec") or []),
            "high_ma": high_vals,
            "low_ma": [],
            "diff_ma": [],
        }
    low_vals = list(low_1s.get("current_ma") or [])
    n = min(len(high_vals), len(low_vals))
    t_sec = list(range(n))
    high_cut = [round(float(x), 2) for x in high_vals[:n]]
    low_cut = [round(float(x), 2) for x in low_vals[:n]]
    diff = [round(high_cut[i] - low_cut[i], 2) for i in range(n)]
    return {
        "mode": "compare",
        "t_sec": t_sec,
        "high_ma": high_cut,
        "low_ma": low_cut,
        "diff_ma": diff,
    }


def _sec_to_rel_time(sec: float) -> str:
    total = max(0, int(round(float(sec))))
    return f"{total // 60:02d}:{total % 60:02d}"


def _diff_avg_ma(diff_ma: list[float], summary: dict[str, Any] | None = None) -> float | None:
    """差值平均值：优先 DOU aligned_avg_diff_ma，否则用序列均值。"""
    s = summary or {}
    try:
        if s.get("aligned_avg_diff_ma") is not None:
            return round(float(s.get("aligned_avg_diff_ma")), 2)
    except (TypeError, ValueError):
        pass
    vals = [float(x) for x in diff_ma if x is not None]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 2)


def _find_windows_vs_avg(
    diff_ma: list[float],
    *,
    avg: float,
    window_sec: float,
    step_sec: float,
    top_n: int,
    mode: str,
    min_abs_residual_ma: float = 20.0,
) -> list[dict[str, Any]]:
    """兼容旧接口：转调连续偏离段检测（忽略固定窗长，仅用 top_n 作上限）。"""
    _ = (window_sec, step_sec)
    return _find_segments_vs_avg(
        diff_ma,
        avg=avg,
        mode=mode,
        top_n=top_n,
        min_abs_residual_ma=min_abs_residual_ma,
    )


def _rolling_mean(vals: list[float], win: int) -> list[float]:
    n = len(vals)
    if n <= 0:
        return []
    w = max(1, int(win))
    if w == 1 or n == 1:
        return [float(x) for x in vals]
    out: list[float] = []
    acc = 0.0
    for i, v in enumerate(vals):
        acc += float(v)
        if i >= w:
            acc -= float(vals[i - w])
        denom = w if i + 1 >= w else (i + 1)
        out.append(acc / denom)
    return out


def _find_segments_vs_avg(
    diff_ma: list[float],
    *,
    avg: float,
    mode: str,
    top_n: int = 12,
    min_abs_residual_ma: float = 15.0,
    min_duration_sec: float = 5.0,
    merge_gap_sec: float = 3.0,
    smooth_sec: float = 3.0,
) -> list[dict[str, Any]]:
    """相对平均值找抬升/回落连续段。

    对每秒 residual=diff-avg：
    - rise：residual ≥ 阈值的连续区间
    - dip：residual ≤ -阈值的连续区间
    短空洞合并，过短段丢弃，再按偏离强度取 Top-N。
    """
    n = len(diff_ma)
    if n <= 0 or top_n <= 0:
        return []
    vals = [float(x) for x in diff_ma]
    smooth = _rolling_mean(vals, max(1, int(round(smooth_sec))))
    thr = max(0.0, float(min_abs_residual_ma))
    flags: list[bool] = []
    for v in smooth:
        residual = v - avg
        if mode == "rise":
            flags.append(residual >= thr)
        else:
            flags.append(residual <= -thr)

    # 原始连续 run: [start_idx, end_idx_exclusive)
    raw_runs: list[tuple[int, int]] = []
    i = 0
    while i < n:
        if not flags[i]:
            i += 1
            continue
        j = i + 1
        while j < n and flags[j]:
            j += 1
        raw_runs.append((i, j))
        i = j

    if not raw_runs:
        return []

    # 合并间隔 ≤ merge_gap_sec 的同向段
    gap = max(0, int(round(merge_gap_sec)))
    merged: list[tuple[int, int]] = [raw_runs[0]]
    for s, e in raw_runs[1:]:
        ps, pe = merged[-1]
        if s - pe <= gap:
            merged[-1] = (ps, e)
        else:
            merged.append((s, e))

    min_dur = max(1, int(round(min_duration_sec)))
    scored: list[tuple[float, int, int, float, float, float]] = []
    for s, e in merged:
        if e - s < min_dur:
            continue
        seg = vals[s:e]
        mean_diff = sum(seg) / len(seg)
        residual = mean_diff - avg
        if mode == "rise":
            if residual < thr:
                continue
            extremum = max(seg)
            score = residual * (e - s)  # 强度×时长，优先覆盖显著长段
        else:
            if (-residual) < thr:
                continue
            extremum = min(seg)
            score = (-residual) * (e - s)
        scored.append((score, s, e, mean_diff, residual, extremum))

    scored.sort(key=lambda x: x[0], reverse=True)
    windows: list[dict[str, Any]] = []
    for _score, s, e, mean_diff, residual, extremum in scored[: max(1, int(top_n))]:
        start_sec = float(s)
        end_sec = float(e)
        item = {
            "rank": len(windows) + 1,
            "start_sec": round(start_sec, 2),
            "end_sec": round(end_sec, 2),
            "duration_sec": round(end_sec - start_sec, 2),
            "mean_diff_ma": round(mean_diff, 2),
            "delta_from_avg_ma": round(residual, 2),
            "relative_time": f"{_sec_to_rel_time(start_sec)}–{_sec_to_rel_time(end_sec)}",
        }
        if mode == "rise":
            item["max_diff_ma"] = round(extremum, 2)
        else:
            item["min_diff_ma"] = round(extremum, 2)
        windows.append(item)
    # 按时间排序后重编号，便于图上从左到右阅读
    windows.sort(key=lambda w: float(w.get("start_sec") or 0))
    for i, w in enumerate(windows, start=1):
        w["rank"] = i
    return windows


def _apply_avg_based_trend_windows(
    spike: dict[str, Any],
    diff_ma: list[float],
    *,
    window_sec: float,
    step_sec: float,
    top_windows: int,
) -> tuple[dict[str, Any], float | None]:
    """用差值相对平均值的连续偏离段标注抬升/回落（覆盖更全）。"""
    out = dict(spike)
    summary = dict(out.get("current_summary") or {})
    avg = _diff_avg_ma(diff_ma, summary)
    if avg is None:
        return out, None
    summary["diff_avg_ma"] = avg
    summary["trend_vs_avg"] = True
    out["current_summary"] = summary
    # 默认抬升/回落都尽量标全；top_windows 作为上限（至少 8）
    rise_n = max(8, int(top_windows) if top_windows else 8)
    dip_n = max(8, int(top_windows) if top_windows else 8)
    out["spike_windows"] = _find_segments_vs_avg(
        diff_ma,
        avg=avg,
        mode="rise",
        top_n=rise_n,
    )
    out["dip_windows"] = _find_segments_vs_avg(
        diff_ma,
        avg=avg,
        mode="dip",
        top_n=dip_n,
    )
    out["trend_basis"] = {
        "method": "vs_diff_avg_contiguous",
        "diff_avg_ma": avg,
        "window_sec": window_sec,
        "step_sec": step_sec,
        "min_abs_residual_ma": 15.0,
        "min_duration_sec": 5.0,
        "merge_gap_sec": 3.0,
        "smooth_sec": 3.0,
        "note": (
            "抬升/回落=差值相对平均值连续偏离≥15mA的时段"
            "（3s平滑、≤3s空洞合并、≥5s保留；按强度×时长取 Top-N）"
        ),
    }
    return out, avg


def _build_chart_payload(
    high_series: dict[str, Any],
    low_series: dict[str, Any] | None,
    *,
    high_label: str,
    low_label: str,
    abs_time: list[str] | None = None,
    thread_series: dict[str, Any] | None = None,
    trend_markers: list[dict[str, Any]] | None = None,
    diff_avg_ma: float | None = None,
) -> dict[str, Any]:
    aligned = _align_series(high_series, low_series)
    avg = diff_avg_ma
    if avg is None and aligned.get("diff_ma"):
        avg = _diff_avg_ma(list(aligned.get("diff_ma") or []))
    return {
        "mode": aligned["mode"],
        "bucket_options": list(_BUCKET_OPTIONS),
        "default_bucket": 1,
        "high_label": high_label,
        "low_label": low_label,
        "t_sec": aligned["t_sec"],
        "high_ma": aligned["high_ma"],
        "low_ma": aligned["low_ma"],
        "diff_ma": aligned["diff_ma"],
        "diff_avg_ma": avg,
        "abs_time": list(abs_time or []),
        "thread_series": thread_series or {},
        "thread_scale_max": _thread_scale_max(thread_series or {}),
        "trend_markers": list(trend_markers or []),
    }


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _parse_log_time(text: str, *, year: int | None = None) -> datetime | None:
    s = str(text or "").strip()
    if not s:
        return None
    year = year or datetime.now().year
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%m-%d %H:%M:%S.%f", "%m-%d %H:%M:%S"):
        try:
            if fmt.startswith("%Y"):
                return datetime.strptime(s, fmt)
            return datetime.strptime(f"{year}-{s}", f"%Y-{fmt}")
        except ValueError:
            continue
    return None


def _scene_start_from_analysis(analysis_dir: Path) -> datetime | None:
    for name in ("game_cpu_gpu_ddr.json", "game_time_window.json"):
        data = _read_json(analysis_dir / name)
        for path in (
            ("game_window", "start"),
            ("kernel_cpu", "game_window", "start"),
            ("time_windows", "T_game", "start"),
            ("window", "start"),
            ("T_game", "start"),
        ):
            cur: Any = data
            ok = True
            for key in path:
                if not isinstance(cur, dict) or key not in cur:
                    ok = False
                    break
                cur = cur[key]
            if ok:
                dt = _parse_log_time(str(cur))
                if dt is not None:
                    return dt
    return None


def _build_abs_time_labels(count: int, start_dt: datetime | None) -> list[str]:
    if start_dt is None or count <= 0:
        return []
    return [(start_dt + timedelta(seconds=i)).strftime("%m-%d %H:%M:%S") for i in range(count)]


def _infer_reason_from_processes(names: list[str], *, thermal_hit: bool, network_hit: bool, background_hit: bool) -> list[str]:
    joined = " ".join(names).lower()
    reasons: list[str] = []
    if any(x in joined for x in ("mainthread-ue4", "mali", "surfaceflinger", "composer", "kfps")):
        reasons.append("游戏渲染/显示链路负载变化")
    if any(x in joined for x in ("touch", "input")):
        reasons.append("输入事件触发负载变化")
    if any(x in joined for x in ("audio", "dsp", "hif_thread")):
        reasons.append("音频/声学链路活动")
    if any(x in joined for x in ("system_server", "binder", "storaged", "rms")):
        reasons.append("系统服务调度或系统后台活动")
    if any("." in x and "ue4" not in x.lower() for x in names):
        reasons.append("第三方应用/后台进程活动")
    if thermal_hit:
        reasons.append("温控/温升介入")
    if network_hit:
        reasons.append("网络信号或数传活动")
    if background_hit:
        reasons.append("后台行为或服务活动")
    if not reasons:
        reasons.append("需结合更多日志进一步确认")
    out: list[str] = []
    for item in reasons:
        if item not in out:
            out.append(item)
    return out[:3]


def _normalize_reason_label(text: str) -> str:
    s = str(text or "").strip()
    if not s:
        return ""
    low = s.lower()
    if low == "thermal":
        return "温控/温升介入"
    if low == "network":
        return "网络信号或数传活动"
    if low == "background":
        return "后台行为或服务活动"
    return s


_THREAD_CATEGORY_COLORS = {
    "render": "#2563eb",
    "display": "#7c3aed",
    "input": "#0891b2",
    "audio": "#059669",
    "system": "#d97706",
    "background_app": "#dc2626",
    "other": "#64748b",
}


def _thread_category(name: str) -> tuple[str, str]:
    n = name.lower()
    if "mainthread" in n or "ue4" in n or "mali" in n:
        return "render", "渲染"
    if "surfaceflinger" in n or "composer" in n or "kfps" in n:
        return "display", "显示"
    if "touch" in n or "input" in n:
        return "input", "输入"
    if "audio" in n or "dsp" in n or "hif" in n:
        return "audio", "音频"
    if "system_server" in n or "binder" in n or "rms" in n or "storaged" in n:
        return "system", "系统"
    if "." in name and "ue4" not in n:
        return "background_app", "后台应用"
    return "other", "其他"


def _category_breakdown(matched: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not matched:
        return []
    total = sum(float(x.get("avg_usage") or 0) for x in matched) or 1.0
    buckets: dict[str, dict[str, Any]] = {}
    for item in matched:
        cat, label = _thread_category(str(item.get("name") or ""))
        bucket = buckets.setdefault(cat, {"category": cat, "label": label, "avg_usage": 0.0})
        bucket["avg_usage"] += float(item.get("avg_usage") or 0)
    out = [
        {
            "category": v["category"],
            "label": v["label"],
            "ratio_pct": round(float(v["avg_usage"]) / total * 100, 1),
            "avg_usage": round(float(v["avg_usage"]), 2),
        }
        for v in buckets.values()
    ]
    out.sort(key=lambda x: (-x["ratio_pct"], -x["avg_usage"]))
    return out


def _evidence_strength(matched: list[dict[str, Any]], trend_type: str) -> str:
    if not matched:
        return "弱"
    top_avg = float(matched[0].get("avg_usage") or 0)
    if trend_type == "rise" and top_avg >= 80 and len(matched) >= 2:
        return "强"
    if top_avg >= 30 or (trend_type == "dip" and matched):
        return "中"
    return "弱"


def _match_processes_in_window(
    samples: list[dict[str, Any]],
    abnormal_names: set[str],
    scene_start: datetime | None,
    start_sec: float,
    end_sec: float,
) -> list[dict[str, Any]]:
    if scene_start is None:
        return []
    abs_start = scene_start + timedelta(seconds=start_sec)
    abs_end = scene_start + timedelta(seconds=end_sec)
    proc_map: dict[str, list[float]] = {}
    for sample in samples:
        ts = _parse_log_time(str(sample.get("time") or ""), year=scene_start.year)
        if ts is None or ts < abs_start or ts > abs_end:
            continue
        for th in (sample.get("threads") or []):
            if not isinstance(th, dict):
                continue
            name = str(th.get("name") or "")
            if not name or name not in abnormal_names:
                continue
            try:
                usage = float(th.get("usage") or 0.0)
            except (TypeError, ValueError):
                usage = 0.0
            proc_map.setdefault(name, []).append(usage)
    matched = [
        {
            "name": name,
            "avg_usage": round(sum(vals) / len(vals), 2),
            "max_usage": round(max(vals), 2),
            "samples": len(vals),
            "category": _thread_category(name)[0],
            "category_label": _thread_category(name)[1],
        }
        for name, vals in proc_map.items()
        if vals
    ]
    matched.sort(key=lambda x: (-x["avg_usage"], -x["max_usage"], -x["samples"]))
    return matched


def _compare_thread_sides(
    high_threads: list[dict[str, Any]],
    low_threads: list[dict[str, Any]],
) -> dict[str, Any]:
    high_names = {str(x.get("name") or "") for x in high_threads}
    low_names = {str(x.get("name") or "") for x in low_threads}
    shared = sorted(high_names & low_names)
    high_only = sorted(high_names - low_names)
    low_only = sorted(low_names - high_names)
    delta_threads: list[dict[str, Any]] = []
    for name in shared:
        h = next((x for x in high_threads if x.get("name") == name), {})
        l = next((x for x in low_threads if x.get("name") == name), {})
        delta_threads.append(
            {
                "name": name,
                "high_avg_usage": h.get("avg_usage"),
                "low_avg_usage": l.get("avg_usage"),
                "delta_avg_usage": round(float(h.get("avg_usage") or 0) - float(l.get("avg_usage") or 0), 2),
            }
        )
    delta_threads.sort(key=lambda x: (-abs(float(x.get("delta_avg_usage") or 0)), x["name"]))
    return {
        "shared_threads": shared[:5],
        "high_only_threads": high_only[:5],
        "low_only_threads": low_only[:5],
        "delta_threads": delta_threads[:5],
    }


def _usage_series_in_window(
    samples: list[dict[str, Any]],
    scene_start: datetime | None,
    start_sec: float,
    end_sec: float,
    names: set[str],
) -> dict[str, list[float]]:
    """窗口内按 1s 桶生成各线程 CPU% 曲线（有采样则更新，否则沿用上次）。"""
    if scene_start is None or not names or end_sec < start_sec:
        return {n: [] for n in names}
    t0 = int(math.floor(float(start_sec)))
    t1 = max(t0, int(math.ceil(float(end_sec))))
    length = t1 - t0 + 1
    buckets: dict[str, dict[int, list[float]]] = {n: {} for n in names}
    abs_start = scene_start + timedelta(seconds=float(start_sec))
    abs_end = scene_start + timedelta(seconds=float(end_sec))
    for sample in samples:
        ts = _parse_log_time(str(sample.get("time") or ""), year=scene_start.year)
        if ts is None or ts < abs_start or ts > abs_end:
            continue
        rel = int(round((ts - scene_start).total_seconds()))
        for th in sample.get("threads") or []:
            if not isinstance(th, dict):
                continue
            name = str(th.get("name") or "")
            if name not in names:
                continue
            try:
                usage = float(th.get("usage") or 0.0)
            except (TypeError, ValueError):
                usage = 0.0
            buckets[name].setdefault(rel, []).append(usage)
    out: dict[str, list[float]] = {}
    for name in names:
        values: list[float] = []
        last = 0.0
        seen = False
        for i in range(length):
            sec = t0 + i
            vals = buckets[name].get(sec) or []
            if vals:
                last = round(sum(vals) / len(vals), 2)
                seen = True
            values.append(last if seen else 0.0)
        out[name] = values
    return out


def _build_thread_compare_curve(
    *,
    compare: dict[str, Any],
    high_threads: list[dict[str, Any]],
    low_threads: list[dict[str, Any]],
    high_samples: list[dict[str, Any]],
    low_samples: list[dict[str, Any]],
    scene_start: datetime | None,
    low_scene_start: datetime | None,
    start_sec: float,
    end_sec: float,
) -> dict[str, Any]:
    """双机线程对照曲线数据：共有进程双线，特有进程单线；上方按进程点选。"""
    high_avg = {str(x.get("name") or ""): float(x.get("avg_usage") or 0) for x in high_threads}
    low_avg = {str(x.get("name") or ""): float(x.get("avg_usage") or 0) for x in low_threads}
    processes: list[dict[str, Any]] = []
    for row in (compare.get("delta_threads") or [])[:5]:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "")
        if not name:
            continue
        processes.append(
            {
                "name": name,
                "kind": "shared",
                "high_avg": round(float(row.get("high_avg_usage") or high_avg.get(name) or 0), 2),
                "low_avg": round(float(row.get("low_avg_usage") or low_avg.get(name) or 0), 2),
                "delta_avg": round(float(row.get("delta_avg_usage") or 0), 2),
            }
        )
    for name in [str(x) for x in (compare.get("high_only_threads") or [])[:3] if str(x)]:
        if any(p["name"] == name for p in processes):
            continue
        processes.append(
            {
                "name": name,
                "kind": "high_only",
                "high_avg": round(high_avg.get(name) or 0, 2),
                "low_avg": None,
                "delta_avg": None,
            }
        )
    for name in [str(x) for x in (compare.get("low_only_threads") or [])[:3] if str(x)]:
        if any(p["name"] == name for p in processes):
            continue
        processes.append(
            {
                "name": name,
                "kind": "low_only",
                "high_avg": None,
                "low_avg": round(low_avg.get(name) or 0, 2),
                "delta_avg": None,
            }
        )
    names = {str(p["name"]) for p in processes}
    high_series = _usage_series_in_window(high_samples, scene_start, start_sec, end_sec, names)
    low_series = _usage_series_in_window(low_samples, low_scene_start, start_sec, end_sec, names)
    t0 = int(math.floor(float(start_sec)))
    t1 = max(t0, int(math.ceil(float(end_sec))))
    t_sec = list(range(t0, t1 + 1))
    for proc in processes:
        name = str(proc["name"])
        kind = str(proc.get("kind") or "")
        hv = high_series.get(name) or [0.0] * len(t_sec)
        lv = low_series.get(name) or [0.0] * len(t_sec)
        if kind == "shared":
            proc["high_values"] = hv
            proc["low_values"] = lv
        elif kind == "high_only":
            proc["high_values"] = hv
            proc["low_values"] = []
        else:
            proc["high_values"] = []
            proc["low_values"] = lv
    return {
        "start_sec": round(float(start_sec), 1),
        "end_sec": round(float(end_sec), 1),
        "t_sec": t_sec,
        "processes": processes,
        "default_name": processes[0]["name"] if processes else "",
    }


def _build_trend_correlations(
    spike: dict[str, Any],
    analysis_dir: Path,
    *,
    compare_analysis_dir: Path | None = None,
) -> list[dict[str, Any]]:
    cpu = _read_json(analysis_dir / "game_cpu_gpu_ddr.json")
    low_cpu = _read_json(compare_analysis_dir / "game_cpu_gpu_ddr.json") if compare_analysis_dir else {}
    thermal = _read_json(analysis_dir / "game_thermal.json")
    network = _read_json(analysis_dir / "game_network.json")
    background = _read_json(analysis_dir / "game_background.json")
    corr = _read_json(analysis_dir / "game_current_log_correlate.json")
    kernel = (cpu.get("kernel_cpu") or {})
    low_kernel = (low_cpu.get("kernel_cpu") or {})
    abnormal = kernel.get("abnormal_processes") or []
    low_abnormal = low_kernel.get("abnormal_processes") or []
    abnormal_names = {str(x.get("name") or "") for x in abnormal if str(x.get("name") or "")}
    low_abnormal_names = {str(x.get("name") or "") for x in low_abnormal if str(x.get("name") or "")}
    samples = [x for x in (kernel.get("cpu_samples") or []) if isinstance(x, dict)]
    low_samples = [x for x in (low_kernel.get("cpu_samples") or []) if isinstance(x, dict)]
    scene_start = _scene_start_from_analysis(analysis_dir)
    low_scene_start = _scene_start_from_analysis(compare_analysis_dir) if compare_analysis_dir else None
    raised = [x for x in (corr.get("raised_windows") or []) if isinstance(x, dict)]
    candidates: list[dict[str, Any]] = []
    for x in spike.get("spike_windows") or []:
        if isinstance(x, dict):
            y = dict(x)
            y["_trend_type"] = "rise"
            candidates.append(y)
    for x in spike.get("dip_windows") or []:
        if isinstance(x, dict):
            y = dict(x)
            y["_trend_type"] = "dip"
            candidates.append(y)
    # 按时间排序，保证图上编号与时段顺序一致
    candidates.sort(key=lambda x: float(x.get("start_sec") or 0))
    out: list[dict[str, Any]] = []
    for idx, item in enumerate(candidates, start=1):
        start_sec = float(item.get("start_sec") or 0.0)
        end_sec = float(item.get("end_sec") or start_sec)
        duration = max(0.0, end_sec - start_sec)
        trend_type = str(item.get("_trend_type") or "")
        abs_start = scene_start + timedelta(seconds=start_sec) if scene_start else None
        abs_end = scene_start + timedelta(seconds=end_sec) if scene_start else None
        matched = _match_processes_in_window(samples, abnormal_names, scene_start, start_sec, end_sec)
        low_matched = (
            _match_processes_in_window(low_samples, low_abnormal_names, low_scene_start, start_sec, end_sec)
            if compare_analysis_dir is not None
            else []
        )
        names = [x["name"] for x in matched[:5]]
        thermal_hit = bool((thermal.get("thermal_events") or thermal.get("events") or [])) or "生效" in json.dumps(thermal, ensure_ascii=False)
        network_hit = "suspect" in json.dumps(network, ensure_ascii=False).lower()
        background_hit = bool(background.get("abnormal_processes_linked") or background.get("abnormal_processes"))
        possible_reasons = _infer_reason_from_processes(
            names,
            thermal_hit=thermal_hit,
            network_hit=network_hit,
            background_hit=background_hit,
        )
        corr_causes: list[str] = []
        for rw in raised:
            rs = float(rw.get("start_sec") or 0.0)
            re = float(rw.get("end_sec") or rs)
            if not (end_sec < rs or start_sec > re):
                cause = _normalize_reason_label(rw.get("primary_cause") or rw.get("cause") or rw.get("summary") or "")
                if cause:
                    corr_causes.append(cause)
        if corr_causes:
            for c in corr_causes:
                if c not in possible_reasons:
                    possible_reasons.append(c)
        side_compare = _compare_thread_sides(matched, low_matched) if low_matched else {}
        if side_compare:
            side_compare["curve"] = _build_thread_compare_curve(
                compare=side_compare,
                high_threads=matched,
                low_threads=low_matched,
                high_samples=samples,
                low_samples=low_samples,
                scene_start=scene_start,
                low_scene_start=low_scene_start,
                start_sec=start_sec,
                end_sec=end_sec,
            )
        mean_diff = item.get("mean_diff_ma")
        delta_from_avg = item.get("delta_from_avg_ma")
        try:
            slope = round(float(mean_diff) / max(duration, 1.0), 2) if mean_diff is not None else None
        except (TypeError, ValueError):
            slope = None
        out.append(
            {
                "segment_id": idx,
                "trend_type": trend_type,
                "stage_label": {"rise": "抬升", "dip": "回落"}.get(trend_type, trend_type),
                "relative_time": item.get("relative_time"),
                "start_sec": start_sec,
                "end_sec": end_sec,
                "duration_sec": round(duration, 1),
                "absolute_start": abs_start.strftime("%m-%d %H:%M:%S") if abs_start else "",
                "absolute_end": abs_end.strftime("%m-%d %H:%M:%S") if abs_end else "",
                "mean_diff_ma": mean_diff,
                "delta_from_avg_ma": delta_from_avg,
                "peak_diff_ma": item.get("max_diff_ma") or item.get("min_diff_ma"),
                "slope_ma_per_sec": slope,
                "matched_processes": matched[:5],
                "low_matched_processes": low_matched[:5],
                "category_breakdown": _category_breakdown(matched[:5]),
                "evidence_strength": _evidence_strength(matched, trend_type),
                "possible_reasons": possible_reasons[:4],
                "thread_compare": side_compare,
            }
        )
    return out


def _resolve_compare_analysis_dir(
    *,
    log_compare: str,
    compare_analysis_dir: str,
) -> Path | None:
    if compare_analysis_dir.strip():
        p = Path(compare_analysis_dir).expanduser()
        return p.resolve() if p.exists() else None
    if log_compare.strip():
        p = Path(log_compare).expanduser()
        if p.exists():
            return (p / "analysis").resolve()
    return None


def _merge_thread_details(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, list[float]] = {}
    for item in items:
        name = str(item.get("name") or "")
        if not name:
            continue
        try:
            usage = float(item.get("usage") or item.get("avg_usage") or 0.0)
        except (TypeError, ValueError):
            usage = 0.0
        merged.setdefault(name, []).append(usage)
    out = [
        {
            "name": name,
            "avg_usage": round(sum(vals) / len(vals), 2),
            "max_usage": round(max(vals), 2),
        }
        for name, vals in merged.items()
        if vals
    ]
    out.sort(key=lambda x: (-x["avg_usage"], -x["max_usage"], x["name"]))
    return out[:5]


def _build_abnormal_thread_timeline(analysis_dir: Path, *, label: str) -> dict[str, Any]:
    cpu = _read_json(analysis_dir / "game_cpu_gpu_ddr.json")
    kernel = cpu.get("kernel_cpu") or {}
    abnormal = kernel.get("abnormal_processes") or []
    abnormal_names = {str(x.get("name") or "") for x in abnormal if str(x.get("name") or "")}
    samples = [x for x in (kernel.get("cpu_samples") or []) if isinstance(x, dict)]
    scene_start = _scene_start_from_analysis(analysis_dir)
    duration_sec = float((kernel.get("game_window") or cpu.get("game_window") or {}).get("duration_seconds") or 0.0)
    point_values: dict[int, list[float]] = {}
    point_details: dict[int, list[dict[str, Any]]] = {}
    thread_points: dict[str, dict[int, list[float]]] = {}
    for sample in samples:
        ts = _parse_log_time(str(sample.get("time") or ""), year=scene_start.year if scene_start else None)
        if ts is None or scene_start is None:
            continue
        rel_sec = (ts - scene_start).total_seconds()
        if rel_sec < 0:
            continue
        idx = int(round(rel_sec))
        total = 0.0
        details: list[dict[str, Any]] = []
        for th in (sample.get("threads") or []):
            if not isinstance(th, dict):
                continue
            name = str(th.get("name") or "")
            if not name or name not in abnormal_names:
                continue
            try:
                usage = float(th.get("usage") or 0.0)
            except (TypeError, ValueError):
                usage = 0.0
            total += usage
            details.append({"name": name, "usage": usage})
            thread_points.setdefault(name, {}).setdefault(idx, []).append(usage)
        point_values.setdefault(idx, []).append(total)
        if details:
            point_details.setdefault(idx, []).extend(details)
    max_idx = max(point_values.keys(), default=max(int(math.ceil(duration_sec)), 0))
    values: list[float] = []
    details_series: list[list[dict[str, Any]]] = []
    last_val = 0.0
    last_details: list[dict[str, Any]] = []
    for idx in range(max_idx + 1):
        if idx in point_values:
            last_val = round(sum(point_values[idx]) / len(point_values[idx]), 2)
            last_details = _merge_thread_details(point_details.get(idx, []))
        values.append(last_val)
        details_series.append(list(last_details))
    per_thread_stats: dict[str, dict[str, Any]] = {}
    for name, buckets in thread_points.items():
        all_vals = [v for vals in buckets.values() for v in vals]
        if not all_vals:
            continue
        cat, cat_label = _thread_category(name)
        active_buckets = len(buckets)
        per_thread_stats[name] = {
            "name": name,
            "category": cat,
            "category_label": cat_label,
            "avg_usage": round(sum(all_vals) / len(all_vals), 2),
            "max_usage": round(max(all_vals), 2),
            "active_ratio": round(active_buckets / max(max_idx + 1, 1), 4),
        }
    return {
        "label": label,
        "values": values,
        "details": details_series,
        "scene_start": scene_start.strftime("%m-%d %H:%M:%S") if scene_start else "",
        "per_thread_stats": list(
            sorted(per_thread_stats.values(), key=lambda x: (-x["avg_usage"], -x["max_usage"], x["name"]))
        ),
        "per_thread_points": {name: buckets for name, buckets in thread_points.items()},
        "length": max_idx + 1,
    }


def _build_thread_series_values(
    per_thread_points: dict[str, dict[int, list[float]]],
    *,
    length: int,
    names: list[str],
) -> list[dict[str, Any]]:
    lanes: list[dict[str, Any]] = []
    for name in names:
        buckets = per_thread_points.get(name) or {}
        values: list[float] = []
        last = 0.0
        for idx in range(length):
            if idx in buckets and buckets[idx]:
                last = round(sum(buckets[idx]) / len(buckets[idx]), 2)
            values.append(last)
        cat, cat_label = _thread_category(name)
        lanes.append(
            {
                "name": name,
                "category": cat,
                "category_label": cat_label,
                "color": _THREAD_CATEGORY_COLORS.get(cat, _THREAD_CATEGORY_COLORS["other"]),
                "values": values,
                "avg_usage": round(sum(values) / len(values), 2) if values else 0.0,
                "max_usage": round(max(values), 2) if values else 0.0,
            }
        )
    return lanes


def _select_display_threads(
    thread_series: dict[str, Any],
    trend_segments: list[dict[str, Any]],
    *,
    limit: int = 6,
) -> list[str]:
    scores: dict[str, float] = {}
    side_names: dict[str, set[str]] = {"high": set(), "low": set()}
    for side in ("high", "low"):
        for stat in (thread_series.get(side) or {}).get("per_thread_stats") or []:
            name = str(stat.get("name") or "")
            if not name:
                continue
            side_names[side].add(name)
            scores[name] = max(
                scores.get(name, 0.0),
                float(stat.get("avg_usage") or 0) * 2 + float(stat.get("max_usage") or 0),
            )
    for seg in trend_segments:
        for key, side in (("matched_processes", "high"), ("low_matched_processes", "low")):
            for proc in seg.get(key) or []:
                if not isinstance(proc, dict):
                    continue
                name = str(proc.get("name") or "")
                if not name:
                    continue
                side_names[side].add(name)
                scores[name] = scores.get(name, 0.0) + 120 + float(proc.get("avg_usage") or 0)
    shared = side_names["high"] & side_names["low"]
    ordered = sorted(scores.items(), key=lambda x: (-x[1], x[0]))
    shared_ordered = [name for name, _ in ordered if name in shared]
    unique_ordered = [name for name, _ in ordered if name not in shared]
    selected: list[str] = []
    # 共享线程优先占位；同时给单侧独有线程预留 1~2 行，保证仍能对齐展示
    unique_reserve = min(2, len(unique_ordered)) if unique_ordered else 0
    shared_slots = max(3, limit - unique_reserve) if shared_ordered else 0
    for name in shared_ordered:
        if len(selected) >= shared_slots:
            break
        selected.append(name)
    for name in unique_ordered:
        if len(selected) >= limit:
            break
        selected.append(name)
    for name in shared_ordered:
        if len(selected) >= limit:
            break
        if name not in selected:
            selected.append(name)
    return selected


def _finalize_thread_series(
    thread_series: dict[str, Any],
    trend_segments: list[dict[str, Any]],
) -> dict[str, Any]:
    display_names = _select_display_threads(thread_series, trend_segments)
    out: dict[str, Any] = {"display_threads": display_names}
    for side in ("high", "low"):
        if side not in thread_series:
            continue
        side_data = thread_series.get(side) or {}
        length = int(side_data.get("length") or len(side_data.get("values") or []))
        points = side_data.get("per_thread_points") or {}
        # 两侧强制同一行顺序；本侧没有的线程填 0，保证上下对齐可比
        names = list(display_names)
        if not names and side_data.get("per_thread_stats"):
            names = [str(x.get("name") or "") for x in side_data["per_thread_stats"][:5] if x.get("name")]
        top_threads = _build_thread_series_values(points, length=length, names=names)
        for lane in top_threads:
            lane["present"] = bool(lane.get("name") in points)
        out[side] = {
            "label": side_data.get("label") or side,
            "values": side_data.get("values") or [],
            "details": side_data.get("details") or [],
            "scene_start": side_data.get("scene_start") or "",
            "top_threads": top_threads,
        }
    return out


def _thread_scale_max(thread_series: dict[str, Any]) -> float:
    max_val = 0.0
    for side in ("high", "low"):
        side_data = thread_series.get(side) or {}
        for lane in side_data.get("top_threads") or []:
            if not isinstance(lane, dict):
                continue
            try:
                lane_max = float(lane.get("max_usage") or 0.0)
            except (TypeError, ValueError):
                lane_max = 0.0
            max_val = max(max_val, lane_max)
    return round(max_val, 2) if max_val > 0 else 1.0


def _trend_markers_from_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in segments:
        if not isinstance(item, dict):
            continue
        try:
            start_sec = float(item.get("start_sec") or 0.0)
            end_sec = float(item.get("end_sec") or start_sec)
        except (TypeError, ValueError):
            continue
        if end_sec < start_sec:
            start_sec, end_sec = end_sec, start_sec
        trend_type = str(item.get("trend_type") or "")
        out.append(
            {
                "segment_id": item.get("segment_id"),
                "trend_type": trend_type,
                "stage_label": item.get("stage_label")
                or {"rise": "抬升", "dip": "回落"}.get(trend_type, trend_type),
                "start_sec": start_sec,
                "end_sec": end_sec,
                "relative_time": item.get("relative_time") or "",
            }
        )
    return out


def _render_chart_block(chart_payload: dict[str, Any]) -> str:
    uid = f"spike_{uuid4().hex[:8]}"
    payload = json.dumps(chart_payload, ensure_ascii=False)
    compare = chart_payload.get("mode") == "compare"
    # 异常线程泳道已合并到澄清报告「二、线程明细」[K] 方块图
    diff_block = (
        f'<div style="margin-top:14px;">'
        f'<p style="margin:0 0 6px;font-size:12px;font-weight:600;color:var(--color-text-primary);">电流差值曲线（测试机 - 对比机）</p>'
        f'<canvas id="{uid}_diff" style="width:100%;height:220px;border:1px solid var(--color-border-tertiary);border-radius:8px;background:#fff;"></canvas>'
        f"</div>"
        f'<div style="margin-top:14px;">'
        f'<p style="margin:0 0 6px;font-size:12px;font-weight:600;color:var(--color-text-primary);">差值变化趋势柱状图</p>'
        f'<canvas id="{uid}_bar" style="width:100%;height:220px;border:1px solid var(--color-border-tertiary);border-radius:8px;background:#fff;"></canvas>'
        f"</div>"
    ) if compare else ""
    single_note = (
        '<p style="margin:8px 0 0;font-size:12px;color:var(--color-text-tertiary);">'
        "仅检测到一份 pt5 电流图，本段只展示单机曲线，不做差值对比。"
        "</p>"
    ) if not compare else ""
    return (
        f'<div id="{uid}" style="margin-top:10px;">'
        '<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:8px;">'
        '<span style="font-size:12px;color:var(--color-text-secondary);">间隔：</span>'
        f'<button type="button" data-bucket="1" style="padding:2px 8px;border:1px solid var(--color-border-tertiary);border-radius:999px;background:#eef6ff;cursor:pointer;">1s</button>'
        f'<button type="button" data-bucket="5" style="padding:2px 8px;border:1px solid var(--color-border-tertiary);border-radius:999px;background:#fff;cursor:pointer;">5s</button>'
        f'<button type="button" data-bucket="10" style="padding:2px 8px;border:1px solid var(--color-border-tertiary);border-radius:999px;background:#fff;cursor:pointer;">10s</button>'
        '<span style="width:8px;"></span>'
        f'<button type="button" data-pan="-1" style="padding:2px 10px;border:1px solid var(--color-border-tertiary);border-radius:999px;background:#fff;cursor:pointer;">◀ 左移</button>'
        f'<button type="button" data-pan="1" style="padding:2px 10px;border:1px solid var(--color-border-tertiary);border-radius:999px;background:#fff;cursor:pointer;">右移 ▶</button>'
        "</div>"
        f'<canvas id="{uid}_main" style="width:100%;height:260px;border:1px solid var(--color-border-tertiary);border-radius:8px;background:#fff;"></canvas>'
        f"{diff_block}{single_note}"
        '<p style="margin:6px 0 0;font-size:11px;color:var(--color-text-tertiary);">'
        "支持鼠标滚轮缩放横轴；悬停时显示当前时刻两份电流值/差值。"
        "红色纵向带=相对平均值的抬升段，蓝色纵向带=相对平均值的回落段，紫色虚线=差值平均值；"
        "抬升/回落按差值连续偏离≥15mA自动分段（更完整覆盖显著差异时段）。"
        "异常线程占用见下方「二、线程明细」[K] 方块图。"
        "</p>"
        f"<script>(function(){{"
        f"const payload={payload};"
        f"const root=document.getElementById('{uid}'); if(!root) return;"
        f"const main=document.getElementById('{uid}_main');"
        f"const diff=document.getElementById('{uid}_diff');"
        f"const bar=document.getElementById('{uid}_bar');"
        f"const buttons=root.querySelectorAll('button[data-bucket]');"
        f"const panButtons=root.querySelectorAll('button[data-pan]');"
        "const colors={high:'#2563eb',low:'#f59e0b',diff:'#16a34a',avg:'#9333ea',pos:'rgba(37,99,235,0.7)',neg:'rgba(239,68,68,0.7)',riseFill:'rgba(239,68,68,0.14)',riseStroke:'rgba(220,38,38,0.75)',dipFill:'rgba(37,99,235,0.12)',dipStroke:'rgba(37,99,235,0.65)'};"
        "const tooltip=document.createElement('div'); tooltip.style.cssText='position:fixed;display:none;pointer-events:none;background:rgba(17,24,39,0.92);color:#fff;padding:6px 8px;border-radius:6px;font-size:12px;line-height:1.45;z-index:9999;box-shadow:0 6px 18px rgba(0,0,0,0.18)'; document.body.appendChild(tooltip);"
        "function bucketize(vals,b){const out=[]; for(let i=0;i<vals.length;i+=b){const seg=vals.slice(i,i+b); if(!seg.length) continue; const mean=seg.reduce((a,c)=>a+Number(c||0),0)/seg.length; out.push(Number(mean.toFixed(2)));} return out;}"
        "function labels(n,b){const out=[]; for(let i=0;i<n;i++){const sec=i*b; const m=Math.floor(sec/60); const s=sec%60; out.push(String(m).padStart(2,'0')+':'+String(s).padStart(2,'0'));} return out;}"
        "function absLabels(b){const src=payload.abs_time||[]; if(!src.length) return []; if(b<=1) return src.slice(); const out=[]; for(let i=0;i<src.length;i+=b){ out.push(src[i]||''); } return out; }"
        "function bucketizeThreadDetails(details,b){const out=[]; for(let i=0;i<details.length;i+=b){ const seg=details.slice(i,i+b); const merged={}; seg.forEach(arr=>{ (arr||[]).forEach(it=>{ if(!it||!it.name) return; const key=String(it.name); const val=Number(it.usage ?? it.avg_usage ?? 0); if(!merged[key]) merged[key]=[]; merged[key].push(val); }); }); const rows=Object.entries(merged).map(([name,vals])=>({name,avg:Number((vals.reduce((a,c)=>a+c,0)/Math.max(vals.length,1)).toFixed(2)),max:Number(Math.max(...vals).toFixed(2))})).sort((a,b)=>b.avg-a.avg||b.max-a.max||String(a.name).localeCompare(String(b.name))).slice(0,4); out.push(rows); } return out; }"
        "function fit(canvas){const r=canvas.getBoundingClientRect(); canvas.width=Math.max(300,Math.floor(r.width)); canvas.height=Math.max(180,Math.floor(r.height));}"
        "function scale(vals,h,pad){let min=Math.min(...vals), max=Math.max(...vals); if(!isFinite(min)||!isFinite(max)){min=0; max=50;} min=Math.floor(min/50)*50; max=Math.ceil(max/50)*50; if(min===max){max=min+50;} return {min,max,toY:(v)=> pad + (h-2*pad)*(1-(v-min)/(max-min))};}"
        "function drawAxes(ctx,w,h,pad,yMin,yMax,xlabs,zoom){const innerW=w-2*pad, innerH=h-2*pad; ctx.strokeStyle='rgba(203,213,225,0.55)'; ctx.lineWidth=1; for(let yv=yMin; yv<=yMax+0.001; yv+=50){ const y=pad + innerH*(1-((yv-yMin)/Math.max(yMax-yMin,1))); ctx.beginPath(); ctx.moveTo(pad,y); ctx.lineTo(w-pad,y); ctx.stroke(); ctx.fillStyle='#64748b'; ctx.font='11px sans-serif'; ctx.fillText(String(Math.round(yv)), 4, y+4); } const start=zoom.start; const end=Math.max(start+1, zoom.end); const visCount=Math.max(end-start,1); for(let i=start;i<end;i++){ const x=pad + innerW*((i-start)/Math.max(visCount-1,1)); ctx.beginPath(); ctx.moveTo(x,pad); ctx.lineTo(x,h-pad); ctx.stroke(); } ctx.strokeStyle='#cbd5e1'; ctx.beginPath(); ctx.moveTo(pad,pad); ctx.lineTo(pad,h-pad); ctx.lineTo(w-pad,h-pad); ctx.stroke(); if(xlabs.length){ ctx.fillStyle='#64748b'; ctx.font='11px sans-serif'; ctx.fillText(xlabs[start]||'',pad,h-8); ctx.fillText(xlabs[end-1]||'',w-pad-36,h-8);} }"
        "function xAt(i,n,w,pad){const den=Math.max(n-1,1); return pad + (w-2*pad)*(i/den);}"
        "function showTip(ev, lines){tooltip.innerHTML=lines.join('<br>'); tooltip.style.display='block'; tooltip.style.left=(ev.clientX+14)+'px'; tooltip.style.top=(ev.clientY+14)+'px';}"
        "function hideTip(){tooltip.style.display='none';}"
        "function pan(dir,total){const span=Math.max(20,state.zoom.end-state.zoom.start); const step=Math.max(1, Math.round(span*0.2)); let start=state.zoom.start + dir*step; start=Math.max(0, Math.min(Math.max(total-span,0), start)); state.zoom.start=start; state.zoom.end=Math.min(total,start+span);}"
        "function markersAtSec(sec){ return (payload.trend_markers||[]).filter(m=>{ const s=Number(m.start_sec||0), e=Number(m.end_sec||s); return sec>=s && sec<=e; }); }"
        "function drawTrendBands(ctx,w,h,pad,zoom){ const segs=payload.trend_markers||[]; if(!segs.length) return; const start=zoom.start; const end=Math.max(start+1, zoom.end); const vis=Math.max(end-start,1); const den=Math.max(vis-1,1); segs.forEach(seg=>{ const sIdx=Math.floor(Number(seg.start_sec||0)/state.bucket); const eIdx=Math.max(sIdx, Math.ceil(Number(seg.end_sec||seg.start_sec||0)/state.bucket)); if(eIdx<start || sIdx>=end) return; const leftIdx=Math.max(sIdx,start); const rightIdx=Math.min(eIdx, end-1); const left=pad + (w-2*pad)*((leftIdx-start)/den); const right=pad + (w-2*pad)*((rightIdx-start)/den); const rise=String(seg.trend_type||'')==='rise'; const fill=rise?colors.riseFill:colors.dipFill; const stroke=rise?colors.riseStroke:colors.dipStroke; ctx.fillStyle=fill; ctx.fillRect(left, pad, Math.max(2, right-left), h-2*pad); ctx.strokeStyle=stroke; ctx.lineWidth=1.5; ctx.setLineDash([5,3]); ctx.beginPath(); ctx.moveTo(left,pad); ctx.lineTo(left,h-pad); ctx.stroke(); ctx.beginPath(); ctx.moveTo(right,pad); ctx.lineTo(right,h-pad); ctx.stroke(); ctx.setLineDash([]); ctx.fillStyle=stroke; ctx.font='11px sans-serif'; const tag=(seg.stage_label|| (rise?'抬升':'回落')) + (seg.segment_id!=null?(' #'+seg.segment_id):''); ctx.fillText(tag, left+3, pad+12); }); }"
        "function drawAvgLine(ctx,w,h,pad,sc,avg){ if(!isFinite(avg)) return; const y=sc.toY(avg); ctx.strokeStyle=colors.avg; ctx.lineWidth=1.6; ctx.setLineDash([7,4]); ctx.beginPath(); ctx.moveTo(pad,y); ctx.lineTo(w-pad,y); ctx.stroke(); ctx.setLineDash([]); ctx.fillStyle=colors.avg; ctx.font='11px sans-serif'; ctx.fillText('平均值 '+Number(avg).toFixed(1)+' mA', pad+4, Math.max(pad+12, y-4)); }"
        "function drawLineChart(canvas, series, title, key){ if(!canvas) return; fit(canvas); const ctx=canvas.getContext('2d'); const w=canvas.width,h=canvas.height,pad=34; ctx.clearRect(0,0,w,h); const all=series.flatMap(s=>s.values); if(!all.length){ctx.fillStyle='#64748b';ctx.fillText('无数据',20,30); return;} const start=state.zoom.start; const end=Math.max(start+2, Math.min(state.zoom.end, series[0].values.length)); const visSeries=series.map(s=>({label:s.label,color:s.color,dashed:!!s.dashed,values:s.values.slice(start,end)})); const visAll=visSeries.flatMap(s=>s.values); const sc=scale(visAll,h,pad); const xlabs=labels(series[0].values.length, state.bucket); const abs=absLabels(state.bucket); drawAxes(ctx,w,h,pad,sc.min,sc.max,xlabs,{start,end}); drawTrendBands(ctx,w,h,pad,{start,end}); if(key==='diff' && isFinite(Number(payload.diff_avg_ma))) drawAvgLine(ctx,w,h,pad,sc,Number(payload.diff_avg_ma)); const n=Math.max(end-start-1,1); visSeries.forEach((s)=>{ if(s.dashed) return; ctx.strokeStyle=s.color; ctx.lineWidth=1.5; ctx.setLineDash([]); ctx.beginPath(); s.values.forEach((v,i)=>{ const x=xAt(i,n+1,w,pad); const y=sc.toY(v); if(i===0) ctx.moveTo(x,y); else ctx.lineTo(x,y); }); ctx.stroke(); }); ctx.fillStyle='#111827'; ctx.font='12px sans-serif'; ctx.fillText(title, pad, 16); let lx=pad; series.forEach((s)=>{ ctx.fillStyle=s.color; if(s.dashed){ ctx.fillRect(lx, h-18, 16, 2); } else { ctx.fillRect(lx, h-22, 10, 10); } ctx.fillStyle='#374151'; ctx.fillText(s.label, lx+18, h-13); lx += Math.max(110, s.label.length*8+24); }); if((payload.trend_markers||[]).length){ ctx.fillStyle=colors.riseStroke; ctx.fillRect(lx, h-22, 10, 10); ctx.fillStyle='#374151'; ctx.fillText('抬升段', lx+14, h-13); lx+=70; ctx.fillStyle=colors.dipStroke; ctx.fillRect(lx, h-22, 10, 10); ctx.fillStyle='#374151'; ctx.fillText('回落段', lx+14, h-13); } canvas.onmousedown=(ev)=>{ if(ev.button!==0) return; state.dragging={x:ev.clientX,start:state.zoom.start,end:state.zoom.end,total:series[0].values.length}; canvas.style.cursor='grabbing'; hideTip(); }; canvas.onmousemove=(ev)=>{ if(state.dragging){ const r=canvas.getBoundingClientRect(); const dx=ev.clientX-state.dragging.x; const span=state.dragging.end-state.dragging.start; const step=Math.round((dx/Math.max(r.width-2*pad,1))*span); let ns=state.dragging.start-step; ns=Math.max(0, Math.min(state.dragging.total-span, ns)); state.zoom.start=ns; state.zoom.end=ns+span; render(false); return; } const r=canvas.getBoundingClientRect(); const x=ev.clientX-r.left; if(x<pad||x>w-pad){ hideTip(); return; } const idx=Math.round(((x-pad)/(w-2*pad))*Math.max(end-start-1,1))+start; const sec=(idx*state.bucket); const t=labels(idx+1,state.bucket)[idx]||('00:00'); const lines=['相对时间 '+t+' ('+sec+'s)']; if(abs[idx]) lines.push('原始时间 '+abs[idx]); if(key==='main'){ lines.push(payload.high_label+': '+(series[0].values[idx]??'—')+' mA'); if(series[1]) lines.push(payload.low_label+': '+(series[1].values[idx]??'—')+' mA'); if((payload.diff_ma||[]).length) lines.push('差值: '+(bucketize(payload.diff_ma||[],state.bucket)[idx]??'—')+' mA'); } else if(key==='diff'){ const dv=series[0].values[idx]; const avg=Number(payload.diff_avg_ma); lines.push('差值: '+(dv??'—')+' mA'); if(isFinite(avg)){ lines.push('平均值: '+avg.toFixed(1)+' mA'); lines.push('相对均差: '+((Number(dv||0)-avg).toFixed(1))+' mA'); } lines.push(payload.high_label+': '+(bucketize(payload.high_ma||[],state.bucket)[idx]??'—')+' mA'); lines.push(payload.low_label+': '+(bucketize(payload.low_ma||[],state.bucket)[idx]??'—')+' mA'); } markersAtSec(sec).forEach(m=>lines.push((m.stage_label||m.trend_type||'趋势段')+(m.segment_id!=null?(' #'+m.segment_id):'')+' · '+(m.relative_time||''))); showTip(ev,lines); ctx.save(); render(false); ctx.strokeStyle='rgba(15,23,42,0.35)'; ctx.beginPath(); const vx=pad+((idx-start)/Math.max(end-start-1,1))*(w-2*pad); ctx.moveTo(vx,pad); ctx.lineTo(vx,h-pad); ctx.stroke(); ctx.restore(); }; canvas.onmouseup=()=>{ state.dragging=null; canvas.style.cursor='default'; }; canvas.onmouseleave=()=>{ if(!state.dragging){ hideTip(); render(false);} }; canvas.onwheel=(ev)=>{ ev.preventDefault(); const dir=ev.deltaY>0?1:-1; const span=Math.max(20, state.zoom.end-state.zoom.start); const center=(state.zoom.start+state.zoom.end)/2; let nextSpan=dir>0?Math.min(series[0].values.length, Math.round(span*1.25)):Math.max(20, Math.round(span*0.8)); state.zoom.start=Math.max(0, Math.round(center-nextSpan/2)); state.zoom.end=Math.min(series[0].values.length, state.zoom.start+nextSpan); if(state.zoom.end-state.zoom.start<20){ state.zoom.end=Math.min(series[0].values.length, state.zoom.start+20);} render(false); }; canvas.ondblclick=()=>{ resetZoom(); render(false); }; }"
        "function drawBarChart(canvas, vals, title){ if(!canvas) return; fit(canvas); const ctx=canvas.getContext('2d'); const w=canvas.width,h=canvas.height,pad=34; ctx.clearRect(0,0,w,h); if(!vals.length){ctx.fillStyle='#64748b';ctx.fillText('无数据',20,30); return;} const start=state.zoom.start; const end=Math.max(start+1, Math.min(state.zoom.end, vals.length)); const view=vals.slice(start,end); const avg=Number(payload.diff_avg_ma); const max=Math.max(...view, isFinite(avg)?avg:0, 0), min=Math.min(...view, isFinite(avg)?avg:0, 0); const range=(max-min)||1; const zeroY=pad + (h-2*pad)*(max/range); drawTrendBands(ctx,w,h,pad,{start,end}); ctx.strokeStyle='#cbd5e1'; ctx.beginPath(); ctx.moveTo(pad,zeroY); ctx.lineTo(w-pad,zeroY); ctx.stroke(); const bw=Math.max(2,(w-2*pad)/Math.max(view.length,1)-1); view.forEach((v,i)=>{ const x=pad+i*((w-2*pad)/Math.max(view.length,1)); const y=pad + (h-2*pad)*((max-v)/range); ctx.fillStyle=v>=0?colors.pos:colors.neg; ctx.fillRect(x, Math.min(y,zeroY), bw, Math.abs(zeroY-y));}); if(isFinite(avg)){ const ay=pad + (h-2*pad)*((max-avg)/range); ctx.strokeStyle=colors.avg; ctx.lineWidth=1.6; ctx.setLineDash([7,4]); ctx.beginPath(); ctx.moveTo(pad,ay); ctx.lineTo(w-pad,ay); ctx.stroke(); ctx.setLineDash([]); ctx.fillStyle=colors.avg; ctx.font='11px sans-serif'; ctx.fillText('平均值 '+avg.toFixed(1)+' mA', pad+4, Math.max(pad+12, ay-4)); } ctx.fillStyle='#111827'; ctx.font='12px sans-serif'; ctx.fillText(title, pad, 16); canvas.onmousemove=(ev)=>{ const r=canvas.getBoundingClientRect(); const x=ev.clientX-r.left; if(x<pad||x>w-pad){ hideTip(); return; } const idx=Math.min(end-1, Math.max(start, Math.floor(((x-pad)/(w-2*pad))*Math.max(view.length,1))+start)); const val=vals[idx]; const sec=idx*state.bucket; const lines=['时间 '+(labels(idx+1,state.bucket)[idx]||'')+' ('+sec+'s)','差值趋势: '+(val??'—')+' mA']; if(isFinite(avg)){ lines.push('平均值: '+avg.toFixed(1)+' mA'); lines.push('相对均差: '+((Number(val||0)-avg).toFixed(1))+' mA'); } markersAtSec(sec).forEach(m=>lines.push((m.stage_label||m.trend_type||'趋势段')+(m.segment_id!=null?(' #'+m.segment_id):'')+' · '+(m.relative_time||''))); showTip(ev, lines); }; canvas.onmouseleave=hideTip; canvas.onwheel=(ev)=>{ ev.preventDefault(); if(main&&main.onwheel) main.onwheel(ev); }; canvas.ondblclick=()=>{ resetZoom(); render(false); }; } "
        "const state={bucket:Number(payload.default_bucket||1), zoom:{start:0,end:Math.max((payload.t_sec||[]).length,1)}, dragging:null};"
        "function resetZoom(){ const len=Math.max(bucketize(payload.high_ma||[],state.bucket).length,1); state.zoom={start:0,end:len}; }"
        "function render(reset=true){const high=bucketize(payload.high_ma||[],state.bucket); const low=bucketize(payload.low_ma||[],state.bucket); const diffVals=bucketize(payload.diff_ma||[],state.bucket); if(reset) resetZoom(); const mainSeries=[{label:payload.high_label,values:high,color:colors.high}]; if((payload.low_ma||[]).length) mainSeries.push({label:payload.low_label,values:low,color:colors.low}); drawLineChart(main, mainSeries, (payload.mode==='compare'?'双机电流曲线':'单机电流曲线')+'（'+state.bucket+'s）', 'main'); if(payload.mode==='compare'){ const avg=Number(payload.diff_avg_ma); const diffSeries=[{label:'差值',values:diffVals,color:colors.diff}]; if(isFinite(avg)){ diffSeries.push({label:'平均值 '+avg.toFixed(1)+'mA',values:diffVals.map(()=>avg),color:colors.avg,dashed:true}); } drawLineChart(diff,diffSeries,'差值曲线（'+state.bucket+'s）','diff'); drawBarChart(bar,diffVals,'差值趋势（'+state.bucket+'s）'); }}"
        "buttons.forEach(btn=>btn.addEventListener('click',()=>{state.bucket=Number(btn.dataset.bucket||1); buttons.forEach(b=>b.style.background='#fff'); btn.style.background='#eef6ff'; render();}));"
        "panButtons.forEach(btn=>btn.addEventListener('click',()=>{const total=Math.max(bucketize(payload.high_ma||[],state.bucket).length,1); pan(Number(btn.dataset.pan||0), total); render(false);}));"
        "render();"
        "})();</script>"
        "</div>"
    )


def _render_segment_thread_curve(
    curve: dict[str, Any],
    *,
    high_label: str,
    low_label: str,
) -> str:
    """段内双机线程对照：上方进程芯片点选，曲线只画当前进程（共有双线 / 特有单线）。"""
    processes = [x for x in (curve.get("processes") or []) if isinstance(x, dict) and x.get("name")]
    t_sec = [int(x) for x in (curve.get("t_sec") or [])]
    if not processes or not t_sec:
        return ""
    uid = f"segth_{uuid4().hex[:8]}"
    payload = json.dumps(
        {
            "t_sec": t_sec,
            "start_sec": curve.get("start_sec"),
            "end_sec": curve.get("end_sec"),
            "high_label": high_label,
            "low_label": low_label,
            "default_name": curve.get("default_name") or processes[0]["name"],
            "processes": processes,
        },
        ensure_ascii=False,
    )
    chips: list[str] = []
    for proc in processes:
        name = str(proc.get("name") or "")
        kind = str(proc.get("kind") or "")
        if kind == "shared":
            tag = "共有"
            meta = f"Δ {float(proc.get('delta_avg') or 0):+.1f}pp"
            border = "#93c5fd"
        elif kind == "high_only":
            tag = f"{high_label}独有"
            meta = f"avg {float(proc.get('high_avg') or 0):.1f}pp"
            border = "#bfdbfe"
        else:
            tag = f"{low_label}独有"
            meta = f"avg {float(proc.get('low_avg') or 0):.1f}pp"
            border = "#fde68a"
        chips.append(
            f'<button type="button" data-name="{_esc(name)}" '
            f'style="padding:4px 10px;border:1px solid {border};border-radius:999px;background:#fff;'
            f'cursor:pointer;font-size:11px;color:#0f172a;max-width:220px;overflow:hidden;'
            f'text-overflow:ellipsis;white-space:nowrap;" title="{_esc(name)} · {_esc(tag)}">'
            f'<b>{_esc(name)}</b>'
            f'<span style="margin-left:6px;color:#64748b;">{_esc(tag)} · {_esc(meta)}</span>'
            f"</button>"
        )
    return (
        f'<div id="{uid}" style="margin-top:10px;">'
        f'<div style="font-size:12px;font-weight:600;color:#111827;margin-bottom:6px;">双机线程对照（曲线）</div>'
        f'<div data-chips style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px;">{"".join(chips)}</div>'
        f'<canvas id="{uid}_cv" style="width:100%;height:200px;border:1px solid #e2e8f0;border-radius:8px;background:#fff;display:block;"></canvas>'
        f'<div data-legend style="margin-top:6px;font-size:11px;color:#64748b;"></div>'
        f'<p style="margin:4px 0 0;font-size:11px;color:#94a3b8;">点击上方进程名仅显示该进程；共有进程同时画 {_esc(high_label)}/{_esc(low_label)} 两条曲线，独有进程只画一侧。</p>'
        f"<script>(function(){{"
        f"const payload={payload};"
        f"const root=document.getElementById('{uid}'); if(!root) return;"
        f"const canvas=document.getElementById('{uid}_cv'); if(!canvas) return;"
        "const chips=root.querySelector('[data-chips]');"
        "const legend=root.querySelector('[data-legend]');"
        "const tip=document.createElement('div');"
        "tip.style.cssText='position:fixed;display:none;pointer-events:none;z-index:9999;background:rgba(17,24,39,0.92);color:#fff;padding:6px 8px;border-radius:6px;font-size:12px;line-height:1.45;box-shadow:0 6px 18px rgba(0,0,0,0.18)';"
        "document.body.appendChild(tip);"
        "const colors={high:'#2563eb',low:'#f59e0b'};"
        "let selected=String(payload.default_name||((payload.processes[0]||{}).name)||'');"
        "function fit(){const r=canvas.getBoundingClientRect(); canvas.width=Math.max(280,Math.floor(r.width)); canvas.height=Math.max(160,Math.floor(r.height));}"
        "function procByName(n){ return (payload.processes||[]).find(p=>String(p.name)===String(n))||null; }"
        "function markChips(){ if(!chips) return; chips.querySelectorAll('button[data-name]').forEach(btn=>{"
        "const on=btn.dataset.name===selected; btn.style.background=on?'#eef6ff':'#fff'; btn.style.borderColor=on?'#2563eb':(btn.style.borderColor||'#cbd5e1'); btn.style.fontWeight=on?'600':'400'; }); }"
        "function draw(){ fit(); const ctx=canvas.getContext('2d'); const w=canvas.width,h=canvas.height,pad=34;"
        "ctx.clearRect(0,0,w,h); const p=procByName(selected); const xs=payload.t_sec||[];"
        "if(!p||!xs.length){ ctx.fillStyle='#94a3b8'; ctx.font='12px sans-serif'; ctx.fillText('无线程曲线',20,30); if(legend) legend.textContent=''; return; }"
        "const series=[];"
        "if((p.high_values||[]).length) series.push({label:payload.high_label, color:colors.high, values:p.high_values});"
        "if((p.low_values||[]).length) series.push({label:payload.low_label, color:colors.low, values:p.low_values});"
        "const all=series.flatMap(s=>s.values||[]); let ymin=0, ymax=Math.max(10, ...(all.length?all:[10]));"
        "ymax=Math.ceil(ymax/10)*10; const yAt=v=> pad+(h-2*pad)*(1-(v-ymin)/Math.max(ymax-ymin,1));"
        "const xAt=i=> pad+(w-2*pad)*(i/Math.max(xs.length-1,1));"
        "ctx.strokeStyle='rgba(226,232,240,0.9)'; ctx.lineWidth=1;"
        "for(let yv=ymin; yv<=ymax+0.001; yv+=Math.max(10, ymax/4)){ const y=yAt(yv); ctx.beginPath(); ctx.moveTo(pad,y); ctx.lineTo(w-pad,y); ctx.stroke();"
        "ctx.fillStyle='#64748b'; ctx.font='11px sans-serif'; ctx.fillText(String(Math.round(yv)),4,y+4); }"
        "ctx.strokeStyle='#cbd5e1'; ctx.beginPath(); ctx.moveTo(pad,pad); ctx.lineTo(pad,h-pad); ctx.lineTo(w-pad,h-pad); ctx.stroke();"
        "ctx.fillStyle='#64748b'; ctx.font='11px sans-serif';"
        "ctx.fillText(String(xs[0])+'s', pad, h-8); ctx.fillText(String(xs[xs.length-1])+'s', w-pad-28, h-8);"
        "series.forEach(s=>{ ctx.strokeStyle=s.color; ctx.lineWidth=2; ctx.beginPath();"
        "(s.values||[]).forEach((v,i)=>{ const x=xAt(i), y=yAt(Number(v||0)); if(i===0) ctx.moveTo(x,y); else ctx.lineTo(x,y); }); ctx.stroke(); });"
        "ctx.fillStyle='#111827'; ctx.font='12px sans-serif'; ctx.fillText(String(p.name||'')+' · CPU%', pad, 16);"
        "let lx=pad; series.forEach(s=>{ ctx.fillStyle=s.color; ctx.fillRect(lx,h-22,10,10); ctx.fillStyle='#374151'; ctx.fillText(s.label, lx+14, h-13); lx+=Math.max(90, String(s.label).length*8+24); });"
        "canvas._meta={pad,w,h,xs,series,ymin,ymax,yAt,xAt};"
        "if(legend){ const kind=String(p.kind||''); let txt='';"
        "if(kind==='shared') txt='共有进程：同时显示 '+payload.high_label+' / '+payload.low_label+'；均差 Δ '+(Number(p.delta_avg||0)>=0?'+':'')+Number(p.delta_avg||0).toFixed(1)+'pp';"
        "else if(kind==='high_only') txt=payload.high_label+' 独有进程（仅一侧曲线） avg '+Number(p.high_avg||0).toFixed(1)+'pp';"
        "else txt=payload.low_label+' 独有进程（仅一侧曲线） avg '+Number(p.low_avg||0).toFixed(1)+'pp';"
        "legend.textContent=txt; }"
        "}"
        "function showTip(ev,lines){ tip.innerHTML=lines.join('<br>'); tip.style.display='block'; tip.style.left=(ev.clientX+14)+'px'; tip.style.top=(ev.clientY+14)+'px'; }"
        "function hideTip(){ tip.style.display='none'; }"
        "canvas.onmousemove=function(ev){ const m=canvas._meta; if(!m) return; const r=canvas.getBoundingClientRect(); const x=ev.clientX-r.left;"
        "if(x<m.pad||x>m.w-m.pad){ hideTip(); return; }"
        "const idx=Math.round(((x-m.pad)/(m.w-2*m.pad))*Math.max(m.xs.length-1,1));"
        "const lines=['相对时间 '+String(m.xs[idx]??'')+'s'];"
        "(m.series||[]).forEach(s=>lines.push(s.label+': '+String((s.values||[])[idx]??'—')+'%'));"
        "showTip(ev,lines); draw(); const ctx=canvas.getContext('2d'); ctx.strokeStyle='rgba(15,23,42,0.35)'; ctx.beginPath();"
        "const vx=m.xAt(idx); ctx.moveTo(vx,m.pad); ctx.lineTo(vx,m.h-m.pad); ctx.stroke(); };"
        "canvas.onmouseleave=function(){ hideTip(); draw(); };"
        "if(chips){ chips.addEventListener('click', (ev)=>{ const btn=ev.target.closest('button[data-name]'); if(!btn) return; selected=btn.dataset.name||selected; markChips(); draw(); }); }"
        "markChips(); draw(); window.addEventListener('resize', draw);"
        "})();</script></div>"
    )


def _render_segment_cards(segments: list[dict[str, Any]], *, high_label: str, low_label: str) -> str:
    if not segments:
        return ""
    cards: list[str] = []
    strength_color = {"强": "#dc2626", "中": "#d97706", "弱": "#64748b"}
    for item in segments[:6]:
        matched = [x for x in (item.get("matched_processes") or []) if isinstance(x, dict)]
        low_matched = [x for x in (item.get("low_matched_processes") or []) if isinstance(x, dict)]
        categories = [x for x in (item.get("category_breakdown") or []) if isinstance(x, dict)]
        reasons = [str(x) for x in (item.get("possible_reasons") or [])[:4]]
        strength = str(item.get("evidence_strength") or "弱")
        high_thread_bars: list[str] = []
        for proc in matched[:4]:
            width = min(100, max(8, int(float(proc.get("avg_usage") or 0))))
            high_thread_bars.append(
                '<div style="display:flex;align-items:center;gap:8px;margin:4px 0;">'
                f'<span style="width:140px;font-size:11px;color:#334155;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="{_esc(proc.get("name"))}">{_esc(proc.get("name"))}</span>'
                f'<span style="flex:1;height:8px;background:#e2e8f0;border-radius:999px;overflow:hidden;">'
                f'<span style="display:block;height:100%;width:{width}%;background:#2563eb;border-radius:999px;"></span></span>'
                f'<span style="width:72px;font-size:11px;color:#64748b;text-align:right;">avg {proc.get("avg_usage")}pp</span>'
                "</div>"
            )
        low_thread_bars: list[str] = []
        for proc in low_matched[:4]:
            width = min(100, max(8, int(float(proc.get("avg_usage") or 0))))
            low_thread_bars.append(
                '<div style="display:flex;align-items:center;gap:8px;margin:4px 0;">'
                f'<span style="width:140px;font-size:11px;color:#334155;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="{_esc(proc.get("name"))}">{_esc(proc.get("name"))}</span>'
                f'<span style="flex:1;height:8px;background:#e2e8f0;border-radius:999px;overflow:hidden;">'
                f'<span style="display:block;height:100%;width:{width}%;background:#f59e0b;border-radius:999px;"></span></span>'
                f'<span style="width:72px;font-size:11px;color:#64748b;text-align:right;">avg {proc.get("avg_usage")}pp</span>'
                "</div>"
            )
        cat_pills = "".join(
            f'<span style="display:inline-block;margin:0 6px 4px 0;padding:2px 8px;border-radius:999px;background:#f1f5f9;font-size:11px;color:#334155;">'
            f'{_esc(x.get("label"))} {x.get("ratio_pct")}%</span>'
            for x in categories[:4]
        )
        compare = item.get("thread_compare") or {}
        compare_block = _render_segment_thread_curve(
            compare.get("curve") or {},
            high_label=high_label,
            low_label=low_label,
        )
        if not compare_block:
            # 无曲线时仍保留独有线程文字提示
            compare_notes: list[str] = []
            high_only = [str(x) for x in (compare.get("high_only_threads") or []) if str(x)]
            low_only = [str(x) for x in (compare.get("low_only_threads") or []) if str(x)]
            if high_only:
                compare_notes.append(f"{high_label}独有活跃线程：" + "；".join(_esc(x) for x in high_only[:3]))
            if low_only:
                compare_notes.append(f"{low_label}独有活跃线程：" + "；".join(_esc(x) for x in low_only[:3]))
            if not compare_notes and low_matched:
                compare_notes.append(
                    f"{low_label}同期活跃："
                    + "；".join(f"{_esc(x.get('name'))} avg {x.get('avg_usage')}pp" for x in low_matched[:3])
                )
            if compare_notes:
                compare_block = (
                    f'<div style="margin-top:10px;">'
                    f'<div style="font-size:12px;font-weight:600;color:#111827;margin-bottom:4px;">双机线程对照</div>'
                    f'<div style="margin-top:6px;font-size:11px;color:#64748b;">{"<br/>".join(compare_notes)}</div>'
                    f"</div>"
                )
        cards.append(
            '<div style="margin-top:10px;padding:12px 14px;border:1px solid var(--color-border-tertiary);border-radius:10px;background:#fff;">'
            '<div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start;flex-wrap:wrap;">'
            f'<div><div style="font-size:13px;font-weight:600;color:#111827;">段 #{_esc(item.get("segment_id"))} · {_esc(item.get("stage_label"))}</div>'
            f'<div style="margin-top:4px;font-size:12px;color:#475569;">{_esc(item.get("relative_time") or "—")} · {_esc(item.get("absolute_start"))} ~ {_esc(item.get("absolute_end"))}</div></div>'
            f'<span style="font-size:11px;font-weight:600;color:{strength_color.get(strength, "#64748b")};">证据强度：{_esc(strength)}</span>'
            "</div>"
            '<div style="display:flex;gap:16px;flex-wrap:wrap;margin-top:8px;font-size:12px;color:#334155;">'
            f'<span>均差 <b>{_esc(item.get("mean_diff_ma"))}</b> mA</span>'
            f'<span>相对均差 <b>{_esc(item.get("delta_from_avg_ma") if item.get("delta_from_avg_ma") is not None else "—")}</b> mA</span>'
            f'<span>峰值差 <b>{_esc(item.get("peak_diff_ma"))}</b> mA</span>'
            f'<span>时长 <b>{_esc(item.get("duration_sec"))}</b> s</span>'
            f'<span>斜率 <b>{_esc(item.get("slope_ma_per_sec"))}</b> mA/s</span>'
            "</div>"
            f'<div style="margin-top:8px;">{cat_pills or "<span style=\'font-size:11px;color:#94a3b8;\'>暂无类别归因</span>"}</div>'
            '<div style="display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:12px;margin-top:10px;">'
            f'<div><div style="font-size:12px;font-weight:600;color:#111827;margin-bottom:4px;">{_esc(high_label)}异常进程（该时段）</div>{"".join(high_thread_bars) or "<span style=\'font-size:11px;color:#94a3b8;\'>未匹配到明显异常进程</span>"}</div>'
            f'<div><div style="font-size:12px;font-weight:600;color:#111827;margin-bottom:4px;">{_esc(low_label)}异常进程（同时间窗）</div>{"".join(low_thread_bars) or "<span style=\'font-size:11px;color:#94a3b8;\'>未匹配到明显异常进程</span>"}</div>'
            "</div>"
            f"{compare_block}"
            f'<div style="margin-top:8px;font-size:12px;color:#334155;"><b>候选原因：</b>{_esc("；".join(reasons) if reasons else "需人工结合日志确认")}</div>'
            "</div>"
        )
    return (
        '<div style="margin-top:12px;">'
        '<p style="margin:0 0 6px;font-size:12px;font-weight:600;color:var(--color-text-primary);">电流趋势 → 异常进程 → 可能原因</p>'
        f'{"".join(cards)}'
        "</div>"
    )


def build_report_html(
    result: dict[str, Any],
    *,
    high_label: str = "测试机",
    low_label: str = "对比机",
) -> str:
    if result.get("status") not in ("ok", "single_ok"):
        msg = result.get("error") or result.get("message") or "电流图分析失败"
        return (
            '<p style="margin:0;font-size:13px;color:var(--color-text-tertiary);">'
            f"{_esc(msg)}</p>"
        )
    mode = str(result.get("mode") or "single")
    spike = result.get("spike") or {}
    chart_payload = result.get("chart_payload") or {}
    s = (spike.get("current_summary") or result.get("current_summary") or {})
    if mode == "compare":
        avg_txt = s.get("diff_avg_ma", s.get("aligned_avg_diff_ma"))
        summary = (
            f"{high_label}均值 {s.get('high_avg_ma')} mA · {low_label}均值 {s.get('low_avg_ma')} mA · "
            f"对齐均差 {s.get('aligned_avg_diff_ma')} mA · 差值平均值 {avg_txt} mA · "
            f"底电差 {s.get('floor_diff_ma')} mA · "
            f"抬升/回落按相对平均值判定"
        )
    else:
        summary = (
            f"{high_label}均值 {s.get('high_avg_ma')} mA · "
            f"单机电流曲线展示（仅 1 份 pt5，不做双机对比）"
        )

    rows: list[str] = []
    for w in [x for x in (spike.get("spike_windows") or []) if isinstance(x, dict)][:5]:
        rows.append(
            "<tr>"
            f"<td>{_esc(w.get('rank'))}</td>"
            f"<td>{_esc(w.get('relative_time') or '—')}</td>"
            f"<td>{_esc(w.get('mean_diff_ma'))}</td>"
            f"<td>{_esc(w.get('delta_from_avg_ma') if w.get('delta_from_avg_ma') is not None else '—')}</td>"
            f"<td>{_esc(w.get('max_diff_ma'))}</td>"
            f"<td>{_esc(w.get('duration_sec'))}</td>"
            "</tr>"
        )
    window_table = ""
    if mode == "compare" and rows:
        window_table = (
            '<table class="cause-table" style="margin-top:10px;">'
            "<thead><tr><th>#</th><th>抬升窗口(相对均值)</th><th>均差(mA)</th><th>相对均差(mA)</th><th>最大差(mA)</th><th>时长(s)</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>"
        )
    trend_cards = ""
    if mode == "compare":
        trend_cards = _render_segment_cards(
            [x for x in (result.get("trend_correlations") or []) if isinstance(x, dict)],
            high_label=high_label,
            low_label=low_label,
        )
    note = str(
        spike.get("time_axis_note")
        or "横轴为相对时间；悬停同时展示原始日志时间，便于与异常进程/系统事件对齐。"
    ).strip()
    return (
        '<div style="margin-top:6px;padding:10px 12px;background:var(--color-background-secondary);'
        'border-radius:var(--border-radius-md);">'
        '<p style="margin:0 0 6px;font-size:12px;font-weight:600;color:var(--color-text-primary);">'
        "电流图分析（DOU current_cpu_spike）</p>"
        f'<p style="margin:0 0 8px;font-size:12px;color:var(--color-text-secondary);">{_esc(summary)}</p>'
        f"{_render_chart_block(chart_payload)}"
        f"{window_table}"
        f"{trend_cards}"
        f'<p style="margin:8px 0 0;font-size:11px;color:var(--color-text-tertiary);">{_esc(note)}</p>'
        "</div>"
    )


def _build_single_result(high_series: dict[str, Any], *, high_pt5: Path) -> dict[str, Any]:
    cur = [float(x) for x in list(_to_1s_series(high_series).get("current_ma") or [])]
    avg = round(sum(cur) / len(cur), 2) if cur else None
    return {
        "success": True,
        "current_summary": {"high_avg_ma": avg},
        "scene_time": {"duration_sec": float(high_series.get("duration_sec") or 0.0)},
        "high_pt5": str(high_pt5),
        "spike_windows": [],
        "time_axis_note": "仅 1 份 pt5：展示单机电流曲线，不做双机差值分析。",
    }


def _percentile(vals: list[float], q: float) -> float | None:
    if not vals:
        return None
    arr = sorted(float(x) for x in vals)
    if len(arr) == 1:
        return round(arr[0], 2)
    pos = max(0.0, min(1.0, float(q))) * (len(arr) - 1)
    lo = int(pos)
    hi = min(len(arr) - 1, lo + 1)
    frac = pos - lo
    return round(arr[lo] * (1.0 - frac) + arr[hi] * frac, 2)


def _build_native_compare_spike(
    high_series: dict[str, Any],
    low_series: dict[str, Any],
    *,
    high_pt5: Path,
    low_pt5: Path,
) -> dict[str, Any]:
    """DOU 工具缺失/失败时：用本机对齐序列生成双机电流图所需 spike 结构。"""
    aligned = _align_series(high_series, low_series)
    high = [float(x) for x in (aligned.get("high_ma") or [])]
    low = [float(x) for x in (aligned.get("low_ma") or [])]
    diff = [float(x) for x in (aligned.get("diff_ma") or [])]
    high_avg = round(sum(high) / len(high), 2) if high else None
    low_avg = round(sum(low) / len(low), 2) if low else None
    aligned_avg = round(sum(diff) / len(diff), 2) if diff else None
    floor_h = _percentile(high, 0.05)
    floor_l = _percentile(low, 0.05)
    floor_diff = (
        round(float(floor_h) - float(floor_l), 2)
        if floor_h is not None and floor_l is not None
        else None
    )
    return {
        "success": True,
        "engine": "native_compare_fallback",
        "current_summary": {
            "high_avg_ma": high_avg,
            "low_avg_ma": low_avg,
            "aligned_avg_diff_ma": aligned_avg,
            "diff_avg_ma": aligned_avg,
            "floor_diff_ma": floor_diff,
        },
        "scene_time": {
            "duration_sec": float(
                max(
                    float(high_series.get("duration_sec") or 0.0),
                    float(low_series.get("duration_sec") or 0.0),
                    float(len(diff) or 0),
                )
            )
        },
        "high_pt5": str(high_pt5),
        "low_pt5": str(low_pt5),
        "spike_windows": [],
        "dip_windows": [],
        "time_axis_note": (
            "横轴为相对时间；悬停同时展示原始日志时间。"
            "（DOU 工具不可用时使用本机对齐回退，仍保留双机电流/差值图与抬升回落标注）"
        ),
    }


def analyze_and_write(
    *,
    analysis_dir: Path,
    high_pt5: Path,
    low_pt5: Path | None,
    duration_sec: float,
    window_sec: float,
    step_sec: float,
    top_windows: int,
    high_label: str,
    low_label: str,
    compare_analysis_dir: Path | None = None,
    output: Path | None = None,
) -> dict[str, Any]:
    analysis_dir.mkdir(parents=True, exist_ok=True)
    spike_out = analysis_dir / "current_cpu_spike_game.json"
    high_series = load_current_series(high_pt5)
    low_series = load_current_series(low_pt5) if low_pt5 else None
    scene_start = _scene_start_from_analysis(analysis_dir)
    thread_series_raw = {"high": _build_abnormal_thread_timeline(analysis_dir, label=high_label)}
    if compare_analysis_dir is not None and compare_analysis_dir.is_dir():
        thread_series_raw["low"] = _build_abnormal_thread_timeline(compare_analysis_dir, label=low_label)
    abs_time = _build_abs_time_labels(
        len(list((_to_1s_series(high_series).get("current_ma") or []))),
        scene_start,
    )

    if low_pt5 is None:
        spike = _build_single_result(high_series, high_pt5=high_pt5)
        thread_series = _finalize_thread_series(thread_series_raw, [])
        result: dict[str, Any] = {
            "skill": "game_current_cpu_spike",
            "engine": "dou_2.current_cpu_spike",
            "status": "ok",
            "message": f"{high_label} 单机电流图已生成",
            "summary": f"{high_label} 单机电流图已生成",
            "mode": "single",
            "high_pt5": str(high_pt5),
            "low_pt5": "",
            "duration_sec": float(duration_sec or high_series.get("duration_sec") or 0.0),
            "spike": spike,
            "current_summary": spike.get("current_summary") or {},
            "chart_payload": _build_chart_payload(
                high_series,
                None,
                high_label=high_label,
                low_label=low_label,
                abs_time=abs_time,
                thread_series=thread_series,
            ),
            "time_mapping": {
                "scene_start": scene_start.strftime("%m-%d %H:%M:%S") if scene_start else "",
                "absolute_labels": abs_time,
            },
            "trend_correlations": [],
            "cli_stdout": "",
            "cli_stderr": "",
            "cli_returncode": 0,
        }
        result["report_html"] = build_report_html(result, high_label=high_label, low_label=low_label)
    else:
        stage_root = Path(tempfile.mkdtemp(prefix="game_dou_stage_", dir=str(analysis_dir)))
        proc: subprocess.CompletedProcess[str] | None = None
        stage_error = ""
        used_native_fallback = False
        try:
            if duration_sec <= 0:
                duration_sec = max(
                    float(high_series.get("duration_sec") or 0.0),
                    float(low_series.get("duration_sec") or 0.0),
                    60.0,
                )
            if not _DOU_TOOL.is_file():
                stage_error = f"缺少 DOU 工具：{_DOU_TOOL}"
            else:
                high_dir, low_dir = _build_dou_stage(
                    stage_root,
                    high_pt5=high_pt5,
                    low_pt5=low_pt5,
                    duration_sec=duration_sec,
                    high_label=high_label,
                    low_label=low_label,
                )
                cmd = [
                    sys.executable,
                    str(_DOU_TOOL),
                    str(high_dir),
                    str(low_dir),
                    "--suffix",
                    _SCENE_SUFFIX,
                    "--output",
                    str(spike_out),
                    "--window-sec",
                    str(window_sec),
                    "--step-sec",
                    str(step_sec),
                    "--top-windows",
                    str(top_windows),
                ]
                proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        except Exception as exc:
            stage_error = str(exc)
        finally:
            shutil.rmtree(stage_root, ignore_errors=True)

        spike: dict[str, Any] = {}
        if spike_out.is_file():
            try:
                spike = json.loads(spike_out.read_text(encoding="utf-8"))
            except Exception as exc:
                spike = {"success": False, "error": f"读取 spike JSON 失败: {exc}"}
        elif stage_error:
            spike = {"success": False, "error": stage_error}
        elif proc is not None and proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip() or f"exit={proc.returncode}"
            spike = {"success": False, "error": err}
        else:
            spike = {"success": False, "error": "DOU current_cpu_spike 未产出结果"}

        ok = bool(spike.get("success"))
        if not ok and low_series is not None:
            # DOU 缺失/失败时仍生成双机电流图，避免澄清报告「一、电流图」空白
            spike = _build_native_compare_spike(
                high_series,
                low_series,
                high_pt5=high_pt5,
                low_pt5=low_pt5,
            )
            ok = True
            used_native_fallback = True
            try:
                spike_out.write_text(json.dumps(spike, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass

        s = spike.get("current_summary") or {}
        diff_avg: float | None = None
        if ok:
            aligned_for_trend = _align_series(high_series, low_series)
            spike, diff_avg = _apply_avg_based_trend_windows(
                spike,
                list(aligned_for_trend.get("diff_ma") or []),
                window_sec=window_sec,
                step_sec=step_sec,
                top_windows=top_windows,
            )
            s = spike.get("current_summary") or s
        trend_correlations = _build_trend_correlations(
            spike,
            analysis_dir,
            compare_analysis_dir=compare_analysis_dir,
        ) if ok else []
        thread_series = _finalize_thread_series(thread_series_raw, trend_correlations)
        engine = "native.compare_fallback" if used_native_fallback else "dou_2.current_cpu_spike"
        result = {
            "skill": "game_current_cpu_spike",
            "engine": engine,
            "status": "ok" if ok else "error",
            "message": (
                f"{high_label}/{low_label} 对齐均差 {s.get('aligned_avg_diff_ma')} mA，底电差 {s.get('floor_diff_ma')} mA"
                + ("（本机回退）" if used_native_fallback else "")
                if ok
                else str(spike.get("error") or "电流图分析失败")
            ),
            "summary": (
                f"{high_label}/{low_label} 对齐均差 {s.get('aligned_avg_diff_ma')} mA，底电差 {s.get('floor_diff_ma')} mA"
                + ("（本机回退）" if used_native_fallback else "")
                if ok
                else str(spike.get("error") or "电流图分析失败")
            ),
            "mode": "compare",
            "high_pt5": str(high_pt5),
            "low_pt5": str(low_pt5),
            "duration_sec": duration_sec or (spike.get("scene_time") or {}).get("duration_sec"),
            "spike": spike,
            "current_summary": s,
            "chart_payload": _build_chart_payload(
                high_series,
                low_series,
                high_label=high_label,
                low_label=low_label,
                abs_time=abs_time,
                thread_series=thread_series,
                trend_markers=_trend_markers_from_segments(trend_correlations),
                diff_avg_ma=diff_avg,
            ),
            "time_mapping": {
                "scene_start": scene_start.strftime("%m-%d %H:%M:%S") if scene_start else "",
                "absolute_labels": abs_time,
            },
            "trend_correlations": trend_correlations,
            "cli_stdout": ((proc.stdout if proc else "") or "")[-2000:],
            "cli_stderr": ((proc.stderr if proc else "") or stage_error or "")[-2000:],
            "cli_returncode": proc.returncode if proc else None,
            "native_fallback": used_native_fallback,
        }
        result["report_html"] = build_report_html(result, high_label=high_label, low_label=low_label)

    out_json = output or (analysis_dir / "game_current_cpu_spike.json")
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path = analysis_dir / "game_current_cpu_spike_report.html"
    html_path.write_text(
        "<!DOCTYPE html><html><head><meta charset='utf-8'><title>电流图对比</title></head>"
        f"<body>{result['report_html']}</body></html>",
        encoding="utf-8",
    )
    result["paths"] = {"json": str(out_json), "html": str(html_path), "spike": str(spike_out)}
    return result


def main(argv: list[str] | None = None) -> int:
    _setup_utf8_stdio()
    parser = argparse.ArgumentParser(description="游戏电流图：接入 DOU current_cpu_spike（不改 DOU 原脚本）")
    add_log_path_argument(parser)
    add_debug_log_arguments(parser)
    parser.add_argument("--analysis-dir", default="", help="默认 <log_path>/analysis")
    parser.add_argument("--pt5", default="", help="测试机（高功耗）电流图")
    parser.add_argument("--pt5-compare", default="", help="对比机（低功耗）电流图")
    parser.add_argument("--pt5-dir", default="", help="目录内自动搜索；≥2 个则对比")
    parser.add_argument("--log-compare", default="", help="对比机 APLog，双日志时用于加载对比机异常线程趋势")
    parser.add_argument("--compare-analysis-dir", default="", help="对比机 analysis 目录，优先于 --log-compare")
    parser.add_argument("--jira-key", default="", help="按单号旁路查找附件")
    parser.add_argument("--duration-sec", type=float, default=0.0, help="场景时长；0 则读 T_game")
    parser.add_argument("--window-sec", type=float, default=10.0)
    parser.add_argument("--step-sec", type=float, default=2.0)
    parser.add_argument("--top-windows", type=int, default=12, help="抬升/回落段数量上限（连续偏离检测）")
    parser.add_argument("--high-label", default="测试机")
    parser.add_argument("--low-label", default="对比机")
    parser.add_argument("--output", default="", help="包装 JSON 输出路径")
    args = parser.parse_args(argv)
    debug_begin(args, "game_current_cpu_spike", inputs={k: getattr(args, k) for k in vars(args)})

    log_path: Path | None
    try:
        log_path = resolve_log_path(args.log_path)
    except Exception:
        log_path = Path(args.log_path).expanduser() if str(args.log_path or "").strip() else None
        if log_path and not log_path.exists():
            log_path = None
    analysis_dir = Path(args.analysis_dir) if args.analysis_dir else (
        (log_path / "analysis") if log_path else Path.cwd() / "analysis"
    )
    search_dirs: list[Path] = [analysis_dir]
    if log_path:
        search_dirs.append(log_path)
        if log_path.parent:
            search_dirs.append(log_path.parent)

    high_pt5, low_pt5 = resolve_pt5_pair(
        pt5=args.pt5,
        pt5_compare=args.pt5_compare,
        pt5_dir=args.pt5_dir,
        search_dirs=search_dirs,
        jira_key=args.jira_key,
    )
    if high_pt5 is None:
        result = {
            "skill": "game_current_cpu_spike",
            "engine": "dou_2.current_cpu_spike",
            "status": "skipped",
            "message": "未找到 pt5 电流图；请传 --pt5，或保证 --pt5-dir 下可检出电流图",
            "mode": "skipped",
            "report_html": '<p style="margin:0;font-size:13px;color:var(--color-text-tertiary);">未找到 pt5 电流图</p>',
            "spike": None,
        }
        out = Path(args.output) if args.output else analysis_dir / "game_current_cpu_spike.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        result["paths"] = {"json": str(out)}
        debug_end("game_current_cpu_spike", result, output_path=out, ok=True)
        print(json.dumps({"status": result["status"], "message": result["message"], "json": str(out)}, ensure_ascii=False))
        return 0

    duration = float(args.duration_sec or 0)
    if duration <= 0:
        duration = _load_duration_sec(analysis_dir)

    result = analyze_and_write(
        analysis_dir=analysis_dir,
        high_pt5=high_pt5,
        low_pt5=low_pt5,
        duration_sec=duration,
        window_sec=args.window_sec,
        step_sec=args.step_sec,
        top_windows=args.top_windows,
        high_label=args.high_label,
        low_label=args.low_label,
        compare_analysis_dir=_resolve_compare_analysis_dir(
            log_compare=args.log_compare,
            compare_analysis_dir=args.compare_analysis_dir,
        ),
        output=Path(args.output) if args.output else None,
    )
    ok = result.get("status") == "ok"
    debug_end(
        "game_current_cpu_spike",
        result,
        output_path=Path((result.get("paths") or {}).get("json") or ""),
        ok=ok,
    )
    print(
        json.dumps(
            {
                "status": result.get("status"),
                "message": result.get("message"),
                "json": (result.get("paths") or {}).get("json"),
                "spike": (result.get("paths") or {}).get("spike"),
            },
            ensure_ascii=False,
        )
    )
    return 0 if ok or result.get("status") == "skipped" else 1


if __name__ == "__main__":
    raise SystemExit(main())
