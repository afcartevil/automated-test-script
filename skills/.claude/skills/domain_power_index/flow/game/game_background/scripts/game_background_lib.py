"""游戏场景后台应用唤醒与服务行为解析。

配置: references/keyword-patterns.yaml, background-behavior-thresholds.yaml
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

_SCRIPT_DIR = Path(__file__).resolve().parent
from game_skill_paths import ensure_game_scripts_on_path  # noqa: E402

ensure_game_scripts_on_path(__file__)
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
from skill_references import evidence_cap, load_analysis_standards, load_keyword_patterns  # noqa: E402

from background_investigation_lib import build_background_investigation  # noqa: E402
from background_behavior import parse_background_logs

_EVIDENCE_CAP = evidence_cap(load_analysis_standards(Path(__file__).resolve().parent.parent / "references"))


def skill_root() -> Path:
    return Path(__file__).resolve().parent.parent


def references_dir() -> Path:
    return skill_root() / "references"


def _load_kernel_cpu_abnormal(
    log_path: Path,
    game_package: str,
) -> list[dict[str, Any]]:
    """可选：从已生成的 game_kernel_cpu.json 读取异常进程用于交叉关联。"""
    candidates = [
        log_path / "analysis" / "game_kernel_cpu.json",
        log_path.parent / "analysis" / "game_kernel_cpu.json",
    ]
    parts = list(log_path.resolve().parts)
    lower = [p.lower() for p in parts]
    if "converted" in lower:
        idx = lower.index("converted")
        candidates.insert(0, Path(*parts[:idx]) / "analysis" / "game_kernel_cpu.json")

    for path in candidates:
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError):
            continue
        abnormal = data.get("abnormal_processes") or []
        if abnormal:
            return [dict(ap) for ap in abnormal]
    return []


def _category_breakdown(
    events: list[dict[str, Any]],
    game_package: str,
) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for ev in events:
        if ev.get("window") != "T_game":
            continue
        pkg = str(ev.get("package_or_process") or "")
        if game_package and pkg == game_package:
            continue
        cat = str(ev.get("category") or "")
        if cat:
            counts[cat] += 1
    return dict(counts.most_common())


def _build_background_summary(top: list[dict[str, Any]]) -> dict[str, Any]:
    relation_counts: Counter[str] = Counter()
    suspicious = 0
    game_related = 0
    wakelock_pkgs = 0
    service_pkgs = 0

    for row in top:
        rel = str(row.get("relation") or "observe")
        relation_counts[rel] += 1
        if rel in ("game_related", "post_persistent"):
            suspicious += 1
        if rel == "game_related":
            game_related += 1
        cats = row.get("categories") or []
        if "wakelock" in cats:
            wakelock_pkgs += 1
        if any(c in cats for c in ("service_start", "service_bind", "foreground_service")):
            service_pkgs += 1

    return {
        "during_game": {
            "suspicious_packages": suspicious,
            "game_related_packages": game_related,
            "wakelock_packages": wakelock_pkgs,
            "service_active_packages": service_pkgs,
        },
        "top_relation_counts": dict(relation_counts),
    }


def _serialize_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for ev in events[:_EVIDENCE_CAP]:
        item = {k: v for k, v in ev.items() if k != "dt"}
        out.append(item)
    return out


def analyze_game_background(
    log_path: Path,
    start: datetime,
    end: datetime,
    *,
    game_package: str = "",
    pre_minutes: int = 5,
    post_minutes: int = 3,
    startup_seconds: int = 60,
    exit_seconds: int = 30,
    link_kernel_cpu: bool = True,
    abnormal_processes: list[dict[str, Any]] | None = None,
    discover_logs: Callable[..., dict[str, list[Path]]],
    extract_ts: Callable[..., Any],
    window_for: Callable[..., str | None],
    iter_lines: Callable[[Path], Any],
    fmt_time: Callable[[datetime | None], str],
    add_event: Callable[[list[dict[str, Any]], dict[str, Any]], None],
    phase_for: Callable[..., str | None],
    load_baseline_processes: Callable[[Path], dict[str, Any]],
    scripts_dir: Path,
) -> dict[str, Any]:
    pre_s = max(0, pre_minutes) * 60
    post_s = max(0, post_minutes) * 60
    logs = discover_logs(log_path)

    has_events = bool(logs.get("events_log"))
    has_main = bool(logs.get("main_log"))
    has_sys = bool(logs.get("sys_log"))
    if not has_events and not has_main and not has_sys:
        return {
            "status": "failed",
            "log_path": str(log_path),
            "notes": ["events / main / sys 日志均缺失"],
        }

    abnormal: list[dict[str, Any]] = []
    if abnormal_processes is not None:
        abnormal = [dict(ap) for ap in abnormal_processes]
    elif link_kernel_cpu:
        abnormal = _load_kernel_cpu_abnormal(log_path, game_package)

    events: list[dict[str, Any]] = []
    bg_summary = parse_background_logs(
        logs.get("events_log", []),
        logs.get("main_log", []) + logs.get("sys_log", []),
        events,
        add_event,
        extract_ts,
        window_for,
        iter_lines,
        start,
        end,
        pre_s,
        post_s,
        startup_seconds,
        exit_seconds,
        game_package.strip(),
        references_dir(),
        load_baseline_processes(scripts_dir).get("common_processes", []),
        abnormal,
        phase_for,
    )

    background_investigation = build_background_investigation(
        lib_file=Path(__file__),
        logs=logs,
        start=start,
        end=end,
        pre_s=pre_s,
        post_s=post_s,
        game_package=game_package.strip(),
        extract_ts=extract_ts,
        iter_lines=iter_lines,
        window_for=window_for,
    )

    top = bg_summary.get("top_background_packages") or []
    hc = [r for r in top if r.get("high_confidence_candidate")]
    cat_breakdown = _category_breakdown(events, game_package.strip())
    summary = _build_background_summary(top)

    notes: list[str] = [
        f"后台包总数 {bg_summary.get('background_stats', {}).get('total_packages', 0)}",
    ]
    if top:
        t0 = top[0]
        notes.append(
            f"Top: {t0.get('package_or_process')} relation={t0.get('relation')} "
            f"boost={t0.get('boost_ratio')}"
        )
    if hc:
        notes.append(f"高置信候选 {len(hc)} 个（需与 CPU 证据并列定责）")
    if link_kernel_cpu and abnormal:
        linked = sum(1 for ap in abnormal if ap.get("related_background_behavior"))
        notes.append(f"与 kernel CPU 异常进程交叉 {linked} 个")

    notes.extend(background_investigation.get("warnings") or [])

    status = "ok"
    if not top and not events:
        status = "partial"

    return {
        "status": status,
        "log_path": str(log_path),
        "game_window": {
            "start": fmt_time(start),
            "end": fmt_time(end),
            "duration_seconds": int((end - start).total_seconds()),
            "package": game_package.strip(),
            "pre_minutes": pre_minutes,
            "post_minutes": post_minutes,
        },
        "log_availability": {
            "events_log": has_events,
            "main_log": has_main,
            "sys_log": has_sys,
        },
        "background_investigation": background_investigation,
        "background_summary": summary,
        "top_background_packages": top,
        "background_stats": bg_summary.get("background_stats"),
        "misidentification": bg_summary.get("misidentification"),
        "category_breakdown_T_game": cat_breakdown,
        "high_confidence_candidates": hc,
        "sample_events": _serialize_events(events),
        "abnormal_processes_linked": abnormal if (link_kernel_cpu or abnormal_processes is not None) else [],
        "notes": notes,
    }
