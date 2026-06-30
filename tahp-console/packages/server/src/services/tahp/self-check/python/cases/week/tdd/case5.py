from utils.tdd.ui_default_sim_card import check_data_and_dial_card_enabled
from utils.tdd.ui_sim_pin import (
    reboot_and_unlock,
    set_sim_pin_disabled,
    set_sim_pin_enabled,
)
from utils.tdd.device_sim import resolve_dut_active, sim_slot_label
from utils.tdd.sim_setup import open_sim_only
from utils.tdd.ui_settings_activity import enter_sim_network_settings_by_adb
from utils.tdd.ui_volte_button import set_volte_enable


def run(category=None, case_index=None, device_info=None, **context):
    step_update = context.get("step_update")
    device_info = device_info or context.get("device_info") or {}

    _, dut_id, active_sim, slot_index, _, sim_err = resolve_dut_active(device_info)
    if sim_err:
        return {"status": "fail", "message": sim_err}

    slot_label = sim_slot_label(slot_index)
    sub_steps = ""

    sub_steps += f"\n进入{slot_label}子界面，打开{slot_label}并打开VoLTE"
    if callable(step_update):
        step_update(sub_steps)
    if not open_sim_only(dut_id, active_sim):
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        return {"status": "fail", "message": f"打开{slot_label}失败"}
    if not set_volte_enable(dut_id, True):
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        return {"status": "fail", "message": f"打开{slot_label} VoLTE失败"}
    sub_steps += "-成功"
    if callable(step_update):
        step_update(sub_steps)

    sub_steps += "\n进入设置的SIM卡与网络设置"
    if callable(step_update):
        step_update(sub_steps)
    if not enter_sim_network_settings_by_adb(dut_id):
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        return {"status": "fail", "message": "进入SIM卡与网络设置失败"}
    sub_steps += "-成功"
    if callable(step_update):
        step_update(sub_steps)

    sub_steps += "\n检查上网卡、拨号卡应不置灰"
    if callable(step_update):
        step_update(sub_steps)
    if not check_data_and_dial_card_enabled(dut_id, expected_enabled=True):
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        return {"status": "fail", "message": "单卡场景下，上网卡或拨号卡出现置灰"}
    sub_steps += "-成功"
    if callable(step_update):
        step_update(sub_steps)

    sub_steps += "\n设置SIM PIN码(1234)"
    if callable(step_update):
        step_update(sub_steps)
    if not set_sim_pin_enabled(dut_id):
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        return {"status": "fail", "message": "设置SIM PIN码失败"}
    sub_steps += "-成功"
    if callable(step_update):
        step_update(sub_steps)

    sub_steps += "\n重启手机"
    if callable(step_update):
        step_update(sub_steps)
    if not reboot_and_unlock(dut_id, unlock_sim_pin=True):
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        return {"status": "fail", "message": "重启或开机解锁失败"}
    sub_steps += "-成功"
    if callable(step_update):
        step_update(sub_steps)

    sub_steps += "\n关闭SIM PIN码"
    if callable(step_update):
        step_update(sub_steps)
    if not set_sim_pin_disabled(dut_id):
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        return {"status": "fail", "message": "关闭SIM PIN码失败"}
    sub_steps += "-成功"
    if callable(step_update):
        step_update(sub_steps)

    return {"status": "pass", "message": "单卡 SIM 设置与 PIN 验证通过"}
