"""STR4 驱动器件：电梯模式导入（QSensorTest 检测 elevator: elevator: transsion）。"""

import subprocess
from pathlib import Path

from utils.driver.qsensor_mode_check import (
    ELEVATOR_MODE_MARKER,
    ELEVATOR_MODE_SUPPORT_PROP,
    QSENSOR_PACKAGE,
    is_qsensor_installed,
    run_qsensor_mode_import_check,
)

QSENSOR_APK = (
    Path(__file__).resolve().parents[3] / "utils" / "driver" / "apk" / "QSensorTest.apk"
)


def _get_dut_device_id(device_info):
    dut_list = (device_info or {}).get("DUT") or []
    if not dut_list:
        return None, "未获取到测试机设备信息"
    dut_id = (dut_list[0].get("device_id") or "").strip()
    if not dut_id:
        return None, "测试机 device_id 为空"
    return dut_id, ""


def _ensure_qsensor_installed(device_id: str) -> tuple[bool, str]:
    if is_qsensor_installed(device_id):
        return True, ""
    if not QSENSOR_APK.is_file():
        return False, f"未找到 {QSENSOR_APK}，请将 QSensorTest.apk 放到 utils/driver/apk/"
    ret = subprocess.run(
        ["adb", "-s", device_id, "install", "-r", str(QSENSOR_APK)],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if ret.returncode == 0 and is_qsensor_installed(device_id):
        return True, ""
    detail = (ret.stderr or ret.stdout or "").strip()
    return False, detail or "adb install 失败"


def run(category=None, case_index=None, device_info=None, **context):
    step_update = context.get("step_update")
    manual_confirm = context.get("manual_confirm")
    device_info = device_info or context.get("device_info") or {}

    dut_id, error = _get_dut_device_id(device_info)
    if not dut_id:
        if callable(step_update):
            step_update(error)
        return {"status": "fail", "message": error}

    sub_steps = ""

    def on_step(label: str, ok: bool) -> None:
        nonlocal sub_steps
        sub_steps += f"\n{label}" + ("-成功" if ok else "-失败")
        if callable(step_update):
            step_update(sub_steps)

    def append_note(note: str) -> None:
        nonlocal sub_steps
        sub_steps += f"\n{note}"
        if callable(step_update):
            step_update(sub_steps)

    # case38 专用：未安装则先 adb install，再走公共检测（公共层不改）
    if is_qsensor_installed(dut_id):
        on_step("检查 QSensorTest 已安装", True)
    else:
        append_note(f"未安装 {QSENSOR_PACKAGE}，开始 adb install -r {QSENSOR_APK.name}")
        ok, detail = _ensure_qsensor_installed(dut_id)
        on_step(f"adb install -r {QSENSOR_APK.name}", ok)
        if not ok:
            return {"status": "fail", "message": f"安装 QSensorTest 失败：{detail}"}

    return run_qsensor_mode_import_check(
        dut_id,
        marker=ELEVATOR_MODE_MARKER,
        mode_label="电梯模式",
        support_prop=ELEVATOR_MODE_SUPPORT_PROP,
        on_step=on_step,
        append_note=append_note,
        manual_confirm=manual_confirm,
    )
