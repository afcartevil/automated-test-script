"""STR4 驱动器件：地磁功能（复用 case23 指南针工模测试结果 + 指南针应用人工确认）。"""

import subprocess

from utils.driver.sensor_items_result import run_reuse_sensor_items_item
from utils.driver.tranfacmode_config import COMPASS_ITEM_KEYWORDS

COMPASS_ACTIVITY = "com.transsion.compass/com.transsion.compass.CompassActivity"


def _get_dut_device_id(device_info):
    dut_list = (device_info or {}).get("DUT") or []
    if not dut_list:
        return None, "未获取到测试机设备信息"
    dut_id = (dut_list[0].get("device_id") or "").strip()
    if not dut_id:
        return None, "测试机 device_id 为空"
    return dut_id, ""


def _adb_run(device_id: str, *args: str, timeout: int = 15) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["adb", "-s", device_id, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _go_home(device_id: str) -> bool:
    ret = _adb_run(device_id, "shell", "input", "keyevent", "3")
    return ret.returncode == 0


def _launch_compass(device_id: str) -> bool:
    ret = _adb_run(
        device_id,
        "shell",
        "am",
        "start",
        "-n",
        COMPASS_ACTIVITY,
    )
    return ret.returncode == 0


def run(category=None, case_index=None, device_info=None, **context):
    step_update = context.get("step_update")
    operator_notify = context.get("operator_notify")
    manual_confirm = context.get("manual_confirm")
    device_info = device_info or context.get("device_info") or {}
    sub_steps = ""

    def update(message: str) -> None:
        if callable(step_update):
            step_update(message)

    def on_step(label: str, ok: bool) -> None:
        nonlocal sub_steps
        sub_steps += f"\n{label}" + ("-成功" if ok else "-失败")
        update(sub_steps)

    def on_reuse_step(message: str) -> None:
        nonlocal sub_steps
        if sub_steps and message.startswith("\n"):
            sub_steps += message
        else:
            sub_steps = message
        update(sub_steps)

    test_result = run_reuse_sensor_items_item(
        context,
        COMPASS_ITEM_KEYWORDS,
        item_label="指南针",
        step_update=on_reuse_step,
        item_source="items",
        source_case_index=23,
    )
    if test_result["status"] != "pass":
        return test_result

    dut_id, error = _get_dut_device_id(device_info)
    if not dut_id:
        update(error)
        return {"status": "fail", "message": error}

    home_ok = _go_home(dut_id)
    on_step("返回桌面", home_ok)
    if not home_ok:
        return {"status": "fail", "message": "返回桌面失败"}

    compass_ok = _launch_compass(dut_id)
    on_step("打开指南针应用", compass_ok)
    if not compass_ok:
        return {"status": "fail", "message": "打开指南针应用失败"}

    operation_text = "请观察指南针指向是否准确（可旋转手机对比实际方位）。"
    if callable(operator_notify):
        operator_notify(operation_text)
    sub_steps += f"\n需人工操作：{operation_text}\n需人工评判"
    update(sub_steps)
    if callable(manual_confirm):
        status = manual_confirm("请确认指南针指向是否准确。")
        return {
            "status": status,
            "message": f"{test_result['message']}; 人工评判{status}",
        }
    return {"status": "pending", "message": "需人工评判"}
