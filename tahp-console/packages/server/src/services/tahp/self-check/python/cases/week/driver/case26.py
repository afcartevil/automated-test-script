"""驱动周版本自检：G-sensor 基本功能人工检查（图库旋转）。"""

import subprocess
import time

from test.result_output import append_case_result, split_sub_steps

GALLERY_ACTIVITY = "com.gallery20/com.gallery20.HomeActivity"
SCREENSHOT_PATH = "/sdcard/Pictures/Screenshots/gsensor_test.png"


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


def _take_screenshot(device_id: str) -> tuple[bool, str]:
    mkdir_ret = _adb_run(device_id, "shell", "mkdir", "-p", "/sdcard/Pictures/Screenshots")
    if mkdir_ret.returncode != 0:
        return False, "创建截图目录失败"

    screencap_ret = _adb_run(
        device_id,
        "shell",
        "screencap",
        "-p",
        SCREENSHOT_PATH,
        timeout=30,
    )
    if screencap_ret.returncode != 0:
        detail = (screencap_ret.stderr or screencap_ret.stdout or "").strip()
        return False, f"截屏失败({detail or '未知错误'})"

    scan_ret = _adb_run(
        device_id,
        "shell",
        "am",
        "broadcast",
        "-a",
        "android.intent.action.MEDIA_SCANNER_SCAN_FILE",
        "-d",
        f"file://{SCREENSHOT_PATH}",
    )
    if scan_ret.returncode != 0:
        detail = (scan_ret.stderr or scan_ret.stdout or "").strip()
        return False, f"刷新图库索引失败({detail or '未知错误'})"

    return True, SCREENSHOT_PATH


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
        step_update(sub_steps + "\n回到桌面")
    home_ok = _go_home(dut_id)
    on_step("回到桌面", home_ok)
    if not home_ok:
        return {"status": "fail", "message": "回到桌面失败"}

    time.sleep(1)

    if callable(step_update):
        step_update(sub_steps + "\n打开屏幕自动旋转 (accelerometer_rotation=1)")
    rotate_ret = _adb_run(
        dut_id,
        "shell",
        "settings",
        "put",
        "system",
        "accelerometer_rotation",
        "1",
    )
    rotate_ok = rotate_ret.returncode == 0
    on_step("打开屏幕自动旋转 (accelerometer_rotation=1)", rotate_ok)
    if not rotate_ok:
        detail = (rotate_ret.stderr or rotate_ret.stdout or "").strip()
        return {
            "status": "fail",
            "message": f"设置自动旋转失败({detail or '未知错误'})",
        }

    time.sleep(1)

    if callable(step_update):
        step_update(sub_steps + "\n截屏")
    screenshot_ok, screenshot_detail = _take_screenshot(dut_id)
    on_step(f"截屏({screenshot_detail})", screenshot_ok)
    if not screenshot_ok:
        return {"status": "fail", "message": screenshot_detail}

    time.sleep(1)

    if callable(step_update):
        step_update(sub_steps + "\n打开图库应用")
    gallery_ret = _adb_run(
        dut_id,
        "shell",
        "am",
        "start",
        "-n",
        GALLERY_ACTIVITY,
    )
    gallery_ok = gallery_ret.returncode == 0
    on_step("打开图库应用", gallery_ok)
    if not gallery_ok:
        detail = (gallery_ret.stderr or gallery_ret.stdout or "").strip()
        return {"status": "fail", "message": f"打开图库应用失败({detail or '未知错误'})"}

    operation_text = (
        "1) 在图库中选择一张照片（可使用刚截取的截图）；\n"
        "2) 分别将手机旋转 90°、180°、360°；\n"
        "3) 观察图片显示方向是否随手机旋转正常变化。"
    )
    if callable(operator_notify):
        operator_notify(operation_text)
    sub_steps += f"\n需人工操作：\n  {operation_text.replace(chr(10), chr(10) + '  ')}\n需人工评判"
    report_steps()
    if callable(manual_confirm):
        status = manual_confirm("请根据图片旋转显示效果评判本用例是否通过。")
        return {"status": status, "message": f"人工评判{status}"}
    return {"status": "pending", "message": "需人工评判"}
