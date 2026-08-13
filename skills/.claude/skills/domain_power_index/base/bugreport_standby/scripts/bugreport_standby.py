import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field


BUGREPORT_FIELDS = (
    "bugreport_summary",
    "top_locks",
    "power_rank",
    "raw_evidence",
)

SECTION_POWER = "Estimated power use (mAh)"
SECTION_KERNEL_LOCK = "All kernel wake locks"
SECTION_PARTIAL_LOCK = "All partial wake locks"
MAX_SECTION_GAP = 2500


def _setup_utf8_stdio() -> None:
    for stream_name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _top3(counter: dict[str, int]) -> str:
    if not counter:
        return "No"
    items = sorted(counter.items(), key=lambda x: x[1], reverse=True)
    total = sum(v for _, v in items)
    if total <= 0:
        return "No"
    top = items[:3]
    body = ", ".join(f"{k}({v},{v / total * 100:.2f}%)" for k, v in top)
    return f"Top3={body}; total={total}"


def _split_tokens(raw: str) -> list[str]:
    return [x for x in re.split(r"[\s,/|]+", (raw or "").strip()) if x]


def _parse_duration_seconds(raw: str) -> float | None:
    text = (raw or "").strip().lower()
    if not text:
        return None

    hms = re.search(r"\b(\d{1,2}):(\d{2}):(\d{2})(?:\.(\d{1,3}))?\b", text)
    if hms:
        hh, mm, ss, ms = hms.groups()
        seconds = int(hh) * 3600 + int(mm) * 60 + int(ss)
        if ms:
            seconds += int(ms) / (10 ** len(ms))
        return seconds

    units = re.findall(r"(\d+(?:\.\d+)?)\s*(ms|s|m|h|d)\b", text)
    if units:
        total = 0.0
        for num_raw, unit in units:
            num = float(num_raw)
            if unit == "ms":
                total += num / 1000.0
            elif unit == "s":
                total += num
            elif unit == "m":
                total += num * 60
            elif unit == "h":
                total += num * 3600
            elif unit == "d":
                total += num * 86400
        return total if total > 0 else None

    return None


def _extract_timestamp(line: str) -> str | None:
    # 兼容 bugreport 常见时间格式：MM-DD HH:MM:SS(.f)
    m = re.match(r"^\s*(\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?)", line)
    if m:
        return m.group(1)
    return None


def _safe_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@dataclass
class LockEntry:
    name: str
    count: int | None = None
    duration_s: float | None = None
    raw_line: str = ""


@dataclass
class ParseState:
    in_power: bool = False
    in_kernel: bool = False
    in_partial: bool = False
    power_gap: int = 0
    kernel_gap: int = 0
    partial_gap: int = 0


@dataclass(order=True)
class BugreportCandidate:
    priority: int
    size: int
    mtime: float
    path: str = field(compare=False)
    kind: str = field(compare=False, default="file")


def _iter_file_lines(path: str, chunk_lines: int = 200_000):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        buf: list[str] = []
        for line in f:
            buf.append(line.rstrip("\n"))
            if len(buf) >= chunk_lines:
                for item in buf:
                    yield item
                buf = []
        for item in buf:
            yield item


def _candidate_priority(name: str) -> int:
    lower = name.lower()

    # 明确排除常见“伪 bugreport”文本，避免误读 dumpstate 摘要。
    ignored_keywords = (
        "dumpstate_log",
        "dumpstate-stats",
        "dumpstate_stats",
        "main_entry",
        "version.txt",
    )
    if any(keyword in lower for keyword in ignored_keywords):
        return -1

    if re.match(r"bugreport-.*\.tmp$", lower):
        return 500
    if re.match(r"bugreport-.*\.txt$", lower):
        return 450
    if lower.startswith("bugreport") and lower.endswith(".tmp"):
        return 420
    if lower.startswith("bugreport") and lower.endswith(".txt"):
        return 400
    if lower.startswith("bugreport"):
        return 350
    if "bugreport" in lower and lower.endswith(".tmp"):
        return 320
    if "bugreport" in lower and lower.endswith(".txt"):
        return 300
    if "bugreport" in lower:
        return 250

    return -1


