from utils.tdd.apk.call import dial_and_check, reset_dial_sequence
from utils.tdd.ui_first_network import set_preferred_network
from utils.tdd.ui_settings_activity import enter_sim_sub_settings_by_adb
from utils.tdd.ui_turn_onoff_sim import set_sim_enable
from utils.tdd.ui_volte_button import set_volte_enable

EMERGENCY_NUMBER = "112"
SERVICE_NUMBER = "10086"
CALL_TYPE_EMERGENCY = 0
CALL_TYPE_VOICE = 2


def _get_sim_by_slot(sim_cards, slot_index):
    return next((s for s in sim_cards if s.get("slot_index") == slot_index), None)


def _sim_subscription_id(sim):
    if not sim:
        return None
    try:
        return int(sim.get("subscription_id"))
    except (TypeError, ValueError):
        return None


def _enter_sim_sub_settings_by_sim(device_id: str, sim) -> bool:
    sub_id = _sim_subscription_id(sim)
    if sub_id is None:
        return False
    return enter_sim_sub_settings_by_adb(device_id, sub_id)


def _setup_sim_enable_volte_network(device_id: str, sim) -> bool:
    if not _enter_sim_sub_settings_by_sim(device_id, sim):
        return False
    if not set_sim_enable(device_id, True):
        return False
    if not set_volte_enable(device_id, True):
        return False
    return set_preferred_network(device_id, 5)


def _set_sim_enable_by_sim(device_id: str, sim, enabled: bool) -> bool:
    if not _enter_sim_sub_settings_by_sim(device_id, sim):
        return False
    return set_sim_enable(device_id, enabled)


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
        return {"status": "fail", "message": "测试机非双卡，无法执行语音通路用例"}

    sub_steps = ""
    setup_ok = True
    emergency_ok = False
    service_ok = False

    def _update():
        if callable(step_update):
            step_update(sub_steps)

    def _mark_setup(ok: bool):
        nonlocal setup_ok
        if not ok:
            setup_ok = False

    sub_steps += "\n卡1打开SIM卡，打开VoLTE，首选网络5G或4G"
    _update()
    step_ok = _setup_sim_enable_volte_network(dut_id, sim1)
    sub_steps += "-成功" if step_ok else "-失败"
    _update()
    _mark_setup(step_ok)

    sub_steps += "\n卡2关闭"
    _update()
    step_ok = _set_sim_enable_by_sim(dut_id, sim2, False)
    sub_steps += "-成功" if step_ok else "-失败"
    _update()
    _mark_setup(step_ok)

    sub_steps += "\n拨打紧急号码112"
    _update()
    emergency_ok = dial_and_check(
        dut_id, 1, EMERGENCY_NUMBER, CALL_TYPE_EMERGENCY
    )
    sub_steps += "-成功" if emergency_ok else "-失败"
    _update()

    reset_dial_sequence()
    sub_steps += "\n卡2打开SIM卡，打开VoLTE，首选网络5G或4G"
    _update()
    step_ok = _setup_sim_enable_volte_network(dut_id, sim2)
    sub_steps += "-成功" if step_ok else "-失败"
    _update()
    _mark_setup(step_ok)

    sub_steps += "\n卡1关闭"
    _update()
    step_ok = _set_sim_enable_by_sim(dut_id, sim1, False)
    sub_steps += "-成功" if step_ok else "-失败"
    _update()
    _mark_setup(step_ok)

    sub_steps += "\n拨打10086"
    _update()
    service_ok = dial_and_check(dut_id, 2, SERVICE_NUMBER, CALL_TYPE_VOICE)
    sub_steps += "-成功" if service_ok else "-失败"
    _update()

    sub_steps += "\n卡1打开"
    _update()
    step_ok = _set_sim_enable_by_sim(dut_id, sim1, True)
    sub_steps += "-成功" if step_ok else "-失败"
    _update()
    _mark_setup(step_ok)

    if not setup_ok:
        return {"status": "fail", "message": "语音通路用例存在其他子步骤失败"}

    if not emergency_ok and service_ok:
        return {"status": "部分pass", "message": "无网络环境"}

    if emergency_ok and service_ok:
        return {"status": "pass", "message": "语音通路call type验证通过"}

    return {"status": "fail", "message": "语音通路用例存在其他子步骤失败"}
