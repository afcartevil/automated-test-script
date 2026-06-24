"""STR4 驱动器件：心率血氧校准（复用 case23 Sensor 工模血氧传感器测试结果）。"""

from utils.driver.sensor_items_result import run_reuse_sensor_item_with_support_check
from utils.driver.tranfacmode_config import PULSE_OXIMETER_ITEM_KEYWORDS

SOURCE_SENSOR_CASE_INDEX = 23


def run(category=None, case_index=None, device_info=None, **context):
    step_update = context.get("step_update")
    sub_steps = ""

    def update(message: str) -> None:
        if callable(step_update):
            step_update(message)

    def on_reuse_step(message: str) -> None:
        nonlocal sub_steps
        if sub_steps and message.startswith("\n"):
            sub_steps += message
        else:
            sub_steps = message
        update(sub_steps)

    result = run_reuse_sensor_item_with_support_check(
        context,
        PULSE_OXIMETER_ITEM_KEYWORDS,
        item_label="血氧传感器测试",
        feature_name="血氧传感器",
        step_update=on_reuse_step,
        item_source="items",
        source_case_index=SOURCE_SENSOR_CASE_INDEX,
    )
    if result["status"] == "pass":
        return {"status": "pass", "message": f"血氧传感器测试: {result['message']}"}
    return result
