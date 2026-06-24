import subprocess
import threading
import time
from typing import Optional, Union

from utils.tdd.apk.get_result import MAX_POLL_TIMES, wait_test_result

PACKAGE = "com.android.transsion.tdd.autotest"
SEND_MESSAGE_ACTIVITY = f"{PACKAGE}/.message.SendMessageActivity"
RECEIVE_MESSAGE_ACTIVITY = f"{PACKAGE}/.message.ReceiveMessageActivity"

SimInput = Union[str, int]
MessageTypeInput = Union[str]

# 接收页 APK 内超时（秒）；Python 轮询仍使用 get_result.wait_test_result（90s）
DEFAULT_RECEIVE_TIMEOUT_SECONDS = 60
DEFAULT_SMS_CONTENT = "TDD短信测试"
RECEIVE_READY_SECONDS = 2.0
EXCHANGE_JOIN_TIMEOUT_SECONDS = MAX_POLL_TIMES + int(RECEIVE_READY_SECONDS) + 15
# 用例中连续短彩信互发（中间无其它操作）时的间隔
MESSAGE_EXCHANGE_INTERVAL_SECONDS = 2.0


def wait_message_exchange_interval() -> None:
    """连续 exchange_sms / exchange_mms 之间等待，避免 APK 未就绪。"""
    time.sleep(MESSAGE_EXCHANGE_INTERVAL_SECONDS)


def _run_adb(device_id: str, args: list[str], timeout: int = 30):
    cmd = ["adb", "-s", device_id, *args]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _normalize_sim(sim: SimInput) -> Optional[str]:
    if sim is None:
        return None
    value = str(sim).strip().lower()
    mapping = {
        "sim1": "sim1",
        "card1": "sim1",
        "slot0": "sim1",
        "slot_0": "sim1",
        "卡1": "sim1",
        "sim_1": "sim1",
        "0": "sim1",
        "1": "sim1",
        "sim2": "sim2",
        "card2": "sim2",
        "slot1": "sim2",
        "slot_1": "sim2",
        "卡2": "sim2",
        "sim_2": "sim2",
        "2": "sim2",
    }
    return mapping.get(value)


def _normalize_message_type(message_type: MessageTypeInput) -> Optional[str]:
    if message_type is None:
        return None
    value = str(message_type).strip().lower()
    mapping = {
        "sms": "sms",
        "text": "sms",
        "短信": "sms",
        "mms": "mms",
        "彩信": "mms",
    }
    return mapping.get(value)


def grant_sms_permissions(device_id: str) -> None:
    """通过 adb 授予短彩信相关运行时权限。"""
    permissions = [
        "android.permission.SEND_SMS",
        "android.permission.RECEIVE_SMS",
        "android.permission.READ_SMS",
        "android.permission.WRITE_SMS",
        "android.permission.RECEIVE_MMS",
        "android.permission.READ_PHONE_STATE",
    ]
    for permission in permissions:
        _run_adb(
            device_id,
            ["shell", "pm", "grant", PACKAGE, permission],
            timeout=15,
        )


def set_default_sms_app(device_id: str) -> bool:
    """尝试将本 APK 设为默认短信应用（接收 SMS_DELIVER 需要）。"""
    result = _run_adb(
        device_id,
        [
            "shell",
            "cmd",
            "role",
            "add-role-holder",
            "android.app.role.SMS",
            PACKAGE,
        ],
        timeout=15,
    )
    return result.returncode == 0


