"""flow 步骤 10：游戏场景网络分析。

输出 JSON（game_network.json）: network_investigation, rf_stats, subsystems.rf
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from network_investigation_lib import build_network_investigation
from rf_probe import probe_rf_stats


def analyze_game_network(
    log_path: Path,
    start: datetime,
    end: datetime,
    *,
    pre_minutes: int = 5,
    post_minutes: int = 3,
    discover_logs: Callable[..., dict[str, list[Path]]],
    extract_ts: Callable[..., Any],
    iter_lines: Callable[[Path], Any],
    window_for: Callable[..., str | None],
    fmt_time: Callable[[datetime | None], str],
) -> dict[str, Any]:
    pre_s = max(0, pre_minutes) * 60
    post_s = max(0, post_minutes) * 60
    logs = discover_logs(log_path)

    network_investigation = build_network_investigation(
        lib_file=Path(__file__),
        logs=logs,
        start=start,
        end=end,
        pre_s=pre_s,
        post_s=post_s,
        extract_ts=extract_ts,
        iter_lines=iter_lines,
        window_for=window_for,
    )

    rf_stats = probe_rf_stats(logs, start, end, pre_s, extract_ts, iter_lines, window_for)

    coverage = rf_stats.get("coverage", "")
    status = "ok" if coverage == "ok" else "partial"
    if not logs.get("radio_log") and not logs.get("main_log") and not logs.get("sys_log"):
        status = "failed"

    notes: list[str] = list(rf_stats.get("notes") or [])
    notes.extend(network_investigation.get("warnings") or [])

    return {
        "status": status,
        "log_path": str(log_path),
        "game_window": {
            "start": fmt_time(start),
            "end": fmt_time(end),
            "duration_seconds": int((end - start).total_seconds()),
        },
        "log_availability": {
            "radio_log": bool(logs.get("radio_log")),
            "main_log": bool(logs.get("main_log")),
            "sys_log": bool(logs.get("sys_log")),
            "kernel_log": bool(logs.get("kernel_log")),
        },
        "network_investigation": network_investigation,
        "rf_stats": rf_stats,
        "subsystems": {
            "rf": {
                "level": rf_stats.get("level", "unknown"),
                "confidence": "medium" if coverage == "ok" else "low",
                "summary": rf_stats.get("summary", ""),
                "evidence": (rf_stats.get("raw_evidence") or [])[:10],
            }
        },
        "notes": notes,
    }
