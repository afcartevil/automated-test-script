"""STR4 驱动器件：距离传感器测试（按超声距感属性选择传感器1/2，复用 case23 校准与测试结果）。"""

import subprocess

from utils.driver.sensor_items_result import run_reuse_sensor_items_item
from utils.driver.tranfacmode_config import (
    PROXIMITY_SENSOR_2_ITEM_KEYWORDS,
    PROXIMITY_SENSOR_EXCLUDE_KEYWORDS,
    PROXIMITY_SENSOR_ITEM_KEYWORDS,
    ULTRASOUND_PROXIMITY_SUPPORT_PROP,
)

SOURCE_SENSOR_CASE_INDEX = 23


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
        exclude_keywords: tuple[str, ...] = ()
    else:
        on_step("判定使用距离传感器1", True)
        item_keywords = PROXIMITY_SENSOR_ITEM_KEYWORDS
        item_label = "距离传感器"
        exclude_keywords = PROXIMITY_SENSOR_EXCLUDE_KEYWORDS

    cali_result = run_reuse_sensor_items_item(
        context,
        item_keywords,
        item_label=item_label,
        step_update=on_reuse_step,
        item_source="cali_items",
        source_case_index=SOURCE_SENSOR_CASE_INDEX,
        exclude_keywords=exclude_keywords,
    )
    if cali_result["status"] != "pass":
        return cali_result

    test_result = run_reuse_sensor_items_item(
        context,
        item_keywords,
        item_label=item_label,
        step_update=on_reuse_step,
        item_source="items",
        source_case_index=SOURCE_SENSOR_CASE_INDEX,
        exclude_keywords=exclude_keywords,
    )
    if test_result["status"] != "pass":
        return test_result

    sensor_path = "距离传感器2" if supported else "距离传感器1"
    return {
        "status": "pass",
        "message": (
            f"距离传感器测试({sensor_path}): "
            f"{cali_result['message']}; {test_result['message']}"
        ),
    }