def start_send_message_test(
    device_id: str,
    sim: SimInput,
    number: str,
    message_type: MessageTypeInput,
    content: str = "",
) -> bool:
    """
    调起 SendMessageActivity 自动发送短信或彩信。

    参数:
        sim: sim1 / sim2（也支持 卡1、卡2、0、2 等别名）
        number: 接收号码
        message_type: sms / mms（也支持 短信、彩信）
        content: 短信正文；彩信可选（彩信默认发送本 APK 图标）

    返回:
        界面拉起成功为 True，否则 False。
    """
    if not device_id:
        return False

    sim_value = _normalize_sim(sim)
    type_value = _normalize_message_type(message_type)
    dest = str(number or "").strip()
    if not sim_value or not type_value or not dest:
        return False

    args = [
        "shell",
        "am",
        "start",
        "-W",
        "-n",
        SEND_MESSAGE_ACTIVITY,
        "--es",
        "sim",
        sim_value,
        "--es",
        "number",
        dest,
        "--es",
        "message_type",
        type_value,
    ]
    body = str(content or "")
    if body:
        args.extend(["--es", "content", body])

    result = _run_adb(device_id, args, timeout=90)
    output = f"{result.stdout or ''}\n{result.stderr or ''}"
    if result.returncode != 0 or "Error" in output or "Exception" in output:
        return False
    return True


def run_send_message_test(
    device_id: str,
    sim: SimInput,
    number: str,
    message_type: MessageTypeInput,
    content: str = "",
) -> bool:
    """
    发送短彩信并轮询 Pass/Fail 结果页。

    返回:
        PassActivity 为 True；FailActivity、拉起失败或超时为 False。
    """
    if not start_send_message_test(
        device_id,
        sim,
        number,
        message_type,
        content=content,
    ):
        return False
    return wait_test_result(device_id)


def start_receive_message_test(
    device_id: str,
    *,
    timeout_seconds: int = DEFAULT_RECEIVE_TIMEOUT_SECONDS,
) -> bool:
    """
    调起 ReceiveMessageActivity，仅在前台时收到短彩信会跳转 Pass。

    参数:
        timeout_seconds: 等待超时秒数，超时后 APK 自动进入 FailActivity

    返回:
        界面拉起成功为 True，否则 False。
    """
    if not device_id:
        return False

    timeout = max(1, int(timeout_seconds))

    result = _run_adb(
        device_id,
        [
            "shell",
            "am",
            "start",
            "-W",
            "-n",
            RECEIVE_MESSAGE_ACTIVITY,
            "--ei",
            "timeout_seconds",
            str(timeout),
        ],
        timeout=30,
    )
    output = f"{result.stdout or ''}\n{result.stderr or ''}"
    if result.returncode != 0 or "Error" in output or "Exception" in output:
        return False
    return True


def run_receive_message_test(
    device_id: str,
    *,
    timeout_seconds: int = DEFAULT_RECEIVE_TIMEOUT_SECONDS,
) -> bool:
    """
    保持接收页面前台并等待收到短彩信（由外部设备发送）。

    通过 get_result.wait_test_result 轮询 Pass/Fail（固定 90s 超时）：
        - PassActivity → 收到消息，成功
        - FailActivity → APK 60s 超时未收到等失败

    返回:
        进入 PassActivity 为 True；FailActivity、拉起失败或轮询超时为 False。
    """
    if not start_receive_message_test(
        device_id,
        timeout_seconds=timeout_seconds,
    ):
        return False
    return wait_test_result(device_id)


def send_sms(
    device_id: str,
    sim: SimInput,
    number: str,
    content: str,
) -> bool:
    """发送短信并校验是否成功。"""
    return run_send_message_test(device_id, sim, number, "sms", content=content)


def send_mms(
    device_id: str,
    sim: SimInput,
    number: str,
    content: str = "",
) -> bool:
    """发送彩信（附件为本 APK 图标）并校验是否成功。"""
    return run_send_message_test(device_id, sim, number, "mms", content=content)


def _receive_in_background(receiver_id: str, outcomes: dict) -> None:
    outcomes["receive_ok"] = False
    if not start_receive_message_test(receiver_id):
        return
    time.sleep(RECEIVE_READY_SECONDS)
    outcomes["receive_ok"] = wait_test_result(receiver_id)


