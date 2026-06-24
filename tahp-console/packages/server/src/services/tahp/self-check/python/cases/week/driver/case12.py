"""驱动周版本自检：设置中开启指针位置以及显示点按操作反馈人工检查。"""

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

    night_off_ret = _adb_run(dut_id, "shell", "cmd", "uimode", "night", "no")
    on_step("关闭深色模式", night_off_ret.returncode == 0)
    if night_off_ret.returncode != 0:
        return {"status": "fail", "message": "关闭深色模式失败"}

    pointer_ret = _adb_run(dut_id, "shell", "settings", "put", "system", "pointer_location", "1")
    on_step("开启指针位置显示", pointer_ret.returncode == 0)
    if pointer_ret.returncode != 0:
        return {"status": "fail", "message": "开启指针位置显示失败"}

    touch_ret = _adb_run(dut_id, "shell", "settings", "put", "system", "show_touches", "1")
    on_step("开启触摸点显示", touch_ret.returncode == 0)
    if touch_ret.returncode != 0:
        return {"status": "fail", "message": "开启触摸点显示失败"}

    settings_ret = _adb_run(
        dut_id,
        "shell",
        "am",
        "start",
        "-n",
        "com.android.settings/com.android.settings.Settings",
    )
    on_step("进入设置应用", settings_ret.returncode == 0)
    if settings_ret.returncode != 0:
        return {"status": "fail", "message": "进入设置应用失败"}

    operation_text = (
        "指针位置与触摸坐标点已开启；观察触摸和显示效果并判定结果。"
    )
    if callable(operator_notify):
        operator_notify(operation_text)
    sub_steps += f"\n需人工操作：{operation_text}\n需人工评判"
    update(sub_steps)
    if callable(manual_confirm):
        status = manual_confirm("1.指针位置与显示点已开启，请进入开发者选项中，关闭指针位置与显示点。\n2.整个过程中是否存在闪屏、抖屏、花屏、色阶等现象。")
        return {"status": status, "message": f"人工评判{status}"}
    return {"status": "pending", "message": "需人工评判"}
