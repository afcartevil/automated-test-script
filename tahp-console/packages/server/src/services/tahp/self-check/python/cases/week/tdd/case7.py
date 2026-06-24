import time

from utils.tdd.apk.web import run_web_test
from utils.tdd.ui_automatic import set_mobile_data_enable, set_wifi_enable
from utils.tdd.device_sim import get_sim_by_slot
from utils.tdd.sim_setup import (
    NETWORK_TYPE_5G_AUTO,
    enter_sim_sub_page,
    open_sim_only,
    setup_sim_preferred_network,
    setup_sim_volte_network,
)
from utils.tdd.ui_first_network import set_preferred_network

BAIDU_URL = "https://www.baidu.com"
WEB_TIMEOUT_SECONDS = 60
NETWORK_SETTLE_SECONDS = 5

NETWORK_WEB_ROUNDS = (
    (4, "4G", "4g"),
    (3, "2/3G", "23g"),
    (2, "3G", "3g"),
    (1, "2G", "2g"),
)
LEGACY_WEB_KEYS = ("23g", "3g", "2g")


def _probe_baidu(device_id: str) -> bool:
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

    sim_cards = dut.get("sim_cards") or []
    sim1 = get_sim_by_slot(sim_cards, 0)
    sim2 = get_sim_by_slot(sim_cards, 1)
    if not sim1 or not sim2:
        return {"status": "fail", "message": "测试机非双卡，无法执行数据连接用例"}

    sub_steps = ""
    critical_ok = True
    web_results: dict[str, bool] = {
        "initial": False,
        "4g": False,
        "23g": False,
        "3g": False,
        "2g": False,
    }

    def _update():
        if callable(step_update):
            step_update(sub_steps)

    def _critical_fail(message: str):
        return {"status": "fail", "message": message}

    sub_steps += "\n卡1打开SIM卡，打开VoLTE，首选网络5G或4G"
    _update()
    if not setup_sim_volte_network(
        dut_id, sim1, network_type=NETWORK_TYPE_5G_AUTO
    ):
        sub_steps += "-失败"
        _update()
        return _critical_fail("卡1打开SIM卡/VoLTE/首选网络失败")
    sub_steps += "-成功"
    _update()

    sub_steps += "\n卡2关闭"
    _update()
    if not setup_sim_preferred_network(dut_id, sim2, enable=False):
        sub_steps += "-失败"
        _update()
        return _critical_fail("关闭卡2失败")
    sub_steps += "-成功"
    _update()

    sub_steps += "\n关闭Wi-Fi开关"
    _update()
    if not set_wifi_enable(dut_id, False):
        sub_steps += "-失败"
        _update()
        return _critical_fail("关闭Wi-Fi失败")
    sub_steps += "-成功"
    _update()

    sub_steps += "\n打开移动数据开关"
    _update()
    if not set_mobile_data_enable(dut_id, True):
        sub_steps += "-失败"
        _update()
        return _critical_fail("打开移动数据失败")
    sub_steps += "-成功"
    _update()

    sub_steps += "\n访问百度主页（5G/4G）"
    _update()
    web_results["initial"] = _probe_baidu(dut_id)
    sub_steps += "-成功" if web_results["initial"] else "-失败"
    _update()

    for network_type, label, result_key in NETWORK_WEB_ROUNDS:
        sub_steps += f"\n卡1切换首选网络{label}并访问百度"
        _update()
        step_ok = True
        if not enter_sim_sub_page(dut_id, sim1):
            sub_steps += "-失败"
            _update()
            critical_ok = False
            break
        if not set_preferred_network(dut_id, network_type):
            sub_steps += "-失败"
            _update()
            critical_ok = False
            break
        time.sleep(NETWORK_SETTLE_SECONDS)
        web_ok = _probe_baidu(dut_id)
        web_results[result_key] = web_ok
        if not web_ok:
            step_ok = False
        sub_steps += "-成功" if step_ok and web_ok else "-失败"
        _update()

    if not critical_ok:
        return _critical_fail("切换首选网络失败")

    sub_steps += "\n卡2打开"
    _update()
    if not open_sim_only(dut_id, sim2):
        sub_steps += "-失败"
        _update()
        return _critical_fail("打开卡2失败")
    sub_steps += "-成功"
    _update()

    legacy = [web_results[k] for k in LEGACY_WEB_KEYS]
    legacy_all_fail = all(not item for item in legacy)
    legacy_any_pass = any(legacy)
    legacy_mixed = legacy_any_pass and not all(legacy)

    if legacy_mixed:
        return {
            "status": "fail",
            "message": "2/3G、3G、2G 访问百度结果不一致（部分成功部分失败）",
        }

    if not web_results["initial"]:
        return {"status": "fail", "message": "5G/4G 下访问百度失败"}

    if not web_results["4g"]:
        return {"status": "fail", "message": "4G 下访问百度失败"}

    if legacy_all_fail:
        return {"status": "部分pass", "message": "2、3g无网络"}

    if all(web_results.values()):
        return {"status": "pass", "message": "数据连接与各制式下百度访问验证通过"}

    return {"status": "fail", "message": "数据连接用例未满足通过条件"}
