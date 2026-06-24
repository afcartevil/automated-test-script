"""检查重开机系统时间更新-IMS：关自动对时、随机设时、重启后校时（对齐 run_case12_time_reboot）。"""

from utils.tdd.time_reboot import (
    POST_SYNC_TOLERANCE_SECONDS,
    SET_VERIFY_SLOP_SECONDS,
    adb_reboot,
    adb_root,
    set_auto_time,
    set_random_wall_time,
    verify_device_time_vs_host,
    wait_for_adb_shell_after_reboot,
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

    sub_steps = ""

    def update(steps: str):
        if callable(step_update):
            step_update(steps)

    def fail_at(label: str, message: str):
        nonlocal sub_steps
        sub_steps += f"\n{label}"
        update(sub_steps)
        sub_steps += "-失败"
        update(sub_steps)
        return {"status": "fail", "message": message}

    def pass_step(label: str):
        nonlocal sub_steps
        sub_steps += f"\n{label}"
        update(sub_steps)
        sub_steps += "-成功"
        update(sub_steps)

    try:
        sub_steps += "\nadb root并关闭自动对时"
        update(sub_steps)
        adb_root(dut_id)
        set_auto_time(dut_id, False)
        sub_steps += "-成功"
        update(sub_steps)
    except RuntimeError as exc:
        sub_steps += "-失败"
        update(sub_steps)
        return {"status": "fail", "message": str(exc)}

    try:
        chosen, drift = set_random_wall_time(
            dut_id,
            set_verify_slop_seconds=SET_VERIFY_SLOP_SECONDS,
        )
        pass_step(
            f"随机设置2000-2025年时刻并校验(目标 {chosen.strftime('%Y-%m-%d %H:%M:%S')}，偏差 {drift}s)"
        )
    except RuntimeError as exc:
        return fail_at("随机设置2000-2025年时刻并校验", str(exc))

    try:
        sub_steps += "\n开启自动对时并重启"
        update(sub_steps)
        set_auto_time(dut_id, True)
        adb_reboot(dut_id)
        wait_for_adb_shell_after_reboot(dut_id)
        sub_steps += "-成功"
        update(sub_steps)
    except RuntimeError as exc:
        sub_steps += "-失败"
        update(sub_steps)
        return {"status": "fail", "message": str(exc)}

    try:
        skew, human = verify_device_time_vs_host(
            dut_id,
            post_sync_tolerance_seconds=POST_SYNC_TOLERANCE_SECONDS,
        )
        pass_step(
            f"重启后校验设备时间与主机一致(偏差 {skew}s，设备 {human.strip()})"
        )
        return {
            "status": "pass",
            "message": (
                "关自动对时随机设时校验通过，重启后自动对时已与主机时间一致"
                f"（偏差 {skew}s，允许 {POST_SYNC_TOLERANCE_SECONDS}s）"
            ),
        }
    except RuntimeError as exc:
        return fail_at("重启后校验设备时间与主机一致", str(exc))
