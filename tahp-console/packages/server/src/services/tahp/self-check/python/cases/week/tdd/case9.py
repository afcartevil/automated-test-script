from utils.tdd.ui_baseband_version import get_baseband_version


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

    sub_steps = "\n读取基带版本号"
    if callable(step_update):
        step_update(sub_steps)

    baseband_version = (get_baseband_version(dut_id) or "").strip()
    if baseband_version:
        sub_steps += "-成功"
        if callable(step_update):
            step_update(sub_steps)
        return {"status": "pass", "message": baseband_version}

    sub_steps += "-失败"
    if callable(step_update):
        step_update(sub_steps)
    return {"status": "fail", "message": "未读取到基带版本号"}
