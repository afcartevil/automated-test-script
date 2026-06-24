import time

from utils.tdd.ui_dsds import (
    PAGE_SETTLE_SECONDS,
    ensure_dsds_switch_state,
    is_dsds_switch_grayed_out,
)
from utils.tdd.ui_first_network import set_preferred_network
from utils.tdd.ui_network_info import check_dual_sim_volte_or_vonr_icons
from utils.tdd.ui_settings_activity import (
    enter_phone_info_settings_by_adb,
    enter_sim_sub_settings_by_adb,
)
from utils.tdd.ui_turn_onoff_sim import set_sim_enable
from utils.tdd.ui_volte_button import set_volte_enable

EXPECTED_SIM_SLOTS = 2
PLATFORM_UNISOC = "展锐"


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


def _is_unisoc_platform(dut: dict) -> bool:
    return (dut.get("platform") or "").strip() == PLATFORM_UNISOC


def _setup_dual_sim_volte_network(
    dut_id: str,
    sim1,
    sim2,
    sub_steps: str,
    update,
    critical_fail,
):
    sub_steps += "\n卡1打开SIM卡，打开VoLTE，首选网络5G或4G"
    update(sub_steps)
    if not _setup_sim_enable_volte_network(dut_id, sim1):
        sub_steps += "-失败"
        update(sub_steps)
        return sub_steps, critical_fail("卡1打开SIM卡/VoLTE/首选网络失败")
    sub_steps += "-成功"
    update(sub_steps)

    sub_steps += "\n卡2打开SIM卡，打开VoLTE，首选网络5G或4G"
    update(sub_steps)
    if not _setup_sim_enable_volte_network(dut_id, sim2):
        sub_steps += "-失败"
        update(sub_steps)
        return sub_steps, critical_fail("卡2打开SIM卡/VoLTE/首选网络失败")
    sub_steps += "-成功"
    update(sub_steps)

    return sub_steps, None


def _check_dual_sim_volte_status_bar(
    dut_id: str,
    sub_steps: str,
    update,
    critical_fail,
    step_label: str,
):
    sub_steps += f"\n{step_label}"
    update(sub_steps)
    ok, detail = check_dual_sim_volte_or_vonr_icons(dut_id, EXPECTED_SIM_SLOTS)
    if not ok:
        sub_steps += "-失败"
        update(sub_steps)
        msg = detail or "双卡状态栏未均显示VoLTE或VoNR图标"
        return sub_steps, critical_fail(msg)
    sub_steps += "-成功"
    update(sub_steps)
    return sub_steps, None


def _enter_phone_info(dut_id: str, sub_steps: str, update, critical_fail):
    sub_steps += "\n进入手机信息"
    update(sub_steps)
    if not enter_phone_info_settings_by_adb(dut_id):
        sub_steps += "-失败"
        update(sub_steps)
        return sub_steps, critical_fail("进入手机信息失败")
    sub_steps += "-成功"
    update(sub_steps)
    if PAGE_SETTLE_SECONDS > 0:
        time.sleep(PAGE_SETTLE_SECONDS)
    return sub_steps, None


def _run_unisoc_flow(dut_id: str, sim1, sim2, sub_steps: str, update, critical_fail):
    sub_steps, err = _setup_dual_sim_volte_network(
        dut_id, sim1, sim2, sub_steps, update, critical_fail
    )
    if err:
        return err

    sub_steps, err = _check_dual_sim_volte_status_bar(
        dut_id,
        sub_steps,
        update,
        critical_fail,
        "检查双卡状态栏VoLTE或VoNR图标",
    )
    if err:
        return err

    sub_steps, err = _enter_phone_info(dut_id, sub_steps, update, critical_fail)
    if err:
        return err

    sub_steps += "\n检查DSDS开关应为置灰"
    update(sub_steps)
    if not is_dsds_switch_grayed_out(dut_id):
        sub_steps += "-失败"
        update(sub_steps)
        return critical_fail("展锐平台DSDS开关未置灰，用户可能可以关闭DSDS")
    sub_steps += "-成功"
    update(sub_steps)

    return {
        "status": "pass",
        "message": "展锐平台双卡VoLTE/VoNR正常，DSDS开关已置灰",
    }


def _run_default_flow(dut_id: str, sim1, sim2, sub_steps: str, update, critical_fail):
    sub_steps, err = _setup_dual_sim_volte_network(
        dut_id, sim1, sim2, sub_steps, update, critical_fail
    )
    if err:
        return err

    sub_steps, err = _check_dual_sim_volte_status_bar(
        dut_id,
        sub_steps,
        update,
        critical_fail,
        "检查双卡状态栏VoLTE或VoNR图标(初始)",
    )
    if err:
        return err

    sub_steps, err = _enter_phone_info(dut_id, sub_steps, update, critical_fail)
    if err:
        return err

    sub_steps += "\n确认DSDS开关为开启"
    update(sub_steps)
    if not ensure_dsds_switch_state(dut_id, True):
        sub_steps += "-失败"
        update(sub_steps)
        return critical_fail("无法将DSDS开关设为开启")
    sub_steps += "-成功"
    update(sub_steps)

    sub_steps, err = _check_dual_sim_volte_status_bar(
        dut_id,
        sub_steps,
        update,
        critical_fail,
        "检查双卡状态栏VoLTE或VoNR图标(before)",
    )
    if err:
        return err

    sub_steps += "\n关闭DSDS开关"
    update(sub_steps)
    if not ensure_dsds_switch_state(dut_id, False):
        sub_steps += "-失败"
        update(sub_steps)
        return critical_fail("无法将DSDS开关设为关闭")
    sub_steps += "-成功"
    update(sub_steps)

    sub_steps, err = _check_dual_sim_volte_status_bar(
        dut_id,
        sub_steps,
        update,
        critical_fail,
        "检查双卡状态栏VoLTE或VoNR图标(after_disable)",
    )
    if err:
        return err

    sub_steps += "\n重新开启DSDS开关"
    update(sub_steps)
    if not ensure_dsds_switch_state(dut_id, True):
        sub_steps += "-失败"
        update(sub_steps)
        return critical_fail("无法将DSDS开关重新开启")
    sub_steps += "-成功"
    update(sub_steps)

    sub_steps, err = _check_dual_sim_volte_status_bar(
        dut_id,
        sub_steps,
        update,
        critical_fail,
        "检查双卡状态栏VoLTE或VoNR图标(after_enable)",
    )
    if err:
        return err

    return {
        "status": "pass",
        "message": "DSDS开关已按开启→关闭→开启完成切换，双卡状态栏VoLTE/VoNR检查通过",
    }


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
        return {"status": "fail", "message": "测试机非双卡，无法执行DSDS能力用例"}

    sub_steps = ""

    def update(steps: str):
        if callable(step_update):
            step_update(steps)

    def critical_fail(message: str):
        return {"status": "fail", "message": message}

    if _is_unisoc_platform(dut):
        return _run_unisoc_flow(dut_id, sim1, sim2, sub_steps, update, critical_fail)

    return _run_default_flow(dut_id, sim1, sim2, sub_steps, update, critical_fail)
