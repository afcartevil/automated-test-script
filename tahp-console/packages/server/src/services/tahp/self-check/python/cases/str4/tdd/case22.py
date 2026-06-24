"""用户插入SIM卡后可自行设定相应的网络模式，优选驻留对应的网络上。"""

import time

from utils.tdd.apk.call import dial_and_check
from utils.tdd.apk.web import run_baidu_test
from utils.tdd.device_sim import (
    aux_call_slot,
    enter_sim_sub_settings_by_sim,
    get_sim_by_slot,
    resolve_aux,
    resolve_dut,
    sim_phone_number,
)
from utils.tdd.sim_setup import (
    NETWORK_TYPE_5G_AUTO,
    PAGE_SETTLE_SECONDS,
    enable_mobile_data,
    open_sim_only,
    setup_sim_preferred_network,
)
from utils.tdd.ui_first_network import set_preferred_network
from test.step_runner import StepRunner

NETWORK_PHASES = (
    (5, "2G/3G/4G/5G自动"),
    (4, "2G/3G/4G自动"),
    (3, "2G/3G自动"),
    (2, "仅3G"),
    (1, "仅2G"),
)
NETWORK_LABEL_23G_AUTO = "2G/3G自动"
NO_NETWORK_MESSAGE = "无网络环境"


def _phase_fail_message(net_label: str, web_ok: bool, mo_ok: bool, mt_ok: bool) -> str:
    parts = []
    if not web_ok:
        parts.append(f"百度访问失败({net_label})")
    if not mo_ok:
        parts.append(f"测试机主叫失败({net_label})")
    if not mt_ok:
        parts.append(f"辅测机主叫失败({net_label})")
    return "；".join(parts) if parts else f"网络档位测试失败({net_label})"


def run(category=None, case_index=None, device_info=None, **context):
    step_update = context.get("step_update")
    device_info = device_info or context.get("device_info") or {}
    dut, dut_id = resolve_dut(device_info)
    if not dut:
        return {"status": "fail", "message": dut_id}
    sim1 = get_sim_by_slot(dut.get("sim_cards") or [], 0)
    sim2 = get_sim_by_slot(dut.get("sim_cards") or [], 1)
    if not sim1:
        return {"status": "fail", "message": "测试机无卡1信息"}
    dut_number = sim_phone_number(sim1)
    aux_id, aux_number, _, err = resolve_aux(device_info)
    if err:
        return {"status": "fail", "message": err}
    aux_sim_cards = (device_info.get("Auxiliary") or [{}])[0].get("sim_cards") or []
    aux_slot = aux_call_slot(
        get_sim_by_slot(aux_sim_cards, 0),
        get_sim_by_slot(aux_sim_cards, 1),
    )
    if not dut_number or not aux_slot:
        return {"status": "fail", "message": "缺少测试机或辅测机号码"}

    steps = StepRunner(step_update)
    sim2_closed = False

    def restore_sim2() -> None:
        if sim2 and sim2_closed:
            steps.begin("恢复打开卡2(用例结束)")
            if open_sim_only(dut_id, sim2):
                steps.ok()
            else:
                steps.fail()

    if not enable_mobile_data(dut_id):
        return {"status": "fail", "message": "打开移动数据失败"}

    steps.begin("卡1打开，首选网络5G或4G")
    if not setup_sim_preferred_network(dut_id, sim1, enable=True, network_type=NETWORK_TYPE_5G_AUTO):
        steps.fail()
        return {"status": "fail", "message": "卡1打开或首选网络设置失败"}
    steps.ok()
    if sim2:
        steps.begin("关闭卡2")
        if not setup_sim_preferred_network(dut_id, sim2, enable=False):
            steps.fail()
            return {"status": "fail", "message": "关闭卡2失败"}
        sim2_closed = True
        steps.ok()

    result_status = "pass"
    result_message = "各档首选网络下百度与双机语音主被叫通过"

    try:
        for net_type, net_label in NETWORK_PHASES:
            steps.begin(f"卡1设置首选网络({net_label})")
            if not enter_sim_sub_settings_by_sim(dut_id, sim1):
                steps.fail()
                result_status = "fail"
                result_message = f"进入卡1子界面失败({net_label})"
                break
            time.sleep(PAGE_SETTLE_SECONDS)
            if not set_preferred_network(dut_id, net_type):
                steps.fail()
                result_status = "fail"
                result_message = f"设置首选网络失败({net_label})"
                break
            steps.ok()

            steps.begin(f"访问百度({net_label})")
            web_ok = run_baidu_test(dut_id)
            if web_ok:
                steps.ok()
            else:
                steps.fail()

            steps.begin(f"测试机主叫辅测机语音({net_label})")
            mo_ok = dial_and_check(dut_id, 1, aux_number, 2)
            if mo_ok:
                steps.ok()
            else:
                steps.fail()

            steps.begin(f"辅测机主叫测试机语音({net_label})")
            mt_ok = dial_and_check(aux_id, aux_slot, dut_number, 2)
            if mt_ok:
                steps.ok()
            else:
                steps.fail()

            if web_ok and mo_ok and mt_ok:
                continue

            if (
                net_label == NETWORK_LABEL_23G_AUTO
                and not web_ok
                and not mo_ok
                and not mt_ok
            ):
                result_status = "部分pass"
                result_message = NO_NETWORK_MESSAGE
            else:
                result_status = "fail"
                result_message = _phase_fail_message(net_label, web_ok, mo_ok, mt_ok)
            break
    finally:
        restore_sim2()

    return {"status": result_status, "message": result_message}
