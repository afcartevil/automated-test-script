"""插入双SIM卡到测试机后，用户开关该sim操作正常：双卡切换后百度可达。"""

from utils.tdd.apk.web import run_baidu_test
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
    if not sim1 or not sim2:
        return {"status": "fail", "message": "测试机非双卡"}

    steps = StepRunner(step_update)
    if not enable_mobile_data(dut_id):
        return {"status": "fail", "message": "打开移动数据失败"}

    steps.begin("卡2打开，首选网络5G或4G")
    if not setup_sim_preferred_network(dut_id, sim2, enable=True, network_type=NETWORK_TYPE_5G_AUTO):
        steps.fail()
        return {"status": "fail", "message": "卡2打开或首选网络失败"}
    steps.ok()

    steps.begin("关闭卡1")
    if not setup_sim_preferred_network(dut_id, sim1, enable=False):
        steps.fail()
        return {"status": "fail", "message": "关闭卡1失败"}
    steps.ok()

    steps.begin("访问百度(卡2数据)")
    if not run_baidu_test(dut_id):
        steps.fail()
        return {"status": "fail", "message": "卡2数据下百度访问失败"}
    steps.ok()

    steps.begin("打开卡1，首选网络5G或4G")
    if not setup_sim_preferred_network(dut_id, sim1, enable=True, network_type=NETWORK_TYPE_5G_AUTO):
        steps.fail()
        return {"status": "fail", "message": "打开卡1失败"}
    steps.ok()

    steps.begin("关闭卡2")
    if not setup_sim_preferred_network(dut_id, sim2, enable=False):
        steps.fail()
        return {"status": "fail", "message": "关闭卡2失败"}
    steps.ok()

    steps.begin("访问百度(卡1数据)")
    if not run_baidu_test(dut_id):
        steps.fail()
        return {"status": "fail", "message": "卡1数据下百度访问失败"}
    steps.ok()

    steps.begin("打开卡2")
    if not open_sim_only(dut_id, sim2):
        steps.fail()
        return {"status": "fail", "message": "打开卡2失败"}
    steps.ok()

    return {"status": "pass", "message": "双卡切换后百度访问通过"}
