import subprocess
import time

from utils.tdd.apk.get_result import wait_test_result

PACKAGE = "com.android.transsion.tdd.autotest"
CALL_CALLBACK_DELAY_SECONDS = 2.0
AUTO_DIAL_ACTION = "com.android.transsion.tdd.autotest.action.AUTO_DIAL"
_prev_dial_without_break = False
AUTO_DIAL_ACTIVITY = f"{PACKAGE}/.call.autodial.AutoDialActivity"


def _run_adb(device_id: str, args: list[str], timeout: int = 30):
    cmd = ["adb", "-s", device_id, *args]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _normalize_slot(slot) -> int:
    if slot in (0, "0", "卡1", "SIM1", "sim1", 1, "1"):
        if slot in (1, "1", "卡1", "SIM1", "sim1"):
            return 0
        return 0
    if slot in (2, "2", "卡2", "SIM2", "sim2"):
        return 1
    text = str(slot or "").strip().upper()
    if text in ("SIM1", "卡1"):
        return 0
    if text in ("SIM2", "卡2"):
        return 1
    try:
        value = int(text)
    except ValueError as exc:
        raise ValueError(f"不支持的 SIM 卡参数: {slot!r}") from exc
    if value == 0:
        return 0
    if value == 1:
        return 0
    if value == 2:
        return 1
    raise ValueError(f"不支持的 SIM 卡参数: {slot!r}")


def start_auto_dial(device_id: str, sim_slot, call_type, number: str) -> bool:
    """
    调起测试 APK 的 AutoDialActivity，并传入拨号参数。

    参数:
        device_id: 设备 adb 序列号
        sim_slot: 指定卡槽（支持 0/1、1/2、卡1/卡2、SIM1/SIM2）
        call_type: 通话类型（0~4）
        number: 拨打号码

    返回:
        界面拉起成功为 True，否则 False。
    """
    if not device_id or not str(number or "").strip():
        return False
    try:
        slot_id = _normalize_slot(sim_slot)
        call_type_int = int(call_type)
    except (ValueError, TypeError):
        return False
    if call_type_int < 0 or call_type_int > 4:
        return False

    result = _run_adb(
        device_id,
        [
            "shell",
            "am",
            "start",
            "-W",
            "-a",
            AUTO_DIAL_ACTION,
            "-n",
            AUTO_DIAL_ACTIVITY,
            "--es",
            "slot_id",
            str(slot_id),
            "--es",
            "number",
            str(number).strip(),
            "--ei",
            "call_type",
            str(call_type_int),
        ],
        timeout=30,
    )

    output = f"{result.stdout or ''}\n{result.stderr or ''}"
    if result.returncode != 0 or "Error" in output or "Exception" in output:
        return False

    return True


def reset_dial_sequence() -> None:
    """标记上一操作非连续拨号；非拨号子步骤开始时应调用。"""
    global _prev_dial_without_break
    _prev_dial_without_break = False


def dial_and_check(
    device_id: str,
    sim_slot,
    target_number: str,
    call_type: int,
) -> bool:
    """拨号并轮询 Pass/Fail 结果页。与上一次拨号之间无其他操作时自动等待 2s。"""
    global _prev_dial_without_break
    if _prev_dial_without_break:
        time.sleep(CALL_CALLBACK_DELAY_SECONDS)
    if not start_auto_dial(
        device_id,
        sim_slot=sim_slot,
        call_type=call_type,
        number=target_number,
    ):
        return False
    ok = wait_test_result(device_id)
    _prev_dial_without_break = True
    return ok