def exchange_message(
    sender_id: str,
    sender_sim: SimInput,
    receiver_id: str,
    destination_number: str,
    message_type: MessageTypeInput,
    content: str = "",
) -> tuple[bool, bool]:
    """
    接收端先打开 ReceiveMessageActivity，发送端再发短/彩信。

    返回:
        (发送端 Pass, 接收端 Pass)
    """
    if not sender_id or not receiver_id:
        return False, False

    outcomes: dict = {}
    thread = threading.Thread(
        target=_receive_in_background,
        args=(receiver_id, outcomes),
        daemon=True,
    )
    thread.start()
    time.sleep(0.5)
    send_ok = run_send_message_test(
        sender_id,
        sender_sim,
        destination_number,
        message_type,
        content=content,
    )
    thread.join(timeout=EXCHANGE_JOIN_TIMEOUT_SECONDS)
    receive_ok = bool(outcomes.get("receive_ok"))
    return send_ok, receive_ok


def exchange_sms(
    sender_id: str,
    sender_sim: SimInput,
    receiver_id: str,
    destination_number: str,
    content: str = "",
) -> tuple[bool, bool]:
    """互发短信用：接收端监听 + 发送端发送，返回 (发送成功, 接收成功)。"""
    return exchange_message(
        sender_id,
        sender_sim,
        receiver_id,
        destination_number,
        "sms",
        content=content,
    )


def exchange_mms(
    sender_id: str,
    sender_sim: SimInput,
    receiver_id: str,
    destination_number: str,
    content: str = "",
) -> tuple[bool, bool]:
    """互发彩信用：接收端监听 + 发送端发送，返回 (发送成功, 接收成功)。"""
    return exchange_message(
        sender_id,
        sender_sim,
        receiver_id,
        destination_number,
        "mms",
        content=content,
    )


def _sms_exchange_message(send_ok: bool, recv_ok: bool, *, dut_to_aux: bool) -> tuple[bool, str]:
    if send_ok and recv_ok:
        return True, ""
    parts = []
    if not send_ok:
        parts.append("测试机发送失败" if dut_to_aux else "辅测机发送失败")
    if not recv_ok:
        parts.append("辅测机接收失败" if dut_to_aux else "测试机接收失败")
    default = (
        "测试机向辅测机发短信失败"
        if dut_to_aux
        else "辅测机向测试机发短信失败"
    )
    return False, "、".join(parts) or default


def exchange_sms_dut_to_aux(
    dut_id: str,
    dut_sim: SimInput,
    aux_id: str,
    aux_number: str,
    *,
    content: str = DEFAULT_SMS_CONTENT,
) -> tuple[bool, str]:
    """测试机发短信至辅测机，返回 (成功, 失败说明)。"""
    send_ok, recv_ok = exchange_sms(dut_id, dut_sim, aux_id, aux_number, content=content)
    return _sms_exchange_message(send_ok, recv_ok, dut_to_aux=True)


def exchange_sms_aux_to_dut(
    aux_id: str,
    aux_sim: SimInput,
    dut_id: str,
    dut_number: str,
    *,
    content: str = DEFAULT_SMS_CONTENT,
) -> tuple[bool, str]:
    """辅测机发短信至测试机，返回 (成功, 失败说明)。"""
    send_ok, recv_ok = exchange_sms(aux_id, aux_sim, dut_id, dut_number, content=content)
    return _sms_exchange_message(send_ok, recv_ok, dut_to_aux=False)


def _mms_exchange_message(send_ok: bool, recv_ok: bool, *, dut_to_aux: bool) -> tuple[bool, str]:
    if send_ok and recv_ok:
        return True, ""
    return (
        False,
        "测试机向辅测机发彩信失败" if dut_to_aux else "辅测机向测试机发彩信失败",
    )


def exchange_mms_dut_to_aux(
    dut_id: str,
    dut_sim: SimInput,
    aux_id: str,
    aux_number: str,
) -> tuple[bool, str]:
    send_ok, recv_ok = exchange_mms(dut_id, dut_sim, aux_id, aux_number)
    return _mms_exchange_message(send_ok, recv_ok, dut_to_aux=True)


def exchange_mms_aux_to_dut(
    aux_id: str,
    aux_sim: SimInput,
    dut_id: str,
    dut_number: str,
) -> tuple[bool, str]:
    send_ok, recv_ok = exchange_mms(aux_id, aux_sim, dut_id, dut_number)
    return _mms_exchange_message(send_ok, recv_ok, dut_to_aux=False)
