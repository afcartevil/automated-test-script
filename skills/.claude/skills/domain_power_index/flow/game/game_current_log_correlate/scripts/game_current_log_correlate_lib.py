"""单机电流抬高窗口检测 + 与分维日志关联。"""

from __future__ import annotations

import html
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from pt5_series_loader import find_pt5_candidates, load_current_series

_DEFAULT_WINDOW_SEC = 10.0
_DEFAULT_STEP_SEC = 2.0
_DEFAULT_TOP_N = 3
_DEFAULT_THRESHOLD_MA = 20.0
_BASELINE_PERCENTILE = 10.0
_BASELINE_TRIM_START_SEC = 10.0
_BASELINE_TRIM_END_SEC = 5.0

_CAUSE_PRIORITY = (
    "kernel_cpu",
    "brightness",
    "background",
    "network",
    "thermal",
)

_CAUSE_LABEL = {
    "kernel_cpu": "CPU/线程负载抬高",
    "brightness": "亮度变化",
    "background": "后台进程/自启动",
    "network": "网络/RF 活动",
    "thermal": "温控/温升",
    "unknown": "未关联到明确日志事件",
}


def _esc(text: Any) -> str:
    return html.escape("" if text is None else str(text))


def _sec_to_rel_time(sec: float) -> str:
    sec_i = max(0, int(sec))
    return f"{sec_i // 60:02d}:{sec_i % 60:02d}"


def _parse_dt(text: Any) -> datetime | None:
    if text is None:
        return None
    if isinstance(text, datetime):
        return text
    s = str(text).strip()
    if not s:
        return None
    # 已有完整年
    for fmt in (
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S.%f",
        "%Y/%m/%d %H:%M:%S",
    ):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    # Android log: MM-DD HH:MM:SS.mmm
    m = re.match(
        r"^(?:(\d{4})-)?(\d{2})-(\d{2})\s+(\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?",
        s,
    )
    if m:
        year = int(m.group(1) or datetime.now().year)
        frac = (m.group(7) or "0")[:6].ljust(6, "0")
        try:
            return datetime(
                year,
                int(m.group(2)),
                int(m.group(3)),
                int(m.group(4)),
                int(m.group(5)),
                int(m.group(6)),
                int(frac),
            )
        except ValueError:
            return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _slice_for_baseline(
    arr: np.ndarray,
    sample_rate_hz: float,
    duration_sec: float,
    *,
    trim_start_sec: float = _BASELINE_TRIM_START_SEC,
    trim_end_sec: float = _BASELINE_TRIM_END_SEC,
) -> np.ndarray:
    if arr.size == 0:
        return arr
    start_idx = max(0, int(trim_start_sec * sample_rate_hz))
    end_idx = min(arr.size, max(start_idx, int((duration_sec - trim_end_sec) * sample_rate_hz)))
    if start_idx >= end_idx:
        return np.array([], dtype=float)
    return arr[start_idx:end_idx]


def _rolling_min_mean(arr: np.ndarray, sample_rate_hz: float, window_sec: float) -> float | None:
    if arr.size == 0:
        return None
    win = max(1, int(window_sec * sample_rate_hz))
    if arr.size < win:
        return round(float(arr.mean()), 2)
    kernel = np.ones(win, dtype=float) / win
    rolling = np.convolve(arr, kernel, mode="valid")
    return round(float(rolling.min()), 2)


def _baseline_stats(
    arr: np.ndarray,
    *,
    sample_rate_hz: float,
    baseline_window_sec: float = _DEFAULT_WINDOW_SEC,
) -> dict[str, float]:
    if arr.size == 0:
        return {}
    avg_baseline = _rolling_min_mean(arr, sample_rate_hz, baseline_window_sec)
    out: dict[str, float] = {
        "min_ma": round(float(arr.min()), 2),
        "p10_ma": round(float(np.percentile(arr, _BASELINE_PERCENTILE)), 2),
        "median_ma": round(float(np.median(arr)), 2),
        "mean_ma": round(float(arr.mean()), 2),
    }
    if avg_baseline is not None:
        out["avg_baseline_ma"] = avg_baseline
    # 单机抬高参考：优先持续底流（滑动最低窗均值），否则 P10
    out["baseline_ma"] = out.get("avg_baseline_ma", out["p10_ma"])
    return out