def _collect_bugreport_candidates(directory: str) -> list[BugreportCandidate]:
    candidates: list[BugreportCandidate] = []
    for root, _, names in os.walk(directory):
        for name in names:
            priority = _candidate_priority(name)
            if priority < 0:
                continue
            path = os.path.join(root, name)
            try:
                stat = os.stat(path)
            except OSError:
                continue
            candidates.append(
                BugreportCandidate(
                    priority=priority,
                    size=stat.st_size,
                    mtime=stat.st_mtime,
                    path=path,
                    kind="file",
                )
            )

    if not candidates:
        raise ValueError("目录下未找到有效 bugreport 文件（会自动忽略 dumpstate_log/stats）")

    candidates.sort()
    return list(reversed(candidates))


def _result_score(result: dict) -> tuple[int, int, int, int, int]:
    summary = result.get("summary") or {}
    stats = result.get("stats") or {}
    return (
        1 if summary.get("raw_evidence") == "Yes" else 0,
        1 if stats.get("power_rank_count", 0) > 0 else 0,
        1 if stats.get("kernel_lock_count", 0) > 0 else 0,
        1 if stats.get("partial_lock_count", 0) > 0 else 0,
        stats.get("line_count", 0),
    )


def _analyze_file_path(path: str) -> dict:
    result = _analyze_lines(_iter_file_lines(path))
    result.setdefault("meta", {})
    result["meta"]["source_path"] = path
    result["meta"]["source_kind"] = "file"
    return result


def _analyze_directory(directory: str) -> dict:
    candidates = _collect_bugreport_candidates(directory)
    best_result = None
    best_score = None
    evaluated = []

    for candidate in candidates:
        result = _analyze_file_path(candidate.path)
        score = _result_score(result)
        evaluated.append(
            {
                "path": candidate.path,
                "priority": candidate.priority,
                "size": candidate.size,
                "score": {
                    "raw_evidence": score[0],
                    "power_rank": score[1],
                    "kernel_lock": score[2],
                    "partial_lock": score[3],
                    "line_count": score[4],
                },
            }
        )
        if best_result is None or score > best_score:
            best_result = result
            best_score = score

    assert best_result is not None
    best_result.setdefault("meta", {})
    best_result["meta"]["source_kind"] = "directory"
    best_result["meta"]["source_dir"] = directory
    best_result["meta"]["candidate_count"] = len(candidates)
    best_result["meta"]["evaluated_candidates"] = evaluated
    best_result["meta"]["selected_source_path"] = best_result["meta"].get("source_path", "")
    return best_result


def _parse_power_line(line: str) -> tuple[str, float] | None:
    # 示例兼容：
    # Screen: 12.34 (mAh)
    # Uid u0a123: 9.8
    m = re.match(r"^\s*([A-Za-z0-9_./\- ()\[\]#:+]+?)\s*:\s*(-?\d+(?:\.\d+)?)\b", line)
    if not m:
        return None
    name = m.group(1).strip()
    value = float(m.group(2))
    if not name:
        return None
    return name, value


