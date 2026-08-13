"""游戏场景 Kernel [K] CPU 与线程解析编排。

配置: references/keyword-patterns.yaml, baseline-*.yaml, analysis-standards.yaml
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from game_skill_paths import ensure_game_scripts_on_path  # noqa: E402

ensure_game_scripts_on_path(__file__)
from skill_references import evidence_cap, load_analysis_standards, load_keyword_patterns  # noqa: E402

_EVIDENCE_CAP = evidence_cap(load_analysis_standards(Path(__file__).resolve().parent.parent / "references"))


def skill_root() -> Path:
    return Path(__file__).resolve().parent.parent


def references_dir() -> Path:
    return skill_root() / "references"


def _scan_cpufreq_placeholders(
    logs: dict[str, list[Path]],
    patterns_cfg: dict[str, Any],
    extract_ts: Callable[..., Any],
    iter_lines: Callable[[Path], Any],
) -> dict[str, Any]:
    """扫描 cpufreq 占位关键词，仅收集证据。"""
    out: dict[str, Any] = {}
    cat = (patterns_cfg.get("categories") or {}).get("cpufreq") or {}
    for pat in cat.get("patterns") or []:
        if not isinstance(pat, dict):
            continue
        pid = str(pat.get("id", ""))
        keywords = [str(k) for k in (pat.get("keywords") or [])]
        log_names = pat.get("logs") or ["kernel_log"]
        samples: list[dict[str, Any]] = []
        for name in log_names:
            for path in logs.get(name, []):
                for line_no, line in iter_lines(path):
                    if keywords and not any(kw in line for kw in keywords):
                        continue
                    ts_raw, _ = extract_ts(line)
                    samples.append(
                        {
                            "time": ts_raw or "",
                            "raw_evidence": f"{path.name}:{line_no}: {line.strip()[:300]}",
                        }
                    )
                    if len(samples) >= 10:
                        break
                if len(samples) >= 10:
                    break
        out[pid] = {
            "status": "placeholder" if samples else "not_found",
            "samples": samples[:10],
        }
    return out


def analyze_game_kernel_cpu(
    log_path: Path,
    game_start: datetime,
    game_end: datetime,
    *,
    game_package: str = "",
    soc_model: str = "",
    pre_minutes: int = 5,
    post_minutes: int = 3,
    startup_seconds: int = 60,
    exit_seconds: int = 30,
    discover_logs: Callable[[Path], dict[str, list[Path]]],
    parse_kernel: Callable[..., dict[str, Any]],
    analyze_kernel_samples: Callable[..., dict[str, Any]],
    serialize_cpu_samples: Callable[..., list[dict[str, Any]]],
    load_baseline_processes: Callable[[Path], dict[str, Any]],
    load_baseline_cpu_cores: Callable[[Path], dict[str, Any]],
    add_event: Callable[[list[dict[str, Any]], dict[str, Any]], None],
    fmt_time: Callable[[datetime | None], str],
    extract_ts: Callable[..., Any],
    iter_lines: Callable[[Path], Any],
    refs_dir: Path | None = None,
) -> dict[str, Any]:
    refs = refs_dir or references_dir()
    logs = discover_logs(log_path)
    pre_s = max(60, pre_minutes * 60)
    post_s = max(60, post_minutes * 60)
    events: list[dict[str, Any]] = []
    warnings: list[str] = []
    notes: list[str] = []

    if not logs.get("kernel_log"):
        return {
            "status": "failed",
            "warnings": ["kernel 日志缺失，AP/CPU 证据不足"],
            "log_availability": {"kernel_log": False},
        }

    kernel_summary = parse_kernel(
        logs.get("kernel_log", []),
        events,
        game_start,
        game_end,
        pre_s,
        post_s,
    )
    analysis = analyze_kernel_samples(
        kernel_summary.get("samples", []),
        game_package.strip(),
        load_baseline_processes(refs),
        load_baseline_cpu_cores(refs),
        soc_model.strip(),
        startup_seconds,
        exit_seconds,
        game_start,
        game_end,
    )
    kernel_summary.update(analysis)

    cpu_samples = serialize_cpu_samples(
        kernel_summary.get("samples", []),
        game_start,
        game_end,
        startup_seconds,
        exit_seconds,
    )
    game_samples = [s for s in cpu_samples if s.get("window") == "T_game"]
    stable_samples = [s for s in game_samples if s.get("phase") == "stable"]

    cpufreq = _scan_cpufreq_placeholders(
        logs, load_keyword_patterns(references_dir()), extract_ts, iter_lines
    )

    notes.extend(kernel_summary.get("baseline_process_notes", []))
    if kernel_summary.get("sample_count", 0) == 0:
        warnings.append("T_pre/T_game 内无 [K][Perf] 采样")
    else:
        notes.append(
            f"[K] 采样 {kernel_summary.get('sample_count')} 轮；"
            f"T_game {len(game_samples)} 轮，stable {len(stable_samples)} 轮"
        )

    abnormal = kernel_summary.get("abnormal_processes") or []
    if abnormal:
        top = abnormal[0]
        notes.append(
            f"异常进程 Top: {top.get('name')} 出现 {top.get('occurrence_count')}/"
            f"{top.get('total_samples')} 轮"
        )

    core_stats = kernel_summary.get("cpu_core_usage_stats") or {}
    if core_stats.get("abnormal_core_count"):
        notes.append(f"可疑/异常 CPU 核数: {core_stats['abnormal_core_count']}")

    status = "ok"
    if kernel_summary.get("sample_count", 0) == 0:
        status = "failed"
    elif warnings:
        status = "partial"

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
        "kernel_cpu_summary": {
            "sample_count": kernel_summary.get("sample_count", 0),
            "T_game_sample_count": len(game_samples),
            "stable_sample_count": len(stable_samples),
            "avg_total_usage": kernel_summary.get("avg_total_usage", 0),
            "max_total_usage": kernel_summary.get("max_total_usage", 0),
            "top_threads": kernel_summary.get("top_threads", []),
        },
        "cpu_core_usage_stats": kernel_summary.get("cpu_core_usage_stats", {}),
        "abnormal_processes": abnormal[:_EVIDENCE_CAP],
        "cpu_samples": cpu_samples,
        "cpufreq": cpufreq,
        "log_availability": {"kernel_log": bool(logs.get("kernel_log"))},
        "warnings": warnings,
        "notes": notes,
    }
