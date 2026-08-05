#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""高通平台 CPU 负载分析：递归合并 kernellogcat-log.* 并解析 [K] 负载行。"""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime

_BASE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "base", "lib")
)
if _BASE_DIR not in sys.path:
    sys.path.insert(0, _BASE_DIR)

from repo_paths import (  # noqa: E402
    find_repo_root,
    jira_workspace_dir,
    resolve_workspace_dir,
    temp_root,
    workspace_analysis,
)

# 用户约定：关键字含空格；[K] 后至少 6 个空格，用于匹配负载行
KEYWORD = ": [K]      "

# 文件名：kernellogcat-log.20260612-071957 或带后缀 .xx
_KERNELLOGCAT_RE = re.compile(
    r"^kernellogcat-log\.(\d{8})-(\d{6})(?:\.\w+)?$",
    re.IGNORECASE,
)
# 行首时间：07-22 23:48:20.776445
_LINE_TIME_RE = re.compile(r"^(\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})(?:\.\d+)?")
# : [K] ... 89%  23850  .lark.transsion / facebook.katana
_LOAD_LINE_RE = re.compile(
    r": \[K\]\s+(\d+(?:\.\d+)?)%\s+(\d+)\s+(\S+)"
)


def _setup_utf8_stdio() -> None:
    """统一脚本标准输入输出编码为 UTF-8，减少 Windows 终端乱码。"""
    for stream_name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def parse_kernellogcat_stamp(file_path: str) -> datetime | None:
    """从 kernellogcat-log.YYYYMMDD-HHMMSS 文件名解析时间。"""
    name = os.path.basename(file_path)
    m = _KERNELLOGCAT_RE.match(name)
    if not m:
        return None
    try:
        return datetime.strptime(f"{m.group(1)}-{m.group(2)}", "%Y%m%d-%H%M%S")
    except ValueError:
        return None


def get_kernellogcat_files(folder_path: str, recursive: bool = True) -> list[str]:
    """递归查找 kernellogcat-log.* 文件。"""
    found: list[str] = []
    if recursive:
        for root, _dirs, files in os.walk(folder_path):
            for file in files:
                if _KERNELLOGCAT_RE.match(file):
                    found.append(os.path.join(root, file))
    else:
        for file in os.listdir(folder_path):
            file_path = os.path.join(folder_path, file)
            if os.path.isfile(file_path) and _KERNELLOGCAT_RE.match(file):
                found.append(file_path)
    return found


def sort_files_by_filename_time(file_paths: list[str]) -> list[str]:
    """按文件名中的 YYYYMMDD-HHMMSS 升序排序；解析失败则回退 mtime。"""
    keyed: list[tuple[datetime, str]] = []
    for file_path in file_paths:
        stamp = parse_kernellogcat_stamp(file_path)
        if stamp is None:
            try:
                stamp = datetime.fromtimestamp(os.path.getmtime(file_path))
            except OSError:
                stamp = datetime.min
        keyed.append((stamp, file_path))
    keyed.sort(key=lambda x: x[0])
    return [path for _, path in keyed]


def _year_from_files(file_paths: list[str]) -> int:
    """取首个 kernellogcat 文件名中的年份；失败则用当前年。"""
    for file_path in file_paths:
        stamp = parse_kernellogcat_stamp(file_path)
        if stamp is not None:
            return stamp.year
    return datetime.now().year


