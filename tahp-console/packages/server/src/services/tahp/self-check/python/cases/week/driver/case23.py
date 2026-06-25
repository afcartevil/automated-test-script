"""驱动周版本自检：光感功能（工模光感校准与测试 + 自动背光人工确认）。"""

import subprocess
import time

from utils.driver.tranfacmode_config import (
    LIGHT_SENSOR_DATA_COLLECT_ITEM_LABEL,
    LIGHT_SENSOR_DATA_COLLECT_START_RAW_RID,
    LIGHT_SENSOR_GROUP_ITEM_SPECS,
    LIGHT_SENSOR_GROUP_LABEL,
    SENSOR,
)
from utils.driver.tranfacmode_ui import dump, tap_xml
from utils.driver.ui_tranfacmode import (
    close_tranfacmode,
    go_home,
    run_tranfacmode_group_items_test,
)


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


def _return_to_home_after_tranfacmode(device_id: str, on_step) -> bool:
    """工模测试结束后关闭工模并回桌面。"""
    closed = close_tranfacmode(device_id)
    on_step("关闭工模应用", closed)
    home_ok = go_home(device_id)
    on_step("返回桌面", home_ok)
    return closed and home_ok


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

    def prompt_light_sensor_calibration():
        nonlocal sub_steps
        operation_text = "请在 Sensor 工模列表中点击光感校准项，并按界面提示完成校准。"
        if callable(operator_notify):
            operator_notify(operation_text)
        sub_steps += f"\n需人工操作：{operation_text}\n需人工确认"
        update(sub_steps)
        if not callable(manual_confirm):
            return {"status": "pending", "message": "需确认光感校准是否完成"}
        status = manual_confirm("请确认光感校准是否已完成。")
        on_step("确认光感校准完成", status == "pass")
        if status != "pass":
            return {"status": "fail", "message": "光感校准未确认完成"}
        return None

    def tap_start_get_raw_on_data_collect(device_id: str) -> bool:
        """仅在「光感数据采集」子项进入后，点击 start_get_raw。"""
        time.sleep(0.8)
        for _ in range(6):
            xml = dump(device_id)
            if xml and tap_xml(
                device_id,
                xml,
                resource_id=LIGHT_SENSOR_DATA_COLLECT_START_RAW_RID,
            ):
                on_step("点击开始光感采集(start_get_raw)", True)
                return True
            time.sleep(0.5)
        on_step("点击开始光感采集(start_get_raw)", False)
        return False

    dut_id, error = _get_dut_device_id(device_info)
    if not dut_id:
        update(error)
        return {"status": "fail", "message": error}

    light_result = run_tranfacmode_group_items_test(
        dut_id,
        SENSOR,
        LIGHT_SENSOR_GROUP_ITEM_SPECS,
        group_label=LIGHT_SENSOR_GROUP_LABEL,
        result_dir=context.get("result_dir"),
        on_step=on_step,
        before_items=prompt_light_sensor_calibration,
        after_item_tap={
            LIGHT_SENSOR_DATA_COLLECT_ITEM_LABEL: tap_start_get_raw_on_data_collect,
        },
    )
    if light_result["status"] != "pass":
        return {"status": light_result["status"], "message": light_result["message"]}

    if not _return_to_home_after_tranfacmode(dut_id, on_step):
        return {"status": "fail", "message": "工模测试后返回桌面失败"}

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
            "message": f"{light_result['message']}; {auto_msg}",
        }
    return {"status": "pending", "message": "需人工评判"}
