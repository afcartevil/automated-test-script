"""游戏场景后台应用四步排查（与 game_background/SKILL.md §分析流程对齐）。"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from background_behavior import (
    is_game_package,
    is_valid_package_name,
    normalize_package,
    parse_proc_died_fields,
)
from skill_references import load_analysis_standards, threshold

_PROC_START_RE = re.compile(
    r"am_proc_start:\s*\[0,(?P<pid>\d+),(?P<uid>\d+),(?P<pkg>[^,\]]+)"
)
_PROC_DIED_RE = re.compile(
    r"am_proc_died:\s*\[0,(?P<pid>\d+),(?P<f2>[^,\]]+)(?:,(?P<f3>[^,\]]+))?"
)
_SERVICE_RESTART_RE = re.compile(
    r"am_schedule_service_restart:\s*\[0,(?P<service>[^,\]]+)(?:,(?P<uid>\d+))?\]"
)
_AM_PSS_RE = re.compile(
    r"am_pss\s*:\s*\[(?P<pid>\d+),(?P<uid>\d+),(?P<pkg>[^,\]]+),[^,]*,[^,]*,[^,]*,(?P<pss>\d+)"
)
_DOWNLOAD_RE = re.compile(r"\bDownload:", re.IGNORECASE)
_GCLOUD_RE = re.compile(r"\bGCloud\b", re.IGNORECASE)
_GC_MARK_RE = re.compile(r"concurrent mark", re.IGNORECASE)
_GC_TOTAL_RE = re.compile(r"total\s+(?P<total_ms>[\d.]+)ms", re.IGNORECASE)


def _ref_dir(from_file: Path) -> Path:
    return from_file.resolve().parent.parent / "references"


def _service_to_package(service: str) -> str:
    s = service.strip()
    if "/" in s:
        return s.split("/", 1)[0]
    return s


def _step1_process_autostart(
    event_files: list[Path],
    start: datetime,
    end: datetime,
    pre_s: int,
    post_s: int,
    game_package: str,
    *,
    extract_ts: Callable[..., Any],
    iter_lines: Callable[[Path], Any],
    window_for: Callable[..., str | None],
    frequent_threshold: int,
) -> dict[str, Any]:
    starts: list[dict[str, Any]] = []
    dies: list[dict[str, Any]] = []
    restarts: list[dict[str, Any]] = []
    open_by_pid: dict[int, dict[str, Any]] = {}

    for path in event_files:
        for line_no, line in iter_lines(path):
            ts_raw, ts = extract_ts(line)
            if not ts or window_for(ts, start, end, pre_s, post_s) != "T_game":
                continue

            m_start = _PROC_START_RE.search(line)
            if m_start:
                pkg = normalize_package(m_start.group("pkg"))
                if not is_valid_package_name(pkg) or is_game_package(pkg, game_package):
                    continue
                pid = int(m_start.group("pid"))
                entry = {
                    "time": ts_raw,
                    "dt": ts,
                    "pid": pid,
                    "uid": int(m_start.group("uid")),
                    "package": pkg,
                    "raw_evidence": f"{path.name}:{line_no}: {line.strip()[:280]}",
                }
                starts.append(entry)
                open_by_pid[pid] = entry
                continue

            m_died = _PROC_DIED_RE.search(line)
            if m_died:
                pid, pkg, _uid = parse_proc_died_fields(m_died)
                if not is_valid_package_name(pkg):
                    pkg = (open_by_pid.get(pid) or {}).get("package", pkg)
                if is_game_package(pkg, game_package):
                    continue
                start_entry = open_by_pid.pop(pid, None)
                duration_s = None
                if start_entry and start_entry.get("dt") and ts:
                    duration_s = round((ts - start_entry["dt"]).total_seconds(), 1)
                dies.append(
                    {
                        "time": ts_raw,
                        "pid": pid,
                        "package": pkg,
                        "duration_from_start_seconds": duration_s,
                        "matched_start": start_entry is not None,
                        "raw_evidence": f"{path.name}:{line_no}: {line.strip()[:280]}",
                    }
                )
                continue

            m_restart = _SERVICE_RESTART_RE.search(line)
            if m_restart:
                service = m_restart.group("service").strip()
                pkg = _service_to_package(service)
                if is_game_package(pkg, game_package):
                    continue
                restarts.append(
                    {
                        "time": ts_raw,
                        "service": service,
                        "package": pkg,
                        "uid": int(m_restart.group("uid")) if m_restart.group("uid") else None,
                        "raw_evidence": f"{path.name}:{line_no}: {line.strip()[:280]}",
                    }
                )

    by_pkg: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "start_count": 0,
            "die_count": 0,
            "service_restart_count": 0,
            "still_alive_count": 0,
            "lifecycle_pairs": [],
        }
    )
    for s in starts:
        by_pkg[s["package"]]["start_count"] += 1
    for d in dies:
        by_pkg[d["package"]]["die_count"] += 1
        if d.get("duration_from_start_seconds") is not None:
            by_pkg[d["package"]]["lifecycle_pairs"].append(
                {
                    "pid": d["pid"],
                    "duration_seconds": d["duration_from_start_seconds"],
                    "die_time": d["time"],
                }
            )
    for r in restarts:
        by_pkg[r["package"]]["service_restart_count"] += 1

    still_alive = [e for e in open_by_pid.values() if not is_game_package(e["package"], game_package)]
    for e in still_alive:
        by_pkg[e["package"]]["still_alive_count"] += 1

    packages = []
    frequent: list[str] = []
    for pkg, stats in sorted(by_pkg.items(), key=lambda x: -x[1]["start_count"]):
        row = {"package": pkg, **stats}
        packages.append(row)
        if stats["start_count"] >= frequent_threshold:
            frequent.append(pkg)

    return {
        "coverage": "ok" if (starts or dies or restarts) else "missing",
        "total_starts": len(starts),
        "total_dies": len(dies),
        "total_service_restarts": len(restarts),
        "still_alive_without_die": [
            {"package": e["package"], "pid": e["pid"], "start_time": e["time"]} for e in still_alive
        ],
        "by_package": packages,
        "frequent_autostart_packages": frequent,
        "frequent_autostart": bool(frequent),
        "starts_sample": [{k: v for k, v in e.items() if k != "dt"} for e in starts[:20]],
        "dies_sample": dies[:20],
        "restarts_sample": restarts[:20],
    }


def _step2_memory_pss(
    event_files: list[Path],
    start: datetime,
    end: datetime,
    pre_s: int,
    post_s: int,
    game_package: str,
    pss_divisor: int,
    *,
    extract_ts: Callable[..., Any],
    iter_lines: Callable[[Path], Any],
    window_for: Callable[..., str | None],
) -> dict[str, Any]:
    by_pkg: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for path in event_files:
        for line_no, line in iter_lines(path):
            m = _AM_PSS_RE.search(line)
            if not m:
                continue
            ts_raw, ts = extract_ts(line)
            if not ts or window_for(ts, start, end, pre_s, post_s) != "T_game":
                continue
            pkg = normalize_package(m.group("pkg"))
            if not is_valid_package_name(pkg) or is_game_package(pkg, game_package):
                continue
            pss = int(m.group("pss"))
            by_pkg[pkg].append(
                {
                    "time": ts_raw,
                    "pid": int(m.group("pid")),
                    "pss_bytes": pss,
                    "pss_mb": round(pss / pss_divisor, 1),
                    "raw_evidence": f"{path.name}:{line_no}: {line.strip()[:260]}",
                }
            )

    packages: list[dict[str, Any]] = []
    for pkg, samples in sorted(by_pkg.items(), key=lambda x: -len(x[1])):
        pss_vals = [s["pss_mb"] for s in samples]
        packages.append(
            {
                "package": pkg,
                "sample_count": len(samples),
                "pss_mb_avg": round(sum(pss_vals) / len(pss_vals), 1),
                "pss_mb_min": round(min(pss_vals), 1),
                "pss_mb_max": round(max(pss_vals), 1),
                "samples": samples[-10:],
            }
        )

    return {
        "coverage": "ok" if packages else "missing",
        "package_count": len(packages),
        "pss_divisor": pss_divisor,
        "by_package": packages,
    }


def _step3_background_download(
    main_files: list[Path],
    start: datetime,
    end: datetime,
    pre_s: int,
    post_s: int,
    *,
    extract_ts: Callable[..., Any],
    iter_lines: Callable[[Path], Any],
    window_for: Callable[..., str | None],
) -> dict[str, Any]:
    downloads: list[dict[str, Any]] = []
    gcloud: list[dict[str, Any]] = []

    for path in main_files:
        for line_no, line in iter_lines(path):
            ts_raw, ts = extract_ts(line)
            if not ts:
                continue
            w = window_for(ts, start, end, pre_s, post_s)
            is_download = bool(_DOWNLOAD_RE.search(line))
            is_gcloud = bool(_GCLOUD_RE.search(line))
            if not is_download and not is_gcloud:
                continue
            entry = {
                "time": ts_raw,
                "window": w,
                "in_game": w == "T_game",
                "is_gcloud": is_gcloud,
                "is_download_manager": is_download,
                "raw_evidence": f"{path.name}:{line_no}: {line.strip()[:300]}",
            }
            if is_download:
                downloads.append(entry)
            if is_gcloud:
                gcloud.append(entry)

    t_game_downloads = [d for d in downloads if d.get("in_game")]
    t_game_gcloud = [g for g in gcloud if g.get("in_game")]

    return {
        "coverage": "ok" if (downloads or gcloud) else "missing",
        "download_count": len(downloads),
        "gcloud_count": len(gcloud),
        "t_game_download_count": len(t_game_downloads),
        "t_game_gcloud_count": len(t_game_gcloud),
        "download_during_game": bool(t_game_downloads),
        "gcloud_tencent_download_during_game": bool(t_game_gcloud),
        "t_game_downloads": t_game_downloads[:20],
        "t_game_gcloud": t_game_gcloud[:20],
        "note": (
            "GCloud 日志表示腾讯游戏下载服务；T_game 内出现则判定为测试期间后台下载"
            if t_game_gcloud
            else None
        ),
    }


def _step4_gc_storm(
    main_files: list[Path],
    start: datetime,
    end: datetime,
    pre_s: int,
    post_s: int,
    game_duration_s: float,
    *,
    extract_ts: Callable[..., Any],
    iter_lines: Callable[[Path], Any],
    window_for: Callable[..., str | None],
    storm_per_minute: float,
    burst_count: int,
    burst_window_s: int,
) -> dict[str, Any]:
    events: list[dict[str, Any]] = []

    for path in main_files:
        for line_no, line in iter_lines(path):
            if not _GC_MARK_RE.search(line):
                continue
            ts_raw, ts = extract_ts(line)
            if not ts or window_for(ts, start, end, pre_s, post_s) != "T_game":
                continue
            proc = "unknown"
            proc_m = re.match(r"^\S+\s+\d+\s+\d+\s+\w\s+([^:]+):", line)
            if proc_m:
                proc = proc_m.group(1).strip()
            total_ms = None
            tm = _GC_TOTAL_RE.search(line)
            if tm:
                total_ms = float(tm.group("total_ms"))
            events.append(
                {
                    "time": ts_raw,
                    "dt": ts,
                    "process": proc,
                    "total_ms": total_ms,
                    "raw_evidence": f"{path.name}:{line_no}: {line.strip()[:280]}",
                }
            )

    events.sort(key=lambda e: e.get("dt") or datetime.min)
    intervals: list[float] = []
    for i in range(1, len(events)):
        a, b = events[i - 1].get("dt"), events[i].get("dt")
        if a and b:
            intervals.append(round((b - a).total_seconds(), 2))

    game_minutes = max(game_duration_s / 60.0, 0.01)
    per_minute = len(events) / game_minutes

    burst_detected = False
    max_burst = 0
    if events:
        i = 0
        while i < len(events):
            j = i + 1
            while j < len(events):
                gap = (events[j]["dt"] - events[i]["dt"]).total_seconds()
                if gap > burst_window_s:
                    break
                j += 1
            burst_size = j - i
            max_burst = max(max_burst, burst_size)
            if burst_size >= burst_count:
                burst_detected = True
            i = j if j > i else i + 1

    gc_storm = burst_detected or per_minute > storm_per_minute

    return {
        "coverage": "ok" if events else "missing",
        "gc_count": len(events),
        "intervals_seconds": intervals[:30],
        "interval_avg_seconds": round(sum(intervals) / len(intervals), 2) if intervals else None,
        "interval_min_seconds": min(intervals) if intervals else None,
        "gc_per_minute": round(per_minute, 2),
        "storm_threshold_per_minute": storm_per_minute,
        "burst_window_seconds": burst_window_s,
        "burst_count_threshold": burst_count,
        "max_burst_in_window": max_burst,
        "gc_storm": gc_storm,
        "events": [{k: v for k, v in e.items() if k != "dt"} for e in events[:30]],
    }


def build_background_investigation(
    *,
    lib_file: Path,
    logs: dict[str, list[Path]],
    start: datetime,
    end: datetime,
    pre_s: int,
    post_s: int,
    game_package: str = "",
    extract_ts: Callable[..., Any],
    iter_lines: Callable[[Path], Any],
    window_for: Callable[..., str | None],
) -> dict[str, Any]:
    ref_dir = _ref_dir(lib_file)
    standards = load_analysis_standards(ref_dir)
    pss_divisor = int(threshold(standards, "pss_divisor", 1_000_000))
    storm_pm = float(threshold(standards, "gc_storm_per_minute", 5))
    burst_count = int(threshold(standards, "gc_burst_count", 5))
    burst_window = int(threshold(standards, "gc_burst_window_seconds", 60))
    frequent_start = int(threshold(standards, "frequent_start_count", 3))

    event_files = logs.get("events_log", [])
    main_files = logs.get("main_log", [])
    game_duration_s = (end - start).total_seconds() if end > start else 0.0

    step1 = _step1_process_autostart(
        event_files, start, end, pre_s, post_s, game_package,
        extract_ts=extract_ts, iter_lines=iter_lines, window_for=window_for,
        frequent_threshold=frequent_start,
    )
    step2 = _step2_memory_pss(
        event_files, start, end, pre_s, post_s, game_package, pss_divisor,
        extract_ts=extract_ts, iter_lines=iter_lines, window_for=window_for,
    )
    step3 = _step3_background_download(
        main_files, start, end, pre_s, post_s,
        extract_ts=extract_ts, iter_lines=iter_lines, window_for=window_for,
    )
    step4 = _step4_gc_storm(
        main_files, start, end, pre_s, post_s, game_duration_s,
        extract_ts=extract_ts, iter_lines=iter_lines, window_for=window_for,
        storm_per_minute=storm_pm, burst_count=burst_count, burst_window_s=burst_window,
    )

    warnings: list[str] = []
    if step1.get("frequent_autostart"):
        warnings.append(f"后台应用频繁自启动: {', '.join(step1.get('frequent_autostart_packages') or [])}")
    if step3.get("download_during_game") or step3.get("gcloud_tencent_download_during_game"):
        warnings.append("游戏测试期间检测到后台下载行为")
    if step4.get("gc_storm"):
        warnings.append(
            f"GC 风暴: {step4.get('gc_count')} 次, "
            f"{step4.get('gc_per_minute')}/min (阈值 {storm_pm}/min)"
        )

    return {
        "flow_version": 1,
        "step1_process_autostart": step1,
        "step2_memory_pss": step2,
        "step3_background_download": step3,
        "step4_gc_storm": step4,
        "warnings": warnings,
    }
