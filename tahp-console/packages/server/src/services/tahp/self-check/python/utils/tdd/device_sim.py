"""device_info 中的 DUT / 辅测机 SIM 解析。"""

from typing import Any, Optional

from utils.tdd.ui_settings_activity import enter_sim_sub_settings_by_adb


def get_sim_by_slot(sim_cards, slot_index):
    return next((s for s in sim_cards if s.get("slot_index") == slot_index), None)


def sim_subscription_id(sim) -> Optional[int]:
    if not sim:
        return None
    try:
        return int(sim.get("subscription_id"))
    except (TypeError, ValueError):
        return None


def sim_phone_number(sim) -> str:
    if not sim:
        return ""
    return (sim.get("phone_number") or "").strip()


def pick_aux_number(aux_sim1_number: str, aux_sim2_number: str) -> str:
    return (aux_sim1_number or "").strip() or (aux_sim2_number or "").strip()


def pick_aux_send_sim(aux_sim1, aux_sim2) -> Optional[str]:
    if aux_sim1:
        return "sim1"
    if aux_sim2:
        return "sim2"
    return None


def aux_call_slot(aux_sim1, aux_sim2) -> Optional[int]:
    if aux_sim1:
        return 1
    if aux_sim2:
        return 2
    return None


def enter_sim_sub_settings_by_sim(device_id: str, sim) -> bool:
    sub_id = sim_subscription_id(sim)
    if sub_id is None:
        return False
    return enter_sim_sub_settings_by_adb(device_id, sub_id)


def resolve_dut(device_info: dict) -> tuple[Optional[dict], str]:
    dut_list = (device_info or {}).get("DUT") or []
    if not dut_list:
        return None, "未获取到测试机设备信息"
    dut = dut_list[0]
    dut_id = (dut.get("device_id") or "").strip()
    if not dut_id:
        return None, "测试机 device_id 为空"
    return dut, dut_id


def resolve_aux(device_info: dict) -> tuple[str, str, str, str]:
    """返回 (aux_id, aux_number, aux_send_sim, error_message)。"""
    aux_list = device_info.get("Auxiliary") or []
    aux = aux_list[0] if aux_list else {}
    aux_id = (aux.get("device_id") or "").strip()
    aux_sim_cards = aux.get("sim_cards") or []
    aux_sim1 = get_sim_by_slot(aux_sim_cards, 0)
    aux_sim2 = get_sim_by_slot(aux_sim_cards, 1)
    aux_number = pick_aux_number(
        sim_phone_number(aux_sim1),
        sim_phone_number(aux_sim2),
    )
    aux_send_sim = pick_aux_send_sim(aux_sim1, aux_sim2)
    if not aux_id or not aux_number or not aux_send_sim:
        return "", "", "", "无可用辅测机或辅测机无可用号码"
    return aux_id, aux_number, aux_send_sim, ""


CAMERA_UNAVAILABLE_MESSAGE = "camera不可用"


def device_camera_count(device: dict) -> int:
    try:
        return int((device or {}).get("camera_count", 0))
    except (TypeError, ValueError):
        return 0


def fail_result_if_camera_unavailable_for_video(device_info: dict) -> Optional[dict]:
    """视频通话用例：DUT/辅测机 camera_count 为 0 时直接 fail。"""
    if not device_info:
        return None
    for dev in (device_info.get("DUT") or []) + (device_info.get("Auxiliary") or []):
        if not isinstance(dev, dict):
            continue
        if not (dev.get("device_id") or "").strip():
            continue
        if device_camera_count(dev) <= 0:
            return {"status": "fail", "message": CAMERA_UNAVAILABLE_MESSAGE}
    return None
