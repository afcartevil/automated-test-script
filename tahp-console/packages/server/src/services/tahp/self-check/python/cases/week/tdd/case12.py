from utils.tdd.ui_network_search import (
    NETWORK_SCAN_INITIAL_DELAY_SECONDS,
    NETWORK_SCAN_POLL_INTERVAL_SECONDS,
    NETWORK_SCAN_POLL_MAX_ATTEMPTS,
    enter_network_select_screen,
    poll_network_scan_found,
    set_auto_select_network,
)
from utils.tdd.device_sim import get_sim_by_slot
from utils.tdd.sim_setup import open_sim_only


def _run_manual_search_for_sim(
    device_id: str,
    sim_card,
    label: str,
    step_update,
    sub_steps: str,
) -> tuple[bool, str]:
    sub_steps += f"\n{label}进入SIM卡子界面并打开SIM卡"
    if callable(step_update):
        step_update(sub_steps)
    if not open_sim_only(device_id, sim_card):
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        return False, sub_steps
    sub_steps += "-成功"
    if callable(step_update):
        step_update(sub_steps)

    sub_steps += f"\n{label}进入选择网络界面"
    if callable(step_update):
        step_update(sub_steps)
    if not enter_network_select_screen(device_id):
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        return False, sub_steps
    sub_steps += "-成功"
    if callable(step_update):
        step_update(sub_steps)

    sub_steps += f"\n{label}关闭自动选择网络"
    if callable(step_update):
        step_update(sub_steps)
    if not set_auto_select_network(device_id, False):
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        return False, sub_steps
    sub_steps += "-成功"
    if callable(step_update):
        step_update(sub_steps)

    sub_steps += (
        f"\n{label}等待搜网（关闭后先等{NETWORK_SCAN_INITIAL_DELAY_SECONDS}s，"
        f"再每{NETWORK_SCAN_POLL_INTERVAL_SECONDS}s检查，"
        f"共{NETWORK_SCAN_POLL_MAX_ATTEMPTS}次，停留选择网络页）"
    )
    if callable(step_update):
        step_update(sub_steps)
    if not poll_network_scan_found(device_id):
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        return False, sub_steps
    sub_steps += "-成功"
    if callable(step_update):
        step_update(sub_steps)

    sub_steps += f"\n{label}打开自动选择网络"
    if callable(step_update):
        step_update(sub_steps)
    if not set_auto_select_network(device_id, True):
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
        return {"status": "fail", "message": "测试机非双卡，无法执行手动搜网用例"}

    sub_steps = ""

    ok, sub_steps = _run_manual_search_for_sim(dut_id, sim1, "卡1", step_update, sub_steps)
    if not ok:
        return {"status": "fail", "message": "卡1手动搜网失败"}

    ok, sub_steps = _run_manual_search_for_sim(dut_id, sim2, "卡2", step_update, sub_steps)
    if not ok:
        return {"status": "fail", "message": "卡2手动搜网失败"}

    return {"status": "pass", "message": "卡1与卡2手动搜网验证通过"}
