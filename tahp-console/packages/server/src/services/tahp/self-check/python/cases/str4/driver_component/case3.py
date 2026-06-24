"""Driver weekly self-check: vibrator factory-mode test."""

from utils.driver.ui_tranfacmode import run_vibrator_test


def _get_dut_device_id(device_info):
    dut_list = (device_info or {}).get("DUT") or []
    if not dut_list:
        return None, "DUT device info is missing"
    dut_id = (dut_list[0].get("device_id") or "").strip()
    if not dut_id:
        return None, "DUT device_id is empty"
    return dut_id, ""


def run(category=None, case_index=None, device_info=None, **context):
    step_update = context.get("step_update")
    device_info = device_info or context.get("device_info") or {}

    dut_id, error = _get_dut_device_id(device_info)
    if not dut_id:
        if callable(step_update):
            step_update(error)
        return {"status": "fail", "message": error}

    sub_steps = ""

    def on_step(label: str, ok: bool) -> None:
        nonlocal sub_steps
        sub_steps += f"\n{label}" + ("-ok" if ok else "-fail")
        if callable(step_update):
            step_update(sub_steps)

    result = run_vibrator_test(
        dut_id,
        result_dir=context.get("result_dir"),
        on_step=on_step,
    )
    return {"status": result["status"], "message": result["message"]}