def _parse_line_time(line: str, base_year: int) -> tuple[str, str] | None:
    """解析行首 MM-DD HH:MM:SS[.mmm]，返回 (full_time_str, time_part YYYY-MM-DD HH:MM:SS)。"""
    m = _LINE_TIME_RE.match(line.strip())
    if not m:
        return None
    mmdd_hms = m.group(1)
    try:
        dt = datetime.strptime(f"{base_year}-{mmdd_hms}", "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    time_part = dt.strftime("%Y-%m-%d %H:%M:%S")
    # 保留原始小数秒（若有）用于排序
    frac = ""
    rest = line.strip()[len(mmdd_hms) :]
    frac_m = re.match(r"(\.\d+)", rest)
    if frac_m:
        frac = frac_m.group(1)
    time_str = f"{time_part}{frac}"
    return time_str, time_part


def search_keyword_in_files(
    files: list[str],
    keyword: str = KEYWORD,
    start_time: str | None = None,
    end_time: str | None = None,
) -> dict:
    """在合并后的 kernellogcat 流中搜索关键字并解析负载/PID/包名。"""
    total_matches = 0
    matches: list[tuple[str, str]] = []
    cpus_usage_matches: list[tuple[str, str, str]] = []
    thread_load_matches: list[tuple[str, str, str, str, str]] = []
    file_info: list[tuple[str, int]] = []

    start_dt = None
    end_dt = None
    if start_time:
        try:
            start_dt = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
    if end_time:
        try:
            end_dt = datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass

    base_year = _year_from_files(files)

    for file_path in files:
        file_matches = 0
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as file:
                for line in file:
                    if keyword not in line:
                        continue

                    parsed = _parse_line_time(line, base_year)
                    if not parsed:
                        continue
                    time_str, time_part = parsed

                    if start_dt or end_dt:
                        try:
                            current_dt = datetime.strptime(time_part, "%Y-%m-%d %H:%M:%S")
                            if start_dt and current_dt < start_dt:
                                continue
                            if end_dt and current_dt > end_dt:
                                continue
                        except ValueError:
                            pass

                    load_m = _LOAD_LINE_RE.search(line)
                    if not load_m:
                        # 命中关键字但非负载行（如表头），仍计入匹配便于排查
                        file_matches += 1
                        total_matches += 1
                        matches.append((time_str, line.strip()))
                        if "Usage" in line or "Cpus" in line:
                            cpus_usage_matches.append((time_str, time_part, line.strip()))
                        continue

                    load = f"{load_m.group(1)}%"
                    pid = load_m.group(2)
                    package_name = load_m.group(3)

                    file_matches += 1
                    total_matches += 1
                    formatted_line = f"{time_str} {load} {pid} {package_name}"
                    matches.append((time_str, formatted_line))
                    thread_load_matches.append(
                        (time_str, time_part, load, pid, package_name)
                    )
        except OSError:
            continue

        file_info.append((os.path.basename(file_path), file_matches))

    def get_time_key(item):
        time_str = item[0]
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(time_str, fmt)
            except ValueError:
                continue
        return datetime.min

    matches.sort(key=get_time_key)
    if cpus_usage_matches:
        cpus_usage_matches.sort(key=get_time_key)
    if thread_load_matches:
        thread_load_matches.sort(key=get_time_key)

    thread_load_by_package: dict[str, list[tuple[str, str, str, str]]] = {}
    for time_str, time_part, load, pid, package_name in thread_load_matches:
        if package_name and load and load not in ("0%", "0"):
            thread_load_by_package.setdefault(package_name, []).append(
                (time_str, time_part, load, pid)
            )

    package_stats: dict[str, dict] = {}
    for package_name, load_info in thread_load_by_package.items():
        total_load = 0.0
        valid_load_count = 0
        for _, _, load, _ in load_info:
            try:
                total_load += float(load.replace("%", ""))
                valid_load_count += 1
            except ValueError:
                pass
        avg_load = total_load / valid_load_count if valid_load_count > 0 else 0.0
        package_stats[package_name] = {"count": len(load_info), "avg_load": avg_load}

    def get_package_sort_key(item):
        package_name, load_info = item
        count = len(load_info)
        total_load = 0.0
        valid_load_count = 0
        for _, _, load, _ in load_info:
            try:
                total_load += float(load.replace("%", ""))
                valid_load_count += 1
            except ValueError:
                pass
        avg_load = total_load / valid_load_count if valid_load_count > 0 else 0.0
        return (-count, -avg_load)

    sorted_thread_load_by_package = dict(
        sorted(thread_load_by_package.items(), key=get_package_sort_key)
    )
    sorted_package_stats = dict(
        sorted(package_stats.items(), key=lambda x: (-x[1]["count"], -x[1]["avg_load"]))
    )

    return {
        "total_matches": total_matches,
        "matches": matches,
        "cpus_usage_matches": cpus_usage_matches,
        "thread_load_matches": thread_load_matches,
        "thread_load_by_package": sorted_thread_load_by_package,
        "package_stats": package_stats,
        "sorted_package_stats": sorted_package_stats,
        "file_info": file_info,
        "keyword": keyword,
        "base_year": base_year,
    }


def detect_anomaly_apps(thread_load_by_package, threshold=10.0, time_window_minutes=10):
    """检测异常应用

    判断标准（自适应阈值）：
    - 常规：在 time_window_minutes 时间窗口内，平均负载超过 threshold 的应用
    - 突发高负载：平均负载 > threshold×5 且持续 >3 分钟，或 > threshold×10 且持续 >1 分钟
    """
    anomaly_apps = []

    for package_name, load_info in thread_load_by_package.items():
        if not load_info:
            continue

        sorted_load_info = sorted(load_info, key=lambda x: x[0])
        n = len(sorted_load_info)

        i = 0
        while i < n:
            window_loads = []
            window_pids = set()
            window_start_time = None
            window_end_time = None
            j = i

            for j in range(i, n):
                time_str, time_part, load, pid = sorted_load_info[j]
                try:
                    load_value = float(load.replace("%", ""))
                except ValueError:
                    continue

                if j > i:
                    try:
                        prev_time_str = sorted_load_info[j - 1][1]
                        prev_dt = datetime.strptime(prev_time_str, "%Y-%m-%d %H:%M:%S")
                        current_dt = datetime.strptime(time_part, "%Y-%m-%d %H:%M:%S")
                        interval = (current_dt - prev_dt).total_seconds() / 60
                        if interval > 10:
                            break
                    except ValueError:
                        pass

                window_loads.append(load_value)
                window_pids.add(pid)

                if window_start_time is None:
                    window_start_time = time_part
                window_end_time = time_part

                if j > i:
                    try:
                        start_dt = datetime.strptime(
                            sorted_load_info[i][1], "%Y-%m-%d %H:%M:%S"
                        )
                        current_dt = datetime.strptime(time_part, "%Y-%m-%d %H:%M:%S")
                        duration = (current_dt - start_dt).total_seconds() / 60
                        if duration > time_window_minutes:
                            break
                    except ValueError:
                        pass

            if len(window_loads) >= 2:
                avg_load = sum(window_loads) / len(window_loads)
                max_load = max(window_loads)
                min_load = min(window_loads)

                try:
                    start_dt = datetime.strptime(window_start_time, "%Y-%m-%d %H:%M:%S")
                    end_dt = datetime.strptime(window_end_time, "%Y-%m-%d %H:%M:%S")
                    duration_minutes = (end_dt - start_dt).total_seconds() / 60
                except (ValueError, TypeError):
                    duration_minutes = 0

                print_density = (
                    len(window_loads) / (duration_minutes / 5) if duration_minutes > 0 else 0
                )

                is_anomalous = False
                if avg_load > threshold and print_density >= 1:
                    if duration_minutes > time_window_minutes:
                        is_anomalous = True
                    elif avg_load > threshold * 5 and duration_minutes > 3:
                        is_anomalous = True
                    elif avg_load > threshold * 10 and duration_minutes > 1:
                        is_anomalous = True

                if is_anomalous:
                    pid_list = list(window_pids)
                    main_pid = pid_list[0] if pid_list else "N/A"
                    anomaly_apps.append(
                        {
                            "package_name": package_name,
                            "pid": main_pid,
                            "duration": duration_minutes,
                            "start_time": window_start_time,
                            "end_time": window_end_time,
                            "avg_load": avg_load,
                            "max_load": max_load,
                            "min_load": min_load,
                            "print_count": len(window_loads),
                        }
                    )
                    i = j
                    continue

            i += 1

    return merge_continuous_anomalies(anomaly_apps)


def merge_continuous_anomalies(anomaly_apps):
    """合并连续的异常时间段。"""
    if not anomaly_apps:
        return anomaly_apps

    apps_by_package: dict[str, list] = {}
    for app in anomaly_apps:
        apps_by_package.setdefault(app["package_name"], []).append(app)

    merged_apps = []
    for package_name, apps in apps_by_package.items():
        sorted_apps = sorted(apps, key=lambda x: x["start_time"])
        i = 0
        while i < len(sorted_apps):
            current_app = sorted_apps[i]
            merged_segment = {
                "package_name": package_name,
                "pid": current_app["pid"],
                "duration": current_app["duration"],
                "start_time": current_app["start_time"],
                "end_time": current_app["end_time"],
                "avg_load": current_app["avg_load"],
                "max_load": current_app["max_load"],
                "min_load": current_app["min_load"],
                "segment_count": 1,
                "print_count": current_app.get("print_count", 0),
            }

            j = i + 1
            while j < len(sorted_apps):
                next_app = sorted_apps[j]
                if next_app["start_time"] == current_app["end_time"]:
                    merged_segment["end_time"] = next_app["end_time"]
                    merged_segment["duration"] += next_app["duration"]
                    merged_segment["segment_count"] += 1
                    merged_segment["print_count"] += next_app.get("print_count", 0)
                    merged_segment["max_load"] = max(
                        merged_segment["max_load"], next_app["max_load"]
                    )
                    merged_segment["min_load"] = min(
                        merged_segment["min_load"], next_app["min_load"]
                    )
                    total_load = (
                        merged_segment["avg_load"] * merged_segment["segment_count"]
                        + next_app["avg_load"]
                    )
                    merged_segment["avg_load"] = (
                        total_load / merged_segment["segment_count"]
                    )
                    current_app = next_app
                    j += 1
                else:
                    break

            merged_apps.append(merged_segment)
            i = j

    return merged_apps


def resolve_report_path(log_dir, output_dir=None, report_name="cpuinfo_q_report.txt"):
    """解析报告输出路径，默认落到 temp 工作区的 analysis/ 目录。"""
    safe_name = os.path.basename((report_name or "").strip()) or "cpuinfo_q_report.txt"
    repo_root = find_repo_root(__file__)

    if output_dir:
        target_dir = os.path.abspath(output_dir)
    else:
        workspace_dir = resolve_workspace_dir(log_dir, repo_root=repo_root)
        workspace_abs = os.path.abspath(workspace_dir)
        repo_temp = os.path.abspath(temp_root(repo_root))

        if workspace_abs != repo_temp and not workspace_abs.startswith(
            repo_temp + os.sep
        ):
            workspace_dir = jira_workspace_dir(
                repo_root, os.path.basename(os.path.abspath(log_dir))
            )

        target_dir = workspace_analysis(workspace_dir)

    os.makedirs(target_dir, exist_ok=True)
    return os.path.join(target_dir, safe_name)


def generate_report(result, report_path):
    """生成报告文件，包含按包名统计与异常应用检测。"""
    report_lines = []

    report_lines.append("=== Cpus Usage ===")
    if result["cpus_usage_matches"]:
        for _, time_part, cpus_usage_part in result["cpus_usage_matches"]:
            report_lines.append(f"{time_part} {cpus_usage_part}")
    else:
        report_lines.append("No Cpus Usage information found")
    report_lines.append("")

    report_lines.append("=== Package Statistics ===")
    if result["sorted_package_stats"]:
        report_lines.append(f"{'Package':<30} {'Load Print Count':<15} {'Avg Load':<10}")
        report_lines.append("-" * 55)
        for package_name, stats in result["sorted_package_stats"].items():
            report_lines.append(
                f"{package_name:<30} {stats['count']:<15} {stats['avg_load']:.2f}%"
            )
        report_lines.append("")

        if result["thread_load_by_package"]:
            for package_name, load_info in result["thread_load_by_package"].items():
                report_lines.append(f"=== Package: {package_name} ===")
                report_lines.append(f"{'Time':<20} {'Load':<10} {'PID':<10}")
                report_lines.append("-" * 40)
                for _, time_part, load, pid in load_info:
                    report_lines.append(f"{time_part:<20} {load:<10} {pid:<10}")
                report_lines.append("")
    else:
        report_lines.append("No thread load information found")

    anomaly_apps = detect_anomaly_apps(result["thread_load_by_package"])
    anomaly_apps = [
        app for app in anomaly_apps if "binder" not in app["package_name"].lower()
    ]
    merged_anomaly_apps = merge_continuous_anomalies(anomaly_apps)

    report_lines.append("")
    report_lines.append(
        "=== Anomaly Applications Detection (adaptive: >10%/10min, >50%/3min, >100%/1min) ==="
    )

    apps_by_package: dict[str, list] = {}
    for app in merged_anomaly_apps:
        apps_by_package.setdefault(app["package_name"], []).append(app)

    if apps_by_package:
        terminal_output = []
        terminal_output.append("\n" + "=" * 90)
        terminal_output.append(
            "Detected anomaly applications (adaptive threshold: >10%/10min, >50%/3min, >100%/1min):"
        )
        terminal_output.append("=" * 90)

        for package_name, apps in apps_by_package.items():
            total_duration = sum(app["duration"] for app in apps)
            pid = apps[0]["pid"]
            summary_line = (
                f"Package: {package_name}   PID: {pid}  "
                f"Total anomaly duration: {total_duration:.1f}min"
            )
            report_lines.append(summary_line)
            terminal_output.append(summary_line)

            report_lines.append("")
            report_lines.append(
                f"{'Duration':<12} {'Time Range':<30} {'Print Count':<12} "
                f"{'Avg Load':<10} {'Max Load':<10} {'Min Load':<10}"
            )
            report_lines.append("-" * 90)
            terminal_output.append("")
            terminal_output.append(
                f"{'Duration':<12} {'Time Range':<30} {'Print Count':<12} "
                f"{'Avg Load':<10} {'Max Load':<10} {'Min Load':<10}"
            )
            terminal_output.append("-" * 90)

            for app in apps:
                time_range = f"{app['start_time']} ~ {app['end_time']}"
                print_count = app.get("print_count", 0)
                detail_line = (
                    f"{app['duration']:.1f}min{'':<6} {time_range:<30} "
                    f"{print_count:<12} {app['avg_load']:.2f}%{'':<5} "
                    f"{app['max_load']:.2f}%{'':<5} {app['min_load']:.2f}%"
                )
                report_lines.append(detail_line)
                terminal_output.append(detail_line)

            report_lines.append("")
            terminal_output.append("")

        terminal_output.append("=" * 90)
        print("\n".join(terminal_output), flush=True)
    else:
        report_lines.append(
            "No anomaly applications detected (All apps avg load <= 10% or burst too short)"
        )
        print(
            "\nNo anomaly applications detected (All apps avg load <= 10% or burst too short)",
            flush=True,
        )

    try:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(report_lines))
    except OSError:
        pass
    return report_path


