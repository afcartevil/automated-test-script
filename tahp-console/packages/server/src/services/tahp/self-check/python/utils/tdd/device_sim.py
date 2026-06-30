"""device_info 中的 DUT / 辅测机 SIM 解析。"""

from typing import Any, Optional

from utils.tdd.ui_settings_activity import enter_sim_sub_settings_by_adb


def get_sim_by_slot(sim_cards, slot_index):
    return next((s for s in sim_cards if s.get("slot_index") == slot_index), None)


def sim_is_present(sim) -> bool:
    """SIM 卡槽是否已插卡（优先 present 字段，否则以号码推断）。"""
    if not sim:
        return False
    present = sim.get("present")
    if present is True:
        return True
    if present is False:
        return bool(sim_phone_number(sim))
    return bool(sim_phone_number(sim))


def resolve_active_sim(sim_cards) -> tuple[Optional[dict], int, str]:
    """
    解析测试机当前应使用的单卡：双卡均插时优先卡1；仅插卡1或卡2亦可。
    返回 (sim, slot_index, error_message)。
    """
    sim1 = get_sim_by_slot(sim_cards or [], 0)
    sim2 = get_sim_by_slot(sim_cards or [], 1)
    sim1_ok = sim_is_present(sim1)
    sim2_ok = sim_is_present(sim2)
    if sim1_ok:
        return sim1, 0, ""
    if sim2_ok:
        return sim2, 1, ""
    return None, -1, "测试机未检测到可用 SIM 卡"


def dut_dial_slot(slot_index: int) -> int:
    """拨号/短信 APK 卡槽参数：slot_index 0→1，1→2。"""
    return slot_index + 1


def dut_storage_key(slot_index: int) -> str:
    """联系人/短信 storage：sim1 / sim2。"""
    return "sim1" if slot_index == 0 else "sim2"


def sim_slot_label(slot_index: int) -> str:
    return f"卡{slot_index + 1}"


def resolve_dut_active(device_info: dict):
    """
    解析 DUT 与当前活动 SIM。
    返回 (dut, dut_id, active_sim, slot_index, phone_number, error_message)。
    """
    dut, dut_id = resolve_dut(device_info)
    if not dut:
        return None, dut_id, None, -1, "", dut_id
    active_sim, slot_index, err = resolve_active_sim(dut.get("sim_cards") or [])
    if err:
        return dut, dut_id, None, -1, "", err
    number = sim_phone_number(active_sim)
    if not number:
        return (
            dut,
            dut_id,
            active_sim,
            slot_index,
            "",
            f"测试机{sim_slot_label(slot_index)}无可用号码",
        )
    return dut, dut_id, active_sim, slot_index, number, ""


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
