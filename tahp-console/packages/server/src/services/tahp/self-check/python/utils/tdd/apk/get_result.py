import re
import subprocess
import time

PASS_ACTIVITY = "com.android.transsion.tdd.autotest/.PassActivity"
FAIL_ACTIVITY = "com.android.transsion.tdd.autotest/.FailActivity"
MAX_POLL_TIMES = 90
POLL_INTERVAL_SECONDS = 1.0
# 轮询前等待，避免仍停留在上一次 Pass/Fail 结果页
RESULT_POLL_INITIAL_WAIT_SECONDS = 2.0


def _run_adb(device_id: str, args: list[str], timeout: int = 20):
    cmd = ["adb", "-s", device_id, *args]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _get_top_activity(device_id: str) -> str:
    activity_dump = _run_adb(device_id, ["shell", "dumpsys", "activity", "activities"])
    text = f"{activity_dump.stdout or ''}\n{activity_dump.stderr or ''}"
    match = re.search(
        r"topResumedActivity(?:=|:).*? ([A-Za-z0-9._$]+/[A-Za-z0-9._$/]+)",
        text,
    )
    if match:
        return match.group(1).strip()
    return ""


def wait_test_result(device_id: str) -> bool:
    """
    轮询测试结果页。

    参数:
        device_id: 设备 adb 序列号

    返回:
        读到 PassActivity 返回 True；
        读到 FailActivity 或超时返回 False。

    轮询开始前先等待 RESULT_POLL_INITIAL_WAIT_SECONDS（2s），避免误读上一次 Pass/Fail 残留。
    """
    if not device_id:
        return False

    if RESULT_POLL_INITIAL_WAIT_SECONDS > 0:
        time.sleep(RESULT_POLL_INITIAL_WAIT_SECONDS)

    seen_result_package = False
    for i in range(MAX_POLL_TIMES):
        top = _get_top_activity(device_id)
        if "com.android.transsion.tdd.autotest/" in top:
            seen_result_package = True
        if PASS_ACTIVITY in top:
            return True
        # 仅在已经进入过测试 APK 前台后，才接受 Fail 判定，避免误读上一次遗留界面
        if FAIL_ACTIVITY in top and seen_result_package:
            return False
        if i < MAX_POLL_TIMES - 1:
            time.sleep(POLL_INTERVAL_SECONDS)
    return False
