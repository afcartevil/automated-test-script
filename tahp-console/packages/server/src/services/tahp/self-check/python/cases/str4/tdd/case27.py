"""检查UE蜂窝热点超出限额后提醒并关闭热点或仅提醒功能。"""



import time



from utils.tdd.apk.web import run_douyin_test

from utils.tdd.device_sim import get_sim_by_slot, resolve_aux, resolve_dut

from utils.tdd.sim_setup import NETWORK_TYPE_5G_AUTO, enable_mobile_data, open_sim_only, setup_sim_preferred_network

from utils.tdd.ui_automatic import open_wifi_settings, set_mobile_data_enable, set_wifi_enable

from utils.tdd.ui_hotspot import (

    disable_personal_hotspot,

    setup_personal_hotspot_with_session_limit_mb,

)

from test.step_runner import StepRunner



AUX_WIFI_SETTINGS_WAIT_SECONDS = 3.0





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

    aux_id, _, _, err = resolve_aux(device_info)

    if err:

        return {"status": "fail", "message": err}



    steps = StepRunner(step_update)

    try:

        steps.begin("打开移动数据")

        if not enable_mobile_data(dut_id):

            steps.fail()

            return {"status": "fail", "message": "打开移动数据失败"}

        steps.ok()

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

        steps.begin(

            "个人热点:连接管理→单次限额→设3MB→回热点页并开启热点"

        )

        if not setup_personal_hotspot_with_session_limit_mb(dut_id, 3):

            steps.fail()

            return {"status": "fail", "message": "热点单次限额3MB或开启热点失败"}

        steps.ok()

        steps.begin("辅测机关闭移动数据、打开Wi-Fi")

        if not set_mobile_data_enable(aux_id, False):

            steps.fail()

            return {"status": "fail", "message": "辅测机关闭移动数据失败"}

        if not set_wifi_enable(aux_id, True):

            steps.fail()

            return {"status": "fail", "message": "辅测机打开Wi-Fi失败"}

        steps.ok()

        steps.begin("辅测机进入Wi-Fi设置并等待3s")

        if not open_wifi_settings(aux_id, settle_seconds=0):

            steps.fail()

            return {"status": "fail", "message": "辅测机进入Wi-Fi设置失败"}

        time.sleep(AUX_WIFI_SETTINGS_WAIT_SECONDS)

        steps.ok()

        steps.begin("辅测机经热点访问抖音首页(最多5次，需先成功后失败)")

        saw_success = False
        saw_failure_after_success = False

        for attempt in range(1, 6):
            ok = run_douyin_test(aux_id, timeout_seconds=90)
            label = "成功" if ok else "失败"
            steps.sub_steps += f"\n  第{attempt}次-{label}"
            steps.update()
            if ok:
                saw_success = True
            elif saw_success:
                saw_failure_after_success = True

        if not saw_success:
            steps.fail()
            return {"status": "fail", "message": "5次访问抖音均未成功，热点可能未正常工作"}
        if not saw_failure_after_success:
            steps.fail()
            return {
                "status": "fail",
                "message": "访问一直成功，未观察到超额关闭热点后的失败",
            }

        steps.ok()

        steps.begin("关闭测试机热点(收尾)")

        disable_personal_hotspot(dut_id)

        steps.ok()

        return {"status": "pass", "message": "热点限额内可上网，超额后热点关闭导致访问失败"}

    finally:

        disable_personal_hotspot(dut_id)

        if sim2:

            steps.begin("恢复打开卡2(用例结束)")

            if open_sim_only(dut_id, sim2):

                steps.ok()

            else:

                steps.fail()

