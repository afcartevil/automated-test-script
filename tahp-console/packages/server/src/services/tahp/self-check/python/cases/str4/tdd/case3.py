import time

from utils.tdd.ui_automatic import (
    disable_airplane_mode,
    enable_airplane_mode,
    screen_off_and_wake,
)
from utils.tdd.ui_mobile_data_switch import check_mobile_data_switch_grayed
from utils.tdd.ui_network_info import (
    check_dual_sim_volte_or_vonr_icons,
    check_quick_settings_airplane_no_sim_info,
)
from utils.tdd.ui_settings_activity import enter_sim_network_settings_by_adb

EXPECTED_SIM_SLOTS = 2
PAGE_SETTLE_SECONDS = 1.0
NETWORK_INFO_SETTLE_SEC = 1.0
AIRPLANE_TOGGLE_SETTLE_SEC = 30.0
SCREEN_OFF_SECONDS = 2.0


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

    sub_steps = ""
    result = {"status": "fail", "message": "用例未执行完成"}

    def update(steps: str):
        if callable(step_update):
            step_update(steps)

    def critical_fail(message: str):
        return {"status": "fail", "message": message}

    def _enter_sim_network():
        nonlocal sub_steps
        sub_steps += "\n进入SIM卡与网络设置"
        update(sub_steps)
        if not enter_sim_network_settings_by_adb(dut_id):
            sub_steps += "-失败"
            update(sub_steps)
            return critical_fail("进入SIM卡与网络设置失败")
        sub_steps += "-成功"
        update(sub_steps)
        if PAGE_SETTLE_SECONDS > 0:
            time.sleep(PAGE_SETTLE_SECONDS)
        return None

    def _check_mobile_data(expected_grayed: bool, step_label: str):
        nonlocal sub_steps
        sub_steps += f"\n{step_label}"
        update(sub_steps)
        ok, detail = check_mobile_data_switch_grayed(dut_id, expected_grayed)
        if not ok:
            sub_steps += "-失败"
            update(sub_steps)
            return critical_fail(detail or "移动数据开关状态不符合预期")
        sub_steps += "-成功"
        update(sub_steps)
        return None

    def _check_status_airplane(step_label: str):
        nonlocal sub_steps
        sub_steps += f"\n{step_label}"
        update(sub_steps)
        if NETWORK_INFO_SETTLE_SEC > 0:
            time.sleep(NETWORK_INFO_SETTLE_SEC)
        ok, detail = check_quick_settings_airplane_no_sim_info(
            dut_id, EXPECTED_SIM_SLOTS
        )
        if not ok:
            sub_steps += "-失败"
            update(sub_steps)
            return critical_fail(detail or "飞行模式状态栏检查失败")
        sub_steps += "-成功"
        update(sub_steps)
        return None

    def _check_status_dual_volte(step_label: str):
        nonlocal sub_steps
        sub_steps += f"\n{step_label}"
        update(sub_steps)
        if NETWORK_INFO_SETTLE_SEC > 0:
            time.sleep(NETWORK_INFO_SETTLE_SEC)
        ok, detail = check_dual_sim_volte_or_vonr_icons(dut_id, EXPECTED_SIM_SLOTS)
        if not ok:
            sub_steps += "-失败"
            update(sub_steps)
            return critical_fail(detail or "双卡状态栏VoLTE/VoNR检查失败")
        sub_steps += "-成功"
        update(sub_steps)
        return None

    try:
        sub_steps += "\n打开飞行模式"
        update(sub_steps)
        if not enable_airplane_mode(dut_id):
            sub_steps += "-失败"
            update(sub_steps)
            return critical_fail("打开飞行模式失败")
        sub_steps += "-成功"
        update(sub_steps)
        if AIRPLANE_TOGGLE_SETTLE_SEC > 0:
            time.sleep(AIRPLANE_TOGGLE_SETTLE_SEC)

        err = _enter_sim_network()
        if err:
            return err
        err = _check_mobile_data(True, '检查"移动数据"开关应为置灰')
        if err:
            return err
        err = _check_status_airplane(
            "下拉状态栏应显示飞行模式图标且无法读到双卡SIM驻网信息"
        )
        if err:
            return err

        sub_steps += "\n关闭飞行模式"
        update(sub_steps)
        if not disable_airplane_mode(dut_id):
            sub_steps += "-失败"
            update(sub_steps)
            return critical_fail("关闭飞行模式失败")
        sub_steps += "-成功"
        update(sub_steps)
        if AIRPLANE_TOGGLE_SETTLE_SEC > 0:
            time.sleep(AIRPLANE_TOGGLE_SETTLE_SEC)

        err = _enter_sim_network()
        if err:
            return err
        err = _check_mobile_data(False, '检查"移动数据"开关应不置灰')
        if err:
            return err

        sub_steps += "\n等待网络恢复"
        update(sub_steps)
        sub_steps += "-成功"
        update(sub_steps)

        err = _check_status_dual_volte(
            "下拉状态栏双卡应显示VoLTE或VoNR图标"
        )
        if err:
            return err

        sub_steps += "\n打开飞行模式"
        update(sub_steps)
        if not enable_airplane_mode(dut_id):
            sub_steps += "-失败"
            update(sub_steps)
            return critical_fail("再次打开飞行模式失败")
        sub_steps += "-成功"
        update(sub_steps)
        if AIRPLANE_TOGGLE_SETTLE_SEC > 0:
            time.sleep(AIRPLANE_TOGGLE_SETTLE_SEC)

        sub_steps += "\n灭屏后亮屏"
        update(sub_steps)
        if not screen_off_and_wake(dut_id, off_seconds=SCREEN_OFF_SECONDS):
            sub_steps += "-失败"
            update(sub_steps)
            return critical_fail("灭屏亮屏操作失败")
        sub_steps += "-成功"
        update(sub_steps)

        err = _check_status_airplane(
            "灭屏亮屏后下拉状态栏应显示飞行模式图标且无法读到双卡SIM驻网信息"
        )
        if err:
            return err

        result = {
            "status": "pass",
            "message": "飞行模式开关、移动数据置灰与状态栏图标检查通过",
        }
        return result
    finally:
        sub_steps += "\n关闭飞行模式(用例结束恢复)"
        update(sub_steps)
        if disable_airplane_mode(dut_id):
            sub_steps += "-成功"
        else:
            sub_steps += "-失败"
        update(sub_steps)
