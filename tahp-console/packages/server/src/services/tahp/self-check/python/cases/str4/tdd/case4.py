import time

from utils.tdd.ui_first_network import set_preferred_network
from utils.tdd.ui_network_info import check_sim_volte_or_vonr_icon
from utils.tdd.ui_roaming_switch import set_roaming_enable
from utils.tdd.ui_settings_activity import enter_sim_sub_settings_by_adb
from utils.tdd.ui_turn_onoff_sim import set_sim_enable
from utils.tdd.ui_volte_button import set_volte_enable

ROAMING_CYCLES = 10
PAGE_SETTLE_SECONDS = 1.0
ROAMING_SETTLE_SECONDS = 1.5


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
    if PAGE_SETTLE_SECONDS > 0:
        time.sleep(PAGE_SETTLE_SECONDS)
    if not set_sim_enable(device_id, True):
        return False
    if not set_volte_enable(device_id, True):
        return False
    return set_preferred_network(device_id, 5)


def _restore_dual_sim_roaming_off(device_id: str, sim1, sim2) -> bool:
    """失败恢复：尽量关闭双卡漫游开关。"""
    ok = True
    for sim in (sim1, sim2):
        if sim is None:
            continue
        if not _enter_sim_sub_settings_by_sim(device_id, sim):
            ok = False
            continue
        if PAGE_SETTLE_SECONDS > 0:
            time.sleep(PAGE_SETTLE_SECONDS)
        if not set_roaming_enable(device_id, False):
            ok = False
    return ok


def _run_roaming_volte_cycles(
    dut_id: str,
    slot_index: int,
    cycles: int,
    sub_steps: str,
    update,
    critical_fail,
):
    card_label = f"卡{slot_index + 1}"

    for cycle in range(1, cycles + 1):
        sub_steps += f"\n{card_label}第{cycle}轮：打开漫游"
        update(sub_steps)
        if not set_roaming_enable(dut_id, True):
            sub_steps += "-失败"
            update(sub_steps)
            return sub_steps, critical_fail(f"{card_label}第{cycle}轮打开漫游失败")
        sub_steps += "-成功"
        update(sub_steps)
        if ROAMING_SETTLE_SECONDS > 0:
            time.sleep(ROAMING_SETTLE_SECONDS)

        sub_steps += f"\n{card_label}第{cycle}轮：检查{card_label}状态栏VoLTE/VoNR(漫游开)"
        update(sub_steps)
        ok, detail = check_sim_volte_or_vonr_icon(dut_id, slot_index)
        if not ok:
            sub_steps += "-失败"
            update(sub_steps)
            return sub_steps, critical_fail(
                detail or f"{card_label}第{cycle}轮漫游开后VoLTE/VoNR检查失败"
            )
        sub_steps += "-成功"
        update(sub_steps)

        sub_steps += f"\n{card_label}第{cycle}轮：关闭漫游"
        update(sub_steps)
        if not set_roaming_enable(dut_id, False):
            sub_steps += "-失败"
            update(sub_steps)
            return sub_steps, critical_fail(f"{card_label}第{cycle}轮关闭漫游失败")
        sub_steps += "-成功"
        update(sub_steps)
        if ROAMING_SETTLE_SECONDS > 0:
            time.sleep(ROAMING_SETTLE_SECONDS)

        sub_steps += f"\n{card_label}第{cycle}轮：检查{card_label}状态栏VoLTE/VoNR(漫游关)"
        update(sub_steps)
        ok, detail = check_sim_volte_or_vonr_icon(dut_id, slot_index)
        if not ok:
            sub_steps += "-失败"
            update(sub_steps)
            return sub_steps, critical_fail(
                detail or f"{card_label}第{cycle}轮漫游关后VoLTE/VoNR检查失败"
            )
        sub_steps += "-成功"
        update(sub_steps)

    return sub_steps, None


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
        return {"status": "fail", "message": "测试机非双卡，无法执行漫游开关用例"}

    sub_steps = ""
    result = {"status": "fail", "message": "用例未执行完成"}

    def update(steps: str):
        if callable(step_update):
            step_update(steps)

    def critical_fail(message: str):
        return {"status": "fail", "message": message}

    try:
        sub_steps += "\n卡1打开SIM卡，打开VoLTE，首选网络5G或4G"
        update(sub_steps)
        if not _setup_sim_enable_volte_network(dut_id, sim1):
            sub_steps += "-失败"
            update(sub_steps)
            return critical_fail("卡1打开SIM卡/VoLTE/首选网络失败")
        sub_steps += "-成功"
        update(sub_steps)

        sub_steps, err = _run_roaming_volte_cycles(
            dut_id, 0, ROAMING_CYCLES, sub_steps, update, critical_fail
        )
        if err:
            return err

        sub_steps += "\n卡2打开SIM卡，打开VoLTE，首选网络5G或4G"
        update(sub_steps)
        if not _setup_sim_enable_volte_network(dut_id, sim2):
            sub_steps += "-失败"
            update(sub_steps)
            return critical_fail("卡2打开SIM卡/VoLTE/首选网络失败")
        sub_steps += "-成功"
        update(sub_steps)

        sub_steps, err = _run_roaming_volte_cycles(
            dut_id, 1, ROAMING_CYCLES, sub_steps, update, critical_fail
        )
        if err:
            return err

        result = {
            "status": "pass",
            "message": (
                f"卡1/卡2各完成{ROAMING_CYCLES}轮漫游开关，"
                "状态栏VoLTE/VoNR检查通过"
            ),
        }
        return result
    finally:
        sub_steps += "\n关闭双卡漫游开关(用例结束恢复)"
        update(sub_steps)
        if _restore_dual_sim_roaming_off(dut_id, sim1, sim2):
            sub_steps += "-成功"
        else:
            sub_steps += "-失败"
        update(sub_steps)
