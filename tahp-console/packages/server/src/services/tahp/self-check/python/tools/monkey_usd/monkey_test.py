#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Android Monkey test launcher used by TAHP self-check."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
BLACKLIST_FILE = SCRIPT_DIR / "MonkeyBlackList.txt"
# 旧版 state 位置（兼容 stop 清理旧版本启动的会话）
LEGACY_STATE_FILE = SCRIPT_DIR / ".monkey_state.json"
DEVICE_BLACKLIST_PATH = "/data/local/tmp/MonkeyBlackList.txt"


def _resolve_runtime_dir() -> Path:
    """monkey 运行时目录（state / 日志 / 子进程 cwd）。

    必须落在构建产物 dist/ 之外：watchdog 与 adb 是长驻守护进程，
    若 cwd 或打开的日志在 dist/server 下，Windows 会锁定该目录链，
    导致 EA 重新构建（rmSync dist/server）EPERM 失败。
    """
    injected = os.environ.get("TAHP_SELF_CHECK_RUNTIME_DIR", "").strip()
    if injected:
        return Path(injected) / "monkey"
    for env_name in ("TAHP_CONSOLE_HOME", "HERMES_WEB_UI_HOME"):
        raw = os.environ.get(env_name, "").strip()
        if raw:
            return Path(raw) / "self-check-runtime" / "monkey"
    return Path.home() / ".tahp-console" / "self-check-runtime" / "monkey"


RUNTIME_DIR = _resolve_runtime_dir()
STATE_FILE = RUNTIME_DIR / "monkey_state.json"
LOG_DIR = RUNTIME_DIR / "logs"
DEFAULT_DURATION = "7d"
MAX_DURATION_SECONDS = 14 * 24 * 3600
DEFAULT_THROTTLE_MS = 500
DEFAULT_EVENT_COUNT = 999999999


class AdbError(RuntimeError):
    pass


def run_adb(args: list[str], serial: str | None = None, timeout: int = 120) -> str:
    cmd = ["adb"]
    if serial:
        cmd += ["-s", serial]
    cmd += args
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired as exc:
        raise AdbError(f"adb 命令超时: {' '.join(cmd)}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or f"exit code {result.returncode}").strip()
        raise AdbError(f"adb 失败: {' '.join(cmd)}\n{detail}")
    return (result.stdout or "").strip()


def get_device_serial(serial: str | None) -> str:
    if serial:
        run_adb(["get-state"], serial=serial, timeout=10)
        return serial
    output = run_adb(["devices"], timeout=10)
    devices = []
    for line in output.splitlines()[1:]:
        parts = line.strip().split()
        if len(parts) >= 2 and parts[1] == "device":
            devices.append(parts[0])
    if not devices:
        raise AdbError("未检测到已连接的 Android 设备")
    if len(devices) > 1:
        raise AdbError(f"检测到多台设备: {', '.join(devices)}，请使用 -s 指定目标设备")
    return devices[0]


_DURATION_PATTERN = re.compile(r"^(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$", re.IGNORECASE)


def parse_duration(text: str) -> int:
    text = (text or "").strip().lower()
    if text.isdigit():
        total = int(text)
    else:
        match = _DURATION_PATTERN.match(text)
        if not match or not any(match.groups()):
            raise ValueError("无法解析时长，示例: 30m, 8h, 7d, 1d12h, 3600")
        days = int(match.group(1) or 0)
        hours = int(match.group(2) or 0)
        minutes = int(match.group(3) or 0)
        seconds = int(match.group(4) or 0)
        total = days * 86400 + hours * 3600 + minutes * 60 + seconds
    if total <= 0:
        raise ValueError("时长必须大于 0")
    if total > MAX_DURATION_SECONDS:
        raise ValueError("时长不能超过 14 天")
    return total


def format_duration(seconds: int) -> str:
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}天")
    if hours:
        parts.append(f"{hours}小时")
    if minutes:
        parts.append(f"{minutes}分钟")
    if seconds or not parts:
        parts.append(f"{seconds}秒")
    return "".join(parts)


