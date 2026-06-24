"""驱动周版本自检：检查深色模式（暗环境下操作）人工测试。"""

import subprocess


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


SECURITY_ACTIVITY = "com.android.settings/.Settings$SecurityDashboardActivity"
SETTINGS_PACKAGES = ("com.android.settings", "com.google.android.settings")


def _force_stop_settings(device_id: str) -> None:
    for package in SETTINGS_PACKAGES:
        _adb_run(device_id, "shell", "am", "force-stop", package)


def _start_security_settings(device_id: str) -> subprocess.CompletedProcess:
    """组件名含 $，须经 shell 引号传递，避免被展开为变量。"""
    safe = SECURITY_ACTIVITY.replace("'", "'\\''")
    _force_stop_settings(device_id)
    return _adb_run(device_id, "shell", f"am start -n '{safe}'")


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

    unlock_text = "请先解锁测试机。"
    if callable(operator_notify):
        operator_notify(unlock_text)
    sub_steps += f"\n需人工操作：{unlock_text}"
    update(sub_steps)
    if callable(manual_confirm):
        unlock_status = manual_confirm("请确认测试机已解锁。")
        on_step("确认测试机已解锁", unlock_status == "pass")
        if unlock_status != "pass":
            return {"status": "fail", "message": "测试机未解锁或用户取消"}
    else:
        return {"status": "pending", "message": "需确认测试机已解锁"}

    security_ret = _start_security_settings(dut_id)
    on_step("进入安全设置界面", security_ret.returncode == 0)
    if security_ret.returncode != 0:
        return {"status": "fail", "message": "进入安全设置界面失败"}

    passwd_text = "请在安全设置中关闭锁屏密码。"
    if callable(operator_notify):
        operator_notify(passwd_text)
    sub_steps += f"\n需人工操作：{passwd_text}"
    update(sub_steps)
    if callable(manual_confirm):
        passwd_status = manual_confirm("请确认已关闭锁屏密码。")
        on_step("确认已关闭锁屏密码", passwd_status == "pass")
        if passwd_status != "pass":
            return {"status": "fail", "message": "未关闭锁屏密码或用户取消"}
    else:
        return {"status": "pending", "message": "需确认已关闭锁屏密码"}

    night_ret = _adb_run(dut_id, "shell", "cmd", "uimode", "night")
    night_ok = night_ret.returncode == 0
    night_text = f"{night_ret.stdout or ''}{night_ret.stderr or ''}".strip().lower()
    on_step("读取当前深色模式状态", night_ok)
    if not night_ok:
        return {"status": "fail", "message": "读取深色模式状态失败"}

    is_dark = "yes" in night_text
    sub_steps += f"\n当前深色模式查询结果: {(night_ret.stdout or '').strip() or '<空>'}"
    if is_dark:
        sub_steps += "\n当前已处于深色模式，跳过切换命令"
        update(sub_steps)
    else:
        set_night_ret = _adb_run(dut_id, "shell", "cmd", "uimode", "night", "yes")
        on_step("切换到深色模式", set_night_ret.returncode == 0)
        if set_night_ret.returncode != 0:
            return {"status": "fail", "message": "切换深色模式失败"}

    fm_ret = _adb_run(
        dut_id,
        "shell",
        "am",
        "start",
        "-n",
        "com.transsion.filemanagerx/com.transsion.filemanagerx.ui.main.MainActivity",
    )
    on_step("打开文件App", fm_ret.returncode == 0)
    if fm_ret.returncode != 0:
        return {"status": "fail", "message": "打开文件App失败"}

    sub_steps += "\n等待人工判断结果\n需人工评判"
    update(sub_steps)
    if callable(manual_confirm):
        status = manual_confirm("1.检查背景是否存在色变、色阶、mura麻点、竖纹等显示异常\n2.正常模式下点击分屏，显示效果是否正常")
        return {"status": status, "message": f"人工评判{status}"}
    return {"status": "pending", "message": "需人工评判"}
