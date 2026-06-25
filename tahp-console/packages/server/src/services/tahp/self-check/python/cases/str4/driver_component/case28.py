"""STR4 驱动器件：距离传感器测试（按超声距感属性选择传感器1/2，工模校准与测试）。"""

import subprocess

from utils.driver.tranfacmode_config import (
    PROXIMITY_SENSOR_2_ITEM_KEYWORDS,
    PROXIMITY_SENSOR_EXCLUDE_KEYWORDS,
    PROXIMITY_SENSOR_ITEM_KEYWORDS,
    SENSOR,
    SENSOR_CALI_EXCLUDE_KEYWORDS,
    ULTRASOUND_PROXIMITY_SUPPORT_PROP,
)
from utils.driver.ui_tranfacmode import run_tranfacmode_group_items_test


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


def _read_prop(device_id: str, prop: str) -> tuple[bool, str]:
    ret = _adb_run(device_id, "shell", "getprop", prop)
    if ret.returncode != 0:
        return False, (ret.stderr or ret.stdout or "").strip()
    return True, (ret.stdout or "").strip()


def _check_ultrasound_support(device_id: str) -> tuple[bool, str]:
    ok, value = _read_prop(device_id, ULTRASOUND_PROXIMITY_SUPPORT_PROP)
    if not ok:
        return False, (
            f"{ULTRASOUND_PROXIMITY_SUPPORT_PROP}=读取失败({value or '未知错误'})"
        )
    supported = _is_prop_supported(value)
    return supported, (
        f"{ULTRASOUND_PROXIMITY_SUPPORT_PROP}={value or '<空>'}"
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

    def on_step(label: str, ok: bool) -> None:
        nonlocal sub_steps
        sub_steps += f"\n{label}" + ("-成功" if ok else "-失败")
        update(sub_steps)

    dut_id, error = _get_dut_device_id(device_info)
    if not dut_id:
        update(error)
        return {"status": "fail", "message": error}

    supported, prop_detail = _check_ultrasound_support(dut_id)
    on_step("读取超声距感支持属性", True)
    sub_steps += f"\n{prop_detail}"
    update(sub_steps)

    if supported:
        on_step("判定使用距离传感器2", True)
        item_keywords = PROXIMITY_SENSOR_2_ITEM_KEYWORDS
        item_label = "距离传感器2"
        exclude_keywords = SENSOR_CALI_EXCLUDE_KEYWORDS
    else:
        on_step("判定使用距离传感器1", True)
        item_keywords = PROXIMITY_SENSOR_ITEM_KEYWORDS
        item_label = "距离传感器"
        exclude_keywords = (
            PROXIMITY_SENSOR_EXCLUDE_KEYWORDS + SENSOR_CALI_EXCLUDE_KEYWORDS
        )

    def prompt_proximity_calibration():
        nonlocal sub_steps
        operation_text = (
            f"请在 Sensor 工模列表中点击{item_label}校准项，并按界面提示完成校准。"
        )
        if callable(operator_notify):
            operator_notify(operation_text)
        sub_steps += f"\n需人工操作：{operation_text}\n需人工确认"
        update(sub_steps)
        if not callable(manual_confirm):
            return {"status": "pending", "message": f"需确认{item_label}校准是否完成"}
        status = manual_confirm(f"请确认{item_label}校准是否已完成。")
        on_step(f"确认{item_label}校准完成", status == "pass")
        if status != "pass":
            return {"status": "fail", "message": f"{item_label}校准未确认完成"}
        return None

    test_result = run_tranfacmode_group_items_test(
        dut_id,
        SENSOR,
        ((item_label, item_keywords, exclude_keywords),),
        group_label=item_label,
        result_dir=context.get("result_dir"),
        on_step=on_step,
        before_items=prompt_proximity_calibration,
    )
    if test_result["status"] != "pass":
        return test_result

    sensor_path = "距离传感器2" if supported else "距离传感器1"
    return {
        "status": "pass",
        "message": (
            f"距离传感器测试({sensor_path}): "
            f"{item_label}校准已确认完成; {test_result['message']}"
        ),
    }
