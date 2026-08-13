from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
_GB_SCRIPTS = _SCRIPT_DIR.parent / "game_background" / "scripts"
if str(_GB_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_GB_SCRIPTS))
from game_log_paths import add_log_path_argument, resolve_log_path  # noqa: E402
# scripts → game → flow → power → domain → analysis → …/analysis/base/lib
_LIB_DIR = Path(__file__).resolve().parents[5] / "base" / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))
from repo_paths import find_repo_root  # noqa: E402
from background_behavior import parse_background_logs  # noqa: E402
from display_brightness import parse_hwcomposer_brightness, parse_kernel_backlight  # noqa: E402
from brightness_summary_bridge import (  # noqa: E402
    enrich_brightness_stats,
    load_game_brightness_doc,
    brightness_analysis_notes,
    display_subsystem_from_brightness,
)
from game_power_report import generate_report  # noqa: E402
from cpu_thread_investigation_lib import (  # noqa: E402
    analyze_cpu_thread_findings,
    build_game_process_context,
    enrich_findings_with_logs,
    is_expected_game_thread,
)
from test_conditions_probe import probe_test_conditions, probe_volume_stats  # noqa: E402

_GTW_SCRIPTS = Path(__file__).resolve().parents[1] / "game_time_window" / "scripts"
if str(_GTW_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_GTW_SCRIPTS))
from game_time_window_lib import (  # noqa: E402
    FULL_COVERAGE_KEYS,
    MOBILE_CORE_LOG_KEYS,
    annotate_event_phases,
    build_log_inventory,
    compute_log_coverage,
    discover_logs,
    extract_ts,
    find_game_window,
    fmt_time,
    iter_lines,
    load_game_name,
    load_known_game_packages,
    parse_dt,
    phase_for,
    phase_windows,
    status_for,
    window_for,
)


K_START_RE = re.compile(r"\[K\]\[Perf\]\s+TRAN Perf Statistic start \((?P<ts>[^)]+)\)")
K_THREAD_RE = re.compile(
    r"\[K\]\s+(?P<usage>\d+)%\s+(?P<pid>\d+)\s+(?P<name>.+?)\s+"
    r"(?P<total_ns>\d+)\(ns\)\s+(?P<oom_adj>-?\d+)"
)
K_CPUS_RE = re.compile(r"\[K\]\s+Cpus Usage (?P<cpu_usages>.+)")
K_TOTAL_RE = re.compile(
    r"\[K\]\s+user\[(?P<user>\d+)\],system\[(?P<system>\d+)\],"
    r"iowait\[(?P<iowait>\d+)\],irq\[(?P<irq>\d+)\],idle\[(?P<idle>\d+)\]"
)
POWERHAL_CPU_RE = re.compile(r"libPowerHal: \[recordCPUFreqInfo\] set (?P<body>.+)")
CLUSTER_RE = re.compile(
    r"cluster\[(?P<cluster>\d+)\]\s+min\((?P<min_source>[^)]*)\):\s*"
    r"(?P<min_value>-?\d+)\s+max\((?P<max_source>[^)]*)\):\s*(?P<max_value>-?\d+)"
)
GPU_SOFT_RE = re.compile(
    r"libPowerHal: \[setGPUFreq\] Soft min/max = \((?P<soft_min>-?\d+),\s*(?P<soft_max>-?\d+)\); "
    r"Hard min/max = \((?P<hard_min>-?\d+),\s*(?P<hard_max>-?\d+)\)"
)
GPU_FINAL_RE = re.compile(
    r"libPowerHal: \[setGPUFreq\] final min/max = \((?P<final_min>-?\d+),\s*(?P<final_max>-?\d+)\)"
)
DVFSRC_RE = re.compile(r"libPowerHal: \[setDvfsrcDevFreqOpp\] opp:(?P<opp>\d+),\s*freq:(?P<freq>\d+)")
THERMALUX_CPU_RE = re.compile(
    r"ThermalEngine: \[thermalux\]\s+cpu:\s*(?P<cpu>\d+),\s*"
    r"thermal engine request frequency:\s*(?P<thermal_freq>-?\d+),\s*"
    r"thermalux request frequency:\s*(?P<thermalux_freq>-?\d+)"
)
BQP_RE = re.compile(
    r"BufferQueueProducer: \[(?P<layer>[^\]]+)\].*queueBuffer:\s+"
    r"fps=(?P<fps>[-\d.]+)\s+dur=(?P<dur>[-\d.]+)\s+max=(?P<max>[-\d.]+)\s+min=(?P<min>[-\d.]+)"
)


