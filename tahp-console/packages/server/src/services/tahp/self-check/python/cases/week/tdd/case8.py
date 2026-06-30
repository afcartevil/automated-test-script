from utils.tdd.apk.message import exchange_mms, exchange_sms, wait_message_exchange_interval
from utils.tdd.ui_automatic import set_mobile_data_enable
from utils.tdd.device_sim import (
    dut_storage_key,
    get_sim_by_slot,
    pick_aux_number,
    resolve_dut_active,
    sim_phone_number,
    sim_slot_label,
)
from utils.tdd.sim_setup import NETWORK_TYPE_5G_AUTO, setup_sim_preferred_network

SMS_CONTENT = "TDD短信测试"


def _pick_aux_send_sim(aux_sim1, aux_sim2):
    if aux_sim1:
        return "sim1"
    if aux_sim2:
        return "sim2"
    return None


def _exchange_round_ok(send_ok: bool, receive_ok: bool) -> bool:
    return send_ok and receive_ok


def _run_sim_message_rounds(
    dut_id: str,
    dut_sim: str,
    dut_number: str,
    aux_id: str,
    aux_sim: str,
    aux_number: str,
    label: str,
    step_update,
    sub_steps: str,
) -> tuple[bool, str]:
    """卡槽 label 下：DUT 发短信、辅测机回复短信、互发彩信各一轮。"""
    sub_steps += f"\n{label}辅测机接收、测试机发短信"
    if callable(step_update):
        step_update(sub_steps)
    send_ok, recv_ok = exchange_sms(
        dut_id, dut_sim, aux_id, aux_number, content=SMS_CONTENT
    )
    if not _exchange_round_ok(send_ok, recv_ok):
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        return False, sub_steps

    sub_steps += "-成功"
    if callable(step_update):
        step_update(sub_steps)

    wait_message_exchange_interval()
    sub_steps += f"\n{label}辅测机发短信、测试机接收"
    if callable(step_update):
        step_update(sub_steps)
    send_ok, recv_ok = exchange_sms(
        aux_id, aux_sim, dut_id, dut_number, content=SMS_CONTENT
    )
    if not _exchange_round_ok(send_ok, recv_ok):
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        return False, sub_steps

    sub_steps += "-成功"
    if callable(step_update):
        step_update(sub_steps)

    wait_message_exchange_interval()
    sub_steps += f"\n{label}测试机发彩信、辅测机接收"
    if callable(step_update):
        step_update(sub_steps)
    send_ok, recv_ok = exchange_mms(dut_id, dut_sim, aux_id, aux_number)
    if not _exchange_round_ok(send_ok, recv_ok):
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        return False, sub_steps

    sub_steps += "-成功"
    if callable(step_update):
        step_update(sub_steps)

    wait_message_exchange_interval()
    sub_steps += f"\n{label}辅测机发彩信、测试机接收"
    if callable(step_update):
        step_update(sub_steps)
    send_ok, recv_ok = exchange_mms(aux_id, aux_sim, dut_id, dut_number)
    if not _exchange_round_ok(send_ok, recv_ok):
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        return False, sub_steps

    sub_steps += "-成功"
    if callable(step_update):
        step_update(sub_steps)

    return True, sub_steps


def run(category=None, case_index=None, device_info=None, **context):
    step_update = context.get("step_update")
    device_info = device_info or context.get("device_info") or {}

    _, dut_id, active_sim, slot_index, dut_number, sim_err = resolve_dut_active(
        device_info
    )
    if sim_err:
        return {"status": "fail", "message": sim_err}

    storage = dut_storage_key(slot_index)
    slot_label = sim_slot_label(slot_index)

    aux_list = device_info.get("Auxiliary") or []
    aux = aux_list[0] if aux_list else {}
    aux_id = (aux.get("device_id") or "").strip()
    aux_sim_cards = aux.get("sim_cards") or []
    aux_sim1 = get_sim_by_slot(aux_sim_cards, 0)
    aux_sim2 = get_sim_by_slot(aux_sim_cards, 1)
    aux_number = pick_aux_number(
        sim_phone_number(aux_sim1), sim_phone_number(aux_sim2)
    )
    aux_send_sim = _pick_aux_send_sim(aux_sim1, aux_sim2)
    if not aux_id or not aux_number or not aux_send_sim:
        return {"status": "fail", "message": "无可用辅测机或辅测机无可用号码"}

    sub_steps = ""

    def _fail(message: str):
        return {"status": "fail", "message": message}

    sub_steps += "\n打开移动数据开关"
    if callable(step_update):
        step_update(sub_steps)
    if not set_mobile_data_enable(dut_id, True):
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        return _fail("打开移动数据失败")
    sub_steps += "-成功"
    if callable(step_update):
        step_update(sub_steps)

    sub_steps += f"\n{slot_label}打开SIM卡，首选网络5G或4G"
    if callable(step_update):
        step_update(sub_steps)
    if not setup_sim_preferred_network(
        dut_id, active_sim, enable=True, network_type=NETWORK_TYPE_5G_AUTO
    ):
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        return _fail(f"{slot_label}打开或首选网络设置失败")
    sub_steps += "-成功"
    if callable(step_update):
        step_update(sub_steps)

    ok, sub_steps = _run_sim_message_rounds(
        dut_id,
        storage,
        dut_number,
        aux_id,
        aux_send_sim,
        aux_number,
        slot_label,
        step_update,
        sub_steps,
    )
    if not ok:
        return _fail(f"{slot_label}短彩信互发失败")

    sub_steps += "\n关闭移动数据开关"
    if callable(step_update):
        step_update(sub_steps)
    if not set_mobile_data_enable(dut_id, False):
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        return _fail("关闭移动数据失败")
    sub_steps += "-成功"
    if callable(step_update):
        step_update(sub_steps)

    ok, sub_steps = _run_sim_message_rounds(
        dut_id,
        storage,
        dut_number,
        aux_id,
        aux_send_sim,
        aux_number,
        f"关闭数据后{slot_label}",
        step_update,
        sub_steps,
    )
    if not ok:
        return _fail(f"关闭数据后{slot_label}短彩信互发失败")

    return {
        "status": "pass",
        "message": f"{slot_label}短彩信收发及关闭数据后验证通过",
    }