def _parse_lock_line(line: str) -> LockEntry | None:
    if not line.strip():
        return None

    # 统计次数（例如 "count=12" 或 "(12 times)"）
    cnt = None
    cnt_match = re.search(r"\bcount\s*[:=]\s*(\d+)\b", line, flags=re.IGNORECASE)
    if cnt_match:
        cnt = _safe_int(cnt_match.group(1))
    if cnt is None:
        times_match = re.search(r"\((\d+)\s+times?\)", line, flags=re.IGNORECASE)
        if times_match:
            cnt = _safe_int(times_match.group(1))

    # 持锁时长
    duration = None
    duration_patterns = (
        r"\btotal(?:_time)?\s*[:=]\s*([0-9:.]+(?:\s*(?:ms|s|m|h|d))?)",
        r"\bheld(?:_time)?\s*[:=]\s*([0-9:.]+(?:\s*(?:ms|s|m|h|d))?)",
        r"\bduration\s*[:=]\s*([0-9:.]+(?:\s*(?:ms|s|m|h|d))?)",
        r"\btime\s*[:=]\s*([0-9:.]+(?:\s*(?:ms|s|m|h|d))?)",
    )
    for p in duration_patterns:
        dm = re.search(p, line, flags=re.IGNORECASE)
        if dm:
            duration = _parse_duration_seconds(dm.group(1))
            if duration is not None:
                break
    if duration is None:
        duration = _parse_duration_seconds(line)

    # 锁名
    name = None
    name_match = re.search(r"^\s*\*?\s*([A-Za-z0-9_./\-:#+@$\[\] ]+?)\s*(?:[:(]|$)", line)
    if name_match:
        name = name_match.group(1).strip()
    if not name:
        return None

    # 至少有 count 或 duration 才认为是有效项，避免把标题行吃进去
    if cnt is None and duration is None:
        return None

    return LockEntry(name=name, count=cnt, duration_s=duration, raw_line=line[:500])


def _analyze_lines(lines_iter) -> dict:
    state = ParseState()
    power_entries: list[tuple[str, float, str]] = []
    kernel_entries: list[LockEntry] = []
    partial_entries: list[LockEntry] = []
    evidence = {
        "power_rank": [],
        "kernel_wake_locks": [],
        "partial_wake_locks": [],
    }
    first_ts = None
    last_ts = None
    total_lines = 0

    for line in lines_iter:
        total_lines += 1
        ts = _extract_timestamp(line)
        if ts:
            if first_ts is None:
                first_ts = ts
            last_ts = ts

        lower = line.lower()

        # section enter
        if SECTION_POWER.lower() in lower:
            state.in_power = True
            state.in_kernel = False
            state.in_partial = False
            state.power_gap = 0
            continue
        if SECTION_KERNEL_LOCK.lower() in lower:
            state.in_power = False
            state.in_kernel = True
            state.in_partial = False
            state.kernel_gap = 0
            continue
        if SECTION_PARTIAL_LOCK.lower() in lower:
            state.in_power = False
            state.in_kernel = False
            state.in_partial = True
            state.partial_gap = 0
            continue

        # section parse
        if state.in_power:
            parsed = _parse_power_line(line)
            if parsed:
                state.power_gap = 0
                name, value = parsed
                power_entries.append((name, value, line[:500]))
                if len(evidence["power_rank"]) < 3:
                    evidence["power_rank"].append(line[:500])
            else:
                state.power_gap += 1
                if state.power_gap > MAX_SECTION_GAP:
                    state.in_power = False

        elif state.in_kernel:
            parsed = _parse_lock_line(line)
            if parsed:
                state.kernel_gap = 0
                kernel_entries.append(parsed)
                if len(evidence["kernel_wake_locks"]) < 3:
                    evidence["kernel_wake_locks"].append(parsed.raw_line)
            else:
                state.kernel_gap += 1
                if state.kernel_gap > MAX_SECTION_GAP:
                    state.in_kernel = False

        elif state.in_partial:
            parsed = _parse_lock_line(line)
            if parsed:
                state.partial_gap = 0
                partial_entries.append(parsed)
                if len(evidence["partial_wake_locks"]) < 3:
                    evidence["partial_wake_locks"].append(parsed.raw_line)
            else:
                state.partial_gap += 1
                if state.partial_gap > MAX_SECTION_GAP:
                    state.in_partial = False

    power_sorted = sorted(power_entries, key=lambda x: x[1], reverse=True)
    kernel_duration = {}
    kernel_count = {}
    partial_duration = {}
    partial_count = {}

    for item in kernel_entries:
        if item.duration_s is not None:
            kernel_duration[item.name] = kernel_duration.get(item.name, 0) + int(round(item.duration_s))
        if item.count is not None:
            kernel_count[item.name] = kernel_count.get(item.name, 0) + item.count

    for item in partial_entries:
        if item.duration_s is not None:
            partial_duration[item.name] = partial_duration.get(item.name, 0) + int(round(item.duration_s))
        if item.count is not None:
            partial_count[item.name] = partial_count.get(item.name, 0) + item.count

    power_counter = {name: int(round(value * 1000)) for name, value, _ in power_sorted}
    kernel_top = sorted(kernel_duration.items(), key=lambda x: x[1], reverse=True)[:3]
    partial_top = sorted(partial_duration.items(), key=lambda x: x[1], reverse=True)[:3]

    summary_bugreport = (
        f"power_items={len(power_entries)}; "
        f"kernel_lock_items={len(kernel_entries)}; "
        f"partial_lock_items={len(partial_entries)}"
    )
    top_lock_text = (
        f"kernel={', '.join([f'{k}({v}s)' for k, v in kernel_top]) if kernel_top else 'No'}; "
        f"partial={', '.join([f'{k}({v}s)' for k, v in partial_top]) if partial_top else 'No'}"
    )

    return {
        "summary": {
            "bugreport_summary": summary_bugreport,
            "top_locks": top_lock_text,
            "power_rank": _top3(power_counter),
            "raw_evidence": "Yes" if any(evidence.values()) else "No",
        },
        "stats": {
            "power_rank_count": len(power_entries),
            "kernel_lock_count": len(kernel_entries),
            "partial_lock_count": len(partial_entries),
            "top_power_rank_raw": [{"name": n, "mah": v, "raw_line": raw} for n, v, raw in power_sorted[:10]],
            "kernel_locks": {
                "top_by_duration_s": [{"name": n, "duration_s": v} for n, v in kernel_top],
                "top_by_count": sorted(
                    [{"name": n, "count": v} for n, v in kernel_count.items()],
                    key=lambda x: x["count"],
                    reverse=True,
                )[:10],
            },
            "partial_locks": {
                "top_by_duration_s": [{"name": n, "duration_s": v} for n, v in partial_top],
                "top_by_count": sorted(
                    [{"name": n, "count": v} for n, v in partial_count.items()],
                    key=lambda x: x["count"],
                    reverse=True,
                )[:10],
            },
            "line_count": total_lines,
        },
        "evidence": evidence,
        "meta": {
            "analysis_start": first_ts or "",
            "analysis_end": last_ts or "",
            "analysis_duration_h": "",
            "chunk_lines": 200000,
        },
        "threshold": {
            "standby_26m_off_pct_threshold": 70,
            "hardware_discharge_abnormal_threshold_ma": 3000,
        },
    }


