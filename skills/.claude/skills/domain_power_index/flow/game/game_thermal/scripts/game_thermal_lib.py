"""游戏场景温控日志解析（温升 / 降背光 / 限频）。

配置: references/keyword-patterns.yaml, analysis-standards.yaml
"""

from __future__ import annotations

import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from game_skill_paths import ensure_game_scripts_on_path  # noqa: E402

ensure_game_scripts_on_path(__file__)
from skill_references import (  # noqa: E402
    evidence_cap,
    load_analysis_standards,
    load_keyword_patterns,
    threshold,
)
from thermal_investigation_lib import build_thermal_investigation  # noqa: E402


def skill_root() -> Path:
    return Path(__file__).resolve().parent.parent


def references_dir() -> Path:
    return skill_root() / "references"


def _standards() -> dict[str, Any]:
    return load_analysis_standards(references_dir())


_EVIDENCE_CAP = evidence_cap(_standards())
RISE_DELTA_C_DEFAULT = float(threshold(_standards(), "rise_delta_c_default", 3.0))
THROTTLE_RANK: dict[str, int] = dict(
    _standards().get("throttle_rank")
    or {
        "NONE": 0,
        "LIGHT": 1,
        "MODERATE": 2,
        "SEVERE": 3,
        "CRITICAL": 4,
        "EMERGENCY": 5,
        "SHUTDOWN": 6,
    }
)


def _log_files(logs: dict[str, list[Path]], log_names: list[str]) -> list[Path]:
    out: list[Path] = []
    for name in log_names:
        out.extend(logs.get(name, []))
    return out


def _window_label(
    dt: datetime,
    game_start: datetime | None,
    game_end: datetime | None,
    pre_s: int,
    post_s: int,
    window_for: Callable[..., str | None],
) -> str:
    return window_for(dt, game_start, game_end, pre_s, post_s) or "unknown"


