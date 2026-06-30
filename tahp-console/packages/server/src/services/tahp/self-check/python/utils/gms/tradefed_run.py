from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

PYTHON_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TOOL_DIRNAME = "gms_{suite}"
TRADEFED_SCRIPT = {
    "cts": "cts-tradefed",
    "gts": "gts-tradefed",
    "vts": "vts-tradefed",
}


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


def _bundled_tool_root(suite: str) -> Path:
    return PYTHON_ROOT / "tools" / DEFAULT_TOOL_DIRNAME.format(suite=suite)


def _launcher_candidates_in_tools_dir(tools_dir: Path, suite: str) -> list[Path]:
    script_name = TRADEFED_SCRIPT.get(suite, f"{suite}-tradefed")
    return [tools_dir / script_name]


def _resolve_launcher_file(path: Path, suite: str) -> Path | None:
    resolved = path.expanduser()
    if resolved.is_dir():
        for candidate in _launcher_candidates_in_tools_dir(resolved / "tools", suite):
            if candidate.is_file():
                return candidate.resolve()
        return None

    if resolved.is_file():
        return resolved.resolve()
    return None


def resolve_launcher(suite: str, device_info: dict | None) -> Path | None:
    info = device_info or {}
    configured_paths = info.get("gmsTradefedPath")
    if not isinstance(configured_paths, dict):
        configured_paths = info.get("gmsTradefedRoot")
    if isinstance(configured_paths, dict):
        custom = configured_paths.get(suite)
        if custom:
            launcher = _resolve_launcher_file(Path(str(custom)), suite)
            if launcher is not None:
                return launcher

    tools_dir = _bundled_tool_root(suite) / "tools"
    for candidate in _launcher_candidates_in_tools_dir(tools_dir, suite):
        if candidate.is_file():
            return candidate.resolve()
    return None


def resolve_suite_root(launcher: Path) -> Path:
    if launcher.parent.name == "tools":
        return launcher.parent.parent
    return launcher.parent


def _bundled_subplans_dir(suite: str) -> Path:
    return _bundled_tool_root(suite) / "subplans"


def _ensure_subplan(suite_root: Path, suite: str, subplan: str) -> Path | None:
    """确保 subplan XML 存在于套件根目录 subplans/ 下。"""
    subplan_file = f"{subplan}.xml" if not subplan.endswith(".xml") else subplan
    target = suite_root / "subplans" / subplan_file
    if target.is_file():
        return target

    bundled = _bundled_subplans_dir(suite) / subplan_file
    if bundled.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(bundled, target)
        return target
    return None


def format_tradefed_command(
    launcher: Path, suite: str, subplan_name: str, serial: str
) -> str:
    return f"{launcher.name} run {suite} --subplan {subplan_name} -s {serial}"


def _build_tradefed_cmd(
    launcher: Path, suite: str, subplan_name: str, serial: str
) -> list[str]:
    args = ["run", suite, "--subplan", subplan_name, "-s", serial]
    return [str(launcher), *args]


def run_gms_subplan(
    suite: str,
    subplan: str,
    device_info: dict | None = None,
    step_update=None,
) -> dict:
    suite = str(suite).strip().lower()
    subplan = str(subplan).strip()
    if suite not in TRADEFED_SCRIPT:
        return {
            "status": "fail",
            "message": f"不支持的 GMS 套件: {suite}",
            "full_automation": True,
        }

    info = device_info or {}
    serial = _device_serial(info)
    launcher = resolve_launcher(suite, info)
    if launcher is None:
        script_name = TRADEFED_SCRIPT[suite]
        return {
            "status": "fail",
            "message": (
                f"未配置或未找到 {script_name}，请在 GMS 测试设置中填写 "
                f"gmsTradefedPath.{suite}（Linux 环境下 {script_name} 的完整路径）"
            ),
            "full_automation": True,
        }

    suite_root = resolve_suite_root(launcher)
    subplan_path = _ensure_subplan(suite_root, suite, subplan)
    if subplan_path is None:
        return {
            "status": "fail",
            "message": (
                f"subplan 不存在: {subplan}（期望 {suite_root / 'subplans'}，"
                f"或仓库内置 {_bundled_subplans_dir(suite)})"
            ),
            "full_automation": True,
        }

    steps: list[str] = []

    def add_step(text: str) -> None:
        steps.append(text)
        if step_update:
            step_update("\n".join(steps))

    subplan_name = subplan[:-4] if subplan.endswith(".xml") else subplan
    add_step(f"准备执行 {suite.upper()} subplan={subplan_name}，设备: {serial}")
    add_step(f"{TRADEFED_SCRIPT[suite]}: {launcher}")
    add_step(f"工作目录: {suite_root}")
    cmd = _build_tradefed_cmd(launcher, suite, subplan_name, serial)
    add_step(f"命令: {format_tradefed_command(launcher, suite, subplan_name, serial)}")

    log_dir = suite_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{suite}_{subplan_name}_{serial}.log"

    try:
        with log_path.open("w", encoding="utf-8") as log_file:
            proc = subprocess.Popen(
                cmd,
                cwd=str(suite_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            assert proc.stdout is not None
            for line in proc.stdout:
                log_file.write(line)
                stripped = line.strip()
                if stripped:
                    tail = stripped if len(stripped) <= 240 else stripped[-240:]
                    if len(steps) > 1 and steps[-1].startswith("…"):
                        steps[-1] = f"…{tail}"
                    else:
                        add_step(f"…{tail}")
            return_code = proc.wait()
    except Exception as exc:
        add_step(f"{suite.upper()} 执行异常-失败")
        return {
            "status": "fail",
            "message": str(exc),
            "full_automation": True,
        }

    tail = ""
    try:
        log_text = log_path.read_text(encoding="utf-8", errors="replace")
        tail = log_text.strip()[-2000:]
    except OSError:
        pass

    if return_code == 0:
        add_step(f"{suite.upper()} subplan {subplan_name} 通过-成功")
        return {
            "status": "pass",
            "message": tail or f"{suite.upper()} {subplan_name} 执行完成",
            "full_automation": True,
        }

    add_step(f"{suite.upper()} subplan {subplan_name} 失败-失败")
    return {
        "status": "fail",
        "message": tail or f"退出码: {return_code}",
        "full_automation": True,
    }
