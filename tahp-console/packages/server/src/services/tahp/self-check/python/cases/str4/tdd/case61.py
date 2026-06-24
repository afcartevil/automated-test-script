"""验证手机在发送不支持的USSD代码时错误弹框是否正确。"""

from utils.tdd.apk.call import start_auto_dial
from utils.tdd.device_sim import get_sim_by_slot, resolve_dut
from utils.tdd.sim_setup import NETWORK_TYPE_5G_AUTO, enable_mobile_data, open_sim_only, setup_sim_preferred_network
from utils.tdd.ui_ussd import dismiss_ussd_error_dialog, wait_ussd_error_dialog
from test.step_runner import StepRunner

USSD_CODE = "*123#"


def run(category=None, case_index=None, device_info=None, **context):
    step_update = context.get("step_update")
    device_info = device_info or context.get("device_info") or {}
    dut, dut_id = resolve_dut(device_info)
    if not dut:
        return {"status": "fail", "message": dut_id}
    sim1 = get_sim_by_slot(dut.get("sim_cards") or [], 0)
    sim2 = get_sim_by_slot(dut.get("sim_cards") or [], 1)

    steps = StepRunner(step_update)
    try:
        if not enable_mobile_data(dut_id):
            return {"status": "fail", "message": "打开移动数据失败"}
        steps.begin("卡1打开，首选网络5G或4G")
        if not setup_sim_preferred_network(dut_id, sim1, enable=True, network_type=NETWORK_TYPE_5G_AUTO):
            steps.fail()
            return {"status": "fail", "message": "卡1设置失败"}
        steps.ok()
        if sim2:
            steps.begin("关闭卡2")
            if not setup_sim_preferred_network(dut_id, sim2, enable=False):
                steps.fail()
                return {"status": "fail", "message": "关闭卡2失败"}
            steps.ok()
        steps.begin(f"拨打无效USSD({USSD_CODE})并检查错误弹框")
        if not start_auto_dial(dut_id, sim_slot=1, call_type=3, number=USSD_CODE):
            steps.fail()
            return {"status": "fail", "message": "USSD拨号发起失败"}
        if not wait_ussd_error_dialog(dut_id):
            steps.fail()
            return {"status": "fail", "message": "未检测到USSD错误提示"}
        steps.ok()
        steps.begin("关闭错误弹框")
        if not dismiss_ussd_error_dialog(dut_id):
            steps.fail()
            return {"status": "fail", "message": "关闭USSD错误弹框失败"}
        steps.ok()
        return {"status": "pass", "message": "无效USSD错误弹框显示并可关闭"}
    finally:
        if sim2:
            steps.begin("恢复打开卡2(用例结束)")
            if open_sim_only(dut_id, sim2):
                steps.ok()
            else:
                steps.fail()
