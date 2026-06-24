"""驱动周版本自检：方向传感器翻转静音人工检查。"""

from __future__ import annotations

import subprocess

from typing import Optional

from test.result_output import append_case_result, split_sub_steps

TDD_DIALER_PACKAGE = "com.android.transsion.tdd.autotest"
ROLE_DIALER = "android.app.role.DIALER"
SYSTEM_DIALER_CANDIDATES = (
    "com.sh.smart.caller",
    "com.android.dialer",
    "com.google.android.dialer",
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


def _is_package_installed(device_id: str, package: str) -> bool:
    ret = _adb_run(device_id, "shell", "pm", "path", package)
    return ret.returncode == 0 and "package:" in (ret.stdout or "")


def _resolve_system_dialer_package(device_id: str) -> Optional[str]:
    ret = _adb_run(
        device_id,
        "shell",
        "pm",
        "resolve-activity",
        "--brief",
        "-a",
        "android.intent.action.DIAL",
        "-c",
        "android.intent.category.DEFAULT",
    )
    for line in (ret.stdout or "").splitlines():
        line = line.strip()
        if "/" not in line or "=" in line:
            continue
        package = line.split("/", 1)[0].strip()
        if package and package != TDD_DIALER_PACKAGE:
            return package

    for package in SYSTEM_DIALER_CANDIDATES:
        if _is_package_installed(device_id, package):
            return package
    return None


def _go_home(device_id: str) -> bool:
    ret = _adb_run(device_id, "shell", "input", "keyevent", "3")
    return ret.returncode == 0


def _restore_system_default_dialer(device_id: str) -> tuple[bool, str]:
    _adb_run(device_id, "shell", "am", "force-stop", TDD_DIALER_PACKAGE)
    _adb_run(
        device_id,
        "shell",
        "cmd",
        "role",
        "remove-role-holder",
        ROLE_DIALER,
        TDD_DIALER_PACKAGE,
    )

    dialer_package = _resolve_system_dialer_package(device_id)
    if not dialer_package:
        return False, "未找到系统默认电话应用"

    add_ret = _adb_run(
        device_id,
        "shell",
        "cmd",
        "role",
        "add-role-holder",
        ROLE_DIALER,
        dialer_package,
    )
    if add_ret.returncode != 0:
        telecom_ret = _adb_run(
            device_id,
            "shell",
            "cmd",
            "telecom",
            "set-default-dialer",
            dialer_package,
        )
        if telecom_ret.returncode != 0:
            return False, f"切换默认电话应用失败({dialer_package})"

    verify_ret = _adb_run(device_id, "shell", "cmd", "telecom", "get-default-dialer")
    current_dialer = (verify_ret.stdout or "").strip()
    if TDD_DIALER_PACKAGE in current_dialer:
        return False, "默认电话应用仍为 TDD"
    if current_dialer and dialer_package not in current_dialer:
        return False, f"默认电话应用异常({current_dialer})"
    return True, dialer_package


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

    def report_steps() -> None:
        if callable(step_update):
            step_update(sub_steps)
        if result_dir and category and case_index:
            append_case_result(
                result_dir,
                category,
                {
                    "case_index": case_index,
                    "case_name": case_name or "",
                    "status": "pending",
                    "message": "需人工评判",
                    "sub_steps": split_sub_steps(sub_steps),
                },
            )

    def on_step(label: str, ok: bool) -> None:
        nonlocal sub_steps
        sub_steps += f"\n{label}" + ("-成功" if ok else "-失败")
        report_steps()

    if callable(step_update):
        step_update(sub_steps + "\n返回桌面")
    home_ok = _go_home(dut_id)
    on_step("返回桌面", home_ok)
    if not home_ok:
        return {"status": "fail", "message": "返回桌面失败"}

    if callable(step_update):
        step_update(sub_steps + "\n切换默认电话应用为系统拨号盘")
    dialer_ok, dialer_detail = _restore_system_default_dialer(dut_id)
    on_step(f"切换默认电话应用为系统拨号盘({dialer_detail})", dialer_ok)
    if not dialer_ok:
        return {"status": "fail", "message": dialer_detail}

    flip_mute_ret = _adb_run(
        dut_id,
        "shell",
        "settings",
        "put",
        "system",
        "os_action_flip_mute",
        "1",
    )
    on_step("开启翻转静音功能", flip_mute_ret.returncode == 0)
    if flip_mute_ret.returncode != 0:
        return {"status": "fail", "message": "开启翻转静音功能失败"}

    operation_text = (
        "请使用另一部手机拨打测试机号码，待来电响铃后翻转测试机，观察来电是否自动静音。"
    )
    if callable(operator_notify):
        operator_notify(operation_text)
    sub_steps += f"\n需人工操作：{operation_text}\n需人工评判"
    report_steps()
    if callable(manual_confirm):
        status = manual_confirm("请根据翻转静音效果评判本用例是否通过。")
        return {"status": status, "message": f"人工评判{status}"}
    return {"status": "pending", "message": "需人工评判"}
