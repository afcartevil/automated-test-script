"""5G SA下内容为图片的彩信发送&接收能力。"""

from utils.tdd.apk.message import (
    exchange_mms_aux_to_dut,
    exchange_mms_dut_to_aux,
    wait_message_exchange_interval,
)
from utils.tdd.device_sim import get_sim_by_slot, resolve_aux, resolve_dut, sim_phone_number
from utils.tdd.sim_setup import (
    NETWORK_TYPE_5G_AUTO,
    enable_mobile_data,
    open_sim_only,
    setup_sim_preferred_network,
)
from test.step_runner import StepRunner


def run(category=None, case_index=None, device_info=None, **context):
    step_update = context.get("step_update")
    device_info = device_info or context.get("device_info") or {}
    dut, dut_id = resolve_dut(device_info)
    if not dut:
        return {"status": "fail", "message": dut_id}
    sim1 = get_sim_by_slot(dut.get("sim_cards") or [], 0)
    sim2 = get_sim_by_slot(dut.get("sim_cards") or [], 1)
    if not sim1 or not sim2:
        return {"status": "fail", "message": "测试机非双卡，无法执行彩信用例"}
    dut_number = sim_phone_number(sim1)
    if not dut_number:
        return {"status": "fail", "message": "测试机卡1无可用号码"}
    aux_id, aux_number, aux_sim, err = resolve_aux(device_info)
    if err:
        return {"status": "fail", "message": err}

    steps = StepRunner(step_update)
    sim2_closed = False
    try:
        if not enable_mobile_data(dut_id):
            return {"status": "fail", "message": "打开移动数据失败"}
        steps.begin("打开卡1，首选网络5G或4G")
        if not setup_sim_preferred_network(
            dut_id, sim1, enable=True, network_type=NETWORK_TYPE_5G_AUTO
        ):
            steps.fail()
            return {"status": "fail", "message": "卡1打开或首选网络设置失败"}
        steps.ok()
        steps.begin("关闭卡2")
        if not setup_sim_preferred_network(dut_id, sim2, enable=False):
            steps.fail()
            return {"status": "fail", "message": "关闭卡2失败"}
        sim2_closed = True
        steps.ok()
        steps.begin("测试机给辅测机发送彩信，检测是否成功")
        ok, msg = exchange_mms_dut_to_aux(dut_id, "sim1", aux_id, aux_number)
        if not ok:
            steps.fail()
            return {"status": "fail", "message": msg}
        steps.ok()
        wait_message_exchange_interval()
        steps.begin("辅测机给测试机发送彩信，检测是否成功")
        ok, msg = exchange_mms_aux_to_dut(aux_id, aux_sim, dut_id, dut_number)
        if not ok:
            steps.fail()
            return {"status": "fail", "message": msg}
        steps.ok()
        steps.begin("打开卡2")
        if not open_sim_only(dut_id, sim2):
            steps.fail()
            return {"status": "fail", "message": "打开卡2失败"}
        sim2_closed = False
        steps.ok()
        return {"status": "pass", "message": "5G/4G首选网络下彩信互发通过"}
    finally:
        if sim2_closed:
            steps.begin("恢复打开卡2(用例结束)")
            if open_sim_only(dut_id, sim2):
                steps.ok()
            else:
                steps.fail()
