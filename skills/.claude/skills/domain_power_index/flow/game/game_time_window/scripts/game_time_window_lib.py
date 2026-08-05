"""游戏场景时间窗对齐：event 识别、T_pre/T_game/T_post、kernel/main/sys 覆盖检查。

输出 JSON 主要字段（game_time_window.json）:
  status, game_package, game_name, game_window{start,end,duration_seconds},
  derived_windows{T_pre,T_post}, log_coverage{kernel,main,sys},
  warnings[], segments[]

Event 关键词: wm_set_resumed_activity, wm_pause_activity, am_focused_app
窗口规则: 最短片段、合并间隔见本模块常量 GAME_START_SETTLE_SECONDS 等
配置: references/game-packages.yaml
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

TS_RE = re.compile(r"(?P<ts>\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3,6})")
TS_SEC_RE = re.compile(r"(?P<ts>\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})(?!\.)")
LINLI_TS_RE = re.compile(r"\[(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)\]")
GAME_START_SETTLE_SECONDS = 60
WM_RESUME_MARKERS = ("wm_set_resumed_activity", "wm_resumed_activity", "wm_set_resume:", "am_focused_app")
WM_PAUSE_MARKERS = ("wm_pause_activity", "wm_set_paused_activity", "wm_set_pause:")
RESUME_START_MARKERS = ("realStartActivityLocked", "resumeTopActivity", "topWhenResuming")
NON_GAME_ACTIVITY_TOKENS = ("Splash", "Proxy", "Permission", "Login", "Account", "Auth", "Dialog", "Downloader", "Extractor", "MainActivityWith")
PRIMARY_GAME_ACTIVITY_TOKENS = ("GameActivity", "UnityPlayer", "UE4", "CODMainActivity", "MobaGameUnity", "MobaGame")

LOG_KEYS = [
    "events_log",
    "main_log",
    "sys_log",
    "kernel_log",
    "radio_log",
    "bugreport",
    "ged_fps_log",
    "spm_log",
    "thermal_log",
    "pmic_log",
    "dramc_log",
    "wifilog",
]

# 步骤1 / 测试手法·日志类：mobile 核心日志（不含可选 ged/pmic 等）
MOBILE_CORE_LOG_KEYS = (
    "events_log",
    "main_log",
    "sys_log",
    "kernel_log",
    "radio_log",
)

# 场景识别后，检查 T_game 时段覆盖（场景日志不全）
SCENE_LOG_KEYS = MOBILE_CORE_LOG_KEYS
FULL_COVERAGE_KEYS = (
    "events_log",
    "main_log",
    "sys_log",
    "kernel_log",
    "radio_log",
    "spm_log",
)


def skill_root() -> Path:
    return Path(__file__).resolve().parent.parent


def references_dir() -> Path:
    return skill_root() / "references"


def parse_dt(value: str | None, year: int | None = None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    year = year or datetime.now().year
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    for fmt in ("%m-%d %H:%M:%S.%f", "%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(f"{year}-{value}", f"%Y-{fmt}")
        except ValueError:
            pass
    return None


def extract_ts(line: str, year: int | None = None) -> tuple[str, datetime] | tuple[None, None]:
    year = year or datetime.now().year
    linli = LINLI_TS_RE.search(line)
    if linli:
        raw = linli.group("ts")
        dt = parse_dt(raw, year)
        if dt:
            return raw, dt
    match = TS_RE.search(line) or TS_SEC_RE.search(line)
    if not match:
        return None, None
    raw = match.group("ts")
    return raw, parse_dt(raw, year)


def iter_lines(path: Path):
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as fh:
            for no, line in enumerate(fh, 1):
                yield no, line.rstrip("\n")
    except OSError:
        return


def _is_bugreport_name(name: str, full_path_lower: str = "") -> bool:
    """按文件名识别 bugreport；避免因目录名 bugreports 误收其它文件。"""
    n = str(name or "").lower()
    if n.startswith("bugreport") or "bug_report" in n:
        return True
    # 兼容路径末段（少数调用只传 full）
    full = str(full_path_lower or "").lower().replace("\\", "/")
    if full:
        base = full.rsplit("/", 1)[-1]
        if base.startswith("bugreport") or "bug_report" in base:
            return True
    return False


def _discover_bugreports_near(log_path: Path, *, max_up: int = 6) -> list[Path]:
    """在 APLog 之外向上查找 bugreports 目录/文件。

    典型布局：``<SN>/mobilelog/APLog_*`` 与 ``<SN>/bugreports/`` 同级。
    仅收集 bugreport*，不把上级目录里的其它日志混入。
    """
    p = Path(log_path).resolve()
    found: list[Path] = []
    seen: set[str] = set()

    def _add(path: Path) -> None:
        try:
            key = str(path.resolve()).lower()
        except OSError:
            key = str(path).lower()
        if key in seen:
            return
        seen.add(key)
        found.append(path)

    def _collect_from_dir(base: Path) -> int:
        n0 = len(found)
        try:
            entries = list(base.iterdir())
        except OSError:
            return 0
        for child in entries:
            try:
                if child.is_file() and _is_bugreport_name(child.name):
                    _add(child)
                elif child.is_dir() and child.name.lower() in {
                    "bugreports",
                    "bugreport",
                    "bug_reports",
                }:
                    for root, _, files in os.walk(child):
                        root_l = root.lower().replace("\\", "/")
                        for name in files:
                            full = f"{root_l}/{name.lower()}"
                            if _is_bugreport_name(name, full):
                                _add(Path(root) / name)
            except OSError:
                continue
        return len(found) - n0

    # 先扫 log_path 自身（含其下 bugreports）
    _collect_from_dir(p)
    for parent in list(p.parents)[:max_up]:
        added = _collect_from_dir(parent)
        # 在 SN 层找到 bugreports 后即可停止继续上行，避免扫到其它机型
        br = parent / "bugreports"
        if br.is_dir() and added:
            break
        if parent.name.lower() in {"bugreports", "bugreport"}:
            break
    return found


def discover_logs(log_path: Path) -> dict[str, list[Path]]:
    logs: dict[str, list[Path]] = {key: [] for key in LOG_KEYS}
    log_path = Path(log_path).resolve()
    for root, _, files in os.walk(log_path):
        root_l = root.lower().replace("\\", "/")
        for name in files:
            p = Path(root) / name
            n = name.lower()
            full = f"{root_l}/{n}"
            if _is_bugreport_name(name, full):
                logs["bugreport"].append(p)
            elif "event" in n or "events" in n:
                logs["events_log"].append(p)
            elif "kernel" in n or "kmsg" in n or "linli_666" in n:
                logs["kernel_log"].append(p)
            elif "main" in n:
                logs["main_log"].append(p)
            elif "system" in n or n.endswith(".sys") or "sys_log" in n:
                logs["sys_log"].append(p)
            elif "radio" in n:
                logs["radio_log"].append(p)
            elif "ged" in full or "fpsgo" in full:
                logs["ged_fps_log"].append(p)
            elif "spm" in full:
                logs["spm_log"].append(p)
            elif "thermal" in full or "tscpu" in n:
                logs["thermal_log"].append(p)
            elif "pmic" in full:
                logs["pmic_log"].append(p)
            elif "dram" in full or "dramc" in full:
                logs["dramc_log"].append(p)
            elif "wifi" in full or "wpa_supplicant" in n:
                logs["wifilog"].append(p)

    # APLog 内未找到时，向上搜索同级 bugreports（如 <SN>/bugreports）
    if not logs["bugreport"]:
        logs["bugreport"] = _discover_bugreports_near(log_path)
    else:
        # 合并上级目录中的 bugreport，去重
        extra = _discover_bugreports_near(log_path)
        known = {str(x.resolve()).lower() for x in logs["bugreport"]}
        for p in extra:
            try:
                key = str(p.resolve()).lower()
            except OSError:
                key = str(p).lower()
            if key not in known:
                logs["bugreport"].append(p)
                known.add(key)

    logs["kernel_log"] = _resolve_kernel_logs(logs["kernel_log"])
    return logs


def build_log_inventory(
    logs: dict[str, list[Path]] | dict[str, Any],
    *,
    log_coverage: dict[str, Any] | None = None,
    log_availability: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """步骤1日志识别结果：mobile 核心 / bugreport / 可选日志 / 场景时段覆盖缺口。"""

    def _present(key: str) -> bool:
        if log_availability and key in log_availability:
            return str(log_availability.get(key) or "").lower() in ("ok", "present", "true", "1")
        files = logs.get(key)
        if isinstance(files, list):
            return bool(files)
        if isinstance(files, dict):
            return str(files.get("status") or "").lower() == "ok" or bool(files.get("files"))
        return bool(files)

    mobile_missing = [k for k in MOBILE_CORE_LOG_KEYS if not _present(k)]
    optional_keys = [k for k in LOG_KEYS if k not in MOBILE_CORE_LOG_KEYS and k != "bugreport"]
    optional_missing = [k for k in optional_keys if not _present(k)]
    bugreport_ok = _present("bugreport")

    scene_missing: list[str] = []
    coverage = log_coverage or {}
    for key in MOBILE_CORE_LOG_KEYS:
        entry = coverage.get(key) if isinstance(coverage, dict) else None
        if not isinstance(entry, dict):
            if key in mobile_missing:
                scene_missing.append(key)
            continue
        status = str(entry.get("status") or "").lower()
        covers = entry.get("covers_t_game")
        if status in ("missing", "no_overlap") or covers is False:
            scene_missing.append(key)

    has_any_mobile = len(mobile_missing) < len(MOBILE_CORE_LOG_KEYS)
    no_logs = (not has_any_mobile) and (not bugreport_ok)
    incomplete = (not no_logs) and (bool(mobile_missing) or not bugreport_ok)

    return {
        "mobile_core_keys": list(MOBILE_CORE_LOG_KEYS),
        "mobile_core_missing": mobile_missing,
        "optional_missing": optional_missing,
        "bugreport": "ok" if bugreport_ok else "missing",
        "bugreport_present": bugreport_ok,
        "has_any_mobile_log": has_any_mobile,
        "no_logs": no_logs,
        "incomplete": incomplete,
        "scene_coverage_missing": scene_missing,
        # 报告「日志不全」第二列优先展示核心缺失 + bugreport
        "missing_for_report": mobile_missing
        + ([] if bugreport_ok else ["bugreport"]),
    }


def _resolve_kernel_logs(files: list[Path]) -> list[Path]:
    linli = [p for p in files if "linli_666" in p.name.lower()]
    raw = [p for p in files if "linli_666" not in p.name.lower()]
    if not linli:
        return raw
    converted_stems = {p.name[: -len("_linli_666.txt")] for p in linli if p.name.lower().endswith("_linli_666.txt")}
    kept_raw = [p for p in raw if p.stem not in converted_stems and p.name not in converted_stems]
    return sorted(linli + kept_raw, key=lambda x: x.name)


def status_for(files: list[Path]) -> str:
    return "ok" if files else "missing"


def file_time_range(path: Path) -> tuple[datetime | None, datetime | None]:
    first = None
    last = None
    for _, line in iter_lines(path):
        _, dt = extract_ts(line)
        if dt is None:
            continue
        if first is None:
            first = dt
        last = dt
    return first, last


def fmt_time(dt: datetime | None) -> str:
    return dt.strftime("%m-%d %H:%M:%S.%f")[:-3] if dt else ""


def load_known_game_packages() -> set[str]:
    packages: set[str] = set()
    yaml_path = references_dir() / "game-packages.yaml"
    if not yaml_path.exists():
        return packages
    for _, line in iter_lines(yaml_path):
        m = re.search(r"package:\s*(?P<pkg>\S+)", line)
        if m:
            raw = m.group("pkg").strip()
            packages.add(raw.split(":")[0])
    return packages


def load_game_name(package: str) -> str:
    if not package:
        return ""
    base_pkg = package.split(":")[0]
    yaml_path = references_dir() / "game-packages.yaml"
    if not yaml_path.exists():
        return base_pkg
    text = yaml_path.read_text(encoding="utf-8", errors="replace")
    for block in re.split(r"\n\s*-\s+name:\s*", text)[1:]:
        lines = block.splitlines()
        if not lines:
            continue
        pkg_m = re.search(r"package:\s*(\S+)", block)
        if pkg_m and pkg_m.group(1).split(":")[0] == base_pkg:
            return lines[0].strip()
    return base_pkg


def _event_evidence(ev: dict[str, Any] | None) -> str:
    if not ev:
        return ""
    return f"{Path(ev['file']).name}:{ev['line']}: {ev.get('raw', '')}"


def _is_wm_resume_event(line: str) -> bool:
    return any(marker in line for marker in WM_RESUME_MARKERS)


def _is_wm_pause_event(line: str) -> bool:
    return any(marker in line for marker in WM_PAUSE_MARKERS)


def extract_package(line: str, known_packages: set[str], game_package: str | None = None) -> str:
    if game_package:
        base = game_package.split(":")[0]
        if base in line or game_package in line:
            return base
    component = extract_component(line)
    if component and "/" in component:
        pkg = component.split("/", 1)[0].strip()
        base = pkg.split(":")[0]
        if not known_packages or base in known_packages:
            return base
    for pkg in sorted(known_packages, key=len, reverse=True):
        base = pkg.split(":")[0]
        if base in line or pkg in line:
            return base
    candidates = re.findall(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+){2,}", line)
    if not candidates:
        return ""
    fallback = candidates[0]
    if "/" in component:
        return component.split("/", 1)[0].split(":")[0]
    return fallback.split(":")[0]


def extract_component(line: str) -> str:
    match = re.search(r"\[0,([^,\]]+)", line)
    return match.group(1).strip() if match else ""


def component_activity(component: str) -> str:
    return component.split("/", 1)[1] if "/" in component else component


def is_primary_game_activity(component: str) -> bool:
    activity = component_activity(component)
    if not activity:
        return False
    if any(token in activity for token in NON_GAME_ACTIVITY_TOKENS):
        return False
    return any(token in activity for token in PRIMARY_GAME_ACTIVITY_TOKENS)


def _resume_start_score(event: dict[str, Any]) -> int:
    if event.get("kind") != "resume":
        return 0
    component = str(event.get("component", ""))
    activity = component_activity(component)
    raw = str(event.get("raw", ""))
    if any(token in activity for token in NON_GAME_ACTIVITY_TOKENS):
        return 1
    if not is_primary_game_activity(component):
        return 2
    score = 10
    if "realStartActivityLocked" in raw:
        score += 20
    elif "resumeTopActivity" in raw:
        score += 12
    elif any(marker in raw for marker in RESUME_START_MARKERS):
        score += 8
    if "MobaGameUnity" in activity or activity.endswith("GameActivity"):
        score += 5
    return score


def is_effective_game_resume(event: dict[str, Any]) -> bool:
    return _resume_start_score(event) >= 15


def is_better_game_start(candidate: dict[str, Any], current: dict[str, Any]) -> bool:
    candidate_score = _resume_start_score(candidate)
    current_score = _resume_start_score(current)
    if candidate_score != current_score:
        return candidate_score > current_score
    if is_effective_game_resume(candidate) and is_effective_game_resume(current):
        delta = (candidate["time"] - current["time"]).total_seconds()
        if 0 < delta <= GAME_START_SETTLE_SECONDS:
            return True
    return False


def _collect_wm_events(
    event_files: list[Path],
    known_packages: set[str],
    game_package: str | None,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for path in event_files:
        for line_no, line in iter_lines(path):
            if not _is_wm_resume_event(line) and not _is_wm_pause_event(line):
                continue
            ts_raw, ts = extract_ts(line)
            if not ts:
                continue
            pkg = extract_package(line, known_packages, game_package)
            if not pkg:
                continue
            kind = "resume" if _is_wm_resume_event(line) else "pause"
            events.append(
                {
                    "time": ts,
                    "time_raw": ts_raw,
                    "kind": kind,
                    "package": pkg,
                    "component": extract_component(line),
                    "file": str(path),
                    "line": line_no,
                    "raw": line.strip(),
                }
            )
    events.sort(key=lambda x: x["time"])
    return events


def _infer_package_in_window(
    events: list[dict[str, Any]],
    start: datetime,
    end: datetime,
    known_packages: set[str],
) -> str:
    counts: dict[str, int] = {}
    for ev in events:
        if ev["kind"] != "resume":
            continue
        if not (start <= ev["time"] <= end):
            continue
        pkg = str(ev.get("package", ""))
        if pkg in known_packages:
            counts[pkg] = counts.get(pkg, 0) + _resume_start_score(ev)
    if not counts:
        return ""
    return max(counts.items(), key=lambda x: (x[1], x[0]))[0]


def _build_segments_for_package(
    events: list[dict[str, Any]],
    target: str,
    end_bound: datetime | None,
    min_segment_seconds: int,
    merge_gap_seconds: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    segments: list[dict[str, Any]] = []
    omitted_segments: list[dict[str, Any]] = []
    start_ev = None
    last_target_ev = None

    for ev in events:
        if ev["kind"] == "resume" and ev["package"] == target:
            if start_ev is None:
                start_ev = ev
            elif is_better_game_start(ev, start_ev):
                start_ev = ev
            last_target_ev = ev
            continue
        if start_ev is None:
            continue
        if ev["kind"] == "pause" and ev["package"] == target:
            last_target_ev = ev
            continue
        if ev["kind"] == "resume" and ev["package"] != target:
            if last_target_ev and (ev["time"] - last_target_ev["time"]).total_seconds() < merge_gap_seconds:
                continue
            end_ev = ev
            duration = int((end_ev["time"] - start_ev["time"]).total_seconds())
            segment = {
                "start": start_ev["time"],
                "end": end_ev["time"],
                "duration_seconds": duration,
                "source": "event",
                "end_reason": f"next_resume:{ev['package']}",
                "start_evidence": _event_evidence(start_ev),
                "end_evidence": _event_evidence(end_ev),
            }
            if duration >= min_segment_seconds:
                segments.append(segment)
            else:
                segment["omit_reason"] = f"duration_lt_{min_segment_seconds}s"
                omitted_segments.append(segment)
            start_ev = None
            last_target_ev = None

    if start_ev is not None:
        segment_end = end_bound or (last_target_ev["time"] if last_target_ev else start_ev["time"])
        duration = int((segment_end - start_ev["time"]).total_seconds())
        end_evidence_ev = last_target_ev if last_target_ev else start_ev
        segment = {
            "start": start_ev["time"],
            "end": segment_end,
            "duration_seconds": duration,
            "source": "event" if not end_bound else "user",
            "end_reason": "user_end" if end_bound else "last_target_event",
            "start_evidence": _event_evidence(start_ev),
            "end_evidence": _event_evidence(end_evidence_ev),
        }
        if duration >= min_segment_seconds:
            segments.append(segment)
        else:
            segment["omit_reason"] = f"duration_lt_{min_segment_seconds}s"
            omitted_segments.append(segment)

    return segments, omitted_segments


def find_game_window(
    event_files: list[Path],
    known_packages: set[str],
    game_package: str | None,
    start: datetime | None,
    end: datetime | None,
    min_segment_seconds: int = 120,
    merge_gap_seconds: int = 30,
) -> dict[str, Any]:
    events = _collect_wm_events(event_files, known_packages, game_package)

    if start and end:
        pkg = game_package or _infer_package_in_window(events, start, end, known_packages)
        return {
            "package": pkg,
            "start": start,
            "end": end,
            "source": "user",
            "start_evidence": "",
            "end_evidence": "",
            "end_reason": "user",
            "segments": [
                {
                    "start": start,
                    "end": end,
                    "duration_seconds": int((end - start).total_seconds()),
                    "source": "user",
                    "start_evidence": "",
                    "end_evidence": "",
                    "end_reason": "user",
                }
            ],
            "omitted_segments": [],
            "candidates": events[:20],
        }

    if game_package:
        pkg_candidates = [game_package]
    else:
        pkg_candidates = sorted(
            {ev["package"] for ev in events if ev["kind"] == "resume" and ev["package"] in known_packages}
        )

    if not pkg_candidates:
        return {"package": "", "start": start, "end": end, "source": "", "candidates": events[:20]}

    all_segments: list[dict[str, Any]] = []
    all_omitted: list[dict[str, Any]] = []
    for target in pkg_candidates:
        segs, omitted = _build_segments_for_package(
            events, target, end, min_segment_seconds, merge_gap_seconds
        )
        for segment in segs:
            segment["package"] = target
        for segment in omitted:
            segment["package"] = target
        all_segments.extend(segs)
        all_omitted.extend(omitted)

    pool = all_segments if all_segments else all_omitted
    if not pool:
        return {
            "package": pkg_candidates[0],
            "start": start,
            "end": end,
            "source": "",
            "segments": [],
            "omitted_segments": [],
            "candidates": events[:20],
        }

    selected = max(pool, key=lambda item: item["duration_seconds"])
    target = str(selected.get("package") or pkg_candidates[0])
    segments = [item for item in all_segments if item.get("package") == target]
    omitted_segments = [item for item in all_omitted if item.get("package") == target]

    return {
        "package": target,
        "start": selected["start"],
        "end": selected["end"],
        "source": selected.get("source", "event"),
        "start_evidence": selected.get("start_evidence", ""),
        "end_evidence": selected.get("end_evidence", ""),
        "end_reason": selected.get("end_reason", ""),
        "segments": segments,
        "omitted_segments": omitted_segments,
        "candidates": events[:20],
    }


def phase_windows(start: datetime | None, end: datetime | None, startup_s: int, exit_s: int) -> dict[str, dict[str, Any]]:
    if not start or not end or end <= start:
        return {}
    duration = int((end - start).total_seconds())
    startup_duration = min(startup_s, duration)
    remaining = max(0, duration - startup_duration)
    exit_duration = min(exit_s, remaining)
    stable_duration = max(0, duration - startup_duration - exit_duration)

    startup_end = start + timedelta(seconds=startup_duration)
    stable_end = startup_end + timedelta(seconds=stable_duration)
    return {
        "startup": {
            "start": fmt_time(start),
            "end": fmt_time(startup_end),
            "duration_seconds": startup_duration,
            "quality": "ok" if startup_duration > 0 else "missing",
        },
        "stable": {
            "start": fmt_time(startup_end),
            "end": fmt_time(stable_end),
            "duration_seconds": stable_duration,
            "quality": "ok" if stable_duration > 0 else "missing",
        },
        "exit": {
            "start": fmt_time(stable_end),
            "end": fmt_time(end),
            "duration_seconds": exit_duration,
            "quality": "ok" if exit_duration > 0 else "missing",
        },
    }


def build_time_windows(
    start: datetime | None,
    end: datetime | None,
    pre_s: int,
    post_s: int,
) -> dict[str, dict[str, Any]]:
    if not start or not end:
        return {}
    pre_start = start - timedelta(seconds=pre_s)
    post_end = end + timedelta(seconds=post_s)
    return {
        "T_pre": {
            "start": fmt_time(pre_start),
            "end": fmt_time(start),
            "duration_seconds": pre_s,
        },
        "T_game": {
            "start": fmt_time(start),
            "end": fmt_time(end),
            "duration_seconds": int((end - start).total_seconds()),
        },
        "T_post": {
            "start": fmt_time(end),
            "end": fmt_time(post_end),
            "duration_seconds": post_s,
        },
    }


def window_for(
    ts: datetime | None,
    start: datetime | None,
    end: datetime | None,
    pre: int,
    post: int,
) -> str | None:
    if not ts or not start or not end:
        return None
    if start - timedelta(seconds=pre) <= ts < start:
        return "T_pre"
    if start <= ts <= end:
        return "T_game"
    if end < ts <= end + timedelta(seconds=post):
        return "T_post"
    return None


def phase_for(
    ts: datetime | None,
    start: datetime | None,
    end: datetime | None,
    startup_s: int,
    exit_s: int,
) -> str | None:
    if not ts or not start or not end or ts < start or ts > end:
        return None
    phases = phase_windows(start, end, startup_s, exit_s)
    for name, info in phases.items():
        phase_start = parse_dt(info.get("start"))
        phase_end = parse_dt(info.get("end"))
        if phase_start and phase_end and phase_start <= ts <= phase_end:
            return name
    return None


def annotate_event_phases(
    events: list[dict[str, Any]],
    start: datetime | None,
    end: datetime | None,
    startup_s: int,
    exit_s: int,
) -> None:
    for event in events:
        event_ts = parse_dt(str(event.get("time", "")))
        phase = phase_for(event_ts, start, end, startup_s, exit_s)
        if phase:
            event["phase"] = phase


def compute_log_coverage(
    logs: dict[str, list[Path]],
    start: datetime | None,
    end: datetime | None,
    keys: tuple[str, ...] | None = None,
    include_missing: bool = True,
) -> tuple[dict[str, Any], list[str]]:
    coverage: dict[str, Any] = {}
    warnings: list[str] = []
    check_keys = keys or SCENE_LOG_KEYS
    for key in check_keys:
        files = logs.get(key, [])
        if not files:
            if include_missing:
                coverage[key] = {"status": "missing", "files": [], "covers_t_game": False}
                warnings.append(f"{key} 缺失，窗口内无法定责")
            continue
        first = None
        last = None
        for path in files:
            f, l = file_time_range(path)
            if f and (first is None or f < first):
                first = f
            if l and (last is None or l > last):
                last = l
        entry: dict[str, Any] = {
            "first": fmt_time(first),
            "last": fmt_time(last),
            "covers_t_game": None,
            "overlap_seconds": None,
        }
        if include_missing:
            entry["status"] = "ok"
            entry["files"] = [p.name for p in files]
        if start and end and first and last:
            overlap_start = max(first, start)
            overlap_end = min(last, end)
            overlap = (overlap_end - overlap_start).total_seconds()
            entry["overlap_seconds"] = int(overlap) if overlap > 0 else 0
            entry["covers_t_game"] = overlap > 0
            if overlap <= 0:
                if include_missing:
                    entry["status"] = "no_overlap"
                warnings.append(
                    f"{key} 时间范围 {entry['first']}~{entry['last']} 与 T_game 无重叠，窗口内无该日志数据"
                    if not include_missing
                    else f"{key} 时间范围 {entry['first']}~{entry['last']} 与 T_game 无重叠"
                )
        coverage[key] = entry
    return coverage, warnings


def serialize_game_window(game_window: dict[str, Any]) -> dict[str, Any]:
    start = game_window.get("start")
    end = game_window.get("end")
    duration = int((end - start).total_seconds()) if start and end else 0
    return {
        "start": fmt_time(start) if isinstance(start, datetime) else "",
        "end": fmt_time(end) if isinstance(end, datetime) else "",
        "duration_seconds": duration,
        "package": game_window.get("package", ""),
        "source": game_window.get("source", ""),
        "start_evidence": game_window.get("start_evidence", ""),
        "end_evidence": game_window.get("end_evidence", ""),
        "end_reason": game_window.get("end_reason", ""),
        "segments": [
            {
                "start": fmt_time(item.get("start")),
                "end": fmt_time(item.get("end")),
                "duration_seconds": item.get("duration_seconds"),
                "end_reason": item.get("end_reason", ""),
            }
            for item in game_window.get("segments", [])
            if isinstance(item.get("start"), datetime)
        ],
        "omitted_segments": [
            {
                "start": fmt_time(item.get("start")),
                "end": fmt_time(item.get("end")),
                "duration_seconds": item.get("duration_seconds"),
                "omit_reason": item.get("omit_reason", ""),
            }
            for item in game_window.get("omitted_segments", [])
            if isinstance(item.get("start"), datetime)
        ],
    }


def serialize_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in candidates:
        ts = item.get("time")
        out.append(
            {
                "time": fmt_time(ts) if isinstance(ts, datetime) else str(item.get("time_raw", "")),
                "kind": item.get("kind", ""),
                "package": item.get("package", ""),
                "component": item.get("component", ""),
                "raw_evidence": _event_evidence(item) if item.get("file") else item.get("raw", ""),
            }
        )
    return out


def analyze_time_window(
    log_path: Path,
    game_package: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    pre_minutes: int = 5,
    post_minutes: int = 3,
    min_segment_seconds: int = 120,
    merge_gap_seconds: int = 30,
    startup_seconds: int = 60,
    exit_seconds: int = 30,
) -> dict[str, Any]:
    logs = discover_logs(log_path)
    known = load_known_game_packages()
    pkg = (game_package or "").strip() or None
    game_window = find_game_window(
        logs["events_log"],
        known,
        pkg,
        start,
        end,
        min_segment_seconds,
        merge_gap_seconds,
    )

    warnings: list[str] = []
    notes: list[str] = []
    win_start = game_window.get("start")
    win_end = game_window.get("end")

    if not logs["events_log"] and not (start and end):
        inv = build_log_inventory(logs)
        return {
            "status": "failed",
            "game_name": "",
            "game_package": pkg or "",
            "game_window": {},
            "time_windows": {},
            "phases": {},
            "log_coverage": {},
            "log_inventory": inv,
            "candidates": [],
            "warnings": ["event log 缺失且未提供起止时间"],
            "notes": notes,
        }

    status = "ok"
    if not win_start or not win_end:
        status = "need_confirm" if game_window.get("candidates") else "failed"
        warnings.append("无法定位完整游戏窗口")
    elif win_end <= win_start:
        status = "failed"
        warnings.append("游戏窗口起止时间无效")

    pre_s = max(60, pre_minutes * 60)
    post_s = max(60, post_minutes * 60)
    time_windows = build_time_windows(win_start, win_end, pre_s, post_s)
    phases = phase_windows(win_start, win_end, startup_seconds, exit_seconds)
    if phases.get("stable", {}).get("quality") == "missing":
        notes.append("稳定阶段不足，下游不得高置信定责")

    log_coverage, cov_warnings = compute_log_coverage(logs, win_start, win_end, SCENE_LOG_KEYS)
    warnings.extend(cov_warnings)
    log_inventory = build_log_inventory(logs, log_coverage=log_coverage)

    resolved_pkg = game_window.get("package", "") or pkg or ""
    game_name = load_game_name(resolved_pkg)
    if pkg and not game_window.get("source"):
        notes.append("用户指定包名")

    return {
        "status": status,
        "game_name": game_name,
        "game_package": resolved_pkg,
        "game_window": serialize_game_window(game_window),
        "time_windows": time_windows,
        "phases": phases,
        "log_coverage": log_coverage,
        "log_inventory": log_inventory,
        "candidates": serialize_candidates(game_window.get("candidates", [])),
        "warnings": warnings,
        "notes": notes,
    }