def load_blacklist() -> list[str]:
    if not BLACKLIST_FILE.is_file():
        raise FileNotFoundError(f"黑名单文件不存在: {BLACKLIST_FILE}")
    packages = []
    seen = set()
    for line in BLACKLIST_FILE.read_text(encoding="utf-8").splitlines():
        pkg = line.strip()
        if not pkg or pkg.startswith("#") or pkg in seen:
            continue
        seen.add(pkg)
        packages.append(pkg)
    return packages


def push_blacklist(serial: str, packages: list[str]) -> None:
    local_tmp = RUNTIME_DIR / ".monkey_blacklist_push.tmp"
    local_tmp.write_text("\n".join(packages) + "\n", encoding="utf-8", newline="\n")
    try:
        run_adb(["push", str(local_tmp), DEVICE_BLACKLIST_PATH], serial=serial)
    finally:
        local_tmp.unlink(missing_ok=True)


def load_state() -> dict | None:
    for candidate in (STATE_FILE, LEGACY_STATE_FILE):
        if not candidate.is_file():
            continue
        try:
            return json.loads(candidate.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def clear_state() -> None:
    STATE_FILE.unlink(missing_ok=True)
    LEGACY_STATE_FILE.unlink(missing_ok=True)


def is_process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return str(pid) in result.stdout
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _query_monkey_pids(serial: str) -> list[str]:
    queries = [
        ["shell", "pidof", "com.android.commands.monkey"],
        ["shell", "pgrep", "-f", "com.android.commands.monkey"],
        ["shell", "pidof", "monkey"],
        ["shell", "pgrep", "-f", "monkey"],
    ]
    for args in queries:
        try:
            output = run_adb(args, serial=serial, timeout=10)
        except AdbError:
            continue
        pids = [p for p in re.split(r"\s+", output.strip()) if p.isdigit()]
        if pids:
            return pids
    return []


def is_monkey_running_on_device(serial: str) -> bool:
    return bool(_query_monkey_pids(serial))


def find_monkey_pid(serial: str) -> str | None:
    for _ in range(15):
        pids = _query_monkey_pids(serial)
        if pids:
            return pids[-1]
        time.sleep(0.5)
    return None


def build_monkey_adb_cmd(serial: str, throttle: int, seed: int | None, extra_args: list[str]) -> list[str]:
    cmd = [
        "adb",
        "-s",
        serial,
        "shell",
        "monkey",
        "--ignore-crashes",
        "--ignore-timeouts",
        "--ignore-security-exceptions",
        "--ignore-native-crashes",
        "--monitor-native-crashes",
        "--pct-syskeys",
        "0",
        "--throttle",
        str(throttle),
        "--pkg-blacklist-file",
        DEVICE_BLACKLIST_PATH,
        "-v",
        "-v",
        "-v",
    ]
    if seed is not None:
        cmd += ["-s", str(seed)]
    cmd += extra_args
    cmd.append(str(DEFAULT_EVENT_COUNT))
    return cmd


def start_monkey(
    serial: str,
    duration_seconds: int,
    throttle: int,
    seed: int | None,
    extra_args: list[str],
    save_log: bool,
) -> None:
    state = load_state()
    if state and is_monkey_running_on_device(state.get("serial", serial)):
        raise RuntimeError("Monkey 测试已在运行中，请先停止当前测试")

    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    packages = load_blacklist()
    print(f"已加载黑名单 {len(packages)} 个包名")
    push_blacklist(serial, packages)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    log_file = LOG_DIR / f"monkey_{now.strftime('%Y%m%d_%H%M%S')}.log" if save_log else None
    log_fp = log_file.open("w", encoding="utf-8", newline="\n") if log_file else None
    stdout_target = log_fp if log_fp else subprocess.DEVNULL
    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

    proc = subprocess.Popen(
        build_monkey_adb_cmd(serial, throttle, seed, extra_args),
        stdout=stdout_target,
        stderr=subprocess.STDOUT,
        cwd=str(RUNTIME_DIR),
        creationflags=creationflags,
    )
    monkey_pid = find_monkey_pid(serial)
    if not monkey_pid:
        proc.terminate()
        raise RuntimeError("Monkey 启动失败，未找到设备端 monkey 进程")

    end_time = now + timedelta(seconds=duration_seconds)
    watchdog_cmd = [
        sys.executable,
        str(Path(__file__).resolve()),
        "_watchdog",
        "--end-time",
        end_time.isoformat(),
        "--serial",
        serial,
    ]
    watchdog_log = LOG_DIR / "watchdog.log"
    watchdog_proc = subprocess.Popen(
        watchdog_cmd,
        stdout=watchdog_log.open("a", encoding="utf-8"),
        stderr=subprocess.STDOUT,
        cwd=str(RUNTIME_DIR),
        creationflags=creationflags,
    )

    state = {
        "serial": serial,
        "monkey_pid": monkey_pid,
        "adb_proc_pid": proc.pid,
        "watchdog_pid": watchdog_proc.pid,
        "start_time": now.isoformat(),
        "end_time": end_time.isoformat(),
        "duration_seconds": duration_seconds,
        "blacklist_count": len(packages),
        "save_log": save_log,
    }
    if log_file:
        state["log_file"] = str(log_file)
    save_state(state)

    print("Monkey 测试已启动")
    print(f"设备序列号: {serial}")
    print(f"Monkey PID: {monkey_pid}")
    print(f"测试时长: {format_duration(duration_seconds)}")
    print(f"预计结束: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    if log_file:
        print(f"本地日志: {log_file}")


def stop_monkey(from_watchdog: bool = False) -> None:
    state = load_state()
    serial = state.get("serial") if state else get_device_serial(None)
    if state and state.get("adb_proc_pid") and is_process_alive(int(state["adb_proc_pid"])):
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/PID", str(state["adb_proc_pid"]), "/T", "/F"], capture_output=True)
        else:
            os.kill(int(state["adb_proc_pid"]), 15)
    if is_monkey_running_on_device(serial):
        for pid in _query_monkey_pids(serial):
            try:
                run_adb(["shell", "kill", "-9", pid], serial=serial, timeout=10)
            except AdbError:
                pass
    if not from_watchdog and state and state.get("watchdog_pid") and is_process_alive(int(state["watchdog_pid"])):
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/PID", str(state["watchdog_pid"]), "/F"], capture_output=True)
        else:
            os.kill(int(state["watchdog_pid"]), 15)
    clear_state()
    print("Monkey 测试已停止。")


def show_status() -> None:
    state = load_state()
    if not state:
        print("当前没有 Monkey 测试记录。")
        return
    serial = state.get("serial", "")
    running = is_monkey_running_on_device(serial) if serial else False
    print(f"运行中: {'是' if running else '否'}")
    print(f"设备序列号: {serial}")
    print(f"预计结束: {state.get('end_time', '')}")


def run_watchdog(end_time_str: str, serial: str) -> None:
    end_time = datetime.fromisoformat(end_time_str)
    while datetime.now() < end_time:
        if not is_monkey_running_on_device(serial):
            clear_state()
            return
        time.sleep(3)
    if is_monkey_running_on_device(serial):
        stop_monkey(from_watchdog=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Android Monkey 测试管理工具")
    parser.add_argument("-s", "--serial", help="目标设备序列号")
    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start")
    start.add_argument("-d", "--duration", default=DEFAULT_DURATION)
    start.add_argument("--throttle", type=int, default=DEFAULT_THROTTLE_MS)
    start.add_argument("--seed", type=int, default=None)
    start.add_argument("--save-log", action="store_true")
    start.add_argument("extra", nargs="*")

    sub.add_parser("stop")
    sub.add_parser("status")
    watchdog = sub.add_parser("_watchdog")
    watchdog.add_argument("--end-time", required=True)
    watchdog.add_argument("--serial", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "_watchdog":
            run_watchdog(args.end_time, args.serial)
            return 0
        if args.command == "status":
            show_status()
            return 0
        serial = get_device_serial(args.serial)
        if args.command == "start":
            start_monkey(
                serial=serial,
                duration_seconds=parse_duration(args.duration),
                throttle=args.throttle,
                seed=args.seed,
                extra_args=args.extra,
                save_log=args.save_log,
            )
            return 0
        if args.command == "stop":
            stop_monkey()
            return 0
    except (AdbError, RuntimeError, ValueError, FileNotFoundError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
