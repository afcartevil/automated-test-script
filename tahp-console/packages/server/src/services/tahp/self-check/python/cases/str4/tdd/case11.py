"""测试机器已打开 OMAPI 接口功能（MTK 检查 secure_element HAL）。"""

from utils.tdd.get_basic_info import (
    EXPECTED_OMAPI_MTK_SERVICE,
    VENDOR_HW_DIR,
    _get_platform,
    check_omapi_enabled,
)

PLATFORM_MTK = "MTK"


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

    sub_steps = ""

    def update(steps: str):
        if callable(step_update):
            step_update(steps)

    platform = (dut.get("platform") or "").strip()
    if not platform or platform == "unknown":
        try:
            platform = _get_platform(dut_id)
        except RuntimeError as exc:
            sub_steps += "\n读取设备平台"
            update(sub_steps)
            sub_steps += "-失败"
            update(sub_steps)
            return {"status": "fail", "message": f"无法读取平台信息: {exc}"}

    sub_steps += f"\n识别平台({platform})"
    update(sub_steps)
    sub_steps += "-成功"
    update(sub_steps)

    if platform != PLATFORM_MTK:
        sub_steps += "\n非MTK平台，跳过secure_element检查"
        update(sub_steps)
        sub_steps += "-跳过"
        update(sub_steps)
        return {
            "status": "pass",
            "message": f"非 MTK 平台（{platform}），按用例不测试，直接 pass",
        }

    sub_steps += f"\nadb shell ls {VENDOR_HW_DIR}，检查 secure_element"
    update(sub_steps)

    ok, detail = check_omapi_enabled(dut_id)
    if ok:
        sub_steps += "-成功"
        update(sub_steps)
        return {
            "status": "pass",
            "message": detail or f"已发现 {EXPECTED_OMAPI_MTK_SERVICE}，OMAPI 接口已打开",
        }

    sub_steps += "-失败"
    update(sub_steps)
    return {
        "status": "fail",
        "message": detail or "OMAPI secure_element 接口未打开",
    }
