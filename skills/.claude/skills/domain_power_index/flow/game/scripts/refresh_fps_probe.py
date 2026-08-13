"""步骤 6：刷新率与帧率独立排查。"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from game_power_parser import parse_main_sys  # noqa: E402

_EVIDENCE_CAP = 30

_REFRESH_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"updateFrameRateVote.*?refreshRate\s*=\s*([\d.]+)"), "frame_rate_vote"),
    (re.compile(r"renderFrameRate\s*=\s*([\d.]+)"), "render_frame_rate"),
    (re.compile(r"RefreshRateSelector: Current:.*?render=\[([\d.]+)\s*Hz"), "policy_fps"),
]


def _evidence(path: Path, line_no: int, line: str) -> str:
    return f"{path.name}:{line_no}: {line.rstrip()[:240]}"


def probe_refresh_fps_stats(
    logs: dict[str, list[Path]],
    events: list[dict[str, Any]],
    game_start: datetime | None,
    game_end: datetime | None,
    pre_seconds: int,
    post_seconds: int,
    game_package: str,
    extract_ts: Callable[..., Any],
    iter_lines: Callable[..., Any],
    window_for: Callable[..., str | None],
    add_event: Callable[[list[dict[str, Any]], dict[str, Any]], None],
) -> dict[str, Any]:
    main_summary = parse_main_sys(
        logs.get("main_log", []) + logs.get("sys_log", []),
        events,
        game_start,
        game_end,
        pre_seconds,
        post_seconds,
        game_package,
    )
    frame_rate_stats = main_summary.get("fps_layers", {})

    scan_start = game_start - timedelta(seconds=pre_seconds) if game_start else None
    refresh_rates: list[dict[str, Any]] = []
    game_refresh_hz: list[float] = []
    game_pkg_refresh_hz: list[float] = []

    for path in logs.get("main_log", []) + logs.get("sys_log", []) + logs.get("events_log", []):
        for line_no, line in iter_lines(path):
            _, ts = extract_ts(line)
            if scan_start and ts and ts < scan_start:
                continue
            if game_end and ts and ts > game_end:
                continue
            window = window_for(ts, game_start, game_end, pre_seconds, post_seconds) or "unknown"
            for pat, kind in _REFRESH_PATTERNS:
                m = pat.search(line)
                if not m:
                    continue
                hz = float(m.group(1))
                item = {
                    "kind": kind,
                    "hz": hz,
                    "window": window,
                    "time": str(ts) if ts else "",
                    "raw_evidence": _evidence(path, line_no, line),
                }
                refresh_rates.append(item)
                if window == "T_game":
                    game_refresh_hz.append(hz)
                    if game_package and game_package in line:
                        game_pkg_refresh_hz.append(hz)
                break

    def _hz_stats(values: list[float]) -> dict[str, Any]:
        if not values:
            return {"min_hz": None, "max_hz": None, "stable_hz": None, "sample_count": 0}
        uniq = sorted(set(values))
        stable = uniq[0] if len(uniq) == 1 else None
        return {
            "min_hz": min(values),
            "max_hz": max(values),
            "stable_hz": stable,
            "sample_count": len(values),
            "unique_hz": uniq[:10],
        }

    refresh_stats = {
        "coverage": "ok" if game_refresh_hz else ("partial" if refresh_rates else "missing"),
        "game_window": _hz_stats(game_refresh_hz),
        "game_package_window": _hz_stats(game_pkg_refresh_hz),
        "samples": [r for r in refresh_rates if r.get("window") == "T_game"][:_EVIDENCE_CAP],
    }

    main_app = frame_rate_stats.get("main_app_layer") or {}
    notes: list[str] = []
    if not main_app:
        notes.append("T_game 内未识别到主应用 BufferQueueProducer 图层 FPS")
    else:
        notes.append(
            f"主应用 FPS avg={main_app.get('avg_fps')} "
            f"min={main_app.get('min_fps')} max={main_app.get('max_fps')} "
            f"samples={main_app.get('sample_count')}"
        )
    gw = refresh_stats["game_window"]
    if gw.get("stable_hz"):
        notes.append(f"T_game 系统刷新率恒定 {gw['stable_hz']}Hz")
    elif gw.get("sample_count"):
        notes.append(f"T_game 刷新率 {gw.get('min_hz')}~{gw.get('max_hz')}Hz")

    return {
        "refresh_rate_stats": refresh_stats,
        "frame_rate_stats": frame_rate_stats,
        "notes": notes,
    }
