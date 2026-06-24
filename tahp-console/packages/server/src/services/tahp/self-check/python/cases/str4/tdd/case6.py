import time

from utils.tdd.ui_settings_activity import enter_sim_sub_settings_by_adb
from utils.tdd.ui_sim_card_name import (
    check_sim_card_display_name,
    set_sim_card_display_name,
    verify_sim_card_display_name_saved,
)
from utils.tdd.ui_turn_onoff_sim import set_sim_enable

PAGE_SETTLE_SECONDS = 1.0
SIM_NAME_TEST_SUFFIX = "*#@&%"


def _get_sim_by_slot(sim_cards, slot_index):
    return next((s for s in sim_cards if s.get("slot_index") == slot_index), None)


def _sim_subscription_id(sim):
    if not sim:
        return None
    try:
        return int(sim.get("subscription_id"))
    except (TypeError, ValueError):
        return None


def _expected_sim_name(sim) -> str:
    return (sim.get("display_name") or sim.get("carrier_name") or "").strip()


def _enter_sim_sub_settings_by_sim(device_id: str, sim) -> bool:
    sub_id = _sim_subscription_id(sim)
    if sub_id is None:
        return False
    return enter_sim_sub_settings_by_adb(device_id, sub_id)


def _restore_sim_display_name(device_id: str, sim, original_name: str) -> bool:
    if not original_name:
        return False
    if not _enter_sim_sub_settings_by_sim(device_id, sim):
        return False
    if PAGE_SETTLE_SECONDS > 0:
        time.sleep(PAGE_SETTLE_SECONDS)
    return set_sim_card_display_name(device_id, original_name)


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

    project_name = (dut.get("project_name") or "").strip()
    if not project_name:
        return {"status": "fail", "message": "device_info 中无 project_name"}

    sim1 = _get_sim_by_slot(dut.get("sim_cards") or [], 0)
    if not sim1:
        return {"status": "fail", "message": "测试机无卡1信息，无法执行SIM卡名称用例"}

    original_name = _expected_sim_name(sim1)
    if not original_name:
        return {"status": "fail", "message": "device_info 中卡1无运营商/显示名称"}

    sub_steps = ""
    name_changed = False

    def update(steps: str):
        if callable(step_update):
            step_update(steps)

    def critical_fail(message: str):
        return {"status": "fail", "message": message}

    try:
        sub_steps += "\n进入卡1子界面"
        update(sub_steps)
        if not _enter_sim_sub_settings_by_sim(dut_id, sim1):
            sub_steps += "-失败"
            update(sub_steps)
            return critical_fail("进入卡1子界面失败")
        sub_steps += "-成功"
        update(sub_steps)
        if PAGE_SETTLE_SECONDS > 0:
            time.sleep(PAGE_SETTLE_SECONDS)

        sub_steps += "\n打开卡1"
        update(sub_steps)
        if not set_sim_enable(dut_id, True):
            sub_steps += "-失败"
            update(sub_steps)
            return critical_fail("打开卡1失败")
        sub_steps += "-成功"
        update(sub_steps)
        if PAGE_SETTLE_SECONDS > 0:
            time.sleep(PAGE_SETTLE_SECONDS)

        sub_steps += "\n检查SIM卡名称菜单运营商名称"
        update(sub_steps)
        ok, detail = check_sim_card_display_name(dut_id, original_name)
        if not ok:
            sub_steps += "-失败"
            update(sub_steps)
            return critical_fail(detail or "SIM卡名称与运营商不符")
        sub_steps += "-成功"
        update(sub_steps)

        test_name = f"{project_name}{SIM_NAME_TEST_SUFFIX}"
        sub_steps += f"\n修改SIM卡名称为「{test_name}」"
        update(sub_steps)
        if not set_sim_card_display_name(dut_id, test_name):
            sub_steps += "-失败"
            update(sub_steps)
            return critical_fail("修改SIM卡名称失败")
        name_changed = True
        sub_steps += "-成功"
        update(sub_steps)

        sub_steps += f"\n检查SIM卡名称已更新为「{test_name}」"
        update(sub_steps)
        ok, detail = verify_sim_card_display_name_saved(dut_id, test_name)
        if not ok:
            sub_steps += "-失败"
            update(sub_steps)
            return critical_fail(detail or "SIM卡名称未更新")
        sub_steps += "-成功"
        update(sub_steps)

        sub_steps += f"\n恢复SIM卡名称为「{original_name}」"
        update(sub_steps)
        if not set_sim_card_display_name(dut_id, original_name):
            sub_steps += "-失败"
            update(sub_steps)
            return critical_fail("恢复SIM卡原名称失败")
        name_changed = False
        sub_steps += "-成功"
        update(sub_steps)

        sub_steps += "\n检查SIM卡名称已恢复"
        update(sub_steps)
        ok, detail = verify_sim_card_display_name_saved(dut_id, original_name)
        if not ok:
            sub_steps += "-失败"
            update(sub_steps)
            return critical_fail(detail or "SIM卡名称未恢复为原运营商名称")
        sub_steps += "-成功"
        update(sub_steps)

        return {
            "status": "pass",
            "message": f"SIM卡名称已改为{project_name}{SIM_NAME_TEST_SUFFIX}并恢复原名称",
        }
    finally:
        if name_changed and original_name:
            sub_steps += "\n恢复SIM卡原名称(用例结束)"
            update(sub_steps)
            if _restore_sim_display_name(dut_id, sim1, original_name):
                sub_steps += "-成功"
            else:
                sub_steps += "-失败"
            update(sub_steps)