def main():
    """主函数（CLI模式）"""
    _setup_utf8_stdio()
    parser = argparse.ArgumentParser(description="高通平台 CPU 负载信息分析工具")
    parser.add_argument(
        "-d",
        "--directory",
        required=True,
        help="日志路径（含 kernellogcat-log.* 的目录，如 mobilelog/）",
    )
    parser.add_argument(
        "-t",
        "--time",
        nargs="*",
        metavar=("START_TIME", "END_TIME"),
        help="开始/结束时间（YYYY-MM-DD HH:MM:SS）；可只给 START 或空 START + END",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        help="报告输出目录；建议 temp/<DATE>/<JIRA_KEY>/analysis",
    )
    parser.add_argument(
        "--report-name",
        default="cpuinfo_q_report.txt",
        help="报告文件名，默认 cpuinfo_q_report.txt",
    )

    args = parser.parse_args()
    folder_path = os.path.normpath(args.directory.strip())

    if len(folder_path) > 250 and not folder_path.startswith("\\\\?\\"):
        folder_path = "\\\\?\\" + os.path.abspath(folder_path)

    start_time = None
    end_time = None
    if args.time:
        if len(args.time) == 1:
            start_time = args.time[0]
        elif len(args.time) >= 2:
            start_time = args.time[0] or None
            end_time = args.time[1]

    if not os.path.exists(folder_path):
        print(f"错误：路径不存在: {folder_path}")
        sys.exit(1)
    if not os.path.isdir(folder_path):
        print(f"错误：'{folder_path}' 不是有效的文件夹路径")
        sys.exit(1)

    kernel_files = get_kernellogcat_files(folder_path, recursive=True)
    if not kernel_files:
        print(f"错误：目录下未找到 kernellogcat-log.*: {folder_path}")
        sys.exit(1)

    sorted_files = sort_files_by_filename_time(kernel_files)
    result = search_keyword_in_files(
        sorted_files, KEYWORD, start_time, end_time
    )

    report_path = resolve_report_path(folder_path, args.output_dir, args.report_name)
    generate_report(result, report_path)
    print(f"\n详细报告已保存到: {report_path}", flush=True)


if __name__ == "__main__":
    main()
