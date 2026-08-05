"""[K] CPU 线程突增 / 单次高占用 / 持续非基线进程检测与日志关联。"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

DEFAULT_SPIKE_PP = 10
DEFAULT_SINGLE_SHOT_MIN_USAGE = 10
DEFAULT_LOG_WINDOW_SECONDS = 10
DEFAULT_MAX_LOG_LINES_PER_SOURCE = 5
DEFAULT_PERSISTENT_MIN_RATIO = 0.4
DEFAULT_PERSISTENT_MIN_OCCURRENCE = 3

_PROC_START_PID_PKG_RE = re.compile(
    r"(?:Start proc|am_proc_start:\s*\[[^\]]*,)\s*(\d+)[^,\n]*(?:,|\s)([^\],\s/]+)"
)


def build_game_process_context(
    events: list[dict[str, Any]],
    game_package: str,
    game_thread_suffixes: list[str] | None = None,
) -> dict[str, Any]:
    """从 events 与配置构建游戏 PID / 子进程后缀集合，用于识别 ds:UnityKillsMe 等。"""
    game_pids: set[int] = set()
    subprocess_suffixes: set[str] = set(game_thread_suffixes or [])
    packages: set[str] = set()

    if game_package:
        packages.add(game_package)
        tail = game_package.split(".")[-1]
        if len(tail) >= 3:
            subprocess_suffixes.add(tail)

    for ev in events:
        blob = " ".join(
            str(ev.get(k, ""))
            for k in ("package_or_process", "raw_evidence", "pid_uid", "category")
        )
        if game_package and game_package not in blob:
            continue
        pid_m = re.search(r"pid=(\d+)", str(ev.get("pid_uid", "")))
        if pid_m:
            game_pids.add(int(pid_m.group(1)))
        pkg = str(ev.get("package_or_process", "")).strip()
        if pkg:
            packages.add(pkg)
            if ":" in pkg:
                subprocess_suffixes.add(pkg.split(":", 1)[1])
        for m in _PROC_START_PID_PKG_RE.finditer(blob):
            try:
                pid = int(m.group(1))
            except (TypeError, ValueError):
                continue
            proc_pkg = m.group(2).strip()
            if game_package and game_package not in proc_pkg:
                continue
            game_pids.add(pid)
            packages.add(proc_pkg)
            if ":" in proc_pkg:
                subprocess_suffixes.add(proc_pkg.split(":", 1)[1])

    return {
        "game_pids": sorted(game_pids),
        "subprocess_suffixes": sorted(subprocess_suffixes),
        "packages": sorted(packages),
    }


def is_expected_game_thread(
    name: str,
    pid: int | None,
    game_package: str,
    baseline_rules: list[dict[str, str]],
    game_ctx: dict[str, Any],
    is_expected_process: Callable[[str, str, list[dict[str, str]]], bool],
) -> bool:
    """游戏主进程/子进程/基线白名单线程，不计入异常排查。"""
    if pid is not None and pid in set(game_ctx.get("game_pids") or []):
        return True
    if is_expected_process(name, game_package, baseline_rules):
        return True
    tail = name.split(":")[-1] if ":" in name else name
    for suf in game_ctx.get("subprocess_suffixes") or []:
        if not suf:
            continue
        if tail == suf or name.endswith(suf) or suf in tail:
            return True
    for pkg in game_ctx.get("packages") or []:
        if name == pkg or name.startswith(f"{pkg}:") or pkg.endswith(name):
            return True
    return False


def resolve_process_owner_hint(
    pid: int | None,
    name: str,
    events: list[dict[str, Any]],
    logs: dict[str, list[Path]],
    *,
    extract_ts: Callable[..., Any],
    iter_lines: Callable[[Path], Any],
    max_hints: int = 3,
) -> list[str]:
    """根据 PID/进程名从 events 与 sys/main 解析归属包名或功能。"""
    hints: list[str] = []
    pid_s = str(pid) if pid is not None else ""

    for ev in events:
        if len(hints) >= max_hints:
            break
        cat = str(ev.get("category", ""))
        if cat not in ("process_start", "process_died", ""):
            if "proc" not in cat:
                continue
        raw = str(ev.get("raw_evidence", ""))
        pkg = str(ev.get("package_or_process", ""))
        blob = f"{raw} {pkg} {ev.get('pid_uid', '')}"
        if pid_s and pid_s not in blob and f" {pid_s} " not in f" {blob} ":
            if not (name and name in blob):
                continue
        if pid_s and (
            f"pid={pid_s}" in blob
            or f"Start proc {pid_s}:" in raw
            or f",{pid_s}," in raw
        ):
            line = raw.strip()[:500]
            if line and line not in hints:
                hints.append(line)
        elif name and name in raw and len(hints) < max_hints:
            line = raw.strip()[:500]
            if line and line not in hints:
                hints.append(line)

    if len(hints) < max_hints and pid_s:
        pat = re.compile(rf"Start proc {re.escape(pid_s)}:([^\s/]+)")
        for log_key in ("sys_log", "main_log"):
            for path in logs.get(log_key, []):
                if len(hints) >= max_hints:
                    break
                for _line_no, line in iter_lines(path):
                    m = pat.search(line)
                    if m:
                        hint = line.strip()[:500]
                        if hint not in hints:
                            hints.append(hint)
                    if len(hints) >= max_hints:
                        break
    return hints


def infer_kernel_thread_owner_hint(
    name: str,
    pid: int | None,
    correlated_logs: dict[str, list[str]],
) -> str:
    """内核 kthread（无 userspace Start proc）从关联 kernel 行推断归属。"""
    kernel_lines = correlated_logs.get("kernel_log") or []
    name_l = name.lower()
    if "touch" in name_l or name == "touch-main-loop":
        for line in kernel_lines:
            if "[CHSC]" in line or "touch_point" in line:
                return (
                    f"内核触控驱动线程 (CHSC)「{name}」"
                    f"{f' pid={pid}' if pid else ''}，非应用进程，需排查触控/TP 驱动负载"
                )
        return (
            f"内核触控相关 kthread「{name}」"
            f"{f' pid={pid}' if pid else ''}，oom_adj=-1000 通常为驱动线程，非系统公共白名单"
        )
    if "mali" in name_l or "gpu" in name_l:
        return f"GPU 驱动内核线程「{name}」{f' pid={pid}' if pid else ''}"
    if "hif_thread" in name_l or "wlan" in name_l:
        for line in kernel_lines:
            if "[wlan]" in line:
                return f"WiFi 驱动内核线程「{name}」{f' pid={pid}' if pid else ''}"
    return ""


def _longest_consecutive_rounds(entries: list[dict[str, Any]]) -> int:
    indices = sorted(e["round_idx"] for e in entries)
    if not indices:
        return 0
    best = cur = 1
    for i in range(1, len(indices)):
        if indices[i] == indices[i - 1] + 1:
            cur += 1
            best = max(best, cur)
        else:
            cur = 1
    return best


def _thread_key(thread: dict[str, Any]) -> str:
    return str(thread.get("name") or "").strip()


def _parse_sample_dt(time_str: str, parse_dt: Callable[..., datetime | None]) -> datetime | None:
    if not time_str:
        return None
    return parse_dt(time_str)


def _in_time_window(
    dt: datetime | None,
    anchor: datetime,
    window_s: int,
) -> bool:
    if not dt:
        return False
    lo = anchor - timedelta(seconds=window_s)
    hi = anchor + timedelta(seconds=window_s)
    return lo <= dt <= hi


def _line_matches_thread(line: str, name: str, pid: int | None) -> bool:
    if pid is not None and str(pid) in line:
        return True
    if not name:
        return False
    if name in line:
        return True
    # 截断进程名（kernel 常截断为 15 字符）
    short = name[:15] if len(name) > 15 else name
    if short and short in line:
        return True
    tail = name.split(":")[-1]
    if len(tail) >= 4 and tail in line:
        return True
    return False


def correlate_logs_for_thread(
    anchor_time: datetime | None,
    name: str,
    pid: int | None,
    logs: dict[str, list[Path]],
    events: list[dict[str, Any]],
    *,
    extract_ts: Callable[..., Any],
    iter_lines: Callable[[Path], Any],
    parse_dt: Callable[..., datetime | None],
    window_seconds: int = DEFAULT_LOG_WINDOW_SECONDS,
    max_per_source: int = DEFAULT_MAX_LOG_LINES_PER_SOURCE,
) -> dict[str, list[str]]:
    """在 anchor 时间 ±window 内检索 main/sys/kernel/events 相关行。"""
    if not anchor_time:
        return {}

    out: dict[str, list[str]] = {
        "events": [],
        "main_log": [],
        "sys_log": [],
        "kernel_log": [],
    }

    for ev in events:
        if len(out["events"]) >= max_per_source:
            break
        ts = parse_dt(str(ev.get("time", "")))
        if not _in_time_window(ts, anchor_time, window_seconds):
            continue
        blob = " ".join(
            str(ev.get(k, ""))
            for k in ("raw_evidence", "package_or_process", "category", "pid_uid")
        )
        if _line_matches_thread(blob, name, pid):
            line = str(ev.get("raw_evidence") or blob).strip()
            if line and line not in out["events"]:
                out["events"].append(line[:500])

    for log_key in ("main_log", "sys_log", "kernel_log"):
        for path in logs.get(log_key, []):
            if len(out[log_key]) >= max_per_source:
                break
            for line_no, line in iter_lines(path):
                if len(out[log_key]) >= max_per_source:
                    break
                _, dt = extract_ts(line)
                if not _in_time_window(dt, anchor_time, window_seconds):
                    continue
                if _line_matches_thread(line, name, pid):
                    entry = f"{path.name}:{line_no}: {line.strip()[:480]}"
                    if entry not in out[log_key]:
                        out[log_key].append(entry)

    return {k: v for k, v in out.items() if v}


def analyze_cpu_thread_findings(
    cpu_samples: list[dict[str, Any]],
    game_package: str,
    baseline_rules: list[dict[str, str]],
    *,
    game_ctx: dict[str, Any],
    is_expected_process: Callable[[str, str, list[dict[str, str]]], bool],
    parse_dt: Callable[..., datetime | None],
    spike_pp: int = DEFAULT_SPIKE_PP,
    single_shot_min_usage: int = DEFAULT_SINGLE_SHOT_MIN_USAGE,
    persistent_min_ratio: float = DEFAULT_PERSISTENT_MIN_RATIO,
    persistent_min_occurrence: int = DEFAULT_PERSISTENT_MIN_OCCURRENCE,
    continuous_n: int = 2,
) -> dict[str, Any]:
    """从 T_game 采样序列检测三类线程异常（游戏子进程/线程不计入）。"""
    samples = [s for s in cpu_samples if s.get("window") == "T_game"]
    total = len(samples)
    if total == 0:
        return {
            "thresholds": {
                "spike_usage_pp": spike_pp,
                "single_shot_min_usage_pct": single_shot_min_usage,
                "persistent_min_sample_ratio": persistent_min_ratio,
                "persistent_min_occurrence": persistent_min_occurrence,
            },
            "findings": [],
            "by_round": {},
            "summary": {"spike": 0, "single_shot": 0, "persistent_non_baseline": 0},
        }

    history: dict[str, list[dict[str, Any]]] = {}
    for idx, sample in enumerate(samples):
        rnd = sample.get("round", idx + 1)
        t = str(sample.get("time", ""))
        for th in sample.get("threads") or []:
            name = _thread_key(th)
            if not name:
                continue
            usage = int(th.get("usage", 0))
            pid = th.get("pid")
            history.setdefault(name, []).append(
                {
                    "round": rnd,
                    "round_idx": idx,
                    "time": t,
                    "usage": usage,
                    "pid": pid,
                }
            )

    def _usage_by_round(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_idx = {int(e["round_idx"]): e for e in entries}
        out: list[dict[str, Any]] = []
        for idx, sample in enumerate(samples):
            e = by_idx.get(idx)
            out.append(
                {
                    "round": sample.get("round", idx + 1),
                    "round_idx": idx,
                    "time": str(sample.get("time", "")),
                    "usage": int(e["usage"]) if e else None,
                    "present": e is not None,
                    "pid": e.get("pid") if e else None,
                }
            )
        return out

    findings: list[dict[str, Any]] = []
    by_round: dict[str, list[str]] = {}

    def _add(finding: dict[str, Any], entries: list[dict[str, Any]]) -> None:
        finding["usage_by_round"] = _usage_by_round(entries)
        findings.append(finding)
        rnd = str(finding.get("round", ""))
        tag = finding.get("finding_type", "")
        by_round.setdefault(rnd, []).append(f"{tag}:{finding.get('name')}")

    def _expected(name: str, pid: int | None) -> bool:
        return is_expected_game_thread(
            name, pid, game_package, baseline_rules, game_ctx, is_expected_process
        )

    for name, entries in history.items():
        pid0 = entries[0].get("pid") if entries else None
        if _expected(name, pid0):
            continue

        usages = [e["usage"] for e in entries]
        occ = len(entries)
        ratio = occ / total
        max_u = max(usages)
        avg_u = round(sum(usages) / occ, 2)
        longest_run = _longest_consecutive_rounds(entries)

        persistent = occ >= persistent_min_occurrence and (
            ratio >= persistent_min_ratio or longest_run >= continuous_n
        )
        if persistent:
            first = entries[0]
            _add(
                {
                    "finding_type": "persistent_non_baseline",
                    "priority": "P0" if ratio >= 0.7 else "P1",
                    "name": name,
                    "pid": first.get("pid"),
                    "round": first.get("round"),
                    "time": first.get("time"),
                    "occurrence_count": occ,
                    "total_rounds": total,
                    "sample_ratio": round(ratio, 4),
                    "longest_consecutive_rounds": longest_run,
                    "avg_usage": avg_u,
                    "max_usage": max_u,
                    "detail": (
                        f"非基线进程多轮出现 {occ}/{total} 轮 "
                        f"(ratio={ratio:.0%}, 最长连续{longest_run}轮), "
                        f"avg={avg_u}% max={max_u}%"
                    ),
                },
                entries,
            )

        if occ == 1 and max_u >= single_shot_min_usage:
            e = entries[0]
            _add(
                {
                    "finding_type": "single_shot",
                    "priority": "P1",
                    "name": name,
                    "pid": e.get("pid"),
                    "round": e.get("round"),
                    "time": e.get("time"),
                    "usage": max_u,
                    "occurrence_count": 1,
                    "total_rounds": total,
                    "avg_usage": float(max_u),
                    "max_usage": max_u,
                    "detail": f"仅出现 1 轮且 CPU={max_u}% (>={single_shot_min_usage}%)",
                },
                entries,
            )

        sorted_entries = sorted(entries, key=lambda x: x["round_idx"])
        for i in range(1, len(sorted_entries)):
            prev, cur = sorted_entries[i - 1], sorted_entries[i]
            if cur["round_idx"] != prev["round_idx"] + 1:
                continue
            delta = cur["usage"] - prev["usage"]
            if delta >= spike_pp:
                _add(
                    {
                        "finding_type": "spike",
                        "priority": "P0" if delta >= spike_pp * 2 else "P1",
                        "name": name,
                        "pid": cur.get("pid"),
                        "round": cur.get("round"),
                        "time": cur.get("time"),
                        "usage_from": prev["usage"],
                        "usage_to": cur["usage"],
                        "usage_delta_pp": delta,
                        "time_from": prev.get("time"),
                        "occurrence_count": occ,
                        "total_rounds": total,
                        "avg_usage": avg_u,
                        "max_usage": max_u,
                        "detail": (
                            f"相邻轮 CPU {prev['usage']}%→{cur['usage']}% "
                            f"(+{delta}pp, 阈值>={spike_pp}pp)"
                        ),
                    },
                    entries,
                )

    deduped: dict[tuple[str, str], dict[str, Any]] = {}
    for f in findings:
        key = (f["finding_type"], f["name"])
        prev = deduped.get(key)
        if not prev:
            deduped[key] = f
            continue
        if f["finding_type"] == "spike":
            if int(f.get("usage_delta_pp", 0)) > int(prev.get("usage_delta_pp", 0)):
                deduped[key] = f
        elif f["finding_type"] == "single_shot":
            if int(f.get("usage", 0)) > int(prev.get("usage", 0)):
                deduped[key] = f
        elif f["finding_type"] == "persistent_non_baseline":
            if float(f.get("sample_ratio", 0)) > float(prev.get("sample_ratio", 0)):
                deduped[key] = f

    final = sorted(
        deduped.values(),
        key=lambda x: (
            -int(x.get("occurrence_count") or 0),
            {"P0": 0, "P1": 1, "P2": 2}.get(str(x.get("priority", "P2")), 9),
            {"persistent_non_baseline": 0, "spike": 1, "single_shot": 2}.get(
                str(x.get("finding_type")), 9
            ),
            -float(x.get("usage_delta_pp") or x.get("max_usage") or x.get("usage") or 0),
        ),
    )

    type_counts = {"spike": 0, "single_shot": 0, "persistent_non_baseline": 0}
    for f in final:
        ft = str(f.get("finding_type", ""))
        if ft in type_counts:
            type_counts[ft] += 1

    return {
        "thresholds": {
            "spike_usage_pp": spike_pp,
            "single_shot_min_usage_pct": single_shot_min_usage,
            "persistent_min_sample_ratio": persistent_min_ratio,
            "persistent_min_occurrence": persistent_min_occurrence,
        },
        "findings": final,
        "by_round": by_round,
        "summary": type_counts,
        "total_rounds": total,
    }


def enrich_findings_with_logs(
    investigation: dict[str, Any],
    logs: dict[str, list[Path]],
    events: list[dict[str, Any]],
    *,
    extract_ts: Callable[..., Any],
    iter_lines: Callable[[Path], Any],
    parse_dt: Callable[..., datetime | None],
    window_seconds: int = DEFAULT_LOG_WINDOW_SECONDS,
    max_per_source: int = DEFAULT_MAX_LOG_LINES_PER_SOURCE,
) -> dict[str, Any]:
    """为每条 finding 附加 correlated_logs 与 owner_hint。"""
    out = dict(investigation)
    enriched: list[dict[str, Any]] = []
    for f in investigation.get("findings") or []:
        item = dict(f)
        anchor = _parse_sample_dt(str(item.get("time", "")), parse_dt)
        item["correlated_logs"] = correlate_logs_for_thread(
            anchor,
            str(item.get("name", "")),
            item.get("pid"),
            logs,
            events,
            extract_ts=extract_ts,
            iter_lines=iter_lines,
            parse_dt=parse_dt,
            window_seconds=window_seconds,
            max_per_source=max_per_source,
        )
        owner_hints = resolve_process_owner_hint(
            item.get("pid"),
            str(item.get("name", "")),
            events,
            logs,
            extract_ts=extract_ts,
            iter_lines=iter_lines,
        )
        corr = item.get("correlated_logs") or {}
        if not owner_hints:
            inferred = infer_kernel_thread_owner_hint(
                str(item.get("name", "")),
                item.get("pid"),
                corr if corr else item.get("correlated_logs") or {},
            )
            if inferred:
                item["owner_hint"] = inferred
                item["owner_hints"] = [inferred]
            else:
                item["owner_hint"] = ""
                item["owner_hints"] = []
        else:
            item["owner_hint"] = owner_hints[0]
            item["owner_hints"] = owner_hints
        enriched.append(item)
    out["findings"] = enriched
    return out
