"""驱动周版本自检：陀螺仪工模检查 + SensorTest 传感器人工测试（QSensorTest）。"""

import subprocess
from pathlib import Path

from utils.driver.qsensor_mode_check import (
    GYRO_SENSOR_MARKER,
    launch_qsensor,
    tap_sensor_marker_in_ui,
)
from utils.driver.tranfacmode_config import (
    GYRO_ITEM_KEYWORDS,
    SENSOR,
    SENSOR_CALI_EXCLUDE_KEYWORDS,
)
from utils.driver.ui_tranfacmode import run_tranfacmode_group_items_test

QSENSOR_PACKAGE = "com.qualcomm.qti.sensors.qsensortest"
QSENSOR_ACTIVITY = (
    "com.qualcomm.qti.sensors.qsensortest/"
    "com.qualcomm.qti.sensors.ui.qsensortest.TabControl"
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


def _adb_run(device_id: str, *args: str, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["adb", "-s", device_id, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _is_package_installed(device_id: str, package: str) -> bool:
    ret = _adb_run(device_id, "shell", "pm", "path", package)
    return ret.returncode == 0 and "package:" in (ret.stdout or "")


def run(category=None, case_index=None, device_info=None, case_name=None, **context):
    step_update = context.get("step_update")
    operator_notify = context.get("operator_notify")
    manual_confirm = context.get("manual_confirm")
    result_dir = context.get("result_dir")
    device_info = device_info or context.get("device_info") or {}

    dut_id, error = _get_dut_device_id(device_info)
    if not dut_id:
        if callable(step_update):
            step_update(error)
        return {"status": "fail", "message": error}

    sub_steps = ""

    def begin_step(label: str) -> None:
        if callable(step_update):
            step_update(sub_steps + f"\n{label}")

    def on_step(label: str, ok: bool) -> None:
        nonlocal sub_steps
        sub_steps += f"\n{label}" + ("-成功" if ok else "-失败")
        if callable(step_update):
            step_update(sub_steps)

    def add_note(label: str) -> None:
        nonlocal sub_steps
        sub_steps += f"\n{label}"
        if callable(step_update):
            step_update(sub_steps)

    def prompt_gyro_calibration():
        operation_text = "请在 Sensor 工模列表中点击陀螺仪校准项，并按界面提示完成校准。"
        if callable(operator_notify):
            operator_notify(operation_text)
        add_note(f"需人工操作：{operation_text}")
        add_note("需人工确认")
        if not callable(manual_confirm):
            return {"status": "pending", "message": "需确认陀螺仪校准是否完成"}
        status = manual_confirm("请确认陀螺仪校准是否已完成。")
        on_step("确认陀螺仪校准完成", status == "pass")
        if status != "pass":
            return {"status": "fail", "message": "陀螺仪校准未确认完成"}
        return None

    gyro_result = run_tranfacmode_group_items_test(
        dut_id,
        SENSOR,
        (("陀螺仪", GYRO_ITEM_KEYWORDS, SENSOR_CALI_EXCLUDE_KEYWORDS),),
        group_label="陀螺仪",
        result_dir=result_dir,
        on_step=on_step,
        before_items=prompt_gyro_calibration,
    )
    if gyro_result["status"] != "pass":
        return {"status": gyro_result["status"], "message": gyro_result["message"]}

    begin_step(f"检查本地 {QSENSOR_APK}")
    apk_exists = QSENSOR_APK.is_file()
    on_step(f"检查本地 {QSENSOR_APK}", apk_exists)
    if not apk_exists:
        return {
            "status": "fail",
            "message": f"未找到 {QSENSOR_APK}，请将 QSensorTest.apk 放到 utils/driver/apk/ 目录",
        }

    begin_step(f"安装 {QSENSOR_APK}")
    install_ret = _adb_run(dut_id, "install", "-r", str(QSENSOR_APK))
    install_ok = install_ret.returncode == 0
    on_step(f"安装 {QSENSOR_APK}", install_ok)
    if not install_ok:
        detail = (install_ret.stderr or install_ret.stdout or "").strip()
        return {
            "status": "fail",
            "message": f"安装 {QSENSOR_APK} 失败：{detail or '未知错误'}",
        }

    begin_step("校验 QSensorTest 已安装")
    installed_ok = _is_package_installed(dut_id, QSENSOR_PACKAGE)
    on_step("校验 QSensorTest 已安装", installed_ok)
    if not installed_ok:
        return {"status": "fail", "message": "安装后未检测到 QSensorTest 应用"}

    begin_step("启动 QSensorTest 主界面")
    start_ok, start_detail = launch_qsensor(dut_id)
    on_step("启动 QSensorTest 主界面", start_ok)
    if not start_ok:
        return {
            "status": "fail",
            "message": f"启动 QSensorTest 失败：{start_detail or '未知错误'}",
        }

    begin_step(f"滑动列表并点击 {GYRO_SENSOR_MARKER}")
    gyro_ok = tap_sensor_marker_in_ui(dut_id, GYRO_SENSOR_MARKER)
    on_step(f"滑动列表并点击 {GYRO_SENSOR_MARKER}", gyro_ok)
    if not gyro_ok:
        return {
            "status": "fail",
            "message": f"未找到或无法点击 {GYRO_SENSOR_MARKER}",
        }

    manual_steps = (
        "进入陀螺仪测试页面，移动设备并观察数值/曲线是否正常",
    )
    for step_text in manual_steps:
        if callable(operator_notify):
            operator_notify(step_text)
        add_note(f"需人工操作：{step_text}")
    add_note("需人工评判")
    if callable(manual_confirm):
        status = manual_confirm("请根据传感器测试现象评判本用例是否通过。")
        return {"status": status, "message": f"人工评判{status}"}
    return {"status": "pending", "message": "需人工评判"}
