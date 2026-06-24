"""驱动周版本自检：光感功能（复用 case22 光感校准与测试结果 + 自动背光人工确认）。"""

import subprocess

from utils.driver.sensor_items_result import run_reuse_sensor_items_item
from utils.driver.tranfacmode_config import LIGHT_SENSOR_ITEM_KEYWORDS


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

    cali_result = run_reuse_sensor_items_item(
        context,
        LIGHT_SENSOR_ITEM_KEYWORDS,
        item_label="光感校准",
        step_update=on_reuse_step,
        item_source="cali_items",
    )
    if cali_result["status"] != "pass":
        return cali_result

    test_result = run_reuse_sensor_items_item(
        context,
        LIGHT_SENSOR_ITEM_KEYWORDS,
        item_label="光感",
        step_update=on_reuse_step,
        item_source="items",
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

    auto_brightness_ret = _adb_run(
        dut_id,
        "shell",
        "settings",
        "put",
        "system",
        "screen_brightness_mode",
        "1",
    )
    on_step("开启自动背光", auto_brightness_ret.returncode == 0)
    if auto_brightness_ret.returncode != 0:
        return {"status": "fail", "message": "开启自动背光失败"}

    operation_text = (
        "已返回桌面并开启自动背光，请在不同环境光下观察屏幕背光是否随光强变化"
        "（如遮挡/照射光感区域、移动至明暗环境等）。"
    )
    if callable(operator_notify):
        operator_notify(operation_text)
    sub_steps += f"\n需人工操作：{operation_text}\n需人工评判"
    update(sub_steps)
    if callable(manual_confirm):
        status = manual_confirm(
            "请确认：开启自动背光后，在不同环境光下，屏幕背光会随着光强而改变。"
        )
        auto_msg = f"人工评判{status}"
        return {
            "status": status,
            "message": f"{cali_result['message']}; {test_result['message']}; {auto_msg}",
        }
    return {"status": "pending", "message": "需人工评判"}
