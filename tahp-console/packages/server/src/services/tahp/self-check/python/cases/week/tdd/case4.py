from utils.tdd.apk.call import start_auto_dial
from utils.tdd.apk.get_result import wait_test_result
from utils.tdd.device_sim import get_sim_by_slot, pick_aux_number, sim_phone_number
from utils.tdd.sim_setup import NETWORK_TYPE_5G_AUTO, setup_sim_volte_network
from utils.tdd.ui_harassment_filter import (
    add_number_to_blacklist,
    add_number_to_whitelist_and_check_blacklist_conflict,
    blacklist_has_number,
    confirm_blacklist_conflict_dialog,
    remove_number_from_whitelist,
    set_block_unknown_call_enable,
    tap_blacklist_entry,
    tap_whitelist_entry,
)
from utils.tdd.ui_settings_activity import enter_harassment_block_settings_by_adb


def _dial_and_check(caller_id: str, sim_slot, target_number: str, call_type: int = 2) -> bool:
    if not start_auto_dial(caller_id, sim_slot=sim_slot, call_type=call_type, number=target_number):
        return False
    return wait_test_result(caller_id)


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

    dut_sim_cards = dut.get("sim_cards") or []
    sim1 = get_sim_by_slot(dut_sim_cards, 0)
    sim2 = get_sim_by_slot(dut_sim_cards, 1)
    if not sim1 or not sim2:
        return {"status": "fail", "message": "测试机非双卡，无法执行骚扰拦截用例"}
    dut_target_number = sim_phone_number(sim1) or sim_phone_number(sim2)
    if not dut_target_number:
        return {"status": "fail", "message": "测试机无可用号码，无法执行辅测机拨号验证"}

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
    if not aux_id or not aux_target_number or not aux_call_slot:
        return {"status": "fail", "message": "无可用辅测机或辅测机无可用号码，无法验证拦截来电"}

    sub_steps = ""

    sub_steps += "\n卡1打开SIM卡，打开VoLTE，首选网络切换（最高）"
    if callable(step_update):
        step_update(sub_steps)
    if not setup_sim_volte_network(
        dut_id, sim1, network_type=NETWORK_TYPE_5G_AUTO
    ):
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        return {"status": "fail", "message": "卡1打开SIM卡/VoLTE/首选网络失败"}
    sub_steps += "-成功"
    if callable(step_update):
        step_update(sub_steps)

    sub_steps += "\n卡2打开SIM卡，打开VoLTE，首选网络切换（最高）"
    if callable(step_update):
        step_update(sub_steps)
    if not setup_sim_volte_network(
        dut_id, sim2, network_type=NETWORK_TYPE_5G_AUTO
    ):
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        return {"status": "fail", "message": "卡2打开SIM卡/VoLTE/首选网络失败"}
    sub_steps += "-成功"
    if callable(step_update):
        step_update(sub_steps)

    sub_steps += "\n进入骚扰拦截设置界面"
    if callable(step_update):
        step_update(sub_steps)
    if not enter_harassment_block_settings_by_adb(dut_id):
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        return {"status": "fail", "message": "进入骚扰拦截设置界面失败"}
    sub_steps += "-成功"
    if callable(step_update):
        step_update(sub_steps)

    sub_steps += "\n打开“拦截陌生号码来电”开关"
    if callable(step_update):
        step_update(sub_steps)
    if not set_block_unknown_call_enable(dut_id, True):
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        return {"status": "fail", "message": "打开“拦截陌生号码来电”开关失败"}
    sub_steps += "-成功"
    if callable(step_update):
        step_update(sub_steps)

    sub_steps += "\n辅测机给测试机拨打电话，检查是否无法拨通"
    if callable(step_update):
        step_update(sub_steps)
    if _dial_and_check(aux_id, aux_call_slot, dut_target_number, call_type=2):
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        return {"status": "fail", "message": "辅测机拨打测试机仍可接通，拦截未生效"}
    sub_steps += "-成功"
    if callable(step_update):
        step_update(sub_steps)

    sub_steps += "\n关闭“拦截陌生号码来电”开关"
    if callable(step_update):
        step_update(sub_steps)
    if not set_block_unknown_call_enable(dut_id, False):
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        return {"status": "fail", "message": "关闭“拦截陌生号码来电”开关失败"}
    sub_steps += "-成功"
    if callable(step_update):
        step_update(sub_steps)

    sub_steps += "\n点击“黑名单”按键"
    if callable(step_update):
        step_update(sub_steps)
    if not tap_blacklist_entry(dut_id):
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        return {"status": "fail", "message": "点击“黑名单”按键失败"}
    sub_steps += "-成功"
    if callable(step_update):
        step_update(sub_steps)

    sub_steps += "\n点击添加按钮并将辅测机号码加入黑名单"
    if callable(step_update):
        step_update(sub_steps)
    if not add_number_to_blacklist(dut_id, aux_target_number):
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        return {"status": "fail", "message": "黑名单添加辅测机号码失败"}
    sub_steps += "-成功"
    if callable(step_update):
        step_update(sub_steps)

    sub_steps += "\n辅测机对应号码拨打测试机，检查应无法呼通"
    if callable(step_update):
        step_update(sub_steps)
    if _dial_and_check(aux_id, aux_call_slot, dut_target_number, call_type=2):
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        return {"status": "fail", "message": "黑名单生效失败：辅测机号码仍可呼通测试机"}
    sub_steps += "-成功"
    if callable(step_update):
        step_update(sub_steps)

    sub_steps += "\n再次进入骚扰拦截设置界面"
    if callable(step_update):
        step_update(sub_steps)
    if not enter_harassment_block_settings_by_adb(dut_id):
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        return {"status": "fail", "message": "再次进入骚扰拦截设置界面失败"}
    sub_steps += "-成功"
    if callable(step_update):
        step_update(sub_steps)

    sub_steps += "\n点击“白名单”按键"
    if callable(step_update):
        step_update(sub_steps)
    if not tap_whitelist_entry(dut_id):
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        return {"status": "fail", "message": "点击“白名单”按键失败"}
    sub_steps += "-成功"
    if callable(step_update):
        step_update(sub_steps)

    sub_steps += "\n白名单添加辅测机相同号码，检查提示“号码已在黑名单中”"
    if callable(step_update):
        step_update(sub_steps)
    if not add_number_to_whitelist_and_check_blacklist_conflict(dut_id, aux_target_number):
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        return {"status": "fail", "message": "白名单重复号码冲突提示校验失败"}
    sub_steps += "-成功"
    if callable(step_update):
        step_update(sub_steps)

    sub_steps += "\n读取冲突弹框后点击“确定”"
    if callable(step_update):
        step_update(sub_steps)
    if not confirm_blacklist_conflict_dialog(dut_id):
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        return {"status": "fail", "message": "冲突弹框确认失败"}
    sub_steps += "-成功"
    if callable(step_update):
        step_update(sub_steps)

    sub_steps += "\n辅测机给测试机拨打电话，检查应可以呼通"
    if callable(step_update):
        step_update(sub_steps)
    if not _dial_and_check(aux_id, aux_call_slot, dut_target_number, call_type=2):
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        return {"status": "fail", "message": "白名单生效失败：辅测机号码无法呼通测试机"}
    sub_steps += "-成功"
    if callable(step_update):
        step_update(sub_steps)

    sub_steps += "\n在白名单删除辅测机号码，并检查白名单中不再存在该号码"
    if callable(step_update):
        step_update(sub_steps)
    if not remove_number_from_whitelist(dut_id, aux_target_number):
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        return {"status": "fail", "message": "白名单删除辅测机号码失败"}
    sub_steps += "-成功"
    if callable(step_update):
        step_update(sub_steps)

    sub_steps += "\n回到黑名单界面，检查不应存在辅测机号码"
    if callable(step_update):
        step_update(sub_steps)
    if not enter_harassment_block_settings_by_adb(dut_id):
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        return {"status": "fail", "message": "回黑名单前进入骚扰拦截设置界面失败"}
    if not tap_blacklist_entry(dut_id):
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        return {"status": "fail", "message": "回黑名单界面失败"}
    if blacklist_has_number(dut_id, aux_target_number):
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        return {"status": "fail", "message": "黑名单仍存在辅测机号码"}
    sub_steps += "-成功"
    if callable(step_update):
        step_update(sub_steps)

    return {"status": "pass", "message": "骚扰拦截、黑白名单迁移与号码校验通过"}