def _print_text_report(result: dict) -> None:
    summary = result.get("summary", {})
    stats = result.get("stats", {})
    evidence = result.get("evidence", {})
    meta = result.get("meta", {})
    threshold = result.get("threshold", {})

    print("===== Bugreport 待机明细 =====")
    print("-" * 120)
    print(f"{'类别':<26} {'Top项(示例)':<92}")
    print("-" * 120)

    power_rows = stats.get("top_power_rank_raw") or []
    if power_rows:
        top_power = ", ".join([f"{x.get('name')}({x.get('mah')}mAh)" for x in power_rows[:3]])
    else:
        top_power = "No"
    print(f"{'Estimated power use':<26} {top_power:<92}")

    kernel_rows = ((stats.get("kernel_locks") or {}).get("top_by_duration_s")) or []
    if kernel_rows:
        top_kernel = ", ".join([f"{x.get('name')}({x.get('duration_s')}s)" for x in kernel_rows[:3]])
    else:
        top_kernel = "No"
    print(f"{'All kernel wake locks':<26} {top_kernel:<92}")

    partial_rows = ((stats.get("partial_locks") or {}).get("top_by_duration_s")) or []
    if partial_rows:
        top_partial = ", ".join([f"{x.get('name')}({x.get('duration_s')}s)" for x in partial_rows[:3]])
    else:
        top_partial = "No"
    print(f"{'All partial wake locks':<26} {top_partial:<92}")
    print("-" * 120)
    print("")

    print("=== 结构化分析摘要(供下游SKILL输入) ===")
    print("[META]")
    print(f"source_path={meta.get('source_path', '')}")
    print(f"source_kind={meta.get('source_kind', '')}")
    print(f"analysis_start={meta.get('analysis_start', '')}")
    print(f"analysis_end={meta.get('analysis_end', '')}")
    print(f"analysis_duration_h={meta.get('analysis_duration_h', '')}")
    print("")

    print("[THRESHOLD]")
    print(f"standby_26m_off_pct_threshold={threshold.get('standby_26m_off_pct_threshold', 70)}")
    print(
        f"hardware_discharge_abnormal_threshold_ma={threshold.get('hardware_discharge_abnormal_threshold_ma', 3000)}"
    )
    print("")

    print("[SUMMARY]")
    print(f"bugreport_summary={summary.get('bugreport_summary', 'No')}")
    print(f"top_locks={summary.get('top_locks', 'No')}")
    print(f"power_rank={summary.get('power_rank', 'No')}")
    print(f"raw_evidence={summary.get('raw_evidence', 'No')}")
    print("")

    print("[STATS]")
    print(f"power_rank_count={stats.get('power_rank_count', 0)}")
    print(f"kernel_lock_count={stats.get('kernel_lock_count', 0)}")
    print(f"partial_lock_count={stats.get('partial_lock_count', 0)}")
    print(f"power_rank_top={summary.get('power_rank', 'No')}")
    print(
        f"kernel_lock_duration_top={_top3({x.get('name'): int(x.get('duration_s', 0)) for x in (((stats.get('kernel_locks') or {}).get('top_by_duration_s')) or [])})}"
    )
    print(
        f"partial_lock_duration_top={_top3({x.get('name'): int(x.get('duration_s', 0)) for x in (((stats.get('partial_locks') or {}).get('top_by_duration_s')) or [])})}"
    )
    print(f"evidence_power_rank_lines={len(evidence.get('power_rank', []))}")
    print(f"evidence_kernel_lock_lines={len(evidence.get('kernel_wake_locks', []))}")
    print(f"evidence_partial_lock_lines={len(evidence.get('partial_wake_locks', []))}")


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="解析 bugreport 待机数据（Estimated power use / kernel locks / partial locks）"
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("-d", "--directory", metavar="DIR", help="bugreport 目录")
    source.add_argument("--file", dest="file_path", metavar="FILE", help="bugreport 单文件")
    source.add_argument("--stdin", action="store_true", help="从标准输入读取 bugreport")
    parser.add_argument("--format", choices=("text", "json"), default="text", help="输出格式，默认 text")
    parser.add_argument(
        "--field",
        action="append",
        dest="fields",
        choices=BUGREPORT_FIELDS,
        metavar="FIELD",
        help="仅在 json 模式生效，可重复指定",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    _setup_utf8_stdio()
    args = _build_arg_parser().parse_args(argv)

    try:
        if args.stdin:
            result = _analyze_lines([line.rstrip("\n") for line in sys.stdin])
            result.setdefault("meta", {})
            result["meta"]["source_path"] = ""
            result["meta"]["source_kind"] = "stdin"
        elif args.file_path:
            if not os.path.exists(args.file_path):
                print(f"错误：文件不存在: {args.file_path}")
                return 1
            result = _analyze_file_path(args.file_path)
        else:
            if not os.path.exists(args.directory):
                print(f"错误：目录不存在: {args.directory}")
                return 1
            result = _analyze_directory(args.directory)
    except Exception as exc:
        print(f"读取日志失败: {exc}")
        return 1

    if args.format == "json":
        if args.fields:
            selected = {name: (result.get("summary") or {}).get(name) for name in args.fields}
            print(json.dumps(selected, ensure_ascii=False, indent=2))
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    _print_text_report(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
