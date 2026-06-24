"""STR4 驱动硬测：开机状态充电（复用器件 case15 标准充电结果）。"""

from utils.driver.tranfacmode_config import USB_STANDARD_CHARGE_ITEM_KEYWORDS
from utils.driver.ui_tranfacmode import run_reuse_usb_group_item

SOURCE_USB_CASE_INDEX = 15


def run(category=None, case_index=None, device_info=None, **context):
    return run_reuse_usb_group_item(
        context,
        USB_STANDARD_CHARGE_ITEM_KEYWORDS,
        item_label="标准充电",
        step_update=context.get("step_update"),
        source_case_index=SOURCE_USB_CASE_INDEX,
    )
