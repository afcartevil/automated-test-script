"""游戏场景亮度与显示相关日志解析（LCM/HWC/刷新率/ColorMode/thermal 占位）。

输出 JSON（game_brightness.json）: pre_test_brightness, game_entry_brightness,
in_game_brightness{stable,transitions[]}, refresh_rate, color_mode, status
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
from auto_brightness_detect import auto_brightness_likely_from_samples  # noqa: E402
from brightness_investigation_lib import build_brightness_investigation  # noqa: E402
from brightness_readings_lib import build_brightness_analysis, collect_brightness_readings  # noqa: E402
from skill_references import (  # noqa: E402
    evidence_cap,
    load_analysis_standards,
    load_keyword_patterns,
    threshold,
)


def skill_root() -> Path:
    return Path(__file__).resolve().parent.parent


def references_dir() -> Path:
    return skill_root() / "references"


def _standards() -> dict[str, Any]:
    return load_analysis_standards(references_dir())


ENTRY_WINDOW_SECONDS = int(threshold(_standards(), "entry_window_seconds", 60))
LAUNCH_WINDOW_SECONDS = int(threshold(_standards(), "launch_window_seconds", 20))
CURVE_MAX = int(threshold(_standards(), "curve_max", 4095))
LEVEL_MAX = int(threshold(_standards(), "level_max", 255))
MERGE_BURST_SECONDS = float(threshold(_standards(), "merge_burst_seconds", 2))
MIN_CURVE_DELTA = int(threshold(_standards(), "min_curve_delta", 20))
THERMAL_CORRELATION_SECONDS = int(threshold(_standards(), "thermal_correlation_seconds", 30))
MIN_LEVEL_DELTA = int(threshold(_standards(), "min_level_delta", 20))
_EVIDENCE_CAP = evidence_cap(_standards())

_AUTO_BRIGHTNESS_PATTERN_IDS = frozenset(
    {
        "sensor_auto_brightness_enable",
        "sensor_auto_brightness_disable",
        "kernel_mtk_drm_cwb",
        "kernel_cwb_work_enable",
    }
)
_AUTO_BRIGHTNESS_CONTROLLER = "com.android.server.display.AutomaticBrightnessController"


def _log_key_for_files(logs: dict[str, list[Path]], log_names: list[str]) -> list[Path]:
    out: list[Path] = []
    for name in log_names:
        out.extend(logs.get(name, []))
    return out


def _should_skip_brightness_noise(line: str) -> bool:
    if "okhttp" in line.lower() and '"Brightness"' in line:
        return True
    return False


def _resolve_window(
    dt: datetime,
    game_start: datetime | None,
    game_end: datetime | None,
    pre_s: int,
    post_s: int,
    entry_seconds: int,
    window_for: Callable[..., str | None],
) -> str:
    base = window_for(dt, game_start, game_end, pre_s, post_s) or "unknown"
    if game_start and base == "T_game" and dt <= game_start + timedelta(seconds=entry_seconds):
        return "game_entry"
    return base


def _scan_keyword_patterns(
    logs: dict[str, list[Path]],
    patterns_cfg: dict[str, Any],
    extract_ts: Callable[..., Any],
    iter_lines: Callable[[Path], Any],
    window_for: Callable[..., str | None],
    game_start: datetime | None,
    game_end: datetime | None,
    pre_s: int,
    post_s: int,
    entry_seconds: int,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    """按 category 扫描关键词；返回 (keyword_hits, by_category_samples, auto_brightness_hits)。"""
    hits: dict[str, list[dict[str, Any]]] = {}
    by_cat: dict[str, list[dict[str, Any]]] = {}
    auto_brightness_hits: list[dict[str, Any]] = []
    categories = patterns_cfg.get("categories") or {}

    for cat_name, cat_body in categories.items():
        if not isinstance(cat_body, dict):
            continue
        cat_hits: list[dict[str, Any]] = []
        for pat in cat_body.get("patterns") or []:
            if not isinstance(pat, dict):
                continue
            pat_id = str(pat.get("id", ""))
            status = str(pat.get("status", "active"))
            log_names = pat.get("logs") or []
            keywords = [str(k) for k in (pat.get("keywords") or [])]
            regex_s = str(pat.get("regex") or "").strip()
            compiled = re.compile(regex_s) if regex_s else None

            files = _log_key_for_files(logs, log_names)
            for path in files:
                for line_no, line in iter_lines(path):
                    if _should_skip_brightness_noise(line):
                        continue
                    if keywords and not all(kw in line for kw in keywords):
                        continue
                    if pat_id in ("sensor_auto_brightness_enable", "sensor_auto_brightness_disable"):
                        if _AUTO_BRIGHTNESS_CONTROLLER not in line:
                            continue
                    ts_raw, dt = extract_ts(line)
                    if not dt:
                        continue
                    window = _resolve_window(
                        dt, game_start, game_end, pre_s, post_s, entry_seconds, window_for
                    )
                    entry: dict[str, Any] = {
                        "category": cat_name,
                        "pattern_id": pat_id,
                        "status": status,
                        "window": window,
                        "time": ts_raw or "",
                        "file": path.name,
                        "line": line_no,
                        "raw_evidence": f"{path.name}:{line_no}: {line.strip()[:300]}",
                    }
                    if compiled:
                        m = compiled.search(line)
                        if m:
                            fields = {k: v for k, v in m.groupdict().items() if v is not None}
                            if "hz" not in fields and m.lastindex and m.lastindex >= 1:
                                fields["hz"] = m.group(1)
                            entry["fields"] = fields
                        elif status == "active":
                            continue
                    elif status == "active":
                        continue
                    cat_hits.append(entry)
                    if pat_id in _AUTO_BRIGHTNESS_PATTERN_IDS:
                        auto_brightness_hits.append(entry)
                    if len(cat_hits) <= _EVIDENCE_CAP:
                        by_cat.setdefault(cat_name, []).append(entry)
        if cat_hits:
            hits[cat_name] = cat_hits[:_EVIDENCE_CAP]

    return hits, by_cat, auto_brightness_hits


def _hz_stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"min_hz": None, "max_hz": None, "stable_hz": None, "sample_count": 0, "unique_hz": []}
    uniq = sorted(set(values))
    return {
        "min_hz": min(values),
        "max_hz": max(values),
        "stable_hz": uniq[0] if len(uniq) == 1 else None,
        "sample_count": len(values),
        "unique_hz": uniq[:10],
    }


def _summarize_refresh_rate(
    by_cat_samples: dict[str, list[dict[str, Any]]],
    game_start: datetime | None,
    game_end: datetime | None,
    pre_s: int,
    entry_s: int,
) -> dict[str, Any]:
    samples = by_cat_samples.get("refresh_rate", [])
    buckets: dict[str, list[float]] = {"T_pre": [], "T_game": [], "game_entry": [], "T_post": [], "unknown": []}
    by_pattern: dict[str, dict[str, Any]] = {}

    for item in samples:
        fields = item.get("fields") or {}
        hz_raw = fields.get("hz")
        if hz_raw is None:
            continue
        try:
            hz = float(hz_raw)
        except (TypeError, ValueError):
            continue
        window = item.get("window", "unknown")
        buckets.setdefault(window, []).append(hz)
        pid = item.get("pattern_id", "")
        if pid not in by_pattern:
            by_pattern[pid] = {"count": 0, "last_hz": None, "example": item.get("raw_evidence", "")}
        by_pattern[pid]["count"] += 1
        by_pattern[pid]["last_hz"] = hz

    return {
        "T_pre": _hz_stats(buckets.get("T_pre", [])),
        "T_game": _hz_stats(buckets.get("T_game", [])),
        "game_entry": _hz_stats(buckets.get("game_entry", [])),
        "T_post": _hz_stats(buckets.get("T_post", [])),
        "by_pattern": by_pattern,
        "samples": [s for s in samples if s.get("window") == "T_game"][:_EVIDENCE_CAP],
        "entry_window_seconds": entry_s,
    }


def _collect_placeholder_samples(
    by_cat_samples: dict[str, list[dict[str, Any]]],
    category: str,
    pattern_ids: list[str],
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    samples = by_cat_samples.get(category, [])
    for pid in pattern_ids:
        matched = [s for s in samples if s.get("pattern_id") == pid]
        out[pid] = {
            "status": "placeholder" if matched else "not_found",
            "samples": matched[:10],
        }
    return out


def _detect_entry_brightness_events(
    lcm_summary: dict[str, Any],
    hwc_summary: dict[str, Any],
    game_start: datetime | None,
    entry_seconds: int,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    if not game_start:
        return events
    entry_end = game_start + timedelta(seconds=entry_seconds)
    baseline_lcm = (lcm_summary.get("baseline_before_game") or {}).get("level")
    baseline_hwc = (hwc_summary.get("baseline_before_game") or {}).get("brightness_val")

    for ramp in (hwc_summary.get("game_window") or {}).get("transitions") or []:
        t_from = ramp.get("time_from") or ramp.get("start_time") or ""
        # transitions from display_brightness use time strings; skip if before game
        events.append(
            {
                "source": "hwcomposer",
                "kind": ramp.get("kind", "in_game_change"),
                "brightness_val_from": ramp.get("brightness_val_from"),
                "brightness_val_to": ramp.get("brightness_val_to"),
                "hint": ramp.get("hint", ""),
                "tags": ["hwc_transition"],
                "raw_evidence": ramp.get("raw_evidence", ""),
            }
        )

    for ramp in (lcm_summary.get("game_window") or {}).get("transitions") or []:
        events.append(
            {
                "source": "kernel_lcm",
                "kind": "lcm_ramp",
                "level_from": ramp.get("level_from"),
                "level_to": ramp.get("level_to"),
                "tags": ["lcm_transition"],
                "raw_evidence": ramp.get("raw_evidence", ""),
            }
        )

    # Filter conceptual entry window using baseline delta when levels known
    if baseline_lcm is not None:
        gw = lcm_summary.get("game_window") or {}
        start_level = gw.get("start_level")
        if start_level is not None and abs(start_level - baseline_lcm) >= MIN_LEVEL_DELTA:
            events.insert(
                0,
                {
                    "source": "kernel_lcm",
                    "delta_from_baseline": start_level - baseline_lcm,
                    "baseline_level": baseline_lcm,
                    "entry_level": start_level,
                    "tags": ["entry_ramp"],
                    "note": f"游戏开局档位相对基线变化 ≥ {MIN_LEVEL_DELTA}",
                },
            )
    if baseline_hwc is not None:
        plateau = (hwc_summary.get("game_window") or {}).get("stable_plateau") or {}
        entry_val = plateau.get("brightness_val")
        if entry_val is not None and abs(entry_val - baseline_hwc) >= MIN_LEVEL_DELTA:
            events.insert(
                0,
                {
                    "source": "hwcomposer",
                    "delta_from_baseline": entry_val - baseline_hwc,
                    "baseline_brightness_val": baseline_hwc,
                    "entry_brightness_val": entry_val,
                    "tags": ["entry_ramp"],
                    "note": f"进游戏后 HWC 档位相对基线变化 ≥ {MIN_LEVEL_DELTA}",
                },
            )

    return events[:_EVIDENCE_CAP]


def _thermal_brightness_section(
    by_cat_samples: dict[str, list[dict[str, Any]]],
    lcm_summary: dict[str, Any],
    hwc_summary: dict[str, Any],
    investigation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    step5 = (investigation or {}).get("step5_thermal_control") or {}
    if step5:
        return {
            "hits": step5.get("hits", []),
            "relevant_hits": step5.get("relevant_hits", []),
            "triggered": step5.get("triggered", False),
            "test_methodology_issue": step5.get("test_methodology_issue", False),
            "coverage": step5.get("coverage", "missing"),
        }

    thermal_samples = by_cat_samples.get("thermal_brightness", [])
    dim_times: list[datetime] = []
    # collect down-ramp times from hwc transitions as proxy
    for ramp in (hwc_summary.get("game_window") or {}).get("transitions") or []:
        if ramp.get("direction") == "down" and ramp.get("time_from"):
            pass

    hits: list[dict[str, Any]] = []
    for item in thermal_samples:
        hit = {
            "pattern_id": item.get("pattern_id"),
            "status": item.get("status", "placeholder"),
            "window": item.get("window"),
            "time": item.get("time"),
            "correlated_dimming": False,
            "raw_evidence": item.get("raw_evidence", ""),
        }
        if item.get("status") == "placeholder":
            hit["note"] = "关键词命中，待 regex 与温控降亮样例对齐"
        hits.append(hit)

    return {"hits": hits}


def _build_pre_test_brightness(
    lcm_summary: dict[str, Any],
    hwc_summary: dict[str, Any],
    by_cat_samples: dict[str, list[dict[str, Any]]],
    auto_brightness_hits: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    pre_samples = list(by_cat_samples.get("pre_test_brightness", []))
    for item in auto_brightness_hits or []:
        if item.get("pattern_id") in _AUTO_BRIGHTNESS_PATTERN_IDS:
            pre_samples.append(item)
    auto_lines = [s for s in pre_samples if s.get("pattern_id") in _AUTO_BRIGHTNESS_PATTERN_IDS]
    likely, evidence = auto_brightness_likely_from_samples(auto_lines)
    out = {
        "lcm": lcm_summary.get("baseline_before_game"),
        "hwc": hwc_summary.get("baseline_before_game"),
        "auto_brightness_likely": likely,
        "auto_brightness_evidence": evidence,
        "screen_brightness_setting": {
            "status": "placeholder",
            "samples": [s for s in pre_samples if s.get("pattern_id") == "screen_brightness_setting"][:5],
        },
    }
    return out


def _merge_pre_test_with_brightness_analysis(
    pre_test: dict[str, Any],
    brightness_analysis: dict[str, Any],
) -> dict[str, Any]:
    setting = brightness_analysis.get("pre_game_setting") or {}
    pre_test["pre_game_setting"] = setting
    if setting.get("coverage") == "ok":
        by_src = setting.get("by_source") or {}
        bc = by_src.get("brightness_collector") or {}
        if bc.get("brightness_level") is not None:
            pre_test["brightness_collector"] = {
                "level": bc.get("brightness_level"),
                "level_pct": bc.get("brightness_level_pct"),
                "time": bc.get("time"),
                "raw_evidence": bc.get("raw_evidence"),
            }
        elif setting.get("brightness_level") is not None:
            pre_test["brightness_collector"] = {
                "level": setting.get("brightness_level"),
                "level_pct": setting.get("brightness_level_pct"),
                "time": setting.get("time"),
                "raw_evidence": setting.get("raw_evidence"),
            }
        if setting.get("curve_val") is not None:
            pre_test["curve_last"] = {
                "curve_val": setting.get("curve_val"),
                "curve_pct": setting.get("curve_pct"),
                "curve_max": setting.get("curve_max"),
                "pattern_id": setting.get("pattern_id"),
                "time": setting.get("time"),
                "raw_evidence": setting.get("raw_evidence"),
            }
    return pre_test


def analyze_game_brightness(
    log_path: Path,
    game_start: datetime,
    game_end: datetime,
    *,
    pre_minutes: int = 5,
    post_minutes: int = 3,
    entry_seconds: int = ENTRY_WINDOW_SECONDS,
    launch_window_seconds: int | None = None,
    game_package: str | None = None,
    max_brightness_scenario: bool | None = None,
    project: str | None = None,
    test_case: str | None = None,
    discover_logs: Callable[[Path], dict[str, list[Path]]],
    parse_kernel_backlight: Callable[..., dict[str, Any]],
    parse_hwcomposer_brightness: Callable[..., dict[str, Any]],
    add_event: Callable[[list[dict[str, Any]], dict[str, Any]], None],
    extract_ts: Callable[..., Any],
    window_for: Callable[..., str | None],
    iter_lines: Callable[[Path], Any],
    fmt_time: Callable[[datetime | None], str],
) -> dict[str, Any]:
    logs = discover_logs(log_path)
    pre_s = max(60, pre_minutes * 60)
    post_s = max(60, post_minutes * 60)
    events: list[dict[str, Any]] = []
    warnings: list[str] = []
    notes: list[str] = []

    if not logs.get("kernel_log") and not logs.get("main_log") and not logs.get("sys_log"):
        return {
            "status": "failed",
            "warnings": ["kernel/main/sys 日志均缺失"],
            "log_availability": {k: bool(logs.get(k)) for k in ("kernel_log", "main_log", "sys_log")},
        }

    lcm = parse_kernel_backlight(
        logs.get("kernel_log", []),
        events,
        add_event,
        extract_ts,
        window_for,
        iter_lines,
        fmt_time,
        game_start,
        game_end,
        pre_s,
        post_s,
    )
    hwc = parse_hwcomposer_brightness(
        logs.get("main_log", []) + logs.get("sys_log", []),
        events,
        add_event,
        extract_ts,
        window_for,
        iter_lines,
        game_start,
        game_end,
        pre_s,
        post_s,
    )

    patterns_cfg = load_keyword_patterns(references_dir())
    brightness_readings = collect_brightness_readings(
        logs,
        patterns_cfg,
        extract_ts,
        iter_lines,
        curve_max=CURVE_MAX,
        level_max=LEVEL_MAX,
    )
    brightness_analysis = build_brightness_analysis(
        brightness_readings,
        game_start,
        game_end,
        launch_window_seconds=launch_window_seconds or LAUNCH_WINDOW_SECONDS,
        burst_gap_seconds=MERGE_BURST_SECONDS,
        min_curve_delta=MIN_CURVE_DELTA,
        curve_max=CURVE_MAX,
        level_max=LEVEL_MAX,
    )

    keyword_hits, by_cat, auto_brightness_hits = _scan_keyword_patterns(
        logs,
        patterns_cfg,
        extract_ts,
        iter_lines,
        window_for,
        game_start,
        game_end,
        pre_s,
        post_s,
        entry_seconds,
    )

    brightness_investigation = build_brightness_investigation(
        lib_file=Path(__file__),
        logs=logs,
        readings=brightness_readings,
        auto_brightness_hits=auto_brightness_hits,
        game_start=game_start,
        game_end=game_end,
        pre_seconds=pre_s,
        game_package=game_package,
        max_brightness_scenario=max_brightness_scenario,
        project=project,
        test_case=test_case,
        extract_ts=extract_ts,
        iter_lines=iter_lines,
    )

    refresh_rate = _summarize_refresh_rate(by_cat, game_start, game_end, pre_s, entry_seconds)
    inv_rr = brightness_investigation.get("step6_refresh_rate") or {}
    if inv_rr.get("coverage") == "ok":
        refresh_rate["investigation"] = inv_rr
    pre_test = _build_pre_test_brightness(lcm, hwc, by_cat, auto_brightness_hits)
    pre_test = _merge_pre_test_with_brightness_analysis(pre_test, brightness_analysis)
    entry_events = _detect_entry_brightness_events(lcm, hwc, game_start, entry_seconds)
    thermal = _thermal_brightness_section(by_cat, lcm, hwc, brightness_investigation)

    color_mode = _collect_placeholder_samples(
        by_cat, "color_mode", ["color_mode", "hdr_mode", "display_color_enhance"]
    )
    game_entry_extra = {
        "launch_brightness": brightness_analysis.get("launch_window"),
        "aal": _collect_placeholder_samples(by_cat, "game_entry_brightness", ["aal_adaptive"]),
        "backlight_optimization": _collect_placeholder_samples(
            by_cat, "game_entry_brightness", ["backlight_optimization"]
        ),
    }

    notes.extend(lcm.get("notes", []))
    notes.extend(hwc.get("notes", []))
    if brightness_analysis.get("launch_window", {}).get("phase_count"):
        notes.append(
            f"启动后 {LAUNCH_WINDOW_SECONDS}s 内背光变光 {brightness_analysis['launch_window']['phase_count']} 段"
        )
    if brightness_analysis.get("in_game_changes", {}).get("phase_count"):
        notes.append(
            f"游戏内背光变光 {brightness_analysis['in_game_changes']['phase_count']} 段"
        )
    if pre_test.get("pre_game_setting", {}).get("coverage") == "ok":
        pg = pre_test["pre_game_setting"]
        if pg.get("brightness_level") is not None:
            notes.append(f"测试前亮度等级(0-255)={pg['brightness_level']}")
        if pg.get("curve_val") is not None:
            notes.append(f"测试前背光曲线(0-4095)={pg['curve_val']}")
    if lcm.get("coverage") == "missing":
        warnings.append("kernel LCM 背光缺失，亮度主结论置信度降低")
    if pre_test.get("auto_brightness_likely"):
        warnings.append("自动背光可能开启（测试手法风险）")
    warnings.extend(brightness_investigation.get("warnings") or [])
    if not refresh_rate["T_game"].get("sample_count"):
        warnings.append("T_game 内未解析到刷新率采样（updateFps 等）")

    status = "ok"
    if lcm.get("coverage") == "missing" and hwc.get("coverage") == "missing":
        status = "failed"
    elif warnings:
        status = "partial"

    entry_end = game_start + timedelta(seconds=entry_seconds)
    return {
        "status": status,
        "log_path": str(log_path),
        "game_window": {
            "start": fmt_time(game_start),
            "end": fmt_time(game_end),
            "duration_seconds": int((game_end - game_start).total_seconds()),
        },
        "time_windows": {
            "T_pre": {"start": fmt_time(game_start - timedelta(seconds=pre_s)), "end": fmt_time(game_start)},
            "T_game": {"start": fmt_time(game_start), "end": fmt_time(game_end)},
            "game_entry": {"start": fmt_time(game_start), "end": fmt_time(entry_end)},
            "T_post": {"start": fmt_time(game_end), "end": fmt_time(game_end + timedelta(seconds=post_s))},
        },
        "pre_test_brightness": pre_test,
        "brightness_investigation": brightness_investigation,
        "brightness_analysis": brightness_analysis,
        "game_entry_brightness": {
            "entry_window_seconds": entry_seconds,
            "events": entry_events,
            **game_entry_extra,
        },
        "in_game_brightness": {
            "lcm": lcm,
            "hwcomposer": hwc,
        },
        "thermal_brightness": thermal,
        "refresh_rate": refresh_rate,
        "color_mode": color_mode,
        "keyword_hits": keyword_hits,
        "log_availability": {
            "kernel_log": bool(logs.get("kernel_log")),
            "main_log": bool(logs.get("main_log")),
            "sys_log": bool(logs.get("sys_log")),
        },
        "warnings": warnings,
        "notes": notes,
    }
