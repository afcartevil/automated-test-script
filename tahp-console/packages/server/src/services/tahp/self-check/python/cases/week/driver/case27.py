"""驱动周版本自检：开机工模指纹（侧边指纹属性校验 + 复用 case22 指纹工模测试结果）。"""

import subprocess

from utils.driver.sensor_items_result import run_reuse_sensor_items_item
from utils.driver.tranfacmode_config import (
    SIDE_FINGERPRINT_EXCLUDE_KEYWORDS,
    SIDE_FINGERPRINT_ITEM_KEYWORDS,
    SIDE_FINGERPRINT_SUPPORT_PROP,
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


def _is_prop_supported(value: str) -> bool:
    val = (value or "").strip().lower()
    return bool(val) and val not in ("0", "false", "no", "off")


def run(category=None, case_index=None, device_info=None, **context):
    step_update = context.get("step_update")
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

    prop_ret = _adb_run(dut_id, "shell", "getprop", SIDE_FINGERPRINT_SUPPORT_PROP)
    prop_ok = prop_ret.returncode == 0
    prop_val = (prop_ret.stdout or "").strip()
    on_step("读取侧边指纹支持属性", prop_ok)
    if prop_ok:
        sub_steps += f"\n侧边指纹支持属性值: {prop_val or '<空>'}"
    else:
        sub_steps += f"\n读取属性失败: {(prop_ret.stderr or '').strip() or '无错误输出'}"
    update(sub_steps)

    supported = _is_prop_supported(prop_val)
    if supported:
        on_step("属性确认支持侧边指纹", True)
    else:
        on_step("属性确认支持侧边指纹", False)
        sub_steps += "\n设备属性显示不支持侧边指纹，需人工二次确认"
        update(sub_steps)
        if callable(manual_confirm):
            confirm_status = manual_confirm(
                "设备属性显示不支持侧边指纹，请确认本项目是否支持侧边指纹功能。",
                pass_label="支持",
                fail_label="不支持",
            )
            on_step(
                "人工确认侧边指纹支持",
                confirm_status == "pass",
                "支持" if confirm_status == "pass" else "不支持",
            )
            if confirm_status != "pass":
                return {"status": "skip", "message": "设备不支持侧边指纹，已跳过"}
        else:
            return {"status": "pending", "message": "需确认设备是否支持侧边指纹"}

    return run_reuse_sensor_items_item(
        context,
        SIDE_FINGERPRINT_ITEM_KEYWORDS,
        item_label="指纹",
        step_update=on_reuse_step,
        item_source="items",
        exclude_keywords=SIDE_FINGERPRINT_EXCLUDE_KEYWORDS,
    )
