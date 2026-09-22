"""monkey结果检查：汇总 /data/TNE/0xffff 下 KE/NE 等异常 log。

流程：
1. adb ls /data/TNE/0xffff，按 tne 类型（0xffffffXX 前缀）统计各类型数量；
2. adb pull 全部 0xffffff39（native crash）tne 文件，用内置纯 Python
   tne_parser（tools/stability_checker/tne_parser.py）逐一解压；
3. 读取每个解压内容中的 android_crash_log，截断提取摘要，写入 result.json
   （供 BFF/Node 侧做 AI 模块归类并合成最终汇报）。

本用例「始终 pass 仅汇报」：发现 KE/NE 异常不影响判定；
仅 ADB 不可用 / 无权限读取目录等执行环境错误返回 fail。
"""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

TNE_REMOTE_DIR = "/data/TNE/0xffff"
NATIVE_CRASH_PREFIX = "0xffffff39"
TNE_TYPE_LABELS = {
    "0xffffff39": "native crash",
    "0xffffff04": "KE",
    "0xffffff0d": "HWT",
    "0xffffff0c": "HANG",
    "0xffffff12": "OOM",
    "0xffffff15": "OCP_REBOOT",
}
_TNE_PREFIX_RE = re.compile(r"^(0x[0-9a-fA-F]+)")
_CRASH_EXCERPT_MAX_CHARS = 4096
# 单次最多拉取/解压的 native crash 条数，防止极端情况下超时
_MAX_PULL = 50
_PULL_TIMEOUT_SECONDS = 300


def _device_serial(device_info: dict) -> str:
    dut = device_info.get("DUT") if isinstance(device_info, dict) else None
    if isinstance(dut, list) and dut:
        serial = dut[0].get("device_id") or dut[0].get("deviceId")
        if serial:
            return str(serial)
    if isinstance(device_info, dict):
        serial = device_info.get("deviceId") or device_info.get("device_id")
        if serial:
            return str(serial)
    raise ValueError("缺少测试机设备序列号")


