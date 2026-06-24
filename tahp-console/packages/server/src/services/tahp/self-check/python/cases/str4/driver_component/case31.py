"""STR4 驱动器件：陀螺仪零飘测试（复用 case23 陀螺仪校准与工模测试结果）。"""

from utils.driver.sensor_items_result import run_reuse_sensor_items_item
from utils.driver.tranfacmode_config import GYRO_ITEM_KEYWORDS

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

    cali_result = run_reuse_sensor_items_item(
        context,
        GYRO_ITEM_KEYWORDS,
        item_label="陀螺仪校准",
        step_update=on_reuse_step,
        item_source="cali_items",
        source_case_index=SOURCE_SENSOR_CASE_INDEX,
    )
    if cali_result["status"] != "pass":
        return cali_result

    test_result = run_reuse_sensor_items_item(
        context,
        GYRO_ITEM_KEYWORDS,
        item_label="陀螺仪",
        step_update=on_reuse_step,
        item_source="items",
        source_case_index=SOURCE_SENSOR_CASE_INDEX,
    )
    if test_result["status"] != "pass":
        return test_result

    return {
        "status": "pass",
        "message": (
            f"陀螺仪零飘测试: {cali_result['message']}; {test_result['message']}"
        ),
    }
