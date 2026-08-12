"""驱动周版本自检：超声距感（属性校验 + 工模距离传感器 + 通话贴耳灭屏人工确认）。"""

import subprocess

from utils.driver.tranfacmode_config import (
    PROXIMITY_SENSOR_EXCLUDE_KEYWORDS,
    PROXIMITY_SENSOR_ITEM_KEYWORDS,
    SENSOR,
)
from utils.driver.ui_tranfacmode import run_tranfacmode_group_items_test

ULTRASOUND_SUPPORT_PROP = "ro.tr_audio.ultrasound.support"


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


def _is_prop_supported(value: str) -> bool:
    val = (value or "").strip().lower()
    return bool(val) and val not in ("0", "false", "no", "off")


def _read_prop(device_id: str, prop: str) -> tuple[bool, str]:
    ret = _adb_run(device_id, "shell", "getprop", prop)
    if ret.returncode != 0:
        return False, (ret.stderr or ret.stdout or "").strip()
    return True, (ret.stdout or "").strip()


def _check_ultrasound_support(device_id: str) -> tuple[bool, str]:
    ok, value = _read_prop(device_id, ULTRASOUND_SUPPORT_PROP)
    if not ok:
        return False, f"{ULTRASOUND_SUPPORT_PROP}=读取失败({value or '未知错误'})"
    supported = _is_prop_supported(value)
    return supported, (
        f"{ULTRASOUND_SUPPORT_PROP}={value or '<空>'}"
        f"({'支持' if supported else '不支持'})"
    )


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

    dut_id, error = _get_dut_device_id(device_info)
    if not dut_id:
        update(error)
        return {"status": "fail", "message": error}

    home_ok = _go_home(dut_id)
    on_step("返回桌面", home_ok)
    if not home_ok:
        return {"status": "fail", "message": "返回桌面失败"}

    supported, prop_detail = _check_ultrasound_support(dut_id)
    on_step("读取超声距感支持属性", "读取失败" not in prop_detail)
    sub_steps += f"\n{prop_detail}"
    update(sub_steps)

    if supported:
        on_step("属性确认支持超声距感", True)
    else:
        on_step("属性确认支持超声距感", False)
        notice = "未找到超声距感属性，请判断是否支持超声距感"
        sub_steps += f"\n需人工确认：{notice}"
        update(sub_steps)
        if callable(manual_confirm):
            confirm_status = manual_confirm(
                notice,
                pass_label="支持",
                fail_label="不支持",
            )
            on_step(
                "人工确认超声距感支持",
                confirm_status == "pass",
                "支持" if confirm_status == "pass" else "不支持",
            )
            if confirm_status != "pass":
                return {"status": "skip", "message": "设备不支持超声距感，已跳过"}
        else:
            return {"status": "pending", "message": "需确认设备是否支持超声距感"}

    test_result = run_tranfacmode_group_items_test(
        dut_id,
        SENSOR,
        (("距离传感器", PROXIMITY_SENSOR_ITEM_KEYWORDS, PROXIMITY_SENSOR_EXCLUDE_KEYWORDS),),
        group_label="距离传感器",
        result_dir=context.get("result_dir"),
        on_step=on_step,
    )
    if test_result["status"] != "pass":
        return test_result

    home_ok = _go_home(dut_id)
    on_step("工模测试后返回桌面", home_ok)
    if not home_ok:
        return {"status": "fail", "message": "工模测试后返回桌面失败"}

    operation_text = (
        "请拨打电话并接听，然后将手机靠近耳朵确认是否灭屏，"
        "远离耳朵确认是否亮屏。"
    )
    if callable(operator_notify):
        operator_notify(operation_text)
    sub_steps += f"\n需人工操作：{operation_text}\n需人工评判"
    update(sub_steps)
    if callable(manual_confirm):
        status = manual_confirm(
            "请确认：通话接听后，靠近耳朵灭屏、远离耳朵亮屏是否正常。"
        )
        return {
            "status": status,
            "message": f"{test_result['message']}; 人工评判{status}",
        }
    return {"status": "pending", "message": "需人工评判"}
