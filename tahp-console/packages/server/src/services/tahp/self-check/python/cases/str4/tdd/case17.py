"""5G SA下单条短信发送&接收能力：卡1开网、关卡2、与辅测机互发短信、恢复卡2。"""

import time

from utils.tdd.apk.message import exchange_sms, wait_message_exchange_interval
from utils.tdd.ui_automatic import set_mobile_data_enable
from utils.tdd.ui_first_network import set_preferred_network
from utils.tdd.ui_settings_activity import enter_sim_sub_settings_by_adb
from utils.tdd.ui_turn_onoff_sim import set_sim_enable

SMS_CONTENT = "TDD短信测试"
PAGE_SETTLE_SECONDS = 1.0
SIM_OFF_SETTLE_SECONDS = 1.0
DATA_SETTLE_SECONDS = 2.0


def _get_sim_by_slot(sim_cards, slot_index):
    return next((s for s in sim_cards if s.get("slot_index") == slot_index), None)


def _sim_subscription_id(sim):
    if not sim:
        return None
    try:
        return int(sim.get("subscription_id"))
    except (TypeError, ValueError):
        return None


def _sim_phone_number(sim):
    if not sim:
        return ""
    return (sim.get("phone_number") or "").strip()


def _pick_aux_number(aux_sim1_number, aux_sim2_number):
    return (aux_sim1_number or "").strip() or (aux_sim2_number or "").strip()


def _pick_aux_send_sim(aux_sim1, aux_sim2):
    if aux_sim1:
        return "sim1"
    if aux_sim2:
        return "sim2"
    return None


def _enter_sim_sub_settings_by_sim(device_id: str, sim) -> bool:
    sub_id = _sim_subscription_id(sim)
    if sub_id is None:
        return False
    return enter_sim_sub_settings_by_adb(device_id, sub_id)


def _setup_sim_preferred_network(device_id: str, sim, *, enable: bool) -> bool:
    if not _enter_sim_sub_settings_by_sim(device_id, sim):
        return False
    if PAGE_SETTLE_SECONDS > 0:
        time.sleep(PAGE_SETTLE_SECONDS)
    if not set_sim_enable(device_id, enable):
        return False
    if not enable:
        if SIM_OFF_SETTLE_SECONDS > 0:
            time.sleep(SIM_OFF_SETTLE_SECONDS)
        return True
    return set_preferred_network(device_id, 5)


def _open_sim_only(device_id: str, sim) -> bool:
    if not _enter_sim_sub_settings_by_sim(device_id, sim):
        return False
    if PAGE_SETTLE_SECONDS > 0:
        time.sleep(PAGE_SETTLE_SECONDS)
    if not set_sim_enable(device_id, True):
        return False
    if PAGE_SETTLE_SECONDS > 0:
        time.sleep(PAGE_SETTLE_SECONDS)
    return True


def run(category=None, case_index=None, device_info=None, **context):
    step_update = context.get("step_update")
    device_info = device_info or context.get("device_info") or {}

    dut_list = (device_info or {}).get("DUT") or []
    if not dut_list:
        return {"status": "fail", "message": "未获取到测试机设备信息"}
    dut = dut_list[0]
    dut_id = (dut.get("device_id") or "").strip()
    if not dut_id:
        return {"status": "fail", "message": "测试机 device_id 为空"}

    dut_sim_cards = dut.get("sim_cards") or []
    sim1 = _get_sim_by_slot(dut_sim_cards, 0)
    sim2 = _get_sim_by_slot(dut_sim_cards, 1)
    if not sim1 or not sim2:
        return {"status": "fail", "message": "测试机非双卡，无法执行短信用例"}

    dut_number = _sim_phone_number(sim1)
    if not dut_number:
        return {"status": "fail", "message": "测试机卡1无可用号码"}

    aux_list = device_info.get("Auxiliary") or []
    aux = aux_list[0] if aux_list else {}
    aux_id = (aux.get("device_id") or "").strip()
    aux_sim_cards = aux.get("sim_cards") or []
    aux_sim1 = _get_sim_by_slot(aux_sim_cards, 0)
    aux_sim2 = _get_sim_by_slot(aux_sim_cards, 1)
    aux_number = _pick_aux_number(
        _sim_phone_number(aux_sim1),
        _sim_phone_number(aux_sim2),
    )
    aux_send_sim = _pick_aux_send_sim(aux_sim1, aux_sim2)
    if not aux_id or not aux_number or not aux_send_sim:
        return {"status": "fail", "message": "无可用辅测机或辅测机无可用号码"}

    sub_steps = ""
    sim2_was_closed = False

    def update(steps: str):
        if callable(step_update):
            step_update(steps)

    def fail(message: str):
        return {"status": "fail", "message": message}

    try:
        if not set_mobile_data_enable(dut_id, True):
            return fail("打开移动数据失败")
        if DATA_SETTLE_SECONDS > 0:
            time.sleep(DATA_SETTLE_SECONDS)

        sub_steps += "\n打开卡1，首选网络5G或4G"
        update(sub_steps)
        if not _setup_sim_preferred_network(dut_id, sim1, enable=True):
            sub_steps += "-失败"
            update(sub_steps)
            return fail("卡1打开或首选网络设置失败")
        sub_steps += "-成功"
        update(sub_steps)

        sub_steps += "\n关闭卡2"
        update(sub_steps)
        if not _setup_sim_preferred_network(dut_id, sim2, enable=False):
            sub_steps += "-失败"
            update(sub_steps)
            return fail("关闭卡2失败")
        sim2_was_closed = True
        sub_steps += "-成功"
        update(sub_steps)

        sub_steps += "\n测试机给辅测机发送短信，检测是否成功"
        update(sub_steps)
        send_ok, recv_ok = exchange_sms(
            dut_id, "sim1", aux_id, aux_number, content=SMS_CONTENT
        )
        if not (send_ok and recv_ok):
            sub_steps += "-失败"
            update(sub_steps)
            detail = []
            if not send_ok:
                detail.append("测试机发送失败")
            if not recv_ok:
                detail.append("辅测机接收失败")
            return fail("、".join(detail) or "测试机向辅测机发短信失败")
        sub_steps += "-成功"
        update(sub_steps)

        wait_message_exchange_interval()
        sub_steps += "\n辅测机给测试机发送短信，检测是否成功"
        update(sub_steps)
        send_ok, recv_ok = exchange_sms(
            aux_id, aux_send_sim, dut_id, dut_number, content=SMS_CONTENT
        )
        if not (send_ok and recv_ok):
            sub_steps += "-失败"
            update(sub_steps)
            detail = []
            if not send_ok:
                detail.append("辅测机发送失败")
            if not recv_ok:
                detail.append("测试机接收失败")
            return fail("、".join(detail) or "辅测机向测试机发短信失败")
        sub_steps += "-成功"
        update(sub_steps)

        sub_steps += "\n打开卡2"
        update(sub_steps)
        if not _open_sim_only(dut_id, sim2):
            sub_steps += "-失败"
            update(sub_steps)
            return fail("打开卡2失败")
        sim2_was_closed = False
        sub_steps += "-成功"
        update(sub_steps)

        return {
            "status": "pass",
            "message": "卡1 5G/4G 首选网络下与辅测机互发短信通过，已恢复打开卡2",
        }
    finally:
        if sim2_was_closed:
            sub_steps += "\n恢复打开卡2(用例结束)"
            update(sub_steps)
            if _open_sim_only(dut_id, sim2):
                sub_steps += "-成功"
            else:
                sub_steps += "-失败"
            update(sub_steps)
