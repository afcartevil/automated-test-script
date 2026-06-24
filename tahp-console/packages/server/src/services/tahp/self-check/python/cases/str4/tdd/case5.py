import time

from utils.tdd.apk.web import run_web_test
from utils.tdd.ui_automatic import set_mobile_data_enable, set_wifi_enable
from utils.tdd.ui_default_sim_card import check_data_card_enabled
from utils.tdd.ui_first_network import set_preferred_network
from utils.tdd.ui_settings_activity import (
    enter_sim_network_settings_by_adb,
    enter_sim_sub_settings_by_adb,
)
from utils.tdd.ui_turn_onoff_sim import set_sim_enable

BAIDU_URL = "https://www.baidu.com"
WEB_TIMEOUT_SECONDS = 60
PAGE_SETTLE_SECONDS = 1.0
DATA_SETTLE_SECONDS = 2.0
SIM_OFF_SETTLE_SECONDS = 1.0


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


def _set_sim_enable_on_current_page(device_id: str, enable: bool) -> bool:
    if not set_sim_enable(device_id, enable):
        return False
    if PAGE_SETTLE_SECONDS > 0:
        time.sleep(PAGE_SETTLE_SECONDS)
    return True


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


def _restore_dual_sim_enabled(device_id: str, sim1, sim2) -> bool:
    ok = True
    for sim in (sim1, sim2):
        if sim is None:
            continue
        if not _setup_sim_preferred_network(device_id, sim, enable=True):
            ok = False
    return ok


def _probe_baidu_access(device_id: str) -> bool:
    """调起 APK 访问百度，返回 Pass/Fail 结果页判定（同 run_web_test）。"""
    return run_web_test(
        device_id,
        BAIDU_URL,
        force_refresh=True,
        timeout_seconds=WEB_TIMEOUT_SECONDS,
    )


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
        return {"status": "fail", "message": "测试机非双卡，无法执行移动数据切换用例"}

    sub_steps = ""
    result = {"status": "fail", "message": "用例未执行完成"}

    def update(steps: str):
        if callable(step_update):
            step_update(steps)

    def critical_fail(message: str):
        return {"status": "fail", "message": message}

    def _set_mobile_data(enabled: bool, step_label: str):
        nonlocal sub_steps
        sub_steps += f"\n{step_label}"
        update(sub_steps)
        if not set_mobile_data_enable(dut_id, enabled):
            sub_steps += "-失败"
            update(sub_steps)
            return critical_fail(
                f"{'打开' if enabled else '关闭'}移动数据开关失败"
            )
        sub_steps += "-成功"
        update(sub_steps)
        if DATA_SETTLE_SECONDS > 0:
            time.sleep(DATA_SETTLE_SECONDS)
        return None

    def _check_baidu(step_label: str, expect_access: bool):
        nonlocal sub_steps
        sub_steps += f"\n{step_label}"
        update(sub_steps)
        accessible = _probe_baidu_access(dut_id)
        if accessible == expect_access:
            sub_steps += "-成功"
            update(sub_steps)
            return None
        sub_steps += "-失败"
        update(sub_steps)
        if expect_access:
            return critical_fail(f"{step_label}：数据开启时应能访问百度")
        return critical_fail(f"{step_label}：数据关闭时不应能访问百度")

    try:
        sub_steps += "\n打开移动数据开关，关闭Wi-Fi开关"
        update(sub_steps)
        if not set_mobile_data_enable(dut_id, True):
            sub_steps += "-失败(移动数据)"
            update(sub_steps)
            return critical_fail("打开移动数据开关失败")
        if not set_wifi_enable(dut_id, False):
            sub_steps += "-失败(Wi-Fi)"
            update(sub_steps)
            return critical_fail("关闭Wi-Fi开关失败")
        sub_steps += "-成功"
        update(sub_steps)
        if DATA_SETTLE_SECONDS > 0:
            time.sleep(DATA_SETTLE_SECONDS)

        sub_steps += "\n卡1打开，首选网络5G或4G自动"
        update(sub_steps)
        if not _setup_sim_preferred_network(dut_id, sim1, enable=True):
            sub_steps += "-失败"
            update(sub_steps)
            return critical_fail("卡1打开或首选网络设置失败")
        sub_steps += "-成功"
        update(sub_steps)

        sub_steps += "\n关闭卡2"
        update(sub_steps)
        if not _setup_sim_preferred_network(dut_id, sim2, enable=False):
            sub_steps += "-失败"
            update(sub_steps)
            return critical_fail("关闭卡2失败")
        sub_steps += "-成功"
        update(sub_steps)

        err = _check_baidu("调起APK访问百度(卡1数据，应能访问)", True)
        if err:
            return err

        err = _set_mobile_data(False, "关闭移动数据开关")
        if err:
            return err

        err = _check_baidu("调起APK访问百度(数据关，应不能访问)", False)
        if err:
            return err

        err = _set_mobile_data(True, "打开移动数据开关")
        if err:
            return err

        sub_steps += "\n卡2打开，首选网络5G或4G自动"
        update(sub_steps)
        if not _setup_sim_preferred_network(dut_id, sim2, enable=True):
            sub_steps += "-失败"
            update(sub_steps)
            return critical_fail("卡2打开或首选网络设置失败")
        sub_steps += "-成功"
        update(sub_steps)

        sub_steps += "\n关闭卡1"
        update(sub_steps)
        if not _setup_sim_preferred_network(dut_id, sim1, enable=False):
            sub_steps += "-失败"
            update(sub_steps)
            return critical_fail("关闭卡1失败")
        sub_steps += "-成功"
        update(sub_steps)

        err = _check_baidu("调起APK访问百度(卡2数据，应能访问)", True)
        if err:
            return err

        err = _set_mobile_data(False, "关闭移动数据开关")
        if err:
            return err

        err = _check_baidu("调起APK访问百度(数据关，应不能访问)", False)
        if err:
            return err

        err = _set_mobile_data(True, "打开移动数据开关")
        if err:
            return err

        sub_steps += "\n打开卡1"
        update(sub_steps)
        if not _enter_sim_sub_settings_by_sim(dut_id, sim1):
            sub_steps += "-失败"
            update(sub_steps)
            return critical_fail("打开卡1失败(进入子界面)")
        if not _set_sim_enable_on_current_page(dut_id, True):
            sub_steps += "-失败"
            update(sub_steps)
            return critical_fail("打开卡1失败")
        sub_steps += "-成功"
        update(sub_steps)

        sub_steps += "\n进入SIM卡与网络设置，检查上网卡菜单应不置灰"
        update(sub_steps)
        if not enter_sim_network_settings_by_adb(dut_id):
            sub_steps += "-失败(进入设置)"
            update(sub_steps)
            return critical_fail("进入SIM卡与网络设置失败")
        if PAGE_SETTLE_SECONDS > 0:
            time.sleep(PAGE_SETTLE_SECONDS)
        ok, detail = check_data_card_enabled(dut_id, expected_enabled=True)
        if not ok:
            sub_steps += "-失败"
            update(sub_steps)
            return critical_fail(detail or "上网卡菜单仍为置灰")
        sub_steps += "-成功"
        update(sub_steps)

        result = {
            "status": "pass",
            "message": "双卡移动数据切换与百度访问、上网卡菜单检查通过",
        }
        return result
    finally:
        sub_steps += "\n恢复打开卡1和卡2(用例结束)"
        update(sub_steps)
        if _restore_dual_sim_enabled(dut_id, sim1, sim2):
            sub_steps += "-成功"
        else:
            sub_steps += "-失败"
        update(sub_steps)