def _scan_patterns(
    logs: dict[str, list[Path]],
    patterns_cfg: dict[str, Any],
    extract_ts: Callable[..., Any],
    iter_lines: Callable[[Path], Any],
    window_for: Callable[..., str | None],
    game_start: datetime | None,
    game_end: datetime | None,
    pre_s: int,
    post_s: int,
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    hits: list[dict[str, Any]] = []
    by_cat: dict[str, list[dict[str, Any]]] = {}
    categories = patterns_cfg.get("categories") or {}

    for cat_name, cat_body in categories.items():
        if not isinstance(cat_body, dict):
            continue
        for pat in cat_body.get("patterns") or []:
            if not isinstance(pat, dict):
                continue
            pat_id = str(pat.get("id", ""))
            status = str(pat.get("status", "active"))
            log_names = pat.get("logs") or []
            keywords = [str(k) for k in (pat.get("keywords") or [])]
            regex_s = str(pat.get("regex") or "").strip()
            compiled = re.compile(regex_s) if regex_s else None

            for path in _log_files(logs, log_names):
                for line_no, line in iter_lines(path):
                    if keywords and not any(kw in line for kw in keywords):
                        continue
                    ts_raw, dt = extract_ts(line)
                    if not dt:
                        continue
                    window = _window_label(dt, game_start, game_end, pre_s, post_s, window_for)
                    entry: dict[str, Any] = {
                        "category": cat_name,
                        "pattern_id": pat_id,
                        "status": status,
                        "window": window,
                        "time": ts_raw or "",
                        "dt": dt,
                        "file": path.name,
                        "line": line_no,
                        "raw_evidence": f"{path.name}:{line_no}: {line.strip()[:320]}",
                    }
                    if compiled:
                        m = compiled.search(line)
                        if not m:
                            if status == "active":
                                continue
                        else:
                            entry["fields"] = {
                                k: v for k, v in m.groupdict().items() if v is not None
                            }
                    elif status == "active":
                        continue
                    hits.append(entry)
                    if len(by_cat.setdefault(cat_name, [])) < _EVIDENCE_CAP:
                        by_cat[cat_name].append(entry)

    hits.sort(key=lambda h: h.get("dt") or datetime.min)
    return hits, by_cat


def _float_field(fields: dict[str, Any], key: str) -> float | None:
    raw = fields.get(key)
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _int_field(fields: dict[str, Any], key: str) -> int | None:
    raw = fields.get(key)
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _temp_stats(samples: list[dict[str, Any]]) -> dict[str, Any]:
    temps = [s["temp_c"] for s in samples if s.get("temp_c") is not None]
    if not temps:
        return {
            "min_c": None,
            "max_c": None,
            "first_c": None,
            "last_c": None,
            "delta_c": None,
            "sample_count": 0,
        }
    first_c = samples[0].get("temp_c")
    last_c = samples[-1].get("temp_c")
    delta = None
    if first_c is not None and last_c is not None:
        delta = round(last_c - first_c, 2)
    return {
        "min_c": round(min(temps), 2),
        "max_c": round(max(temps), 2),
        "first_c": first_c,
        "last_c": last_c,
        "delta_c": delta,
        "sample_count": len(temps),
    }


LIMITS_RE = re.compile(r"([a-zA-Z0-9_]+)=(\d+)")


def _parse_limits(limits_raw: str | None) -> dict[str, int]:
    if not limits_raw:
        return {}
    return {k: int(v) for k, v in LIMITS_RE.findall(limits_raw)}


def _limits_summary(limits: dict[str, int]) -> dict[str, Any]:
    active = {k: v for k, v in limits.items() if v > 0}
    return {
        "all_zero": not active,
        "active_keys": sorted(active.keys()),
        "active_limits": active,
    }


def _collect_temperature_samples(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    cpu_pids = {
        "thermal_cpu_fill_temp",
        "tscpu_temp",
        "thermal_engine_tj",
    }
    cpu_sensor_names = {
        "cpu",
        "soc",
        "ap",
        "cpu_big",
        "cpu_little",
        "cpu0",
        "cpu1",
        "tj",
        "tscpu",
        "mtktscpu",
    }
    for hit in hits:
        cat = hit.get("category")
        pid = str(hit.get("pattern_id") or "")
        if cat not in ("temperature_sample", "tran_thermal_engine") and pid not in cpu_pids:
            continue
        fields = hit.get("fields") or {}
        temp = _float_field(fields, "temp")
        if temp is None:
            continue
        # tscpu 偶发毫摄氏度
        if pid == "tscpu_temp" and temp > 200:
            temp = temp / 1000.0
        sensor = fields.get("sensor") or (
            "vt_shell" if cat == "tran_thermal_engine" else "thermal_light"
        )
        if pid in cpu_pids or str(sensor).lower() in cpu_sensor_names:
            sensor = "CPU"
        out.append(
            {
                "time": hit.get("time", ""),
                "window": hit.get("window", ""),
                "sensor": sensor,
                "temp_c": round(float(temp), 2),
                "throttle_status": fields.get("throttle_status"),
                "pattern_id": pid,
                "scene": fields.get("scene"),
                "thermal_level": _int_field(fields, "level"),
                "raw_evidence": hit.get("raw_evidence", ""),
                "dt": hit.get("dt"),
            }
        )
    out.sort(key=lambda s: s.get("dt") or datetime.min)
    return out


def _build_temperature_section(
    samples: list[dict[str, Any]],
    rise_threshold: float,
) -> dict[str, Any]:
    pre = [s for s in samples if s.get("window") == "T_pre"]
    game = [s for s in samples if s.get("window") == "T_game"]
    pre_stats = _temp_stats(pre)
    game_stats = _temp_stats(game)

    rise_detected = False
    if game_stats.get("delta_c") is not None and game_stats["delta_c"] >= rise_threshold:
        rise_detected = True
    elif game_stats.get("max_c") is not None and pre_stats.get("max_c") is not None:
        if game_stats["max_c"] - pre_stats["max_c"] >= rise_threshold:
            rise_detected = True

    coverage = "missing"
    if game:
        coverage = "ok" if pre else "partial"
    elif pre:
        coverage = "partial"

    game_stats["rise_detected"] = rise_detected
    return {
        "coverage": coverage,
        "rise_delta_c_threshold": rise_threshold,
        "T_pre": pre_stats,
        "T_game": game_stats,
        "samples": [
            {k: v for k, v in s.items() if k != "dt"}
            for s in (pre[-3:] + game[:_EVIDENCE_CAP])
        ],
    }


def _build_backlight_section(hits: list[dict[str, Any]], game_package: str) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    seen: set[str] = set()

    for hit in hits:
        if hit.get("window") != "T_game":
            continue
        if hit.get("category") != "thermal_backlight":
            continue
        pid = hit.get("pattern_id", "")
        fields = hit.get("fields") or {}
        if pid == "thermal_light_upgrade":
            key = f"{hit.get('time')}|{fields.get('level_idx')}"
            if key in seen:
                continue
            seen.add(key)
            events.append(
                {
                    "time": hit.get("time", ""),
                    "package": fields.get("package", "").strip(),
                    "level": _int_field(fields, "level_idx") or _int_field(fields, "level"),
                    "temp_c": _float_field(fields, "temp"),
                    "brightness_nits": _int_field(fields, "nits"),
                    "is_level_upgrade": True,
                    "pattern_id": pid,
                    "raw_evidence": hit.get("raw_evidence", ""),
                }
            )
        elif pid == "thermal_light_update_brightness":
            events.append(
                {
                    "time": hit.get("time", ""),
                    "action": "update_brightness",
                    "pattern_id": pid,
                    "raw_evidence": hit.get("raw_evidence", ""),
                }
            )

    upgrade_events = [e for e in events if e.get("is_level_upgrade")]
    if game_package:
        upgrade_events = [
            e for e in upgrade_events if not e.get("package") or game_package in str(e.get("package"))
        ] or upgrade_events

    max_level = max((e.get("level") or 0 for e in upgrade_events), default=0)
    triggered = bool(upgrade_events) or any(
        e.get("action") == "update_brightness" for e in events
    )

    return {
        "triggered_in_game": triggered,
        "event_count": len(events),
        "upgrade_event_count": len(upgrade_events),
        "max_level": max_level if max_level else None,
        "events": events[:_EVIDENCE_CAP],
    }


def _max_throttle_status(statuses: list[str]) -> str | None:
    best = None
    best_rank = -1
    for st in statuses:
        rank = THROTTLE_RANK.get(st, -1)
        if rank > best_rank:
            best_rank = rank
            best = st
    return best if best_rank > 0 else None


def _build_tran_thermal_engine_section(
    hits: list[dict[str, Any]],
    game_package: str,
) -> dict[str, Any]:
    engine_hits = [h for h in hits if h.get("category") == "tran_thermal_engine"]
    events: list[dict[str, Any]] = []

    for hit in engine_hits:
        fields = hit.get("fields") or {}
        limits = _parse_limits(fields.get("limits"))
        lim = _limits_summary(limits)
        fg_pkg = (fields.get("fg_pkg") or "").strip()
        events.append(
            {
                "time": hit.get("time", ""),
                "window": hit.get("window", ""),
                "event": fields.get("event"),
                "op": fields.get("op"),
                "temp_c": _float_field(fields, "temp"),
                "thermal_level": _int_field(fields, "level"),
                "scene": fields.get("scene"),
                "fg_pkg": fg_pkg,
                "fg_act": fields.get("fg_act"),
                "game_mode": _int_field(fields, "game_mode"),
                "game_func_mode": _int_field(fields, "game_func_mode"),
                "cur_fps": _int_field(fields, "cur_fps"),
                "touch": fields.get("touch"),
                "limits_all_zero": lim["all_zero"],
                "active_limit_keys": lim["active_keys"],
                "active_limits": lim["active_limits"],
                "raw_evidence": hit.get("raw_evidence", ""),
            }
        )

    t_game = [e for e in events if e.get("window") == "T_game"]
    if game_package:
        t_game_pkg = [e for e in t_game if game_package in str(e.get("fg_pkg") or "")]
        if t_game_pkg:
            t_game = t_game_pkg

    scene_game = [e for e in t_game if e.get("scene") == "scene_game"]
    limits_active = [e for e in t_game if not e.get("limits_all_zero", True)]
    temps = [e["temp_c"] for e in t_game if e.get("temp_c") is not None]

    return {
        "status": "active" if engine_hits else "not_found",
        "sample_count": len(engine_hits),
        "T_game_sample_count": len(t_game),
        "scene_game_count": len(scene_game),
        "limits_active_in_game": bool(limits_active),
        "limits_active_event_count": len(limits_active),
        "temp_min_c": round(min(temps), 2) if temps else None,
        "temp_max_c": round(max(temps), 2) if temps else None,
        "thermal_level_range": (
            [min(e["thermal_level"] for e in t_game if e.get("thermal_level") is not None),
             max(e["thermal_level"] for e in t_game if e.get("thermal_level") is not None)]
            if t_game and any(e.get("thermal_level") is not None for e in t_game)
            else None
        ),
        "events": events[:_EVIDENCE_CAP],
    }


def _build_throttle_section(
    hits: list[dict[str, Any]],
    throttle_statuses: list[str],
    tran_engine: dict[str, Any],
) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    statuses: list[str] = []

    for hit in hits:
        if hit.get("window") != "T_game":
            continue
        if hit.get("category") != "thermal_throttle_freq":
            continue
        fields = hit.get("fields") or {}
        pid = hit.get("pattern_id", "")
        throttle = fields.get("throttle_status")
        if throttle and throttle != "NONE":
            statuses.append(str(throttle))

        is_throttle = False
        if throttle and throttle != "NONE":
            is_throttle = True
        elif pid == "thermal_engine_thermalux":
            tf = _int_field(fields, "thermalux_freq")
            is_throttle = tf is not None and tf >= 0
        elif pid == "mtk_thermal_ux_policy":
            dur = _int_field(fields, "duration")
            is_throttle = dur is not None and dur > 0

        if not is_throttle and hit.get("status") == "placeholder":
            continue
        if not is_throttle and pid not in ("thermal_engine_thermalux", "mtk_thermal_ux_policy"):
            continue

        events.append(
            {
                "time": hit.get("time", ""),
                "pattern_id": pid,
                "sensor": fields.get("sensor"),
                "throttle_status": throttle,
                "temp_c": _float_field(fields, "temp"),
                "cpu": _int_field(fields, "cpu"),
                "thermalux_freq": _int_field(fields, "thermalux_freq"),
                "duration_ms": _int_field(fields, "duration"),
                "raw_evidence": hit.get("raw_evidence", ""),
            }
        )

    for item in tran_engine.get("events") or []:
        if item.get("window") != "T_game" or item.get("limits_all_zero", True):
            continue
        events.append(
            {
                "time": item.get("time", ""),
                "pattern_id": "tran_thermal_engine_vt_shell",
                "source": "tran_thermal_engine.limits",
                "active_limit_keys": item.get("active_limit_keys"),
                "active_limits": item.get("active_limits"),
                "temp_c": item.get("temp_c"),
                "scene": item.get("scene"),
                "raw_evidence": item.get("raw_evidence", ""),
            }
        )

    status_max = _max_throttle_status(statuses)
    freq_limit = bool(events) or tran_engine.get("limits_active_in_game", False)
    return {
        "freq_limit_triggered": freq_limit,
        "throttle_status_max": status_max,
        "event_count": len(events),
        "tran_thermal_engine_limits_active": tran_engine.get("limits_active_in_game", False),
        "known_statuses": throttle_statuses,
        "events": events[:_EVIDENCE_CAP],
    }


def _dedupe_temp_timeline(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按时间去重，优先保留 vt_shell。"""
    best: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for p in points:
        t = str(p.get("time") or "")
        if not t or p.get("temp_c") is None:
            continue
        sensor = str(p.get("sensor") or "")
        prev = best.get(t)
        if prev is None:
            best[t] = {
                "time": t,
                "temp_c": round(float(p["temp_c"]), 2),
                "sensor": sensor or "unknown",
            }
            order.append(t)
            continue
        # vt_shell 覆盖 SKIN 等同秒采样
        if sensor == "vt_shell" and prev.get("sensor") != "vt_shell":
            best[t] = {
                "time": t,
                "temp_c": round(float(p["temp_c"]), 2),
                "sensor": sensor,
            }
    return [best[t] for t in order]


def _build_thermal_report(
    *,
    temperature: dict[str, Any],
    temp_samples: list[dict[str, Any]],
    thermal_backlight: dict[str, Any],
    thermal_throttle: dict[str, Any],
    tran_thermal_engine: dict[str, Any],
) -> dict[str, Any]:
    """澄清报告用：降亮度/限频一句话 + 分档证据 + T_game 温度曲线数据。"""
    t_game = temperature.get("T_game") or {}
    max_temp = t_game.get("max_c")
    if max_temp is None:
        max_temp = tran_thermal_engine.get("temp_max_c")

    # 温度曲线：分源独立（vt_shell / SKIN / CPU），避免混绘假跌落
    def _series(sensor_names: set[str], pattern_ids: set[str] | None = None) -> list[dict[str, Any]]:
        names_l = {str(s).lower() for s in sensor_names}
        pts = []
        for s in temp_samples:
            if s.get("window") != "T_game" or s.get("temp_c") is None:
                continue
            sensor = str(s.get("sensor") or "")
            pid = str(s.get("pattern_id") or "")
            sensor_l = sensor.lower()
            # 优先按 sensor 归类；pattern 仅作补洞，且不得把已明确的其他传感器串入本系列
            if sensor_l in names_l:
                pts.append(s)
            elif (
                pattern_ids
                and pid in pattern_ids
                and sensor_l in names_l.union({"", "unknown", "thermal_light"})
            ):
                pts.append(s)
        return _dedupe_temp_timeline(pts)

    vt_timeline = _series(
        {"vt_shell"},
        {"tran_thermal_engine_vt_shell"},
    )
    skin_timeline = _series({"SKIN", "skin"}, {"thermal_skin_temp"})
    cpu_timeline = _series(
        {"CPU", "cpu", "SOC", "AP", "Tj", "tscpu", "mtktscpu"},
        {"thermal_cpu_fill_temp", "tscpu_temp", "thermal_engine_tj"},
    )

    temp_curves = {
        "vt_shell": {
            "label": "vt_shell 壳温",
            "points": vt_timeline,
            "sample_count": len(vt_timeline),
            "max_c": round(max(p["temp_c"] for p in vt_timeline), 2) if vt_timeline else None,
            "min_c": round(min(p["temp_c"] for p in vt_timeline), 2) if vt_timeline else None,
        },
        "SKIN": {
            "label": "SKIN",
            "points": skin_timeline,
            "sample_count": len(skin_timeline),
            "max_c": round(max(p["temp_c"] for p in skin_timeline), 2) if skin_timeline else None,
            "min_c": round(min(p["temp_c"] for p in skin_timeline), 2) if skin_timeline else None,
        },
        "CPU": {
            "label": "CPU",
            "points": cpu_timeline,
            "sample_count": len(cpu_timeline),
            "max_c": round(max(p["temp_c"] for p in cpu_timeline), 2) if cpu_timeline else None,
            "min_c": round(min(p["temp_c"] for p in cpu_timeline), 2) if cpu_timeline else None,
            "note": None if cpu_timeline else "日志未获取到 CPU 温度",
        },
    }

    # 主曲线兼容字段：优先壳温，否则 SKIN
    temp_timeline = vt_timeline or skin_timeline
    timeline_max = (
        round(max(p["temp_c"] for p in temp_timeline), 2) if temp_timeline else None
    )
    timeline_min = (
        round(min(p["temp_c"] for p in temp_timeline), 2) if temp_timeline else None
    )
    curve_max = timeline_max if timeline_max is not None else max_temp
    # 多曲线全局极值（用于图轴）
    all_vals = [
        p["temp_c"]
        for series in (vt_timeline, skin_timeline, cpu_timeline)
        for p in series
    ]
    curves_max = round(max(all_vals), 2) if all_vals else curve_max
    curves_min = round(min(all_vals), 2) if all_vals else timeline_min

    # —— 降亮度分档 ——
    upgrade_events = [
        e for e in (thermal_backlight.get("events") or []) if e.get("is_level_upgrade")
    ]
    # 按 level 升序保留首次出现
    seen_levels: set[int] = set()
    dim_gears: list[dict[str, Any]] = []
    for e in upgrade_events:
        level = e.get("level")
        if level is None:
            continue
        try:
            level_i = int(level)
        except (TypeError, ValueError):
            continue
        if level_i in seen_levels:
            continue
        seen_levels.add(level_i)
        temp_c = e.get("temp_c")
        nits = e.get("brightness_nits")
        gear_idx = len(dim_gears) + 1
        line = (
            f"第{gear_idx}档: 生效温度={temp_c}℃，亮度降至 {nits} nits，"
            f"测试最高温度={max_temp}℃"
            if temp_c is not None
            else f"第{gear_idx}档: level={level_i}，亮度降至 {nits} nits，测试最高温度={max_temp}℃"
        )
        dim_gears.append(
            {
                "gear": gear_idx,
                "level": level_i,
                "temp_c": temp_c,
                "brightness_nits": nits,
                "max_temp_c": max_temp,
                "time": e.get("time"),
                "line": line,
                "raw_evidence": e.get("raw_evidence"),
            }
        )

    dim_effective = bool(dim_gears) or bool(thermal_backlight.get("triggered_in_game"))
    if dim_gears:
        dim_summary = f"thermal降亮度：生效，下降{len(dim_gears)}档（最高温度{max_temp}℃）"
    elif dim_effective:
        dim_summary = f"thermal降亮度：生效（未解析到分档细节，最高温度{max_temp}℃）"
    else:
        dim_summary = "thermal降亮度：未生效"

    # —— 限频分档 ——
    throttle_events = list(thermal_throttle.get("events") or [])
    freq_gears: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for e in throttle_events:
        limits = e.get("active_limits") or {}
        status = e.get("throttle_status")
        key = (
            f"limits:{sorted((limits or {}).items())}"
            if limits
            else f"status:{status}|cpu:{e.get('cpu')}|ux:{e.get('thermalux_freq')}"
        )
        if key in seen_keys:
            continue
        seen_keys.add(key)
        gear_idx = len(freq_gears) + 1
        temp_c = e.get("temp_c")
        if limits:
            lim_txt = ",".join(f"{k}={v}" for k, v in sorted(limits.items()))
            detail = f"limits{{{lim_txt}}}"
        elif status:
            detail = f"throttle={status}"
        else:
            detail = e.get("pattern_id") or "限频事件"
        line = (
            f"第{gear_idx}档: 生效温度={temp_c}℃，{detail}，测试最高温度={max_temp}℃"
            if temp_c is not None
            else f"第{gear_idx}档: {detail}，测试最高温度={max_temp}℃"
        )
        freq_gears.append(
            {
                "gear": gear_idx,
                "temp_c": temp_c,
                "max_temp_c": max_temp,
                "active_limits": limits or None,
                "throttle_status": status,
                "time": e.get("time"),
                "line": line,
                "raw_evidence": e.get("raw_evidence"),
            }
        )

    freq_effective = bool(thermal_throttle.get("freq_limit_triggered")) or bool(freq_gears)
    if freq_gears:
        freq_summary = f"thermal限频：生效，下降{len(freq_gears)}档（最高温度{max_temp}℃）"
    elif freq_effective:
        freq_summary = f"thermal限频：生效（最高温度{max_temp}℃）"
    else:
        freq_summary = "thermal限频：未生效"

    return {
        "backlight_dim": {
            "effective": bool(dim_gears) or bool(thermal_backlight.get("triggered_in_game")),
            "gear_count": len(dim_gears),
            "gears": dim_gears,
            "report_summary": dim_summary,
            "report_evidence": [g["line"] for g in dim_gears],
            "max_temp_c": max_temp,
        },
        "freq_throttle": {
            "effective": bool(freq_effective),
            "gear_count": len(freq_gears),
            "gears": freq_gears,
            "report_summary": freq_summary,
            "report_evidence": [g["line"] for g in freq_gears],
            "max_temp_c": max_temp,
        },
        "temp_timeline": temp_timeline,
        "temp_curves": temp_curves,
        "temp_source": (temp_timeline[0].get("sensor") if temp_timeline else None),
        "temp_max_c": curves_max,
        "temp_min_c": curves_min if curves_min is not None else t_game.get("min_c"),
        "temp_delta_c": (
            round(curves_max - curves_min, 2)
            if curves_max is not None and curves_min is not None
            else t_game.get("delta_c")
        ),
        "temp_max_all_sensors_c": max_temp,
        "cpu_temp_available": bool(cpu_timeline),
    }


def analyze_game_thermal(
    log_path: Path,
    game_start: datetime,
    game_end: datetime,
    *,
    game_package: str = "",
    pre_minutes: int = 5,
    post_minutes: int = 3,
    rise_delta_c_threshold: float = RISE_DELTA_C_DEFAULT,
    discover_logs: Callable[[Path], dict[str, list[Path]]],
    extract_ts: Callable[..., Any],
    window_for: Callable[..., str | None],
    iter_lines: Callable[[Path], Any],
    fmt_time: Callable[[datetime | None], str],
) -> dict[str, Any]:
    patterns_cfg = load_keyword_patterns(references_dir())
    logs = discover_logs(log_path)
    pre_s = max(60, pre_minutes * 60)
    post_s = max(60, post_minutes * 60)
    warnings: list[str] = []
    notes: list[str] = ["温控降亮/限频为系统保护策略，需追溯导致温升的上游负载"]

    if not logs.get("sys_log") and not logs.get("main_log"):
        return {
            "status": "failed",
            "warnings": ["sys/main 日志均缺失"],
            "log_availability": {"sys_log": False, "main_log": False},
        }

    hits, by_cat = _scan_patterns(
        logs,
        patterns_cfg,
        extract_ts,
        iter_lines,
        window_for,
        game_start,
        game_end,
        pre_s,
        post_s,
    )

    # Strip dt from serializable keyword_hits
    keyword_hits: dict[str, list[dict[str, Any]]] = {}
    for cat, items in by_cat.items():
        keyword_hits[cat] = [
            {k: v for k, v in item.items() if k != "dt"} for item in items
        ]

    temp_samples = _collect_temperature_samples(hits)
    temperature = _build_temperature_section(temp_samples, rise_delta_c_threshold)
    thermal_backlight = _build_backlight_section(hits, game_package.strip())
    tran_thermal_engine = _build_tran_thermal_engine_section(hits, game_package.strip())
    thermal_throttle = _build_throttle_section(
        hits,
        list(patterns_cfg.get("throttle_statuses") or THROTTLE_RANK.keys()),
        tran_thermal_engine,
    )

    thermal_investigation = build_thermal_investigation(
        lib_file=Path(__file__),
        logs=logs,
        start=game_start,
        end=game_end,
        pre_s=pre_s,
        post_s=post_s,
        game_package=game_package.strip(),
        extract_ts=extract_ts,
        iter_lines=iter_lines,
        window_for=window_for,
    )

    thermal_report = _build_thermal_report(
        temperature=temperature,
        temp_samples=temp_samples,
        thermal_backlight=thermal_backlight,
        thermal_throttle=thermal_throttle,
        tran_thermal_engine=tran_thermal_engine,
    )

    inv_s2 = thermal_investigation.get("step2_cpu_intervention") or {}
    during_game = {
        "temp_rise": bool((temperature.get("T_game") or {}).get("rise_detected")),
        "thermal_backlight": thermal_backlight.get("triggered_in_game", False),
        "freq_throttle": thermal_throttle.get("freq_limit_triggered", False),
        "cpu_min_freq_intervention": bool(inv_s2.get("cpu_intervention_detected")),
    }

    if not logs.get("sys_log"):
        warnings.append("sys 日志缺失，温控降背光证据可能不足")
    if temperature.get("coverage") == "missing":
        warnings.append("T_game 内未解析到温度采样")
    if during_game["temp_rise"]:
        gw = temperature.get("T_game") or {}
        notes.append(
            f"T_game 温升 delta={gw.get('delta_c')}°C max={gw.get('max_c')}°C"
        )
    if during_game["thermal_backlight"]:
        notes.append(
            f"触发温控降背光 {thermal_backlight.get('upgrade_event_count')} 次，"
            f"max_level={thermal_backlight.get('max_level')}"
        )
    if during_game["freq_throttle"]:
        notes.append(
            f"触发温控限频，最严重状态={thermal_throttle.get('throttle_status_max')}，"
            f"事件 {thermal_throttle.get('event_count')} 条"
        )
    inv_s2 = (thermal_investigation.get("step2_cpu_intervention") or {})
    if inv_s2.get("cpu_intervention_detected"):
        notes.append(
            f"ThermalEngineTypeData min_cpu_freq 介入 "
            f"{inv_s2.get('cpu_intervention_event_count')} 次"
        )
    notes.extend(thermal_investigation.get("warnings") or [])
    if tran_thermal_engine.get("T_game_sample_count"):
        notes.append(
            f"tran_thermal_engine T_game 采样 {tran_thermal_engine.get('T_game_sample_count')} 条，"
            f"壳温 {tran_thermal_engine.get('temp_min_c')}~{tran_thermal_engine.get('temp_max_c')}°C，"
            f"limits_active={tran_thermal_engine.get('limits_active_in_game')}"
        )
    if not any(during_game.values()):
        notes.append("T_game 内未检测到明显温升/温控降背光/限频")

    status = "ok"
    if temperature.get("coverage") == "missing" and not thermal_backlight.get("triggered_in_game"):
        if not thermal_throttle.get("freq_limit_triggered"):
            status = "partial" if logs.get("sys_log") or logs.get("main_log") else "failed"
    if warnings:
        status = "partial" if status != "failed" else "failed"

    confidence = "low"
    if any(during_game.values()):
        confidence = "medium" if sum(1 for v in during_game.values() if v) == 1 else "high"

    return {
        "status": status,
        "log_path": str(log_path),
        "game_window": {
            "start": fmt_time(game_start),
            "end": fmt_time(game_end),
            "duration_seconds": int((game_end - game_start).total_seconds()),
            "package": game_package.strip(),
        },
        "time_windows": {
            "T_pre": {
                "start": fmt_time(game_start - timedelta(seconds=pre_s)),
                "end": fmt_time(game_start),
            },
            "T_game": {"start": fmt_time(game_start), "end": fmt_time(game_end)},
            "T_post": {
                "start": fmt_time(game_end),
                "end": fmt_time(game_end + timedelta(seconds=post_s)),
            },
        },
        "thermal_summary": {"during_game": during_game, "confidence": confidence},
        "thermal_investigation": thermal_investigation,
        "thermal_report": thermal_report,
        "temperature": temperature,
        "thermal_backlight": thermal_backlight,
        "tran_thermal_engine": tran_thermal_engine,
        "thermal_throttle": thermal_throttle,
        "keyword_hits": keyword_hits,
        "log_availability": {
            "sys_log": bool(logs.get("sys_log")),
            "main_log": bool(logs.get("main_log")),
        },
        "warnings": warnings,
        "notes": notes,
    }