def _find_raised_windows(
    raise_arr: np.ndarray,
    *,
    sample_rate_hz: float,
    window_sec: float,
    step_sec: float,
    top_n: int,
    threshold_ma: float,
) -> list[dict[str, Any]]:
    if raise_arr.size == 0:
        return []
    win = max(1, int(window_sec * sample_rate_hz))
    step = max(1, int(step_sec * sample_rate_hz))
    if raise_arr.size < win:
        mean_diff = float(raise_arr.mean())
        if mean_diff < threshold_ma:
            return []
        return [
            {
                "rank": 1,
                "start_sec": 0.0,
                "end_sec": round(raise_arr.size / sample_rate_hz, 2),
                "duration_sec": round(raise_arr.size / sample_rate_hz, 2),
                "mean_raise_ma": round(mean_diff, 2),
                "max_raise_ma": round(float(raise_arr.max()), 2),
                "relative_time": f"00:00–{_sec_to_rel_time(raise_arr.size / sample_rate_hz)}",
            }
        ]

    scored: list[tuple[float, int, float, float]] = []
    for i in range(0, raise_arr.size - win + 1, step):
        seg = raise_arr[i : i + win]
        mean_diff = float(seg.mean())
        if mean_diff < threshold_ma:
            continue
        scored.append((mean_diff, i, float(seg.max()), win / sample_rate_hz))
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
                "mean_raise_ma": round(mean_diff, 2),
                "max_raise_ma": round(max_diff, 2),
                "relative_time": f"{_sec_to_rel_time(start_sec)}–{_sec_to_rel_time(end_sec)}",
            }
        )
        if len(windows) >= top_n:
            break
    return windows


def _rel_sec(event_time: Any, scene_start: datetime | None) -> float | None:
    if event_time is None:
        return None
    if isinstance(event_time, (int, float)):
        return float(event_time)
    dt = _parse_dt(event_time)
    if dt is None or scene_start is None:
        return None
    # 忽略年份不一致：对齐月日时分秒
    if dt.year != scene_start.year and (dt.month, dt.day) == (scene_start.month, scene_start.day):
        dt = dt.replace(year=scene_start.year)
    return (dt - scene_start).total_seconds()


def _walk_timed_events(obj: Any, out: list[dict[str, Any]], *, limit: int = 400) -> None:
    if len(out) >= limit or obj is None:
        return
    if isinstance(obj, dict):
        t = obj.get("time") or obj.get("start_time") or obj.get("timestamp")
        if t is not None and (
            obj.get("raw_evidence")
            or obj.get("name")
            or obj.get("package")
            or obj.get("level") is not None
            or obj.get("temp_c") is not None
            or obj.get("threads")
            or obj.get("aggregate_usage_pct") is not None
        ):
            out.append(obj)
        for v in obj.values():
            _walk_timed_events(v, out, limit=limit)
    elif isinstance(obj, list):
        for item in obj:
            _walk_timed_events(item, out, limit=limit)


def _events_in_window(
    events: list[dict[str, Any]],
    *,
    scene_start: datetime | None,
    start_sec: float,
    end_sec: float,
    offset_sec: float = 0.0,
) -> list[dict[str, Any]]:
    picked: list[dict[str, Any]] = []
    for ev in events:
        # 优先显式相对秒
        rs = ev.get("t_offset_seconds")
        if rs is None:
            rs = _rel_sec(ev.get("time") or ev.get("start_time") or ev.get("timestamp"), scene_start)
        if rs is None:
            continue
        rs = float(rs) - float(offset_sec)
        if start_sec <= rs <= end_sec:
            row = dict(ev)
            row["_rel_sec"] = round(rs, 2)
            picked.append(row)
    picked.sort(key=lambda x: float(x.get("_rel_sec") or 0))
    return picked


