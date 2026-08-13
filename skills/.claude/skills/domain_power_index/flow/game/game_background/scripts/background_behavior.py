"""Event/Main/Sys 后台行为解析与聚合。

category: process_start/died, activity_resume/pause, service_*, broadcast,
alarm, job, wakelock, location, sensor, audio, network_scan, crash, gc, binder,
oem_freeze/unfreeze, game_download
relation: pre_existing | game_related | post_persistent（boost_ratio 阈值见 yaml）
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

# --- Event log 结构化正则 ---
EVENT_PROC_START_RE = re.compile(
    r"am_proc_start:\s*\[0,(?P<pid>\d+),(?P<uid>\d+),(?P<pkg>[^,\]]+)"
)
EVENT_PROC_DIED_RE = re.compile(
    r"am_proc_died:\s*\[0,(?P<pid>\d+),(?P<f2>[^,\]]+)(?:,(?P<f3>[^,\]]+))?"
)


def parse_proc_died_fields(match: re.Match[str]) -> tuple[int, str, int | None]:
    """兼容 [pid,uid,pkg] 与 [pid,pkg,uid] 两种 am_proc_died 格式。"""
    pid = int(match.group("pid"))
    f2 = match.group("f2").strip()
    f3 = match.group("f3")
    if f3 is None:
        return pid, f2, None
    f3 = f3.strip()
    if f2.isdigit() and ("." in f3 or f3.startswith("com")):
        return pid, f3, int(f2)
    uid = int(f3) if f3.isdigit() else None
    return pid, f2, uid
EVENT_PROC_BOUND_RE = re.compile(
    r"am_proc_bound:\s*\[0,(?P<pid>\d+),(?P<uid>\d+),(?P<pkg>[^,\]]+)"
)
EVENT_AM_KILL_RE = re.compile(
    r"am_kill:\s*\[0,(?P<pid>\d+),(?P<uid>\d+),(?P<pkg>[^,\]]+)"
)
EVENT_WM_RESUME_RE = re.compile(
    r"wm_set_resumed?_activity:\s*\[0,(?P<component>[^,\]]+)"
)
EVENT_WM_PAUSE_RE = re.compile(
    r"wm_set_paused?_activity:\s*\[0,(?P<component>[^,\]]+)"
)
EVENT_AM_CRASH_RE = re.compile(
    r"am_crash:\s*\[0,(?P<pid>\d+),(?P<uid>\d+),(?P<pkg>[^,\]]+)"
)
EVENT_AM_ANR_RE = re.compile(
    r"am_anr:\s*\[0,(?P<pid>\d+),(?P<uid>\d+),(?P<pkg>[^,\]]+)"
)
EVENT_AM_FREEZE_RE = re.compile(
    r"am_(?:freeze|compact|unfreeze):\s*\[0,(?P<pid>\d+),(?P<uid>\d+),(?P<pkg>[^,\]]+)"
)

PKG_CANDIDATE_RE = re.compile(r"\b([a-zA-Z][a-zA-Z0-9_]*(?:\.[a-zA-Z0-9_]+)+)\b")
INVALID_PKG_PREFIXES = (
    "android.",
    "java.",
    "javax.",
    "kotlin.",
    "dalvik.",
    "com.android.internal.",
)

OEM_PKG_ACTION_RE = re.compile(
    r"Usf_Hiber/[^\n]*?(?:freeze|unfreeze) uid:\s*\d+\s+(?P<pkg>com\.[a-zA-Z0-9_.:]+)"
)
OEM_PKG_NAME_RE = re.compile(
    r"Usf_Hiber/[^\n]*?pkgName=(?P<pkg>com\.[a-zA-Z0-9_.]+)"
)
OEM_STATE_MACHINE_RE = re.compile(
    r"Usf_Hiber/appStateMachine:.*?pkg=(?P<pkg>com\.[a-zA-Z0-9_.]+).*transition from Frozen to Running"
)
GAME_DOWNLOAD_RE = re.compile(r"DownloaderActivity|download.*resource", re.IGNORECASE)

WAKELOCK_ACQUIRE_RE = re.compile(
    r"WakeLock.*acquire.*?(?:from )?(?P<pkg>com\.[a-zA-Z0-9_.]+)|"
    r"acquireWakeLock.*?pkg=(?P<pkg2>com\.[a-zA-Z0-9_.]+)",
    re.IGNORECASE,
)
WAKELOCK_RELEASE_RE = re.compile(
    r"WakeLock.*release.*?(?:from )?(?P<pkg>com\.[a-zA-Z0-9_.]+)|"
    r"releaseWakeLock.*?pkg=(?P<pkg2>com\.[a-zA-Z0-9_.]+)",
    re.IGNORECASE,
)


def _read_ref_text(ref_dir: Path, name: str) -> str:
    path = ref_dir / name
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _yaml_float(text: str, key: str, default: float) -> float:
    m = re.search(rf"{re.escape(key)}:\s*(\d+(?:\.\d+)?)", text)
    return float(m.group(1)) if m else default


def _yaml_int(text: str, key: str, default: int) -> int:
    m = re.search(rf"{re.escape(key)}:\s*(\d+)", text)
    return int(m.group(1)) if m else default


def load_background_thresholds(ref_dir: Path) -> dict[str, Any]:
    text = _read_ref_text(ref_dir, "background-behavior-thresholds.yaml")
    br_suspect = 3.0
    br_abnormal = 5.0
    br_m = re.search(
        r"boost_ratio:\s*\n\s+suspect:\s*([\d.]+)\s*\n\s+abnormal:\s*([\d.]+)",
        text,
    )
    if br_m:
        br_suspect = float(br_m.group(1))
        br_abnormal = float(br_m.group(2))
    filter_cats = [
        "gc",
        "wakelock",
        "service_start",
        "service_bind",
    ]
    fc_m = re.search(
        r"game_self_filter_categories:\s*\n((?:\s+- [^\n]+\n)+)",
        text,
    )
    if fc_m:
        filter_cats = [
            line.strip().lstrip("- ").strip()
            for line in fc_m.group(1).splitlines()
            if line.strip()
        ]
    hc_m = re.search(
        r"high_confidence_requires:\s*\n\s+boost_ratio_min:\s*([\d.]+)\s*\n\s+t_game_count_min:\s*(\d+)",
        text,
    )
    hc_boost = float(hc_m.group(1)) if hc_m else 3.0
    hc_count = int(hc_m.group(2)) if hc_m else 5
    return {
        "min_rate_floor": _yaml_float(text, "min_rate_floor", 0.1),
        "boost_ratio_suspect": br_suspect,
        "boost_ratio_abnormal": br_abnormal,
        "wakelock_unreleased_seconds_suspect": _yaml_int(
            text, "wakelock_unreleased_seconds_suspect", 30
        ),
        "game_self_filter_categories": filter_cats,
        "high_confidence_boost_ratio_min": hc_boost,
        "high_confidence_t_game_count_min": hc_count,
    }


def load_background_system_packages(ref_dir: Path) -> dict[str, Any]:
    text = _read_ref_text(ref_dir, "background-system-packages.yaml")
    core: list[dict[str, str]] = []
    oem: list[str] = []
    hints: list[dict[str, str]] = []
    for m in re.finditer(
        r"- name:\s*(?P<name>[^\n]+)\n\s+match:\s*(?P<match>exact|prefix)",
        text,
    ):
        core.append({"name": m.group("name").strip().strip('"'), "match": m.group("match")})
    for m in re.finditer(r"oem_feature_packages:\s*\n((?:\s+- [^\n]+\n)+)", text):
        for line in m.group(1).splitlines():
            pkg = line.strip().lstrip("- ").strip()
            if pkg:
                oem.append(pkg)
    for m in re.finditer(
        r"- fragment:\s*\"(?P<frag>[^\"]+)\"\s*\n\s+package:\s*(?P<pkg>\S+)",
        text,
    ):
        hints.append({"fragment": m.group("frag"), "package": m.group("pkg")})
    return {"system_core_packages": core, "oem_feature_packages": oem, "process_name_hints": hints}


def component_to_package(component: str) -> str:
    comp = component.strip()
    if "/" in comp:
        return comp.split("/", 1)[0]
    if comp.startswith("."):
        return ""
    return comp


def is_valid_package_name(pkg: str) -> bool:
    if not pkg or pkg == "unknown_package":
        return False
    if any(pkg.startswith(p) for p in INVALID_PKG_PREFIXES):
        return False
    if "." not in pkg:
        return False
    if pkg.count(".") < 1:
        return False
    return True


def normalize_package(pkg: str) -> str:
    pkg = (pkg or "").strip().strip('"').strip("'")
    if pkg.startswith("{"):
        inner = re.search(r"\{([^/]+)", pkg)
        if inner:
            pkg = inner.group(1)
    if ":" in pkg:
        base, suffix = pkg.split(":", 1)
        if is_valid_package_name(base):
            return base
        if suffix and is_valid_package_name(suffix):
            return suffix
    return pkg


def match_package_rule(pkg: str, rules: list[dict[str, str]]) -> bool:
    for rule in rules:
        name = rule["name"]
        if rule["match"] == "prefix":
            if pkg.startswith(name):
                return True
        elif pkg == name:
            return True
    return False


def is_game_package(pkg: str, game_package: str) -> bool:
    if not game_package or not pkg:
        return False
    if pkg == game_package or pkg.startswith(f"{game_package}:"):
        return True
    if pkg.startswith(game_package + "."):
        return True
    return False


def extract_packages_from_line(line: str) -> list[str]:
    found: list[str] = []
    for m in PKG_CANDIDATE_RE.finditer(line):
        pkg = normalize_package(m.group(1))
        if is_valid_package_name(pkg):
            found.append(pkg)
    return found


def best_package_from_line(
    line: str,
    game_package: str,
    pid_map: dict[int, str],
    uid_map: dict[int, str],
    hints: list[dict[str, str]],
) -> tuple[str, str | None]:
    """返回 (package, pid_uid)。"""
    pid_uid = None
    for pattern in (
        EVENT_PROC_START_RE,
        EVENT_PROC_DIED_RE,
        EVENT_AM_KILL_RE,
        EVENT_AM_CRASH_RE,
        EVENT_AM_ANR_RE,
        EVENT_AM_FREEZE_RE,
    ):
        m = pattern.search(line)
        if m:
            if pattern is EVENT_PROC_DIED_RE:
                pid, pkg, uid = parse_proc_died_fields(m)
                pid_uid = f"pid={pid}" + (f" uid={uid}" if uid is not None else "")
            else:
                pkg = normalize_package(m.group("pkg"))
                pid = m.group("pid")
                uid = m.group("uid")
                pid_uid = f"pid={pid} uid={uid}"
            if is_valid_package_name(pkg):
                return pkg, pid_uid

    m = EVENT_WM_RESUME_RE.search(line) or EVENT_WM_PAUSE_RE.search(line)
    if m:
        pkg = component_to_package(m.group("component"))
        if is_valid_package_name(pkg):
            return pkg, pid_uid

    for pattern in (OEM_PKG_ACTION_RE, OEM_PKG_NAME_RE, OEM_STATE_MACHINE_RE):
        m = pattern.search(line)
        if m:
            return normalize_package(m.group("pkg")), pid_uid

    pid_m = re.search(r"\bpid[=:](\d+)\b", line, re.IGNORECASE)
    uid_m = re.search(r"\buid[=:](\d+)\b", line, re.IGNORECASE)
    if pid_m:
        pid = int(pid_m.group(1))
        if pid in pid_map:
            return pid_map[pid], f"pid={pid}" + (f" uid={uid_m.group(1)}" if uid_m else "")
    if uid_m:
        uid = int(uid_m.group(1))
        if uid in uid_map:
            return uid_map[uid], f"uid={uid}"

    candidates = extract_packages_from_line(line)
    if game_package:
        for pkg in candidates:
            if pkg == game_package:
                return pkg, pid_uid
    for pkg in sorted(candidates, key=len, reverse=True):
        if is_valid_package_name(pkg):
            return pkg, pid_uid

    for hint in hints:
        if hint["fragment"] in line:
            return hint["package"], pid_uid

    return "unknown_package", pid_uid


# Main/sys 文本行 category 检测（见 background_behavior.py TEXT_CATEGORY_RULES）
TEXT_CATEGORY_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("process_start", re.compile(r"(?:am_proc_start|Start proc)", re.IGNORECASE)),
    ("process_died", re.compile(r"(?:am_proc_died|am_kill|Killing)", re.IGNORECASE)),
    ("activity_resume", re.compile(r"(?:wm_set_resumed?_activity|wm_set_resume|Displayed)", re.IGNORECASE)),
    ("activity_pause", re.compile(r"(?:wm_set_paused?_activity|wm_set_pause)", re.IGNORECASE)),
    ("service_start", re.compile(r"startService|ActiveServices.*start", re.IGNORECASE)),
    ("service_bind", re.compile(r"bindService", re.IGNORECASE)),
    ("foreground_service", re.compile(r"foreground service|\bFGS\b|ServiceRecord.*fg", re.IGNORECASE)),
    ("broadcast", re.compile(r"BroadcastQueue|sendBroadcast|ReceiverList", re.IGNORECASE)),
    ("alarm", re.compile(r"AlarmManager|setExact|wakeup alarm", re.IGNORECASE)),
    ("job", re.compile(r"JobScheduler|JobServiceContext|WorkManager|SyncManager", re.IGNORECASE)),
    ("wakelock", re.compile(r"WakeLock|PowerManagerService|PARTIAL_WAKE_LOCK|wake_lock", re.IGNORECASE)),
    ("location", re.compile(r"LocationManagerService|Gnss|\bGPS\b", re.IGNORECASE)),
    ("sensor", re.compile(r"SensorService|registerListener|accelerometer|gyro", re.IGNORECASE)),
    ("audio", re.compile(r"AudioService|AudioFlinger|MediaSession|AudioTrack|startOutput", re.IGNORECASE)),
    ("network_scan", re.compile(r"WifiScanner|WifiConnectivityManager|BluetoothLeScanner|NetworkAgent", re.IGNORECASE)),
    ("crash", re.compile(r"(?:am_crash|am_anr|\bANR\b|FATAL EXCEPTION|Crash|tombstone)", re.IGNORECASE)),
    ("gc", re.compile(r"\bGC\b|gc_concurrent|Background concurrent copying GC", re.IGNORECASE)),
    ("binder", re.compile(r"Binder|binder transaction", re.IGNORECASE)),
    ("oem_unfreeze", re.compile(r"Usf_Hiber/[^\n]*\bunfreeze uid:", re.IGNORECASE)),
    ("oem_freeze", re.compile(r"Usf_Hiber/[^\n]*\bfreeze uid:|fastFreeze", re.IGNORECASE)),
    ("game_download", GAME_DOWNLOAD_RE),
]


def parse_event_background_line(line: str) -> tuple[str, str | None] | None:
    """解析 events_log 结构化行，返回 (category, pid_uid)。"""
    rules: list[tuple[str, re.Pattern[str]]] = [
        ("process_start", EVENT_PROC_START_RE),
        ("process_died", EVENT_PROC_DIED_RE),
        ("process_start", EVENT_PROC_BOUND_RE),
        ("process_died", EVENT_AM_KILL_RE),
        ("activity_resume", EVENT_WM_RESUME_RE),
        ("activity_pause", EVENT_WM_PAUSE_RE),
        ("crash", EVENT_AM_CRASH_RE),
        ("crash", EVENT_AM_ANR_RE),
    ]
    freeze_m = EVENT_AM_FREEZE_RE.search(line)
    if freeze_m:
        cat = "oem_unfreeze" if "unfreeze" in line else "oem_freeze"
        return cat, f"pid={freeze_m.group('pid')} uid={freeze_m.group('uid')}"
    for category, pattern in rules:
        m = pattern.search(line)
        if m:
            pid_uid = None
            if pattern is EVENT_PROC_DIED_RE:
                pid, _, uid = parse_proc_died_fields(m)
                pid_uid = f"pid={pid}" + (f" uid={uid}" if uid is not None else "")
            elif "pid" in m.groupdict() and m.group("pid"):
                uid_part = f" uid={m.group('uid')}" if m.groupdict().get("uid") else ""
                pid_uid = f"pid={m.group('pid')}{uid_part}"
            return category, pid_uid
    return None


def parse_text_background_line(line: str) -> str | None:
    for category, pattern in TEXT_CATEGORY_RULES:
        if pattern.search(line):
            return category
    return None


def process_name_matches_package(proc_name: str, pkg: str, hints: list[dict[str, str]]) -> bool:
    if not proc_name or not pkg:
        return False
    if pkg in proc_name or proc_name in pkg:
        return True
    tail = pkg.split(".")[-1]
    if len(tail) >= 3 and tail in proc_name:
        return True
    for hint in hints:
        if hint["package"] == pkg and hint["fragment"] in proc_name:
            return True
    return False


class BackgroundAnalyzer:
    def __init__(
        self,
        game_package: str,
        thresholds: dict[str, Any],
        system_cfg: dict[str, Any],
        baseline_rules: list[dict[str, str]],
    ) -> None:
        self.game_package = game_package or ""
        self.thresholds = thresholds
        self.system_core = system_cfg.get("system_core_packages", [])
        self.oem_features = set(system_cfg.get("oem_feature_packages", []))
        self.hints = system_cfg.get("process_name_hints", [])
        self.baseline_rules = baseline_rules
        self.pid_map: dict[int, str] = {}
        self.uid_map: dict[int, str] = {}
        self.pkg_windows: dict[str, dict[str, Counter[str]]] = defaultdict(
            lambda: defaultdict(Counter)
        )
        self.pkg_times: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
        self.wakelock_open: dict[tuple[str, str], datetime] = {}
        self.wakelock_duration: dict[str, float] = defaultdict(float)
        self.game_self_gc_filtered = False
        self.game_self_wakelock_filtered = False
        self.filtered_game_self_count = 0
        self.spm_events: list[dict[str, Any]] = []

    def register_pid_maps(self, line: str) -> None:
        m = EVENT_PROC_START_RE.search(line)
        if not m:
            return
        pkg = normalize_package(m.group("pkg"))
        if not is_valid_package_name(pkg):
            return
        pid = int(m.group("pid"))
        uid = int(m.group("uid"))
        self.pid_map[pid] = pkg
        self.uid_map[uid] = pkg

    def is_system_core(self, pkg: str) -> bool:
        return match_package_rule(pkg, self.system_core)

    def is_oem_feature(self, pkg: str) -> bool:
        return pkg in self.oem_features or any(pkg.startswith(o + ".") for o in self.oem_features)

    def should_skip_game_self(self, category: str, pkg: str) -> bool:
        if not is_game_package(pkg, self.game_package):
            return False
        if category in self.thresholds.get("game_self_filter_categories", []):
            if category == "gc":
                self.game_self_gc_filtered = True
            if category == "wakelock":
                self.game_self_wakelock_filtered = True
            self.filtered_game_self_count += 1
            return True
        return False

    def record(
        self,
        events: list[dict[str, Any]],
        add_event: Callable[[list[dict[str, Any]], dict[str, Any]], None],
        ts_raw: str | None,
        ts: datetime | None,
        window: str,
        source: str,
        category: str,
        pkg: str,
        pid_uid: str | None,
        line: str,
        path: Path,
        line_no: int,
        phase: str | None = None,
        duration_seconds: float | None = None,
    ) -> None:
        if not window or not category:
            return
        pkg = normalize_package(pkg)
        if self.should_skip_game_self(category, pkg):
            return

        self.pkg_windows[pkg][window][category] += 1
        if ts_raw:
            self.pkg_times[pkg][window].append(ts_raw)

        if category == "wakelock" and ts:
            self._track_wakelock(pkg, line, ts)

        item: dict[str, Any] = {
            "time": ts_raw or "",
            "window": window,
            "source": source,
            "category": category,
            "package_or_process": pkg if is_valid_package_name(pkg) else "unknown_package",
            "raw_evidence": f"{path.name}:{line_no}: {line.strip()[:220]}",
        }
        if pid_uid:
            item["pid_uid"] = pid_uid
        if phase:
            item["phase"] = phase
        if duration_seconds is not None:
            item["duration_seconds"] = round(duration_seconds, 2)
        add_event(events, item)

    def _track_wakelock(self, pkg: str, line: str, ts: datetime) -> None:
        key_tag = pkg
        if WAKELOCK_ACQUIRE_RE.search(line):
            self.wakelock_open[(pkg, key_tag)] = ts
        elif WAKELOCK_RELEASE_RE.search(line):
            opened = self.wakelock_open.pop((pkg, key_tag), None)
            if opened:
                self.wakelock_duration[pkg] += (ts - opened).total_seconds()

    def ingest_line(
        self,
        events: list[dict[str, Any]],
        add_event: Callable[[list[dict[str, Any]], dict[str, Any]], None],
        line: str,
        path: Path,
        line_no: int,
        source: str,
        ts_raw: str | None,
        ts: datetime | None,
        window: str | None,
        phase: str | None,
        extract_ts: Callable[[str], tuple[str | None, datetime | None]],
        window_for: Callable[..., str | None],
        start: datetime | None,
        end: datetime | None,
        pre_s: int,
        post_s: int,
    ) -> None:
        if source == "event":
            self.register_pid_maps(line)
            parsed = parse_event_background_line(line)
            if not parsed:
                return
            category, pid_uid = parsed
        else:
            category = parse_text_background_line(line)
            if not category:
                return
            pid_uid = None

        if not ts:
            ts_raw, ts = extract_ts(line)
        if not ts:
            return
        if not window:
            window = window_for(ts, start, end, pre_s, post_s)
        if not window:
            return

        pkg, resolved_pid_uid = best_package_from_line(
            line, self.game_package, self.pid_map, self.uid_map, self.hints
        )
        if pid_uid is None:
            pid_uid = resolved_pid_uid

        self.record(
            events,
            add_event,
            ts_raw,
            ts,
            window,
            source,
            category,
            pkg,
            pid_uid,
            line,
            path,
            line_no,
            phase,
        )

    def finalize(
        self,
        abnormal_processes: list[dict[str, Any]],
        pre_s: int,
        post_s: int,
        game_duration_s: float,
    ) -> dict[str, Any]:
        cpu_linked_packages = self._link_abnormal_processes(abnormal_processes)
        top = self._build_top_packages(cpu_linked_packages, pre_s, post_s, game_duration_s)
        return {
            "top_background_packages": top,
            "background_stats": {
                "total_packages": len(self.pkg_windows),
                "game_self_filtered_count": self.filtered_game_self_count,
            },
            "misidentification": {
                "game_self_gc_filtered": self.game_self_gc_filtered,
                "game_self_wakelock_filtered": self.game_self_wakelock_filtered,
                "boost_ratio_used_as_primary_sort": bool(top),
            },
        }

    def _link_abnormal_processes(self, abnormal_processes: list[dict[str, Any]]) -> set[str]:
        bg_packages = {
            pkg
            for pkg in self.pkg_windows
            if is_valid_package_name(pkg) and not is_game_package(pkg, self.game_package)
        }
        linked: set[str] = set()
        for ap in abnormal_processes:
            name = ap.get("name", "")
            for pkg in bg_packages:
                if process_name_matches_package(name, pkg, self.hints):
                    ap["related_background_behavior"] = True
                    linked.add(pkg)
                    break
        return linked

    def _build_top_packages(
        self,
        cpu_linked: set[str],
        pre_s: int,
        post_s: int,
        game_duration_s: float,
    ) -> list[dict[str, Any]]:
        min_floor = self.thresholds.get("min_rate_floor", 0.1)
        br_suspect = self.thresholds.get("boost_ratio_suspect", 3.0)
        br_abnormal = self.thresholds.get("boost_ratio_abnormal", 5.0)
        pre_min = max(pre_s / 60.0, 0.01)
        game_min = max(game_duration_s / 60.0, 0.01)
        post_min = max(post_s / 60.0, 0.01)

        rows: list[dict[str, Any]] = []
        for pkg, windows in self.pkg_windows.items():
            if not is_valid_package_name(pkg):
                continue
            if is_game_package(pkg, self.game_package):
                continue
            t_pre = sum(windows.get("T_pre", Counter()).values())
            t_game = sum(windows.get("T_game", Counter()).values())
            t_post = sum(windows.get("T_post", Counter()).values())
            if t_game == 0 and t_pre == 0 and t_post == 0:
                continue

            t_pre_rate = t_pre / pre_min
            t_game_rate = t_game / game_min
            boost_ratio = round(t_game_rate / max(t_pre_rate, min_floor), 2)

            categories = sorted(
                {cat for win_counts in windows.values() for cat in win_counts}
            )
            relation = "observe"
            if t_pre > 0 and t_game <= t_pre:
                relation = "pre_existing"
            elif t_game > 0 and (t_pre == 0 or boost_ratio >= br_suspect):
                relation = "game_related"
            if t_post > 0 and t_game > 0 and t_post >= t_game * 0.5:
                relation = "post_persistent"

            related_cpu = pkg in cpu_linked
            confidence = "low"
            priority = "observe"
            if relation == "game_related" and boost_ratio >= br_abnormal and related_cpu:
                confidence = "high"
                priority = "P0"
            elif relation == "game_related" and boost_ratio >= br_suspect:
                confidence = "medium"
                priority = "P1" if related_cpu else "P2"
            elif self.is_system_core(pkg) and relation == "pre_existing":
                priority = "observe"
                confidence = "low"

            wakelock_dur = round(self.wakelock_duration.get(pkg, 0.0), 1)
            rows.append(
                {
                    "package_or_process": pkg,
                    "boost_ratio": boost_ratio,
                    "t_pre_rate_per_min": round(t_pre_rate, 2),
                    "t_game_rate_per_min": round(t_game_rate, 2),
                    "t_post_rate_per_min": round(t_post / post_min, 2),
                    "t_pre_event_count": t_pre,
                    "t_game_event_count": t_game,
                    "t_post_event_count": t_post,
                    "categories": categories,
                    "relation": relation,
                    "related_cpu_usage": related_cpu,
                    "wakelock_total_duration_s": wakelock_dur if wakelock_dur > 0 else None,
                    "is_oem_feature": self.is_oem_feature(pkg),
                    "is_system_core": self.is_system_core(pkg),
                    "power_estimate_mws": None,
                    "power_estimate_method": "",
                    "confidence": confidence,
                    "priority": priority,
                    "high_confidence_candidate": (
                        relation == "game_related"
                        and related_cpu
                        and boost_ratio >= self.thresholds.get("high_confidence_boost_ratio_min", 3.0)
                        and t_game >= self.thresholds.get("high_confidence_t_game_count_min", 5)
                    ),
                }
            )

        rows.sort(
            key=lambda r: (
                -int(r.get("high_confidence_candidate", False)),
                -(r.get("boost_ratio") or 0),
                -(r.get("t_game_event_count") or 0),
            )
        )
        for idx, row in enumerate(rows[:20]):
            row["rank"] = idx + 1
        return rows[:20]


def parse_background_logs(
    event_files: list[Path],
    main_sys_files: list[Path],
    events: list[dict[str, Any]],
    add_event: Callable[[list[dict[str, Any]], dict[str, Any]], None],
    extract_ts: Callable[[str], tuple[str | None, datetime | None]],
    window_for: Callable[..., str | None],
    iter_lines: Callable[[Path], Any],
    start: datetime | None,
    end: datetime | None,
    pre_s: int,
    post_s: int,
    startup_s: int,
    exit_s: int,
    game_package: str,
    ref_dir: Path,
    baseline_rules: list[dict[str, str]],
    abnormal_processes: list[dict[str, Any]],
    phase_for: Callable[..., str | None] | None = None,
) -> dict[str, Any]:
    thresholds = load_background_thresholds(ref_dir)
    system_cfg = load_background_system_packages(ref_dir)
    analyzer = BackgroundAnalyzer(game_package, thresholds, system_cfg, baseline_rules)

    for path in event_files:
        for line_no, line in iter_lines(path):
            phase = None
            ts_raw, ts = extract_ts(line)
            if ts and phase_for and start and end:
                phase = phase_for(ts, start, end, startup_s, exit_s)
            analyzer.ingest_line(
                events,
                add_event,
                line,
                path,
                line_no,
                "event",
                ts_raw,
                ts,
                window_for(ts, start, end, pre_s, post_s) if ts else None,
                phase,
                extract_ts,
                window_for,
                start,
                end,
                pre_s,
                post_s,
            )

    for path in main_sys_files:
        source = "main" if "main" in path.name.lower() else "sys"
        for line_no, line in iter_lines(path):
            ts_raw, ts = extract_ts(line)
            phase = phase_for(ts, start, end, startup_s, exit_s) if ts and phase_for else None
            analyzer.ingest_line(
                events,
                add_event,
                line,
                path,
                line_no,
                source,
                ts_raw,
                ts,
                window_for(ts, start, end, pre_s, post_s) if ts else None,
                phase,
                extract_ts,
                window_for,
                start,
                end,
                pre_s,
                post_s,
            )

    game_duration_s = (end - start).total_seconds() if start and end else 0.0
    return analyzer.finalize(abnormal_processes, pre_s, post_s, game_duration_s)
