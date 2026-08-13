"""Wireshark CLI（tshark / mergecap）发现、检测与可选自动安装。供同目录 wifi_data.py 使用。"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from datetime import datetime

WIRESHARK_ENV_HINTS = ("WIRESHARK_HOME", "WIRESHARK_DIR")
WIRESHARK_PACKAGE_ID = "WiresharkFoundation.Wireshark"
_AUTO_INSTALL_WIRESHARK = False
_WIRESHARK_DIR_HINT = ""
_WIRESHARK_INSTALL_ATTEMPTED = False


def _unique_keep_order(items):
    seen = set()
    result = []
    for item in items:
        if not item:
            continue
        norm = os.path.normcase(os.path.normpath(item))
        if norm in seen:
            continue
        seen.add(norm)
        result.append(item)
    return result


def _command_executable_name(command_name):
    if os.name == "nt" and not command_name.lower().endswith(".exe"):
        return f"{command_name}.exe"
    return command_name


def _prepend_to_path(dir_path):
    if not dir_path:
        return
    current = os.environ.get("PATH", "")
    parts = current.split(os.pathsep) if current else []
    norm_dir = os.path.normcase(os.path.normpath(dir_path))
    for part in parts:
        if part and os.path.normcase(os.path.normpath(part)) == norm_dir:
            return
    os.environ["PATH"] = f"{dir_path}{os.pathsep}{current}" if current else dir_path


def configure_wireshark_cli(*, auto_install=False, wireshark_dir=""):
    """配置 Wireshark CLI 的自动安装与安装目录提示。"""
    global _AUTO_INSTALL_WIRESHARK, _WIRESHARK_DIR_HINT
    _AUTO_INSTALL_WIRESHARK = auto_install
    _WIRESHARK_DIR_HINT = (wireshark_dir or "").strip()
    if _WIRESHARK_DIR_HINT:
        _prepend_to_path(_WIRESHARK_DIR_HINT)


def _wireshark_candidate_paths(command_name):
    exe_name = _command_executable_name(command_name)
    candidates = []

    resolved = shutil.which(command_name)
    if resolved:
        candidates.append(resolved)

    base_dirs = []
    if _WIRESHARK_DIR_HINT:
        base_dirs.append(_WIRESHARK_DIR_HINT)

    for env_name in WIRESHARK_ENV_HINTS:
        env_dir = os.environ.get(env_name, "").strip()
        if env_dir:
            base_dirs.append(env_dir)

    if os.name == "nt":
        program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        base_dirs.extend(
            [
                os.path.join(program_files, "Wireshark"),
                os.path.join(program_files_x86, "Wireshark"),
                os.path.join(local_app_data, "Programs", "Wireshark") if local_app_data else "",
            ]
        )

    for base_dir in _unique_keep_order(base_dirs):
        if not base_dir:
            continue
        candidates.append(os.path.join(base_dir, exe_name))
        if os.path.basename(base_dir).lower() != "wireshark":
            candidates.append(os.path.join(base_dir, "Wireshark", exe_name))

    return _unique_keep_order(candidates)


def resolve_command_path(command_name):
    resolved = shutil.which(command_name)
    if resolved:
        return resolved

    for candidate in _wireshark_candidate_paths(command_name):
        if os.path.isfile(candidate):
            _prepend_to_path(os.path.dirname(candidate))
            return shutil.which(command_name) or candidate
    return None


def _install_wireshark_cli():
    if os.name != "nt":
        return False, "当前仅支持 Windows 端使用 winget 自动安装 Wireshark。"

    winget = shutil.which("winget")
    if not winget:
        return False, "未找到 winget，无法自动安装 Wireshark。请先安装 App Installer 或手动安装 Wireshark。"

    print("检测到缺少 Wireshark CLI，尝试使用 winget 自动安装 Wireshark...")
    cmd = [
        winget,
        "install",
        "-e",
        "--id",
        WIRESHARK_PACKAGE_ID,
        "--accept-package-agreements",
        "--accept-source-agreements",
        "--silent",
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
    except Exception as exc:
        return False, f"调用 winget 安装失败: {exc}"

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        if not detail:
            detail = f"winget exit code={result.returncode}"
        return False, detail

    for required_cmd in ("tshark", "mergecap"):
        resolve_command_path(required_cmd)

    return True, (result.stdout or "").strip()


def require_command(command_name, purpose):
    """检查外部命令是否可用，不可用时打印可操作提示。"""
    global _WIRESHARK_INSTALL_ATTEMPTED

    command_path = resolve_command_path(command_name)
    if command_path:
        return command_path

    if _AUTO_INSTALL_WIRESHARK and not _WIRESHARK_INSTALL_ATTEMPTED:
        _WIRESHARK_INSTALL_ATTEMPTED = True
        ok, detail = _install_wireshark_cli()
        if not ok:
            print(f"自动安装 Wireshark 失败: {detail}")
        else:
            command_path = resolve_command_path(command_name)
            if command_path:
                print(f"Wireshark CLI 自动安装完成，已找到 `{command_name}`: {command_path}")
                return command_path

    extra_hint = ""
    if os.name == "nt":
        extra_hint = (
            " 可使用 `--auto-install-wireshark` 让脚本尝试用 winget 自动安装，"
            "或通过 `--wireshark-dir` 指定 Wireshark 安装目录。"
        )
    print(
        f"错误：未找到 `{command_name}` 命令，无法{purpose}。"
        f" 请安装 Wireshark 并确保 `{command_name}` 在 PATH 中。{extra_hint}"
    )
    return None


def wireshark_cli_status():
    """返回 tshark/mergecap 是否可用及解析到的路径（不打印错误）。"""
    return {
        cmd: resolve_command_path(cmd) for cmd in ("tshark", "mergecap")
    }


def wireshark_cli_preflight(*, auto_install=False, wireshark_dir="", quiet=False):
    """
    运行数传分析脚本前的主机工具检测。
    返回 (ok, message)。auto_install 仅 Windows+winget 时尝试安装 Wireshark。
    """
    configure_wireshark_cli(auto_install=auto_install, wireshark_dir=wireshark_dir)
    status = wireshark_cli_status()
    missing = [cmd for cmd, path in status.items() if not path]

    if missing and auto_install:
        ok, detail = _install_wireshark_cli()
        if not quiet:
            if ok:
                print("Wireshark CLI 自动安装完成。")
            else:
                print(f"Wireshark CLI 自动安装失败: {detail}")
        status = wireshark_cli_status()
        missing = [cmd for cmd, path in status.items() if not path]

    if not missing:
        lines = [f"OK: {cmd} -> {path}" for cmd, path in status.items() if path]
        return True, "\n".join(lines)

    lines = [f"MISSING: {cmd}" for cmd in missing]
    for cmd, path in status.items():
        if path:
            lines.append(f"OK: {cmd} -> {path}")
    hint = (
        "请安装 Wireshark（含命令行工具 tshark、mergecap），"
        "或将安装目录加入 PATH / 设置 WIRESHARK_HOME。"
    )
    if os.name == "nt":
        hint += " Windows 可加 --auto-install-wireshark 由 winget 安装。"
    else:
        hint += (
            " Linux/WSL 示例: sudo apt update && sudo apt install -y wireshark tshark"
            "（部分发行版包名为 wireshark-common；安装后执行 tshark -v 验证）。"
            " --auto-install-wireshark 仅 Windows 有效。"
        )
    return False, "\n".join(lines) + "\n" + hint


def convert_tshark_frame_time(time_str: str) -> str:
    """将 tshark frame.time 转为 YYYY-MM-DD HH:MM:SS（兼容 9 位纳秒小数）。"""
    time_str = (time_str or "").strip()
    if not time_str:
        return time_str

    if "T" in time_str:
        normalized = time_str.replace("000+0800", "+08:00")
        try:
            return datetime.fromisoformat(normalized).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass

    match = re.match(
        r"(\w{3}\s+\d{1,2},\s+\d{4}\s+\d{2}:\d{2}:\d{2})(?:\.(\d+))?",
        time_str,
    )
    if match:
        base = match.group(1)
        frac = (match.group(2) or "0")[:6].ljust(6, "0")
        for candidate, fmt in (
            (f"{base}.{frac}", "%b %d, %Y %H:%M:%S.%f"),
            (base, "%b %d, %Y %H:%M:%S"),
        ):
            try:
                return datetime.strptime(candidate, fmt).strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue

    return time_str


_resolve_command_path = resolve_command_path
_require_command = require_command
