import time

from utils.tdd.apk.call import dial_and_check, reset_dial_sequence
from utils.tdd.device_sim import fail_result_if_camera_unavailable_for_video
from utils.tdd.device_sim import get_sim_by_slot, pick_aux_number, sim_phone_number
from utils.tdd.sim_setup import (
    NETWORK_TYPE_5G_AUTO,
    enter_sim_sub_page,
    open_sim_only,
    setup_sim_preferred_network,
)
from utils.tdd.ui_first_network import set_preferred_network
from utils.tdd.ui_network_info import read_quick_settings_sim_network_info
from utils.tdd.ui_volte_button import set_volte_enable

CALL_TYPE_VIDEO = 1
CALL_TYPE_VOICE = 2

FAIL_MESSAGE = "无网络环境"
FULL_PASS_MESSAGE = "用例执行通过"
NETWORK_INFO_SETTLE_SEC = 1.0


def _evaluate_call_result(
    *,
    video_connected: bool,
    dut_voice_connected: bool,
    aux_voice_connected: bool,
    recovery_ok: bool,
) -> dict:
    if (
        not video_connected
        and not dut_voice_connected
        and not aux_voice_connected
    ):
        return {"status": "部分pass", "message": FAIL_MESSAGE}

    video_ok = not video_connected
    if video_ok and dut_voice_connected and aux_voice_connected and recovery_ok:
        return {"status": "pass", "message": FULL_PASS_MESSAGE}

    return {"status": "fail", "message": "用例存在子步骤未达预期"}


