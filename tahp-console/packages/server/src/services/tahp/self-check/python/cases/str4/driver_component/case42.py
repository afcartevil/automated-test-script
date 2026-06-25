"""STR4 驱动器件：开机工模指纹(屏下)（属性校验 + 校准人工确认 + 工模测试）。"""

import subprocess

from utils.driver.tranfacmode_config import (
    OPTICAL_FINGERPRINT_GROUP_ITEM_SPECS,
    OPTICAL_FINGERPRINT_GROUP_LABEL,
    OPTICAL_FINGERPRINT_SUPPORT_PROP,
    SENSOR,
)
from utils.driver.ui_tranfacmode import enter_group, run_tranfacmode_group_items_test


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


def _is_prop_supported(value: str) -> bool:
    val = (value or "").strip().lower()
    return bool(val) and val not in ("0", "false", "no", "off")


def run(category=None, case_index=None, device_info=None, **context):
    step_update = context.get("step_update")
    operator_notify = context.get("operator_notify")
    manual_confirm = context.get("manual_confirm")
    device_info = device_info or context.get("device_info") or {}
    sub_steps = ""

    def update(message: str) -> None:
        if callable(step_update):
            step_update(message)

    def on_step(label: str, ok: bool, result_label: str | None = None) -> None:
        nonlocal sub_steps
        suffix = result_label if result_label is not None else ("成功" if ok else "失败")
        sub_steps += f"\n{label}-{suffix}"
        update(sub_steps)

    def prompt_optical_fingerprint_calibration():
        nonlocal sub_steps
        operation_text = (
            "请在 Sensor 工模列表中自行选择屏下指纹校准项，并按界面提示完成校准；"
            "校准完成后请返回 Sensor 工模列表，再确认继续。"
        )
        if callable(operator_notify):
            operator_notify(operation_text)
        sub_steps += f"\n需人工操作：{operation_text}\n需人工确认"
        update(sub_steps)
        if not callable(manual_confirm):
            return {"status": "pending", "message": "需确认屏下指纹校准是否完成"}
        status = manual_confirm("请确认屏下指纹校准是否已完成并通过。")
        on_step("确认屏下指纹校准完成", status == "pass")
        if status != "pass":
            return {"status": "fail", "message": "屏下指纹校准未确认通过"}
        sensor_ready = enter_group(dut_id, SENSOR)
        on_step("校准后进入 Sensor 工模列表", sensor_ready)
        if not sensor_ready:
            return {"status": "fail", "message": "校准后进入 Sensor 工模列表失败"}
        return None

    dut_id, error = _get_dut_device_id(device_info)
    if not dut_id:
        update(error)
        return {"status": "fail", "message": error}

    prop_ret = _adb_run(dut_id, "shell", "getprop", OPTICAL_FINGERPRINT_SUPPORT_PROP)
    prop_ok = prop_ret.returncode == 0
    prop_val = (prop_ret.stdout or "").strip()
    on_step("读取屏下指纹支持属性", prop_ok)
    if prop_ok:
        sub_steps += f"\n屏下指纹支持属性值: {prop_val or '<空>'}"
    else:
        sub_steps += f"\n读取属性失败: {(prop_ret.stderr or '').strip() or '无错误输出'}"
    update(sub_steps)

    supported = _is_prop_supported(prop_val)
    if supported:
        on_step("属性确认支持屏下指纹", True)
    else:
        on_step("属性确认支持屏下指纹", False)
        sub_steps += "\n设备属性显示不支持屏下指纹，需人工二次确认"
        update(sub_steps)
        if callable(manual_confirm):
            confirm_status = manual_confirm(
                "设备属性显示不支持屏下指纹，请确认本项目是否支持屏下指纹功能。",
                pass_label="支持",
                fail_label="不支持",
            )
            on_step(
                "人工确认屏下指纹支持",
                confirm_status == "pass",
                "支持" if confirm_status == "pass" else "不支持",
            )
            if confirm_status != "pass":
                return {"status": "skip", "message": "设备不支持屏下指纹，已跳过"}
        else:
            return {"status": "pending", "message": "需确认设备是否支持屏下指纹"}

    fingerprint_result = run_tranfacmode_group_items_test(
        dut_id,
        SENSOR,
        OPTICAL_FINGERPRINT_GROUP_ITEM_SPECS,
        group_label=OPTICAL_FINGERPRINT_GROUP_LABEL,
        result_dir=context.get("result_dir"),
        on_step=on_step,
        before_items=prompt_optical_fingerprint_calibration,
    )
    return {
        "status": fingerprint_result["status"],
        "message": fingerprint_result["message"],
    }
