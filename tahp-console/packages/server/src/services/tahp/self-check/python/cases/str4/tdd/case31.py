"""用户关闭4G通话后,UE注册网络无异常。"""

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
    enable_mobile_data,
    open_sim_only,
    setup_sim_preferred_network,
    setup_sim_volte_network,
)
from utils.tdd.ui_volte_button import set_volte_enable
from test.step_runner import StepRunner

NO_NETWORK_MESSAGE = "无网络环境"
PASS_MESSAGE = "关闭VoLTE后网络与语音主被叫正常"


def _finalize_result(*, baidu_ok: bool, dut_call_ok: bool, aux_call_ok: bool) -> dict:
    if baidu_ok and dut_call_ok and aux_call_ok:
        return {"status": "pass", "message": PASS_MESSAGE}
    if not dut_call_ok and not aux_call_ok:
        return {"status": "NA", "message": NO_NETWORK_MESSAGE}
    return {"status": "fail", "message": "用例存在子步骤未达预期"}


def run(category=None, case_index=None, device_info=None, **context):
    step_update = context.get("step_update")
    device_info = device_info or context.get("device_info") or {}
    dut, dut_id = resolve_dut(device_info)
    if not dut:
        return {"status": "fail", "message": dut_id}
    sim1 = get_sim_by_slot(dut.get("sim_cards") or [], 0)
    sim2 = get_sim_by_slot(dut.get("sim_cards") or [], 1)
    if not sim1:
        return {"status": "fail", "message": "测试机无卡1"}
    dut_number = sim_phone_number(sim1)
    aux_id, aux_number, _, err = resolve_aux(device_info)
    if err:
        return {"status": "fail", "message": err}
    aux_sim_cards = (device_info.get("Auxiliary") or [{}])[0].get("sim_cards") or []
    aux_slot = aux_call_slot(
        get_sim_by_slot(aux_sim_cards, 0),
        get_sim_by_slot(aux_sim_cards, 1),
    )

    steps = StepRunner(step_update)
    try:
        if not enable_mobile_data(dut_id):
            return {"status": "fail", "message": "打开移动数据失败"}
        steps.begin("卡1打开，关闭VoLTE，首选网络5G或4G")
        if not setup_sim_volte_network(
            dut_id, sim1, volte=False, network_type=NETWORK_TYPE_5G_AUTO
        ):
            steps.fail()
            return {"status": "fail", "message": "卡1打开、关闭VoLTE或首选网络设置失败"}
        steps.ok()
        if sim2:
            steps.begin("关闭卡2")
            if not setup_sim_preferred_network(dut_id, sim2, enable=False):
                steps.fail()
                return {"status": "fail", "message": "关闭卡2失败"}
            steps.ok()

        steps.begin("访问百度")
        baidu_ok = run_baidu_test(dut_id)
        if baidu_ok:
            steps.ok()
        else:
            steps.fail()

        steps.begin("测试机主叫辅测机语音")
        dut_call_ok = dial_and_check(dut_id, 1, aux_number, 2)
        if dut_call_ok:
            steps.ok()
        else:
            steps.fail()

        steps.begin("辅测机主叫测试机语音")
        aux_call_ok = dial_and_check(aux_id, aux_slot, dut_number, 2)
        if aux_call_ok:
            steps.ok()
        else:
            steps.fail()

        return _finalize_result(
            baidu_ok=baidu_ok,
            dut_call_ok=dut_call_ok,
            aux_call_ok=aux_call_ok,
        )
    finally:
        if enter_sim_sub_settings_by_sim(dut_id, sim1):
            set_volte_enable(dut_id, True)
        if sim2:
            steps.begin("恢复打开卡2(用例结束)")
            if open_sim_only(dut_id, sim2):
                steps.ok()
            else:
                steps.fail()
