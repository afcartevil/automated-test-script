"""检查测试网页数据链接-IPV4/6。"""

from utils.tdd.apk.web import IPV6_TEST_URL, run_web_test
from utils.tdd.device_sim import get_sim_by_slot, resolve_dut
from utils.tdd.sim_setup import NETWORK_TYPE_5G_AUTO, enable_mobile_data, open_sim_only, setup_sim_preferred_network
from test.step_runner import StepRunner


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

    steps = StepRunner(step_update)
    if not enable_mobile_data(dut_id):
        return {"status": "fail", "message": "打开移动数据失败"}
    steps.begin("卡1打开，首选网络5G或4G")
    if not setup_sim_preferred_network(dut_id, sim1, enable=True, network_type=NETWORK_TYPE_5G_AUTO):
        steps.fail()
        return {"status": "fail", "message": "卡1或首选网络设置失败"}
    steps.ok()
    if sim2:
        steps.begin("关闭卡2")
        if not setup_sim_preferred_network(dut_id, sim2, enable=False):
            steps.fail()
            return {"status": "fail", "message": "关闭卡2失败"}
        steps.ok()
    steps.begin(f"访问{IPV6_TEST_URL}(双栈探测)")
    if not run_web_test(dut_id, IPV6_TEST_URL, force_refresh=True, timeout_seconds=90):
        steps.fail()
        return {"status": "fail", "message": "test-ipv6.com 网页探测失败"}
    steps.ok()
    if sim2:
        steps.begin("恢复打开卡2(用例结束)")
        if open_sim_only(dut_id, sim2):
            steps.ok()
        else:
            steps.fail()
    return {"status": "pass", "message": "IPV4/6 网页数据链接探测通过"}