def _adb(serial: str, args: list[str], timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["adb", "-s", serial, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def _load_tne_parser():
    script = (
        Path(__file__).resolve().parents[3]
        / "tools"
        / "stability_checker"
        / "tne_parser.py"
    )
    spec = importlib.util.spec_from_file_location("tne_parser_tool", script)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 tne_parser: {script}")
    module = importlib.util.module_from_spec(spec)
    # tne_parser 使用 @dataclass，Python 3.12+ 要求模块先注册进 sys.modules 再 exec
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _resolve_work_dir(info: dict) -> Path:
    result_dir = str(info.get("resultDir") or "").strip()
    if result_dir:
        return Path(result_dir) / "monkey_check"
    return Path(tempfile.mkdtemp(prefix="monkey_check_"))


def _format_counts(counts: dict[str, int]) -> str:
    parts: list[str] = []
    for prefix, label in TNE_TYPE_LABELS.items():
        count = counts.get(prefix, 0)
        if count > 0:
            parts.append(f"{label} {count}次")
    for prefix, count in counts.items():
        if prefix not in TNE_TYPE_LABELS and count > 0:
            parts.append(f"{prefix} {count}次")
    return "，".join(parts)


def _write_result_json(work_root: Path, payload: dict) -> None:
    try:
        work_root.mkdir(parents=True, exist_ok=True)
        (work_root / "result.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass


def run(device_info=None, step_update=None, **_context):
    info = device_info or {}
    serial = _device_serial(info)

    steps: list[str] = []

    def add_step(text: str) -> None:
        steps.append(text)
        if step_update:
            step_update("\n".join(steps))

    work_root = _resolve_work_dir(info)

    add_step(f"开始 monkey 结果检查，设备: {serial}")
    add_step(f"读取 {TNE_REMOTE_DIR} 目录")
    try:
        proc = _adb(serial, ["shell", "ls", "-1", TNE_REMOTE_DIR])
    except FileNotFoundError:
        add_step("未找到 adb，请确认 ADB 已安装并加入 PATH-失败")
        return {"status": "fail", "message": "未找到 adb", "full_automation": True}
    except Exception as exc:
        add_step(f"adb 执行异常: {exc}-失败")
        return {"status": "fail", "message": f"adb 执行异常: {exc}", "full_automation": True}

    listing = (proc.stdout or "").strip()
    err_text = f"{proc.stderr or ''}\n{listing}"
    lowered = err_text.lower()
    device_lost = (
        ("not found" in lowered and "device" in lowered)
        or "offline" in lowered
        or "no devices" in lowered
        or "unauthorized" in lowered
    )
    if device_lost:
        add_step(f"设备 {serial} 未连接或不在线，请检查 ADB 连接-失败")
        return {
            "status": "fail",
            "message": f"设备 {serial} 未连接或不在线",
            "full_automation": True,
        }
    if "Permission denied" in err_text:
        add_step(f"无权限读取 {TNE_REMOTE_DIR}，请确认设备已 root-失败")
        return {
            "status": "fail",
            "message": f"无权限读取 {TNE_REMOTE_DIR}（需要 root 权限）",
            "full_automation": True,
        }
    if proc.returncode != 0 or "No such file or directory" in err_text:
        add_step(f"{TNE_REMOTE_DIR} 不存在或为空，未发现异常 log-成功")
        _write_result_json(work_root, {
            "version": 1,
            "tne_remote_dir": TNE_REMOTE_DIR,
            "counts": {},
            "native_crashes": [],
            "errors": [],
        })
        return {
            "status": "pass",
            "message": f"未发现 KE/NE 等异常 log（{TNE_REMOTE_DIR} 不存在或为空）",
            "full_automation": True,
        }

    names = [line.strip() for line in listing.splitlines() if line.strip()]
    counts: dict[str, int] = {}
    native_files: list[str] = []
    for name in names:
        match = _TNE_PREFIX_RE.match(name)
        if not match:
            continue
        prefix = match.group(1).lower()
        counts[prefix] = counts.get(prefix, 0) + 1
        if prefix == NATIVE_CRASH_PREFIX and name.lower().endswith(".tne"):
            native_files.append(name)

    summary = _format_counts(counts)
    if not summary:
        add_step(f"{TNE_REMOTE_DIR} 下未发现 KE/NE 等异常 log-成功")
        _write_result_json(work_root, {
            "version": 1,
            "tne_remote_dir": TNE_REMOTE_DIR,
            "counts": {},
            "native_crashes": [],
            "errors": [],
        })
        return {
            "status": "pass",
            "message": "未发现 KE/NE 等异常 log",
            "full_automation": True,
        }

    add_step(f"发现异常 log：{summary}")

    native_crashes: list[dict] = []
    errors: list[str] = []
    parser = None
    if native_files:
        try:
            parser = _load_tne_parser()
        except Exception as exc:
            errors.append(f"tne_parser 加载失败: {exc}")

    pull_dir = work_root / "tne_pulled"
    crash_dir = work_root / "android_crash_log"
    if native_files:
        pull_dir.mkdir(parents=True, exist_ok=True)

    for index, name in enumerate(native_files[:_MAX_PULL], start=1):
        add_step(f"解压 native crash ({index}/{min(len(native_files), _MAX_PULL)}): {name}")
        entry = {
            "tne_name": name,
            "crash_log_found": False,
            "excerpt": "",
            "excerpt_truncated": False,
            "crash_log_path": "",
            "decompress_error": "",
        }
        local_tne = pull_dir / name
        try:
            pull = _adb(serial, ["pull", f"{TNE_REMOTE_DIR}/{name}", str(local_tne)], timeout=_PULL_TIMEOUT_SECONDS)
            if pull.returncode != 0 or not local_tne.is_file():
                detail = (pull.stderr or pull.stdout or "").strip()[-200:]
                entry["decompress_error"] = f"adb pull 失败: {detail}"
        except Exception as exc:
            entry["decompress_error"] = f"adb pull 异常: {exc}"

        if not entry["decompress_error"]:
            if parser is None:
                entry["decompress_error"] = "tne_parser 不可用"
            else:
                try:
                    parsed = parser.parse_tne(str(local_tne))
                    crash_file = parsed.find_file_containing("android_crash_log")
                    if crash_file is None:
                        entry["decompress_error"] = "解压内容中未找到 android_crash_log"
                    else:
                        text = crash_file.data.decode("utf-8", errors="replace")
                        entry["crash_log_found"] = True
                        entry["excerpt"] = text[:_CRASH_EXCERPT_MAX_CHARS]
                        entry["excerpt_truncated"] = len(text) > _CRASH_EXCERPT_MAX_CHARS
                        try:
                            crash_dir.mkdir(parents=True, exist_ok=True)
                            crash_path = crash_dir / f"{Path(name).stem}.log"
                            crash_path.write_text(text, encoding="utf-8")
                            entry["crash_log_path"] = str(crash_path)
                        except OSError:
                            pass
                except ImportError as exc:
                    entry["decompress_error"] = str(exc)
                except Exception as exc:
                    entry["decompress_error"] = f"解压失败: {exc}"

        if entry["decompress_error"]:
            errors.append(f"{name}: {entry['decompress_error']}")
        native_crashes.append(entry)

    if len(native_files) > _MAX_PULL:
        errors.append(f"native crash 共 {len(native_files)} 条，仅处理前 {_MAX_PULL} 条")

    _write_result_json(work_root, {
        "version": 1,
        "tne_remote_dir": TNE_REMOTE_DIR,
        "counts": counts,
        "native_crashes": native_crashes,
        "errors": errors,
    })

    extracted = sum(1 for c in native_crashes if c["crash_log_found"])
    if extracted > 0:
        message = f"发现 {summary}\nnative crash 模块 AI 归类中…"
    elif native_files:
        message = f"发现 {summary}\n未能从 native crash tne 中提取 android_crash_log"
    else:
        message = f"发现 {summary}"

    add_step(f"结果汇总：{summary}-成功")
    return {"status": "pass", "message": message, "full_automation": True}