def run(category=None, case_index=None, device_info=None, **context):
    step_update = context.get("step_update")
    device_info = device_info or context.get("device_info") or {}

    cam_fail = fail_result_if_camera_unavailable_for_video(device_info)
    if cam_fail:
        return cam_fail

    dut_list = (device_info or {}).get("DUT") or []
    if not dut_list:
        return {"status": "fail", "message": FAIL_MESSAGE}
    dut = dut_list[0]
    dut_id = (dut.get("device_id") or "").strip()
    if not dut_id:
        return {"status": "fail", "message": FAIL_MESSAGE}

    dut_sim_cards = dut.get("sim_cards") or []
    sim1 = get_sim_by_slot(dut_sim_cards, 0)
    sim2 = get_sim_by_slot(dut_sim_cards, 1)
    sim1_number = sim_phone_number(sim1)
    if not sim1:
        return {"status": "fail", "message": FAIL_MESSAGE}

    aux_list = device_info.get("Auxiliary") or []
    aux = aux_list[0] if aux_list else {}
    aux_id = (aux.get("device_id") or "").strip()
    aux_sim_cards = aux.get("sim_cards") or []
    aux_sim1 = get_sim_by_slot(aux_sim_cards, 0)
    aux_sim2 = get_sim_by_slot(aux_sim_cards, 1)
    aux_target_number = pick_aux_number(
        sim_phone_number(aux_sim1), sim_phone_number(aux_sim2)
    )
    aux_call_slot = 1 if aux_sim1 else (2 if aux_sim2 else None)
    if not aux_id or not aux_target_number:
        return {"status": "fail", "message": FAIL_MESSAGE}
    if not sim1_number:
        return {"status": "fail", "message": FAIL_MESSAGE}

    sub_steps = ""

    sub_steps += "\n进入卡1子界面并设置首选网络(5G或4G自动)"
    if callable(step_update):
        step_update(sub_steps)
    if not enter_sim_sub_page(dut_id, sim1):
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        return {"status": "fail", "message": "设置卡1首选网络失败"}
    if not set_preferred_network(dut_id, NETWORK_TYPE_5G_AUTO):
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        return {"status": "fail", "message": "设置卡1首选网络失败"}
    sub_steps += "-成功"
    if callable(step_update):
        step_update(sub_steps)

    sub_steps += "\n关闭卡1 VoLTE 开关"
    if callable(step_update):
        step_update(sub_steps)
    if not set_volte_enable(dut_id, False):
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        return {"status": "fail", "message": "关闭卡1 VoLTE失败"}
    sub_steps += "-成功"
    if callable(step_update):
        step_update(sub_steps)

    sub_steps += "\n检查卡1快捷设置状态栏无VoLTE图标"
    if callable(step_update):
        step_update(sub_steps)
    time.sleep(NETWORK_INFO_SETTLE_SEC)
    net_info = read_quick_settings_sim_network_info(dut_id, 1)
    if net_info is None:
        sub_steps += "-失败(无法读取卡1网络信息)"
        if callable(step_update):
            step_update(sub_steps)
        return {"status": "fail", "message": "关闭VoLTE后无法读取卡1状态栏网络信息"}
    if net_info.volte:
        sub_steps += "-失败(仍显示VoLTE)"
        if callable(step_update):
            step_update(sub_steps)
        return {
            "status": "fail",
            "message": (
                f"关闭VoLTE后状态栏仍显示VoLTE: "
                f"carrier={net_info.carrier_name}, type={net_info.network_type}"
            ),
        }
    sub_steps += "-成功"
    if callable(step_update):
        step_update(sub_steps)

    if sim2:
        sub_steps += "\n进入卡2子界面并关闭卡2"
        if callable(step_update):
            step_update(sub_steps)
        if not setup_sim_preferred_network(dut_id, sim2, enable=False):
            sub_steps += "-失败"
            if callable(step_update):
                step_update(sub_steps)
            return {"status": "fail", "message": "关闭卡2失败"}
        sub_steps += "-成功"
        if callable(step_update):
            step_update(sub_steps)

    sub_steps += "\n测试机给辅测机拨打视频通话，应无法呼通"
    if callable(step_update):
        step_update(sub_steps)
    video_connected = dial_and_check(
        dut_id, 1, aux_target_number, CALL_TYPE_VIDEO
    )
    if video_connected:
        sub_steps += "-失败(不应呼通但已接通)"
    else:
        sub_steps += "-成功"
    if callable(step_update):
        step_update(sub_steps)

    sub_steps += "\n测试机给辅测机拨打电话，检查能否接通"
    if callable(step_update):
        step_update(sub_steps)
    dut_voice_connected = dial_and_check(
        dut_id, 1, aux_target_number, CALL_TYPE_VOICE
    )
    sub_steps += "-成功" if dut_voice_connected else "-失败"
    if callable(step_update):
        step_update(sub_steps)

    sub_steps += "\n辅测机给测试机拨打电话，检查能否接通"
    if callable(step_update):
        step_update(sub_steps)
    aux_voice_connected = dial_and_check(
        aux_id, aux_call_slot, sim1_number, CALL_TYPE_VOICE
    )
    sub_steps += "-成功" if aux_voice_connected else "-失败"
    if callable(step_update):
        step_update(sub_steps)

    reset_dial_sequence()
    recovery_ok = True

    sub_steps += "\n卡1打开VoLTE"
    if callable(step_update):
        step_update(sub_steps)
    if not enter_sim_sub_page(dut_id, sim1):
        sub_steps += "-失败"
        recovery_ok = False
    elif not set_volte_enable(dut_id, True):
        sub_steps += "-失败"
        recovery_ok = False
    else:
        sub_steps += "-成功"
    if callable(step_update):
        step_update(sub_steps)

    if sim2:
        sub_steps += "\n打开卡2"
        if callable(step_update):
            step_update(sub_steps)
        if not open_sim_only(dut_id, sim2):
            sub_steps += "-失败"
            recovery_ok = False
        else:
            sub_steps += "-成功"
        if callable(step_update):
            step_update(sub_steps)

    return _evaluate_call_result(
        video_connected=video_connected,
        dut_voice_connected=dut_voice_connected,
        aux_voice_connected=aux_voice_connected,
        recovery_ok=recovery_ok,
    )