def _top_threads_from_cpu_samples(samples: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    agg: dict[str, dict[str, Any]] = {}
    for s in samples:
        for th in s.get("threads") or []:
            if not isinstance(th, dict):
                continue
            name = str(th.get("name") or "").strip()
            if not name:
                continue
            try:
                usage = float(th.get("usage") or 0)
            except (TypeError, ValueError):
                usage = 0.0
            if name not in agg:
                agg[name] = {"name": name, "usage_sum": 0.0, "samples": 0, "pid": th.get("pid")}
            agg[name]["usage_sum"] += usage
            agg[name]["samples"] += 1
    rows = sorted(agg.values(), key=lambda x: x["usage_sum"], reverse=True)
    out = []
    for r in rows[:limit]:
        out.append(
            {
                "name": r["name"],
                "avg_usage": round(r["usage_sum"] / max(r["samples"], 1), 2),
                "samples": r["samples"],
                "pid": r.get("pid"),
            }
        )
    return out


def _correlate_window(
    win: dict[str, Any],
    *,
    scene_start: datetime | None,
    analysis: dict[str, Any],
    pt5_offset_sec: float,
) -> dict[str, Any]:
    start = float(win["start_sec"])
    end = float(win["end_sec"])
    dims: dict[str, Any] = {}

    # 1) kernel_cpu
    kcpu = analysis.get("game_kernel_cpu") or {}
    cpu_samples = kcpu.get("cpu_samples") or []
    if isinstance(cpu_samples, list):
        in_win = _events_in_window(
            [s for s in cpu_samples if isinstance(s, dict)],
            scene_start=scene_start,
            start_sec=start,
            end_sec=end,
            offset_sec=pt5_offset_sec,
        )
        top = _top_threads_from_cpu_samples(in_win)
        usages = []
        for s in in_win:
            try:
                usages.append(float(s.get("aggregate_usage_pct") or 0))
            except (TypeError, ValueError):
                pass
        evidence = []
        for s in in_win[:3]:
            if s.get("raw_evidence"):
                evidence.append(str(s["raw_evidence"]))
            else:
                evidence.append(
                    f"{s.get('time')} aggregate={s.get('aggregate_usage_pct')}%"
                )
        hit = bool(top) or (usages and max(usages) >= 40)
        dims["kernel_cpu"] = {
            "hit": hit,
            "sample_count": len(in_win),
            "avg_usage_pct": round(sum(usages) / len(usages), 2) if usages else None,
            "max_usage_pct": round(max(usages), 2) if usages else None,
            "top_threads": top,
            "evidence": evidence[:4],
        }

    # 2) brightness
    bright = analysis.get("game_brightness") or {}
    bright_events: list[dict[str, Any]] = []
    _walk_timed_events(bright.get("in_game_brightness") or {}, bright_events, limit=200)
    _walk_timed_events(bright.get("brightness_analysis") or {}, bright_events, limit=200)
    _walk_timed_events(bright.get("thermal_brightness") or {}, bright_events, limit=100)
    b_in = _events_in_window(
        bright_events, scene_start=scene_start, start_sec=start, end_sec=end, offset_sec=pt5_offset_sec
    )
    b_evidence = [str(e.get("raw_evidence") or e.get("time") or "") for e in b_in[:4] if e]
    dims["brightness"] = {
        "hit": len(b_in) > 0,
        "event_count": len(b_in),
        "evidence": [x for x in b_evidence if x][:4],
    }

    # 3) background
    bg = analysis.get("game_background") or {}
    bg_events: list[dict[str, Any]] = []
    inv = bg.get("background_investigation") or {}
    _walk_timed_events(inv, bg_events, limit=300)
    _walk_timed_events(bg.get("sample_events") or [], bg_events, limit=100)
    g_in = _events_in_window(
        bg_events, scene_start=scene_start, start_sec=start, end_sec=end, offset_sec=pt5_offset_sec
    )
    pkgs = []
    for e in g_in:
        pkg = e.get("package") or e.get("name")
        if pkg and pkg not in pkgs:
            pkgs.append(pkg)
    dims["background"] = {
        "hit": len(g_in) > 0,
        "event_count": len(g_in),
        "packages": pkgs[:8],
        "evidence": [str(e.get("raw_evidence") or f"{e.get('time')} {e.get('package')}") for e in g_in[:4]],
    }

    # 4) network
    net = analysis.get("game_network") or {}
    net_events: list[dict[str, Any]] = []
    _walk_timed_events(net.get("network_investigation") or {}, net_events, limit=200)
    _walk_timed_events(net.get("rf_stats") or {}, net_events, limit=100)
    n_in = _events_in_window(
        net_events, scene_start=scene_start, start_sec=start, end_sec=end, offset_sec=pt5_offset_sec
    )
    dims["network"] = {
        "hit": len(n_in) > 0,
        "event_count": len(n_in),
        "evidence": [str(e.get("raw_evidence") or e.get("time") or "") for e in n_in[:4]],
    }

    # 5) thermal
    th = analysis.get("game_thermal") or {}
    th_events: list[dict[str, Any]] = []
    _walk_timed_events(th.get("thermal_investigation") or {}, th_events, limit=200)
    _walk_timed_events(th.get("temperature") or {}, th_events, limit=100)
    t_in = _events_in_window(
        th_events, scene_start=scene_start, start_sec=start, end_sec=end, offset_sec=pt5_offset_sec
    )
    temps = []
    for e in t_in:
        if e.get("temp_c") is not None:
            try:
                temps.append(float(e["temp_c"]))
            except (TypeError, ValueError):
                pass
    dims["thermal"] = {
        "hit": len(t_in) > 0,
        "event_count": len(t_in),
        "temp_c_max": round(max(temps), 2) if temps else None,
        "evidence": [str(e.get("raw_evidence") or f"{e.get('time')} temp={e.get('temp_c')}") for e in t_in[:4]],
    }

    primary = "unknown"
    for key in _CAUSE_PRIORITY:
        if (dims.get(key) or {}).get("hit"):
            primary = key
            break

    abs_start = None
    abs_end = None
    if scene_start is not None:
        abs_start = (scene_start + timedelta(seconds=start + pt5_offset_sec)).strftime("%m-%d %H:%M:%S")
        abs_end = (scene_start + timedelta(seconds=end + pt5_offset_sec)).strftime("%m-%d %H:%M:%S")

    return {
        **win,
        "abs_start": abs_start,
        "abs_end": abs_end,
        "primary_cause": primary,
        "primary_cause_label": _CAUSE_LABEL.get(primary, primary),
        "dimensions": dims,
        "evidence": (dims.get(primary) or {}).get("evidence") or [],
    }


def build_waveform_analysis(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("status") == "skipped":
        return {
            "has_abnormal_spike": None,
            "spike_impact_on_avg": "",
            "avg_delta_without_spike_ma": None,
            "conclusion": "未提供 pt5/电流序列，跳过电流-日志关联。",
            "coverage": "missing",
            "source": "game_current_log_correlate",
        }
    windows = result.get("raised_windows") or []
    has_spike = bool(windows)
    contrib = result.get("raise_contribution_to_avg_ma")
    impact = ""
    if has_spike and contrib is not None:
        impact = f"Top抬高窗合计抬高整段均值约 {contrib:.1f} mA"
    elif has_spike:
        impact = "检测到相对底电抬高窗口，详见 raised_windows"
    baseline = (result.get("baseline") or {}).get("baseline_ma")
    conclusion = result.get("summary") or ""
    if not conclusion:
        if has_spike:
            conclusion = (
                f"单机相对底电（{baseline} mA）检测到 {len(windows)} 段抬高窗口；"
                f"主因示例：{windows[0].get('primary_cause_label')}"
            )
        else:
            conclusion = f"相对底电未发现超过阈值的持续抬高窗口（阈值 {result.get('threshold_ma')} mA）。"
    return {
        "has_abnormal_spike": has_spike,
        "spike_impact_on_avg": impact,
        "avg_delta_without_spike_ma": result.get("avg_without_raised_windows_ma"),
        "conclusion": conclusion,
        "coverage": "ok",
        "source": "game_current_log_correlate",
        "raised_window_count": len(windows),
    }


def analyze_current_log_correlate(
    *,
    log_path: Path,
    analysis_dir: Path | None = None,
    pt5_path: str | Path | None = None,
    pt5_dir: str | Path | None = None,
    jira_key: str = "",
    threshold_ma: float = _DEFAULT_THRESHOLD_MA,
    window_sec: float = _DEFAULT_WINDOW_SEC,
    step_sec: float = _DEFAULT_STEP_SEC,
    top_n: int = _DEFAULT_TOP_N,
    pt5_offset_sec: float = 0.0,
) -> dict[str, Any]:
    log_path = Path(log_path).resolve()
    analysis_dir = Path(analysis_dir) if analysis_dir else log_path / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)

    search_dirs: list[Path] = [
        analysis_dir,
        log_path,
        log_path.parent,
    ]
    if pt5_dir:
        search_dirs.insert(0, Path(pt5_dir))
    if jira_key:
        # 常见下载旁路
        for base in (log_path.parents[0], analysis_dir, Path.cwd()):
            search_dirs.append(base / jira_key)
            search_dirs.append(base / "downloads")
            search_dirs.append(base / "temp")

    candidates = find_pt5_candidates(
        explicit=pt5_path,
        search_dirs=search_dirs,
        jira_key=jira_key,
    )
    if not candidates:
        return {
            "skill": "game_current_log_correlate",
            "status": "skipped",
            "reason": "no_pt5",
            "message": "未找到 pt5/电流 CSV/JSON，跳过电流-日志关联",
            "log_path": str(log_path),
            "analysis_dir": str(analysis_dir),
            "jira_key": jira_key,
            "raised_windows": [],
            "waveform_analysis": build_waveform_analysis({"status": "skipped"}),
        }

    series = load_current_series(candidates[0])
    cur = np.asarray(series["current_ma"], dtype=float)
    rate = float(series["sample_rate_hz"] or 1.0)
    duration = float(series.get("duration_sec") or (cur.size / max(rate, 1e-9)))

    base_slice = _slice_for_baseline(cur, rate, duration)
    baseline = _baseline_stats(base_slice if base_slice.size else cur, sample_rate_hz=rate)
    baseline_ma = float(baseline.get("baseline_ma") or 0.0)
    raise_arr = cur - baseline_ma

    windows = _find_raised_windows(
        raise_arr,
        sample_rate_hz=rate,
        window_sec=window_sec,
        step_sec=step_sec,
        top_n=top_n,
        threshold_ma=threshold_ma,
    )

    tw = _load_json(analysis_dir / "game_time_window.json")
    gw = tw.get("game_window") or (tw.get("time_windows") or {}).get("T_game") or {}
    scene_start = _parse_dt(gw.get("start"))
    scene_end = _parse_dt(gw.get("end"))

    analysis = {
        "game_kernel_cpu": _load_json(analysis_dir / "game_kernel_cpu.json"),
        "game_brightness": _load_json(analysis_dir / "game_brightness.json"),
        "game_background": _load_json(analysis_dir / "game_background.json"),
        "game_network": _load_json(analysis_dir / "game_network.json"),
        "game_thermal": _load_json(analysis_dir / "game_thermal.json"),
        "game_cpu_gpu_ddr": _load_json(analysis_dir / "game_cpu_gpu_ddr.json"),
    }

    enriched = [
        _correlate_window(
            w,
            scene_start=scene_start,
            analysis=analysis,
            pt5_offset_sec=pt5_offset_sec,
        )
        for w in windows
    ]

    # 对整段均值贡献：Σ(mean_raise * dur) / total_duration
    total_dur = max(duration, 1e-9)
    contrib = sum(float(w["mean_raise_ma"]) * float(w["duration_sec"]) for w in enriched) / total_dur
    # 去掉抬高窗后的近似均值
    mask = np.ones(cur.size, dtype=bool)
    for w in enriched:
        i0 = max(0, int(float(w["start_sec"]) * rate))
        i1 = min(cur.size, int(float(w["end_sec"]) * rate))
        mask[i0:i1] = False
    avg_wo = float(cur[mask].mean()) if mask.any() and mask.sum() > 0 else None

    cause_counts: dict[str, int] = {}
    for w in enriched:
        c = str(w.get("primary_cause") or "unknown")
        cause_counts[c] = cause_counts.get(c, 0) + 1

    summary = (
        f"底电≈{baseline_ma:.1f} mA，阈值 {threshold_ma:.0f} mA，"
        f"检出 {len(enriched)} 个抬高窗；对均值贡献约 {contrib:.1f} mA。"
        if enriched
        else f"底电≈{baseline_ma:.1f} mA，未检出 ≥{threshold_ma:.0f} mA 的持续抬高窗。"
    )

    result: dict[str, Any] = {
        "skill": "game_current_log_correlate",
        "status": "ok",
        "mode": "single_device_a",
        "log_path": str(log_path),
        "analysis_dir": str(analysis_dir),
        "jira_key": jira_key,
        "pt5_path": series.get("source_path"),
        "pt5_format": series.get("source_format"),
        "pt5_candidates": [str(p) for p in candidates[:5]],
        "sample_rate_hz": rate,
        "duration_sec": round(duration, 2),
        "n_samples": int(series.get("n_samples") or cur.size),
        "threshold_ma": threshold_ma,
        "window_sec": window_sec,
        "step_sec": step_sec,
        "top_n": top_n,
        "pt5_offset_sec": pt5_offset_sec,
        "game_window": {
            "start": gw.get("start"),
            "end": gw.get("end"),
            "duration_seconds": gw.get("duration_seconds"),
        },
        "baseline": baseline,
        "mean_current_ma": round(float(cur.mean()), 2),
        "avg_without_raised_windows_ma": round(avg_wo, 2) if avg_wo is not None else None,
        "raise_contribution_to_avg_ma": round(contrib, 2),
        "raised_windows": enriched,
        "primary_cause_counts": cause_counts,
        "summary": summary,
        "analysis_time": datetime.now().isoformat(timespec="seconds"),
    }
    result["waveform_analysis"] = build_waveform_analysis(result)
    return result


def render_correlate_html(result: dict[str, Any]) -> str:
    status = result.get("status")
    windows = result.get("raised_windows") or []
    rows = ""
    for w in windows:
        ev = "<br/>".join(_esc(x)[:180] for x in (w.get("evidence") or [])[:3]) or "—"
        rows += (
            f"<tr><td>{_esc(w.get('rank'))}</td>"
            f"<td>{_esc(w.get('relative_time'))}<br/><span style='color:#888'>"
            f"{_esc(w.get('abs_start'))} ~ {_esc(w.get('abs_end'))}</span></td>"
            f"<td>{_esc(w.get('mean_raise_ma'))}</td>"
            f"<td>{_esc(w.get('primary_cause_label'))}</td>"
            f"<td style='font-size:12px;word-break:break-all'>{ev}</td></tr>"
        )
    if not rows:
        rows = "<tr><td colspan='5'>无抬高窗口或已跳过</td></tr>"
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"/>
<title>电流-日志关联</title>
<style>
body{{font-family:Segoe UI,Microsoft YaHei,sans-serif;margin:24px;background:#f5f7fa;color:#2c3e50}}
.card{{background:#fff;border-radius:8px;padding:16px 20px;box-shadow:0 1px 3px rgba(0,0,0,.08);margin-bottom:16px}}
h1{{font-size:20px;margin:0 0 8px}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th,td{{border-bottom:1px solid #e5e7eb;padding:8px;text-align:left;vertical-align:top}}
th{{background:#f8fafc;color:#64748b}}
.muted{{color:#64748b;font-size:13px}}
</style></head><body>
<div class="card">
  <h1>电流波形 ↔ 日志关联</h1>
  <p class="muted">status={_esc(status)} · {_esc(result.get('summary') or result.get('message') or '')}</p>
  <p class="muted">pt5={_esc(result.get('pt5_path') or '—')} · baseline=
  {_esc((result.get('baseline') or {}).get('baseline_ma'))} mA · 阈值 {_esc(result.get('threshold_ma'))} mA</p>
</div>
<div class="card">
  <table>
    <thead><tr><th>#</th><th>窗口</th><th>均值抬高(mA)</th><th>主因</th><th>证据</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>
</body></html>
"""


def write_correlate_outputs(analysis_dir: Path, result: dict[str, Any]) -> dict[str, Path]:
    analysis_dir = Path(analysis_dir)
    analysis_dir.mkdir(parents=True, exist_ok=True)
    json_path = analysis_dir / "game_current_log_correlate.json"
    html_path = analysis_dir / "game_current_log_correlate_report.html"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path.write_text(render_correlate_html(result), encoding="utf-8")
    return {"json": json_path, "html": html_path}