def _setup_utf8_stdio() -> None:
    for stream_name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def serialize_cpu_samples(
    samples: list[dict[str, Any]],
    start: datetime | None,
    end: datetime | None,
    startup_s: int,
    exit_s: int,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for idx, sample in enumerate(samples, start=1):
        total = sample.get("total") or {}
        idle = total.get("idle")
        cpus = sample.get("cpus_usage") or []
        if idle is not None:
            agg = round(100 - int(idle), 2)
        elif cpus:
            agg = round(sum(cpus) / len(cpus), 2)
        else:
            agg = None
        phase = sample.get("phase")
        if not phase:
            phase = phase_for(sample.get("dt"), start, end, startup_s, exit_s)
        threads = sorted(sample.get("threads") or [], key=lambda t: t.get("usage", 0), reverse=True)
        item = {
            "round": idx,
            "time": sample.get("time", ""),
            "window": sample.get("window", ""),
            "phase": phase,
            "cpus_usage": cpus,
            "total": total,
            "aggregate_usage_pct": agg,
            "threads": threads,
            "raw_evidence": sample.get("raw_evidence", ""),
        }
        if sample.get("cpus_usage_raw"):
            item["cpus_usage_raw"] = sample.get("cpus_usage_raw")
        threads_raw = sample.get("threads_raw")
        if isinstance(threads_raw, list) and threads_raw:
            item["threads_raw"] = list(threads_raw)
        raw_lines = sample.get("raw_lines")
        if isinstance(raw_lines, list) and raw_lines:
            item["raw_lines"] = list(raw_lines)
        out.append(item)
    return out


def cpu_samples_t_game_only(serialized: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """汇总/报告仅保留游戏时段 T_game 采样，并重编号 round。"""
    out = [dict(s) for s in serialized if s.get("window") == "T_game"]
    for idx, sample in enumerate(out, start=1):
        sample["round"] = idx
    return out


def _kernel_cpu_ref_dir(base: Path) -> Path:
    game_dir = base.parent if base.name == "scripts" else base
    return game_dir / "game_kernel_cpu" / "references"


def load_kernel_cpu_thresholds(base: Path) -> dict[str, Any]:
    path = _kernel_cpu_ref_dir(base) / "analysis-standards.yaml"
    text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
    return {
        "spike_pp": _yaml_int(text, "spike_usage_pp", 10),
        "single_shot_min_usage": _yaml_int(text, "single_shot_min_usage_pct", 10),
        "persistent_min_ratio": float(_yaml_nullable_float(text, "persistent_min_sample_ratio") or 0.4),
        "persistent_min_occurrence": _yaml_int(text, "persistent_min_occurrence", 3),
        "log_window_seconds": _yaml_int(text, "log_correlation_seconds", 10),
        "log_max_per_source": _yaml_int(text, "log_correlation_max_lines_per_source", 5),
    }


def build_cpu_thread_investigation(
    cpu_samples: list[dict[str, Any]],
    logs: dict[str, list[Path]],
    events: list[dict[str, Any]],
    game_package: str,
    baseline_rules: list[dict[str, str]],
    thresholds: dict[str, Any],
    game_thread_suffixes: list[str] | None = None,
) -> dict[str, Any]:
    game_ctx = build_game_process_context(events, game_package, game_thread_suffixes)
    base = analyze_cpu_thread_findings(
        cpu_samples,
        game_package,
        baseline_rules,
        game_ctx=game_ctx,
        is_expected_process=is_expected_process,
        parse_dt=parse_dt,
        spike_pp=int(thresholds.get("spike_pp", 10)),
        single_shot_min_usage=int(thresholds.get("single_shot_min_usage", 10)),
        persistent_min_ratio=float(thresholds.get("persistent_min_ratio", 0.4)),
        persistent_min_occurrence=int(thresholds.get("persistent_min_occurrence", 3)),
        continuous_n=int(thresholds.get("continuous_n", 2)),
    )
    enriched = enrich_findings_with_logs(
        base,
        logs,
        events,
        extract_ts=extract_ts,
        iter_lines=iter_lines,
        parse_dt=parse_dt,
        window_seconds=int(thresholds.get("log_window_seconds", 10)),
        max_per_source=int(thresholds.get("log_max_per_source", 5)),
    )
    enriched["game_process_context"] = game_ctx
    return enriched


def _baseline_ref_dirs(base: Path) -> list[Path]:
    if base.is_dir() and base.name == "references":
        return [base]
    game_dir = base.parent if base.name == "scripts" else base
    dirs: list[Path] = []
    gkc = game_dir / "game_kernel_cpu" / "references"
    legacy = game_dir / "references"
    if gkc.is_dir():
        dirs.append(gkc)
    if legacy.is_dir():
        dirs.append(legacy)
    return dirs


def _precondition_ref_dir(base: Path) -> Path:
    game_dir = base.parent if base.name == "scripts" else base
    gp = game_dir / "game_precondition" / "references"
    legacy = game_dir / "references"
    if gp.is_dir():
        return gp
    return legacy


def _background_ref_dir(base: Path) -> Path:
    game_dir = base.parent if base.name == "scripts" else base
    gb = game_dir / "game_background" / "references"
    legacy = game_dir / "references"
    if gb.is_dir():
        return gb
    return legacy


def _read_ref_text(base: Path, name: str) -> str:
    for ref_dir in _baseline_ref_dirs(base):
        path = ref_dir / name
        if path.exists():
            return path.read_text(encoding="utf-8", errors="replace")
    return ""


def _yaml_int(text: str, key: str, default: int) -> int:
    m = re.search(rf"{re.escape(key)}:\s*(\d+)", text)
    return int(m.group(1)) if m else default


def _yaml_nullable_float(text: str, key: str) -> float | None:
    m = re.search(rf"{re.escape(key)}:\s*(\S+)", text)
    if not m:
        return None
    val = m.group(1)
    if val in ("null", "~", ""):
        return None
    try:
        return float(val)
    except ValueError:
        return None


def load_baseline_processes(base: Path) -> dict[str, Any]:
    text = _read_ref_text(base, "baseline-processes.yaml")
    rules: list[dict[str, str]] = []
    for m in re.finditer(
        r"- name:\s*(?P<name>[^\n]+)\n\s+match:\s*(?P<match>exact|prefix)",
        text,
    ):
        rules.append({"name": m.group("name").strip().strip('"'), "match": m.group("match")})
    return {
        "baseline_fluctuation_pct": _yaml_int(text, "baseline_fluctuation_pct", 5),
        "continuous_sample_count": _yaml_int(text, "continuous_sample_count", 2),
        "persistent_min_sample_ratio": float(
            _yaml_nullable_float(text, "persistent_min_sample_ratio") or 0.4
        ),
        "persistent_min_occurrence": _yaml_int(text, "persistent_min_occurrence", 3),
        "common_processes": rules,
        "game_thread_suffixes": _yaml_string_list(text, "game_thread_suffixes"),
    }


def _yaml_string_list(text: str, key: str) -> list[str]:
    m = re.search(rf"{re.escape(key)}:\s*\n((?:\s+-\s+[^\n]+\n?)+)", text)
    if not m:
        return []
    return [
        line.strip().strip('"').strip("'")
        for line in re.findall(r"^\s+-\s+(.+)$", m.group(1), re.MULTILINE)
        if line.strip()
    ]


def load_baseline_cpu_cores(base: Path) -> dict[str, Any]:
    text = _read_ref_text(base, "baseline-cpu-cores.yaml")
    standards: list[dict[str, Any]] = []
    for block in re.split(r"\n\s*- id:\s*", text)[1:]:
        sid_m = re.match(r"(\S+)", block)
        if not sid_m:
            continue
        soc_m = re.search(r"soc_model:\s*(\S+)", block)
        pkg_m = re.search(r"game_package:\s*(\S+)", block)
        cores: list[dict[str, Any]] = []
        for cm in re.finditer(
            r"- core_id:\s*(\d+)\s*\n\s+standard_avg:\s*(\S+)\s*\n\s+standard_fluctuation_pp:\s*(\S+)",
            block,
        ):
            def _nf(v: str) -> float | None:
                return None if v in ("null", "~") else float(v)

            cores.append(
                {
                    "core_id": int(cm.group(1)),
                    "standard_avg": _nf(cm.group(2)),
                    "standard_fluctuation_pp": _nf(cm.group(3)),
                }
            )
        standards.append(
            {
                "id": sid_m.group(1),
                "soc_model": soc_m.group(1) if soc_m else "*",
                "game_package": pkg_m.group(1) if pkg_m else "*",
                "cores": cores,
            }
        )
    return {
        "default_fluctuation_pp_max": _yaml_int(text, "default_fluctuation_pp_max", 5),
        "default_avg_delta_pp_max": _yaml_int(text, "default_avg_delta_pp_max", 5),
        "default_fluctuation_delta_pp_max": _yaml_int(text, "default_fluctuation_delta_pp_max", 3),
        "min_samples_for_stats": _yaml_int(text, "min_samples_for_stats", 3),
        "platform_standards": standards,
    }


def match_baseline_process(name: str, rules: list[dict[str, str]]) -> bool:
    for rule in rules:
        rname = rule["name"]
        if rule["match"] == "prefix":
            if name.startswith(rname):
                return True
        elif name == rname:
            return True
    return False


def is_expected_process(name: str, game_package: str, baseline_rules: list[dict[str, str]]) -> bool:
    if game_package:
        if name == game_package or name.startswith(f"{game_package}:"):
            return True
        pkg_tail = game_package.split(".")[-1]
        if len(pkg_tail) >= 3 and (pkg_tail in name or name.endswith(pkg_tail)):
            return True
    return match_baseline_process(name, baseline_rules)


def _longest_consecutive_runs(indices: list[int]) -> int:
    if not indices:
        return 0
    best = 1
    cur = 1
    for i in range(1, len(indices)):
        if indices[i] == indices[i - 1] + 1:
            cur += 1
            best = max(best, cur)
        else:
            cur = 1
    return best


def _core_level(
    avg_usage: float,
    fluctuation_pp: float,
    standard_avg: float | None,
    standard_fluctuation_pp: float | None,
    avg_delta_pp: float | None,
    fluctuation_delta_pp: float | None,
    sample_count: int,
    min_samples: int,
    default_fluctuation_pp_max: int,
    default_avg_delta_pp_max: int,
    default_fluctuation_delta_pp_max: int,
    t_pre_avg: float | None,
) -> str:
    if sample_count < min_samples:
        return "unknown"
    if standard_avg is not None and avg_delta_pp is not None:
        if abs(avg_delta_pp) > 10:
            return "abnormal"
        if abs(avg_delta_pp) > default_avg_delta_pp_max:
            return "suspect"
    if standard_fluctuation_pp is not None and fluctuation_delta_pp is not None:
        if fluctuation_delta_pp > 5:
            return "abnormal"
        if fluctuation_delta_pp > default_fluctuation_delta_pp_max:
            return "suspect"
    if standard_avg is None and t_pre_avg is not None:
        if avg_usage - t_pre_avg > default_avg_delta_pp_max:
            return "suspect"
    if fluctuation_pp > default_fluctuation_pp_max:
        return "suspect"
    if standard_avg is not None or standard_fluctuation_pp is not None or t_pre_avg is not None:
        return "normal"
    return "unknown"


def pick_platform_standard(
    standards: list[dict[str, Any]], soc_model: str, game_package: str
) -> tuple[dict[str, Any] | None, str]:
    soc_model = soc_model or "*"
    game_package = game_package or "*"
    best_item: dict[str, Any] | None = None
    best_score = -1
    best_id = ""
    for item in standards:
        item_soc = item.get("soc_model", "*")
        item_pkg = item.get("game_package", "*")
        if item_soc != "*" and item_soc != soc_model:
            continue
        if item_pkg != "*" and item_pkg != game_package:
            continue
        score = 0
        if item_soc == soc_model:
            score += 2
        elif item_soc == "*":
            score += 1
        if item_pkg == game_package:
            score += 4
        elif item_pkg == "*":
            score += 2
        if score > best_score:
            best_score = score
            best_item = item
            best_id = str(item.get("id", ""))
    return best_item, best_id


def analyze_kernel_samples(
    samples: list[dict[str, Any]],
    game_package: str,
    baseline_processes: dict[str, Any],
    baseline_cpu: dict[str, Any],
    soc_model: str,
    startup_s: int,
    exit_s: int,
    start: datetime | None,
    end: datetime | None,
    game_ctx: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rules = baseline_processes.get("common_processes", [])
    fluctuation_pct = baseline_processes.get("baseline_fluctuation_pct", 5)
    continuous_n = baseline_processes.get("continuous_sample_count", 2)
    min_samples = baseline_cpu.get("min_samples_for_stats", 3)
    ctx = game_ctx or {"game_pids": [], "subprocess_suffixes": [], "packages": []}

    def _expected(name: str, pid: int | None) -> bool:
        return is_expected_game_thread(
            name, pid, game_package, rules, ctx, is_expected_process
        )

    game_samples = [s for s in samples if s.get("window") == "T_game"]
    stable_samples = [
        s
        for s in game_samples
        if phase_for(s.get("dt"), start, end, startup_s, exit_s) == "stable"
    ]
    phase_samples = stable_samples if len(stable_samples) >= min_samples else game_samples
    phase_label = "stable" if stable_samples and len(stable_samples) >= min_samples else (
        "T_game" if game_samples else "degraded"
    )
    pre_samples = [s for s in samples if s.get("window") == "T_pre"]

    total_samples = len(game_samples)
    abnormal_map: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "name": "",
            "pid": None,
            "usages": [],
            "sample_indices": [],
            "times": [],
        }
    )
    baseline_usage: dict[str, list[int]] = defaultdict(list)

    for idx, sample in enumerate(game_samples):
        for thread in sample.get("threads", []):
            name = thread.get("name", "")
            if not name:
                continue
            if _expected(name, thread.get("pid")):
                baseline_usage[name].append(int(thread.get("usage", 0)))
                continue
            entry = abnormal_map[name]
            entry["name"] = name
            entry["pid"] = thread.get("pid")
            usage = int(thread.get("usage", 0))
            entry["usages"].append(usage)
            entry["sample_indices"].append(idx)
            entry["times"].append(sample.get("time", ""))

    abnormal_processes: list[dict[str, Any]] = []
    for name, data in abnormal_map.items():
        occ = len(data["sample_indices"])
        if occ == 0:
            continue
        indices = sorted(set(data["sample_indices"]))
        longest = _longest_consecutive_runs(indices)
        abnormal_processes.append(
            {
                "name": name,
                "pid": data["pid"],
                "occurrence_count": occ,
                "total_samples": total_samples,
                "sample_ratio": round(occ / total_samples, 4) if total_samples else 0.0,
                "continuity": "continuous" if longest >= continuous_n else "transient",
                "longest_run": longest,
                "time_ranges": data["times"][:5],
                "avg_usage": round(sum(data["usages"]) / len(data["usages"]), 2),
                "max_usage": max(data["usages"]),
                "baseline_match": False,
                "related_background_behavior": False,
            }
        )
    abnormal_processes.sort(key=lambda x: (-x["sample_ratio"], -x["avg_usage"]))

    baseline_notes: list[str] = []
    for name, usages in baseline_usage.items():
        if len(usages) < 2:
            continue
        if _expected(name, None) and not match_baseline_process(name, rules):
            continue
        if max(usages) - min(usages) > fluctuation_pct:
            baseline_notes.append(
                f"基线进程 {name} 同场景 CPU 波动 {max(usages) - min(usages)}pp > {fluctuation_pct}pp"
            )

    core_series: dict[int, list[int]] = defaultdict(list)
    for sample in phase_samples:
        for core_id, val in enumerate(sample.get("cpus_usage", [])):
            core_series[core_id].append(int(val))
    pre_core_avg: dict[int, float] = {}
    for sample in pre_samples:
        for core_id, val in enumerate(sample.get("cpus_usage", [])):
            pre_core_avg.setdefault(core_id, [])
            pre_core_avg[core_id].append(int(val))
    pre_core_avg = {k: sum(v) / len(v) for k, v in pre_core_avg.items() if v}

    platform, platform_id = pick_platform_standard(
        baseline_cpu.get("platform_standards", []), soc_model, game_package
    )
    std_by_core = {
        int(c["core_id"]): c for c in (platform.get("cores", []) if platform else [])
    }
    has_platform_std = any(
        c.get("standard_avg") is not None or c.get("standard_fluctuation_pp") is not None
        for c in std_by_core.values()
    )

    cores_out: list[dict[str, Any]] = []
    abnormal_core_count = 0
    for core_id in range(8):
        values = core_series.get(core_id, [])
        sample_count = len(values)
        if sample_count:
            avg_u = sum(values) / sample_count
            min_u = min(values)
            max_u = max(values)
            fluc_pp = max_u - min_u
            fluc_rate = round(fluc_pp / avg_u * 100, 2) if avg_u > 0 else 0.0
        else:
            avg_u = min_u = max_u = fluc_pp = fluc_rate = 0.0

        std = std_by_core.get(core_id, {})
        standard_avg = std.get("standard_avg")
        standard_fluctuation_pp = std.get("standard_fluctuation_pp")
        avg_delta = round(avg_u - standard_avg, 2) if standard_avg is not None and sample_count else None
        fluc_delta = (
            round(fluc_pp - standard_fluctuation_pp, 2)
            if standard_fluctuation_pp is not None and sample_count
            else None
        )
        level = _core_level(
            avg_u,
            fluc_pp,
            standard_avg,
            standard_fluctuation_pp,
            avg_delta,
            fluc_delta,
            sample_count,
            min_samples,
            baseline_cpu.get("default_fluctuation_pp_max", 5),
            baseline_cpu.get("default_avg_delta_pp_max", 5),
            baseline_cpu.get("default_fluctuation_delta_pp_max", 3),
            pre_core_avg.get(core_id),
        )
        if level in ("suspect", "abnormal"):
            abnormal_core_count += 1
        cores_out.append(
            {
                "core_id": core_id,
                "sample_count": sample_count,
                "avg_usage": round(avg_u, 2),
                "min_usage": int(min_u),
                "max_usage": int(max_u),
                "fluctuation_pp": int(fluc_pp),
                "fluctuation_rate_pct": fluc_rate,
                "standard_avg": standard_avg,
                "standard_fluctuation_pp": standard_fluctuation_pp,
                "avg_delta_pp": avg_delta,
                "fluctuation_delta_pp": fluc_delta,
                "level": level,
            }
        )

    cpu_core_usage_stats = {
        "total_samples": len(phase_samples),
        "phase": phase_label,
        "platform_match_id": platform_id,
        "abnormal_core_count": abnormal_core_count,
        "cores": cores_out,
    }
    if not has_platform_std:
        baseline_notes.append("无平台各核标准（standard_avg 均为 null），仅使用同场景波动与 T_pre 对比兜底")

    return {
        "abnormal_processes": abnormal_processes,
        "cpu_core_usage_stats": cpu_core_usage_stats,
        "baseline_process_notes": baseline_notes,
    }


def add_event(events: list[dict[str, Any]], item: dict[str, Any]) -> None:
    item.setdefault("raw_evidence", "")
    events.append(item)


def parse_kernel(files: list[Path], events: list[dict[str, Any]], start, end, pre_s, post_s) -> dict[str, Any]:
    cpu_counter: Counter[str] = Counter()
    cpu_usage_values: list[int] = []
    game_cpu_usage_values: list[int] = []
    sample_count = 0
    samples: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for path in files:
        for line_no, line in iter_lines(path):
            m = K_START_RE.search(line)
            if m:
                _, outer_ts = extract_ts(line)
                ts = outer_ts or parse_dt(m.group("ts"))
                current = {
                    "time": fmt_time(ts),
                    "dt": ts,
                    "threads": [],
                    "threads_raw": [],
                    "raw_lines": [],
                    "cpus_usage_raw": None,
                    "file": str(path),
                    "line": line_no,
                }
                continue
            if current is None:
                continue
            mt = K_THREAD_RE.search(line)
            if mt:
                k_idx = line.find("[K]")
                raw_frag = line[k_idx:].rstrip() if k_idx >= 0 else line.strip()
                thread = {
                    "usage": int(mt.group("usage")),
                    "pid": int(mt.group("pid")),
                    "name": mt.group("name").strip(),
                    "total_ns": int(mt.group("total_ns")),
                    "oom_adj": int(mt.group("oom_adj")),
                    "raw": raw_frag,
                }
                current["threads"].append(thread)
                current["threads_raw"].append(raw_frag)
                current["raw_lines"].append(raw_frag)
                continue
            mc = K_CPUS_RE.search(line)
            if mc:
                values = [int(x) for x in re.findall(r"\[\s*(\d+)\]", mc.group("cpu_usages"))]
                current["cpus_usage"] = values
                k_idx = line.find("[K]")
                raw_frag = line[k_idx:].rstrip() if k_idx >= 0 else line.strip()
                current["cpus_usage_raw"] = raw_frag
                current["raw_lines"].append(raw_frag)
                continue
            mg = K_TOTAL_RE.search(line)
            if mg:
                current["total"] = {k: int(v) for k, v in mg.groupdict().items()}
                continue
            if "[K][Perf]" in line and "done" in line:
                w = window_for(current.get("dt"), start, end, pre_s, post_s)
                if w:
                    sample_count += 1
                    for thread in current.get("threads", []):
                        cpu_counter[thread["name"]] += thread["usage"]
                    cpu_usage_values.extend(current.get("cpus_usage", []))
                    if w == "T_game":
                        game_cpu_usage_values.extend(current.get("cpus_usage", []))
                    raw_ev = f"{Path(current['file']).name}:{current['line']}"
                    sample = {
                        "time": current["time"],
                        "dt": current.get("dt"),
                        "window": w,
                        "threads": list(current.get("threads", [])),
                        "threads_raw": list(current.get("threads_raw", [])),
                        "cpus_usage": list(current.get("cpus_usage", [])),
                        "cpus_usage_raw": current.get("cpus_usage_raw"),
                        "raw_lines": list(current.get("raw_lines", [])),
                        "total": current.get("total", {}),
                        "raw_evidence": raw_ev,
                    }
                    samples.append(sample)
                    add_event(
                        events,
                        {
                            "time": current["time"],
                            "window": w,
                            "source": "kernel",
                            "category": "kernel_cpu_sample",
                            "threads": list(current.get("threads", [])),
                            "cpus_usage": current.get("cpus_usage", []),
                            "total": current.get("total", {}),
                            "raw_evidence": raw_ev,
                        },
                    )
                current = None

    top_threads = [
        {"name": name, "total_usage_points": usage}
        for name, usage in cpu_counter.most_common(10)
    ]
    game_values = game_cpu_usage_values or cpu_usage_values
    return {
        "sample_count": sample_count,
        "samples": samples,
        "top_threads": top_threads,
        "avg_total_usage": round(sum(game_values) / len(game_values), 2) if game_values else 0,
        "max_total_usage": max(game_values) if game_values else 0,
    }


def parse_main_sys(files: list[Path], events: list[dict[str, Any]], start, end, pre_s, post_s, game_package: str) -> dict[str, Any]:
    powerhal_events = []
    fps_layers: dict[str, list[float]] = defaultdict(list)
    gpu_policy: dict[str, int | None] = {
        "soft_min": None,
        "soft_max": None,
        "hard_min": None,
        "hard_max": None,
        "final_min": None,
        "final_max": None,
    }
    dvfsrc_counter: Counter[str] = Counter()
    cluster_constraints: dict[str, dict[str, Any]] = {}
    thermalux_requests: Counter[str] = Counter()

    for path in files:
        source = "main" if "main" in path.name.lower() else "sys"
        for line_no, line in iter_lines(path):
            ts_raw, ts = extract_ts(line)
            w = window_for(ts, start, end, pre_s, post_s)
            if not w:
                continue

            cpu_m = POWERHAL_CPU_RE.search(line)
            if cpu_m:
                clusters = []
                for cm in CLUSTER_RE.finditer(cpu_m.group("body")):
                    info = {
                        "cluster": cm.group("cluster"),
                        "min_source": cm.group("min_source"),
                        "min_value": int(cm.group("min_value")),
                        "max_source": cm.group("max_source"),
                        "max_value": int(cm.group("max_value")),
                    }
                    clusters.append(info)
                    cluster_constraints[info["cluster"]] = info
                powerhal_events.append({"time": ts_raw, "clusters": clusters})
                add_event(events, event_base(ts_raw, w, source, "powerhal_cpu_freq", line, path, line_no) | {"clusters": clusters})
                continue

            gpu_m = GPU_SOFT_RE.search(line)
            if gpu_m:
                for key, value in gpu_m.groupdict().items():
                    gpu_policy[key] = int(value)
                add_event(events, event_base(ts_raw, w, source, "gpu_freq_policy", line, path, line_no) | {"policy": dict(gpu_policy)})
                continue

            gpu_f = GPU_FINAL_RE.search(line)
            if gpu_f:
                for key, value in gpu_f.groupdict().items():
                    gpu_policy[key] = int(value)
                add_event(events, event_base(ts_raw, w, source, "gpu_freq_policy", line, path, line_no) | {"policy": dict(gpu_policy)})
                continue

            dv = DVFSRC_RE.search(line)
            if dv:
                key = f"opp{dv.group('opp')}_{dv.group('freq')}"
                dvfsrc_counter[key] += 1
                add_event(
                    events,
                    event_base(ts_raw, w, source, "dvfsrc_opp", line, path, line_no)
                    | {"opp": int(dv.group("opp")), "freq": int(dv.group("freq"))},
                )
                continue

            thermalux = THERMALUX_CPU_RE.search(line)
            if thermalux:
                item = {
                    "cpu": int(thermalux.group("cpu")),
                    "thermal_engine_request_frequency": int(thermalux.group("thermal_freq")),
                    "thermalux_request_frequency": int(thermalux.group("thermalux_freq")),
                }
                key = (
                    f"cpu{item['cpu']}_thermal_{item['thermal_engine_request_frequency']}"
                    f"_thermalux_{item['thermalux_request_frequency']}"
                )
                thermalux_requests[key] += 1
                add_event(events, event_base(ts_raw, w, source, "thermalux_cpu_request", line, path, line_no) | item)
                continue

            bq = BQP_RE.search(line)
            if bq:
                layer = bq.group("layer")
                fps = safe_float(bq.group("fps"))
                fps_layers[layer].append(fps)
                add_event(
                    events,
                    event_base(ts_raw, w, source, "frame_rate", line, path, line_no)
                    | {
                        "layer": layer,
                        "layer_type": classify_layer(layer, game_package),
                        "fps": fps,
                        "dur": safe_float(bq.group("dur")),
                        "max": safe_float(bq.group("max")),
                        "min": safe_float(bq.group("min")),
                    },
                )
                continue

    return {
        "cluster_constraints": cluster_constraints,
        "gpu_policy": gpu_policy,
        "dvfsrc": dvfsrc_counter,
        "thermalux_requests": thermalux_requests,
        "fps_layers": summarize_layers(fps_layers, game_package),
        "powerhal_event_count": len(powerhal_events),
    }


def event_base(ts_raw: str | None, window: str, source: str, category: str, line: str, path: Path, line_no: int) -> dict[str, Any]:
    return {
        "time": ts_raw or "",
        "window": window,
        "source": source,
        "category": category,
        "raw_evidence": f"{path.name}:{line_no}: {line.strip()[:220]}",
    }


def safe_float(v: str) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def classify_layer(layer: str, game_package: str) -> str:
    if game_package and game_package in layer:
        return "main_app_layer"
    if any(key in layer for key in ("StatusBar", "NotificationShade", "Taskbar", "SmartPanel")):
        return "system_ui_layer"
    if any(key in layer for key in ("FramebufferSurface", "SurfaceView", "Dim Layer")):
        return "composition_layer"
    return "unknown_layer"


def summarize_layers(layers: dict[str, list[float]], game_package: str) -> dict[str, Any]:
    main = {}
    system = []
    composition = []
    unknown = []
    for layer, values in layers.items():
        if not values:
            continue
        item = {
            "layer": layer,
            "avg_fps": round(sum(values) / len(values), 2),
            "min_fps": min(values),
            "max_fps": max(values),
            "sample_count": len(values),
        }
        kind = classify_layer(layer, game_package)
        if kind == "main_app_layer" and not main:
            main = item | {
                "low_fps_sample_count": sum(1 for v in values if v < 25),
                "jank_like_sample_count": sum(1 for v in values if v < 15),
            }
        elif kind == "system_ui_layer":
            system.append(item)
        elif kind == "composition_layer":
            composition.append(item)
        else:
            unknown.append(layer)
    system.sort(key=lambda x: x["sample_count"], reverse=True)
    composition.sort(key=lambda x: x["sample_count"], reverse=True)
    return {
        "main_app_layer": main,
        "system_layers_top": system[:5],
        "composition_layers": composition[:5],
        "unknown_candidate_layers": unknown[:20],
    }


def _build_subsystems(
    logs: dict[str, list[Path]],
    kernel_summary: dict[str, Any],
    brightness_summary: dict[str, Any],
) -> dict[str, Any]:
    display_level = "unknown"
    display_confidence = "low"
    display_summary = ""
    display_evidence: list[str] = []
    bw = brightness_summary.get("game_window", {})
    baseline = brightness_summary.get("baseline_before_game") or {}
    coverage = brightness_summary.get("coverage", "missing")
    if coverage == "ok":
        if bw.get("changed"):
            display_level = "suspect"
            display_summary = (
                f"T_game 背光变化 level {bw.get('level_min')}~{bw.get('level_max')}，"
                f"基线={baseline.get('level')}"
            )
        else:
            display_level = "normal"
            display_summary = f"T_game 背光恒定 level={bw.get('start_level')}，基线={baseline.get('level')}"
        display_confidence = "medium"
    elif coverage == "partial":
        display_level = "unknown"
        display_summary = "kernel lcm 背光部分覆盖，见 brightness_stats.notes"
    display_evidence.extend(brightness_summary.get("notes", []))
    ba_display = display_subsystem_from_brightness(brightness_summary)
    if ba_display:
        display_level = ba_display.get("level", display_level)
        display_confidence = ba_display.get("confidence", display_confidence)
        if ba_display.get("summary"):
            display_summary = ba_display["summary"]
        display_evidence.extend(ba_display.get("evidence", []))

    return {
        "ap": {
            "level": "unknown" if not logs["kernel_log"] else "suspect",
            "confidence": "low",
            "summary": "",
            "evidence": [],
        },
        "display": {
            "level": display_level,
            "confidence": display_confidence,
            "summary": display_summary,
            "evidence": display_evidence,
        },
        "audio": {"level": "unknown", "confidence": "low", "summary": "", "evidence": []},
        "rf": {"level": "unknown", "confidence": "low", "summary": "", "evidence": []},
        "others": {"level": "unknown", "confidence": "low", "summary": "", "evidence": []},
    }


def build_summary(
    log_path: Path,
    out_dir: Path,
    logs: dict[str, list[Path]],
    game_window: dict[str, Any],
    kernel_summary: dict[str, Any],
    main_summary: dict[str, Any],
    background_summary: dict[str, Any],
    brightness_summary: dict[str, Any],
    events: list[dict[str, Any]],
    pre_s: int,
    post_s: int,
    startup_s: int,
    exit_s: int,
    min_segment_seconds: int,
    merge_gap_seconds: int,
    notes: list[str],
    test_conditions: dict[str, Any] | None = None,
    volume_stats: dict[str, Any] | None = None,
    game_name: str = "",
    cpu_thread_investigation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    all_missing = [key for key, files in logs.items() if not files]
    log_inventory = build_log_inventory(logs)
    missing = list(log_inventory.get("missing_for_report") or [])
    start = game_window.get("start")
    end = game_window.get("end")
    status = "complete"
    blocked_reason = ""
    if log_inventory.get("no_logs"):
        status = "blocked"
        blocked_reason = "无 mobile 日志且无 bugreport，无法分析"
    elif not start or not end:
        status = "blocked"
        blocked_reason = "无法定位完整游戏窗口；请提供游戏包名和测试起止时间"
    elif log_inventory.get("incomplete") or missing:
        status = "partial"

    top_background = background_summary.get("top_background_packages", [])
    bg_mis = background_summary.get("misidentification", {})

    clusters = [
        {
            "name": f"cluster{cluster}",
            "min_constraint": data.get("min_value"),
            "max_constraint": data.get("max_value"),
            "min_source": data.get("min_source"),
            "max_source": data.get("max_source"),
            "constraint_duration_seconds": 0,
            "constraint_change_count": 1,
            "min_freq": 0,
            "max_freq": 0,
            "avg_freq": 0,
            "top_freq_ratio": 0,
            "high_freq_duration_seconds": 0,
            "freq_switch_count": 0,
        }
        for cluster, data in sorted(main_summary.get("cluster_constraints", {}).items())
    ]

    return {
        "skill": "flow_power_game",
        "status": status,
        "blocked_reason": blocked_reason,
        "log_path": str(log_path),
        "analysis_meta": {
            "analysis_time": datetime.now().isoformat(timespec="seconds"),
            "device_model": "",
            "soc_model": "",
            "build_version": "",
            "game_package": game_window.get("package", ""),
            "game_pid": None,
            "analyst_note": "",
        },
        "log_availability": {key: status_for(files) for key, files in logs.items()},
        "log_inventory": log_inventory,
        "game_window": {
            "game_name": game_name,
            "package": game_window.get("package", ""),
            "start": fmt_time(start),
            "end": fmt_time(end),
            "duration_seconds": int((end - start).total_seconds()) if start and end else 0,
            "source": game_window.get("source", ""),
            "start_evidence": game_window.get("start_evidence", ""),
            "end_evidence": game_window.get("end_evidence", ""),
            "end_reason": game_window.get("end_reason", ""),
            "min_segment_seconds": min_segment_seconds,
            "merge_gap_seconds": merge_gap_seconds,
            "segments": [
                {
                    "start": fmt_time(item.get("start")),
                    "end": fmt_time(item.get("end")),
                    "duration_seconds": item.get("duration_seconds", 0),
                    "source": item.get("source", ""),
                    "end_reason": item.get("end_reason", ""),
                    "start_evidence": item.get("start_evidence", ""),
                    "end_evidence": item.get("end_evidence", ""),
                }
                for item in game_window.get("segments", [])
            ],
            "omitted_segments": [
                {
                    "start": fmt_time(item.get("start")),
                    "end": fmt_time(item.get("end")),
                    "duration_seconds": item.get("duration_seconds", 0),
                    "omit_reason": item.get("omit_reason", ""),
                    "end_reason": item.get("end_reason", ""),
                }
                for item in game_window.get("omitted_segments", [])
            ],
        },
        "time_windows": {
            "T_pre": {"start": fmt_time(start - timedelta(seconds=pre_s)) if start else "", "end": fmt_time(start), "duration_seconds": pre_s, "quality": "default"},
            "T_game": {"start": fmt_time(start), "end": fmt_time(end), "duration_seconds": int((end - start).total_seconds()) if start and end else 0, "quality": "ok" if start and end else "partial"},
            "T_post": {"start": fmt_time(end), "end": fmt_time(end + timedelta(seconds=post_s)) if end else "", "duration_seconds": post_s, "quality": "default"},
            "phases": phase_windows(start, end, startup_s, exit_s),
        },
        "test_conditions": test_conditions
        or {"completeness": "poor", "missing_items": ["manual_test_conditions"], "logger_state": "", "tags": []},
        "subsystems": _build_subsystems(logs, kernel_summary, brightness_summary),
        "comparison_outputs": {
            "timeseries_file": str(out_dir / "game_power_timeseries.jsonl"),
            "summary_file": str(out_dir / "game_power_compare_summary.json"),
            "sample_interval_seconds": 10,
            "background_stats": background_summary.get("background_stats", {}),
            "thread_baseline": kernel_summary.get("top_threads", []),
            "cpu_usage_trend": {
                "avg_total_usage": kernel_summary.get("avg_total_usage", 0),
                "max_total_usage": kernel_summary.get("max_total_usage", 0),
                "trend": "unknown",
            },
            "cpu_core_usage_stats": kernel_summary.get("cpu_core_usage_stats", {}),
            "cpu_samples": cpu_samples_t_game_only(
                serialize_cpu_samples(
                    kernel_summary.get("samples", []),
                    start,
                    end,
                    startup_s,
                    exit_s,
                )
            ),
            "cpu_frequency_stats": {
                "clusters": clusters,
                "gpu_frequency_policy": main_summary.get("gpu_policy", {}),
                "dvfsrc_opp_stats": [
                    {"key": key, "count": count} for key, count in main_summary.get("dvfsrc", Counter()).most_common()
                ],
                "thermalux_cpu_requests": [
                    {"key": key, "count": count}
                    for key, count in main_summary.get("thermalux_requests", Counter()).most_common()
                ],
                "policy_findings": [],
            },
            "fpsgo_stats": {"available": bool(logs["ged_fps_log"]), "target_fps": 0, "avg_actual_fps": 0, "boost_events": 0, "scheduler_events": 0, "findings": []},
            "frame_rate_stats": main_summary.get("fps_layers", {}),
            "brightness_stats": brightness_summary,
            "volume_stats": volume_stats or {},
            "cpu_thread_investigation": cpu_thread_investigation or {},
        },
        "power_summary": {"estimation_method": "none", "confidence": "N/A", "delta_power_estimate_mw": None, "battery_impact_estimate_min": None, "battery_capacity_mah_assumed": None},
        "power_buckets": {},
        "mtk_specific": {
            "fpsgo": {"available": bool(logs["ged_fps_log"]), "false_boost_count": 0, "boost_events": 0, "gpu_high_freq_pct": None},
            "spm": {"available": bool(logs["spm_log"]), "wakeup_rate_per_min_game": None, "wakeup_rate_per_min_pre": None, "c2_deep_idle_pct_game": None, "top_wakeup_irq": ""},
            "thermal": {"available": bool(logs["thermal_log"]), "throttle_count": 0, "max_cpu_temp_celsius": None, "avg_cpu_temp_game_celsius": None},
            "dram": {"available": bool(logs["dramc_log"]), "high_freq_pct_game": None, "self_refresh_pct_game": None},
            "pmic": {"available": bool(logs["pmic_log"]), "rails": []},
        },
        "top_background_packages": top_background,
        "abnormal_processes": kernel_summary.get("abnormal_processes", []),
        "top_causes": [],
        "optimization_suggestions": [],
        "misidentification_checks": {
            "game_self_gc_filtered": bg_mis.get("game_self_gc_filtered", False),
            "game_self_wakelock_filtered": bg_mis.get("game_self_wakelock_filtered", False),
            "boost_ratio_used_as_primary_sort": bg_mis.get("boost_ratio_used_as_primary_sort", False),
            "fpsgo_boost_distinguished_from_false": False,
            "main_app_fps_distinguished_from_system_layers": bool(main_summary.get("fps_layers", {}).get("main_app_layer")),
            "spm_wakeup_source_identified_to_irq": False,
            "thermal_traced_to_upstream_load": False,
            "missing_logs_noted_in_report": bool(missing),
        },
        "missing_logs": missing,
        "missing_optional_logs": list(log_inventory.get("optional_missing") or [])
        or [k for k in all_missing if k not in MOBILE_CORE_LOG_KEYS and k != "bugreport"],
        "notes": notes,
    }


def write_outputs(events: list[dict[str, Any]], summary: dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    events.sort(key=lambda e: e.get("time", ""))
    with (out_dir / "game_power_timeseries.jsonl").open("w", encoding="utf-8") as fh:
        for item in events:
            fh.write(json.dumps(item, ensure_ascii=False, default=str) + "\n")
    (out_dir / "game_power_compare_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )


def ensure_kernel_time_converted(log_path: Path) -> list[str]:
    """若存在 kernel_log + events_log 且无 linli_666，自动调用 base_mtk_kernellog_convert。"""
    notes: list[str] = []
    kernel_raw: list[Path] = []
    has_events = False
    for root, _, files in os.walk(log_path):
        for name in files:
            n = name.lower()
            if "linli_666" in n:
                return notes
            if re.match(r"kernel_log_[a-z0-9_]+", name, re.I) and "linli_666" not in n:
                kernel_raw.append(Path(root) / name)
            if re.match(r"events_log_[a-z0-9_]+", name, re.I):
                has_events = True
    if not kernel_raw or not has_events:
        return notes
    convert_script = (
        Path(__file__).resolve().parents[5]
        / "base"
        / "mtk_kernellog_convert"
        / "scripts"
        / "time_convert.py"
    )
    if not convert_script.exists():
        notes.append("未找到 mtk_kernellog_convert/time_convert.py，跳过 kernel 时间转换")
        return notes
    import subprocess

    try:
        subprocess.run(
            [sys.executable, str(convert_script), str(log_path)],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        notes.append("已自动执行 base_mtk_kernellog_convert 生成 *_linli_666.txt")
    except subprocess.CalledProcessError as exc:
        notes.append(f"kernel 时间转换失败: {(exc.stderr or exc.stdout or '').strip()[:200]}")
    return notes


def default_output_dir(log_path: Path) -> Path:
    parts = list(log_path.resolve().parts)
    lower = [p.lower() for p in parts]
    if "converted" in lower:
        idx = lower.index("converted")
        return Path(*parts[:idx]) / "analysis"
    return log_path / "analysis"


def _load_saved_time_window(out_dir: Path) -> dict[str, Any] | None:
    path = out_dir / "game_time_window.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MTK 游戏功耗日志解析器")
    add_log_path_argument(parser)
    parser.add_argument("--output-dir", default="", help="输出 analysis 目录，默认自动推断")
    parser.add_argument("--game-package", default="", help="游戏包名；无法自动识别时必填")
    parser.add_argument("--start", default="", help="游戏开始时间，格式 YYYY-MM-DD HH:MM:SS 或 MM-DD HH:MM:SS")
    parser.add_argument("--end", default="", help="游戏结束时间，格式 YYYY-MM-DD HH:MM:SS 或 MM-DD HH:MM:SS")
    parser.add_argument("--pre-minutes", type=int, default=5, help="T_pre 分钟数，默认 5")
    parser.add_argument("--post-minutes", type=int, default=3, help="T_post 分钟数，默认 3")
    parser.add_argument("--min-segment-seconds", type=int, default=120, help="自动识别时忽略小于该时长的游戏片段，默认 120")
    parser.add_argument("--merge-gap-seconds", type=int, default=30, help="同一游戏前台短暂中断合并阈值，默认 30")
    parser.add_argument("--startup-seconds", type=int, default=60, help="T_game 启动阶段时长，默认 60")
    parser.add_argument("--exit-seconds", type=int, default=30, help="T_game 退出阶段时长，默认 30")
    parser.add_argument("--soc-model", default="", help="SoC 型号，用于匹配 baseline-cpu-cores 平台标准")
    return parser


def main(argv: list[str] | None = None) -> int:
    _setup_utf8_stdio()
    args = build_parser().parse_args(argv)
    log_path = resolve_log_path(args.log_path)
    if not log_path.is_dir():
        print(f"日志目录不存在或不可读：{log_path}", file=sys.stderr)
        return 2

    script_dir = Path(__file__).resolve().parent
    out_dir = Path(args.output_dir).resolve() if args.output_dir else default_output_dir(log_path)
    notes: list[str] = []
    notes.extend(ensure_kernel_time_converted(log_path))
    logs = discover_logs(log_path)
    known_packages = load_known_game_packages()
    start = parse_dt(args.start)
    end = parse_dt(args.end)
    saved_game_name = ""
    if not args.start and not args.end:
        tw_saved = _load_saved_time_window(out_dir)
        if tw_saved and tw_saved.get("status") in ("ok", "need_confirm"):
            gw_saved = tw_saved.get("game_window") or {}
            s_saved = parse_dt(gw_saved.get("start"))
            e_saved = parse_dt(gw_saved.get("end"))
            if s_saved and e_saved and e_saved > s_saved:
                start, end = s_saved, e_saved
                if not args.game_package.strip():
                    args.game_package = (
                        str(tw_saved.get("game_package") or gw_saved.get("package") or "")
                    )
                saved_game_name = str(tw_saved.get("game_name") or "")
                notes.append("复用 analysis/game_time_window.json 时间窗")
    pre_s = max(60, int(args.pre_minutes) * 60)
    post_s = max(60, int(args.post_minutes) * 60)
    min_segment_s = max(0, int(args.min_segment_seconds))
    merge_gap_s = max(0, int(args.merge_gap_seconds))
    startup_s = max(0, int(args.startup_seconds))
    exit_s = max(0, int(args.exit_seconds))

    game_window = find_game_window(
        logs["events_log"],
        known_packages,
        args.game_package.strip() or None,
        start,
        end,
        min_segment_s,
        merge_gap_s,
    )
    events: list[dict[str, Any]] = []

    if not game_window.get("start") or not game_window.get("end"):
        notes.append("无法定位完整游戏窗口；仅输出日志可用性和候选事件")
        for cand in game_window.get("candidates", []):
            add_event(
                events,
                {
                    "time": cand.get("time_raw", ""),
                    "window": "unknown",
                    "source": "event",
                    "category": f"candidate_{cand.get('kind', '')}",
                    "package_or_process": cand.get("package", ""),
                    "raw_evidence": cand.get("raw", ""),
                },
            )

    kernel_summary = parse_kernel(
        logs["kernel_log"], events, game_window.get("start"), game_window.get("end"), pre_s, post_s
    )
    baseline_processes = load_baseline_processes(script_dir)
    game_pkg = game_window.get("package", "")
    game_ctx_partial = build_game_process_context(
        [], game_pkg, baseline_processes.get("game_thread_suffixes")
    )
    kernel_analysis = analyze_kernel_samples(
        kernel_summary.get("samples", []),
        game_pkg,
        baseline_processes,
        load_baseline_cpu_cores(script_dir),
        args.soc_model.strip(),
        startup_s,
        exit_s,
        game_window.get("start"),
        game_window.get("end"),
        game_ctx=game_ctx_partial,
    )
    kernel_summary.update(kernel_analysis)
    main_summary = parse_main_sys(
        logs["main_log"] + logs["sys_log"],
        events,
        game_window.get("start"),
        game_window.get("end"),
        pre_s,
        post_s,
        game_window.get("package", ""),
    )
    background_summary = parse_background_logs(
        logs["events_log"],
        logs["main_log"] + logs["sys_log"],
        events,
        add_event,
        extract_ts,
        window_for,
        iter_lines,
        game_window.get("start"),
        game_window.get("end"),
        pre_s,
        post_s,
        startup_s,
        exit_s,
        game_window.get("package", ""),
        _background_ref_dir(script_dir),
        baseline_processes.get("common_processes", []),
        kernel_summary.get("abnormal_processes", []),
        phase_for,
    )
    brightness_summary = parse_kernel_backlight(
        logs["kernel_log"],
        events,
        add_event,
        extract_ts,
        window_for,
        iter_lines,
        fmt_time,
        game_window.get("start"),
        game_window.get("end"),
        pre_s,
        post_s,
    )
    brightness_summary["hwcomposer"] = parse_hwcomposer_brightness(
        logs["main_log"] + logs["sys_log"],
        events,
        add_event,
        extract_ts,
        window_for,
        iter_lines,
        game_window.get("start"),
        game_window.get("end"),
        pre_s,
        post_s,
    )
    notes.extend(brightness_summary.get("notes", []))
    notes.extend(brightness_summary.get("hwcomposer", {}).get("notes", []))

    game_brightness_doc = load_game_brightness_doc(out_dir)
    brightness_summary = enrich_brightness_stats(brightness_summary, game_brightness_doc)
    notes.extend(brightness_analysis_notes(brightness_summary.get("brightness_analysis") or {}))

    annotate_event_phases(events, game_window.get("start"), game_window.get("end"), startup_s, exit_s)
    game_ctx = build_game_process_context(
        events, game_pkg, baseline_processes.get("game_thread_suffixes")
    )
    kernel_summary.update(
        analyze_kernel_samples(
            kernel_summary.get("samples", []),
            game_pkg,
            baseline_processes,
            load_baseline_cpu_cores(script_dir),
            args.soc_model.strip(),
            startup_s,
            exit_s,
            game_window.get("start"),
            game_window.get("end"),
            game_ctx=game_ctx,
        )
    )
    notes.extend(kernel_summary.get("baseline_process_notes", []))

    log_coverage, coverage_warnings = compute_log_coverage(
        logs,
        game_window.get("start"),
        game_window.get("end"),
        keys=FULL_COVERAGE_KEYS,
        include_missing=False,
    )
    notes.extend(coverage_warnings)
    in_game_keys = ("main_log", "sys_log", "kernel_log")
    present_keys = [k for k in in_game_keys if logs.get(k)]
    covered_keys = [
        k for k in present_keys if log_coverage.get(k, {}).get("covers_t_game")
    ]
    if present_keys and not covered_keys:
        notes.append(
            "main/sys/kernel 日志均与 T_game 无时间重叠，窗口内无 AP/Display/线程级数据，"
            "无法对游戏时段做有效功耗归因；请确认抓取的日志是否覆盖游戏时段"
        )

    game_name = load_game_name(game_window.get("package", ""))
    if not game_name and saved_game_name:
        game_name = saved_game_name
    test_conditions = probe_test_conditions(
        log_path,
        logs,
        game_window.get("start"),
        game_window.get("end"),
        pre_s,
        brightness_summary,
        _precondition_ref_dir(script_dir),
        extract_ts,
        iter_lines,
        game_window.get("package", ""),
    )
    volume_stats = probe_volume_stats(
        logs,
        game_window.get("start"),
        game_window.get("end"),
        pre_s,
        extract_ts,
        iter_lines,
    )

    kcpu_thr = load_kernel_cpu_thresholds(script_dir)
    kcpu_thr["continuous_n"] = baseline_processes.get("continuous_sample_count", 2)
    cpu_serialized = cpu_samples_t_game_only(
        serialize_cpu_samples(
            kernel_summary.get("samples", []),
            game_window.get("start"),
            game_window.get("end"),
            startup_s,
            exit_s,
        )
    )
    cpu_thread_investigation = build_cpu_thread_investigation(
        cpu_serialized,
        logs,
        events,
        game_pkg,
        baseline_processes.get("common_processes", []),
        kcpu_thr,
        baseline_processes.get("game_thread_suffixes"),
    )
    inv_summary = cpu_thread_investigation.get("summary") or {}
    if inv_summary.get("spike") or inv_summary.get("single_shot") or inv_summary.get("persistent_non_baseline"):
        notes.append(
            f"[K] 线程排查: 突增 {inv_summary.get('spike', 0)} / "
            f"单次高占用 {inv_summary.get('single_shot', 0)} / "
            f"持续非基线 {inv_summary.get('persistent_non_baseline', 0)}"
        )

    summary = build_summary(
        log_path,
        out_dir,
        logs,
        game_window,
        kernel_summary,
        main_summary,
        background_summary,
        brightness_summary,
        events,
        pre_s,
        post_s,
        startup_s,
        exit_s,
        min_segment_s,
        merge_gap_s,
        notes,
        test_conditions,
        volume_stats,
        game_name,
        cpu_thread_investigation,
    )
    summary["log_coverage"] = log_coverage
    summary["in_game_data_available"] = bool(covered_keys) or not present_keys
    report_path = out_dir / "game_power_report.html"
    summary["comparison_outputs"]["dashboard_file"] = str(report_path)
    write_outputs(events, summary, out_dir)
    generate_report(summary, report_path)
    print(f"已输出: {out_dir / 'game_power_timeseries.jsonl'}")
    print(f"已输出: {out_dir / 'game_power_compare_summary.json'}")
    print(f"已输出: {report_path}")
    return 0 if summary["status"] != "blocked" else 1


if __name__ == "__main__":
    raise SystemExit(main())
