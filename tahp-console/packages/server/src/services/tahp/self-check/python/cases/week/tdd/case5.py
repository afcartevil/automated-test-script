from utils.tdd.ui_default_sim_card import (
    check_data_and_dial_card_enabled,
)
from utils.tdd.ui_sim_pin import (
    reboot_and_unlock,
    set_sim_pin_disabled,
    set_sim_pin_enabled,
)
from utils.tdd.device_sim import get_sim_by_slot, sim_phone_number
from utils.tdd.sim_setup import open_sim_only, setup_sim_preferred_network
from utils.tdd.ui_settings_activity import enter_sim_network_settings_by_adb
from utils.tdd.ui_volte_button import set_volte_enable


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

    sim_cards = dut.get("sim_cards") or []
    sim1 = get_sim_by_slot(sim_cards, 0)
    sim2 = get_sim_by_slot(sim_cards, 1)
    if not sim1 or not sim2:
        return {"status": "fail", "message": "测试机非双卡，无法测试"}

    sim1_name = (sim1.get("display_name") or sim1.get("carrier_name") or "").strip()
    sim2_name = (sim2.get("display_name") or sim2.get("carrier_name") or "").strip()
    sim1_number = sim_phone_number(sim1)
    sim2_number = sim_phone_number(sim2)
    sub_steps = ""

    # 先确保两张卡与 VoLTE 均打开，建立一致前置条件。
    sub_steps += "\n进入卡1子界面，打开卡1并打开VoLTE"
    if callable(step_update):
        step_update(sub_steps)
    if not open_sim_only(dut_id, sim1):
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        return {"status": "fail", "message": "打开卡1失败"}
    if not set_volte_enable(dut_id, True):
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        return {"status": "fail", "message": "打开卡1 VoLTE失败"}
    sub_steps += "-成功"
    if callable(step_update):
        step_update(sub_steps)

    sub_steps += "\n进入卡2子界面，打开卡2并打开VoLTE"
    if callable(step_update):
        step_update(sub_steps)
    if not open_sim_only(dut_id, sim2):
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        return {"status": "fail", "message": "打开卡2失败"}
    if not set_volte_enable(dut_id, True):
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        return {"status": "fail", "message": "打开卡2 VoLTE失败"}
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
        return {"status": "fail", "message": "双卡均开启时，上网卡或拨号卡出现置灰"}
    sub_steps += "-成功"
    if callable(step_update):
        step_update(sub_steps)

    sub_steps += "\n测试机关闭卡1"
    if callable(step_update):
        step_update(sub_steps)
    if not setup_sim_preferred_network(dut_id, sim1, enable=False):
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        return {"status": "fail", "message": "关闭卡1失败"}
    sub_steps += "-成功"
    if callable(step_update):
        step_update(sub_steps)

    sub_steps += "\n检查上网卡、拨号卡应置灰"
    if callable(step_update):
        step_update(sub_steps)
    if not enter_sim_network_settings_by_adb(dut_id):
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        return {"status": "fail", "message": "进入SIM卡与网络设置失败（关闭卡1后）"}
    if not check_data_and_dial_card_enabled(dut_id, expected_enabled=False):
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        return {"status": "fail", "message": "关闭卡1后，上网卡或拨号卡未置灰"}
    sub_steps += "-成功"
    if callable(step_update):
        step_update(sub_steps)

    sub_steps += "\n测试机恢复打开卡1"
    if callable(step_update):
        step_update(sub_steps)
    if not open_sim_only(dut_id, sim1):
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        return {"status": "fail", "message": "恢复打开卡1失败"}
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

    return {"status": "pass", "message": "子步骤均pass"}
