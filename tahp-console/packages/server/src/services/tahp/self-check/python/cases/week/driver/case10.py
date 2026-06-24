"""驱动周版本自检：LCM 闪屏场景（屏下指纹工模校准 + 指纹录入）人工测试。"""

import subprocess

from utils.driver.tranfacmode_config import SENSOR
from utils.driver.tranfacmode_ui import dump, poll_bool, ui_has_keywords
from utils.driver.ui_tranfacmode import (
    enter_group,
    skip_rf_calibration,
    start_main,
    tranfacmode_prep_steps,
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


def _enter_sensor_group_list(dut_id: str, on_step) -> tuple[bool, str]:
    pre_steps = [
        *tranfacmode_prep_steps(dut_id),
        ("启动工模主界面", lambda: start_main(dut_id), "启动工模 MainActivity 失败"),
        ("跳过射频参数校准", lambda: skip_rf_calibration(dut_id), "跳过射频参数校准失败"),
        (
            "进入sensor工模列表",
            lambda: enter_group(dut_id, SENSOR),
            f"未找到测试组入口: {SENSOR.entry_keywords}",
        ),
        (
            "校验sensor工模界面",
            lambda: poll_bool(
                lambda: (xml := dump(dut_id)) is not None
                and ui_has_keywords(xml, SENSOR.page_keywords),
                8.0,
                0.35,
            ),
            f"未进入测试组界面: {SENSOR.page_keywords}",
        ),
    ]
    for label, action, fail_msg in pre_steps:
        ok = action()
        on_step(label, ok)
        if not ok:
            return False, fail_msg
    return True, ""


def run(category=None, case_index=None, device_info=None, **context):
    step_update = context.get("step_update")
    operator_notify = context.get("operator_notify")
    manual_confirm = context.get("manual_confirm")
    device_info = device_info or context.get("device_info") or {}

    dut_id, error = _get_dut_device_id(device_info)
    if not dut_id:
        if callable(step_update):
            step_update(error)
        return {"status": "fail", "message": error}

    sub_steps = ""

    def update(message: str) -> None:
        if callable(step_update):
            step_update(message)

    def on_step(label: str, ok: bool) -> None:
        nonlocal sub_steps
        sub_steps += f"\n{label}" + ("-成功" if ok else "-失败")
        update(sub_steps)

    prop_ret = _adb_run(
        dut_id, "shell", "getprop", "ro.tr_fingerprint.optical.feature.support"
    )
    prop_ok = prop_ret.returncode == 0
    prop_val = (prop_ret.stdout or "").strip()
    on_step("读取屏下指纹支持属性", prop_ok)
    if prop_ok:
        sub_steps += f"\n屏下指纹支持属性值: {prop_val or '<空>'}"
    else:
        sub_steps += f"\n读取属性失败: {(prop_ret.stderr or '').strip() or '无错误输出'}"

    supported = bool(prop_val and prop_val != "0")
    if supported:
        sub_steps += "\n设备声明支持屏下指纹"
    else:
        sub_steps += "\n设备属性显示不支持屏下指纹，请人工确认"
    update(sub_steps)

    if not supported:
        if callable(manual_confirm):
            status = manual_confirm(
                "设备属性显示不支持屏下指纹，请确认是否仍继续本用例。",
                pass_label="继续",
                fail_label="不继续",
            )
            sub_steps += f"\n人工确认是否继续本用例-{'继续' if status == 'pass' else '不继续'}"
            update(sub_steps)
            if status != "pass":
                return {"status": "skip", "message": "设备不支持屏下指纹，已跳过"}
        else:
            return {"status": "pending", "message": "需确认设备是否支持屏下指纹"}

    entered, enter_error = _enter_sensor_group_list(dut_id, on_step)
    if not entered:
        return {"status": "fail", "message": enter_error}

    cali_text = (
        "请在 Sensor 工模列表中找到指纹相关校准项。"
    )
    if callable(operator_notify):
        operator_notify(cali_text)
    sub_steps += f"\n需人工操作：{cali_text}\n需人工评判"
    update(sub_steps)
    if callable(manual_confirm):
        cali_status = manual_confirm("请确认指纹工模校准是否成功。")
        on_step("确认指纹工模校准", cali_status == "pass")
        if cali_status != "pass":
            return {"status": "fail", "message": "指纹工模校准未通过"}
    else:
        return {"status": "pending", "message": "需确认指纹工模校准是否成功"}

    start_ret = _adb_run(
        dut_id,
        "shell",
        "am",
        "start",
        "-n",
        "com.android.settings/com.transsion.settings.fpmanager.TranFpPwdGuide",
    )
    on_step("进入指纹设置界面", start_ret.returncode == 0)
    if start_ret.returncode != 0:
        return {"status": "fail", "message": "进入指纹设置界面失败"}

    flash_text = "录入一个指纹；灭屏后持续触摸指纹区域，观察是否出现 LCM 闪屏。"
    if callable(operator_notify):
        operator_notify(flash_text)
    sub_steps += f"\n需人工操作：{flash_text}\n需人工评判"
    update(sub_steps)
    if callable(manual_confirm):
        status = manual_confirm("请根据测试结果评判是否出现 LCM 闪屏。")
        return {"status": status, "message": f"人工评判{status}"}
    return {"status": "pending", "message": "需人工评判"}
