"""STR4 驱动器件：肩键功能（工模 Other 页肩键校准 + 肩键测试）。"""

from utils.driver.tranfacmode_config import SHOULDER_KEY, SHOULDER_KEY_CALI
from utils.driver.ui_tranfacmode import run_other_tab_item_test


def _is_item_not_found(result: dict) -> bool:
    message = (result.get("message") or "").strip()
    return "未找到" in message and "测试项" in message


def _handle_missing_item(
    result: dict,
    item_label: str,
    *,
    operator_notify,
    manual_confirm,
    sub_steps: str,
    update,
) -> dict | None:
    """未找到工模项时人工确认是否支持肩键；不支持则 skip，支持则返回 None 由调用方 fail。"""
    if not _is_item_not_found(result):
        return result

    notice = f"工模 Other 页未找到{item_label}，请确认本机是否支持肩键功能。"
    sub_steps += f"\n需人工确认：{notice}"
    update(sub_steps)
    if callable(operator_notify):
        operator_notify(notice)

    if not callable(manual_confirm):
        return {"status": "pending", "message": "需确认设备是否支持肩键"}

    status = manual_confirm(
        f"工模未找到{item_label}，请确认本机是否支持肩键功能（不支持请选择 fail）。"
    )
    if status != "pass":
        return {
            "status": "skip",
            "message": f"设备不支持肩键，已跳过（{item_label}未找到）",
        }
    return None


def _get_dut_device_id(device_info):
    dut_list = (device_info or {}).get("DUT") or []
    if not dut_list:
        return None, "未获取到测试机设备信息"
    dut_id = (dut_list[0].get("device_id") or "").strip()
    if not dut_id:
        return None, "测试机 device_id 为空"
    return dut_id, ""


def run(category=None, case_index=None, device_info=None, **context):
    step_update = context.get("step_update")
    operator_notify = context.get("operator_notify")
    manual_confirm = context.get("manual_confirm")
    device_info = device_info or context.get("device_info") or {}

    dut_id, error = _get_dut_device_id(device_info)
    if not dut_id:
        if callable(step_update):
            step_update(error)
        return {"status": "fail", "message": error}

    sub_steps = ""

    def update(message: str) -> None:
        if callable(step_update):
            step_update(message)

    def on_step(label: str, ok: bool) -> None:
        nonlocal sub_steps
        sub_steps += f"\n{label}" + ("-成功" if ok else "-失败")
        update(sub_steps)

    cali_result = run_other_tab_item_test(
        dut_id,
        SHOULDER_KEY_CALI,
        result_dir=context.get("result_dir"),
        on_step=on_step,
    )
    if cali_result["status"] != "pass":
        handled = _handle_missing_item(
            cali_result,
            SHOULDER_KEY_CALI.label,
            operator_notify=operator_notify,
            manual_confirm=manual_confirm,
            sub_steps=sub_steps,
            update=update,
        )
        if handled is not None:
            return handled
        return {
            "status": "fail",
            "message": f"{cali_result['message']}（人工确认支持肩键）",
        }

    test_result = run_other_tab_item_test(
        dut_id,
        SHOULDER_KEY,
        result_dir=context.get("result_dir"),
        on_step=on_step,
    )
    if test_result["status"] != "pass":
        handled = _handle_missing_item(
            test_result,
            SHOULDER_KEY.label,
            operator_notify=operator_notify,
            manual_confirm=manual_confirm,
            sub_steps=sub_steps,
            update=update,
        )
        if handled is not None:
            return handled
        return {
            "status": "fail",
            "message": f"{test_result['message']}（人工确认支持肩键）",
        }

    return {
        "status": "pass",
        "message": f"{cali_result['message']}; {test_result['message']}",
    }
