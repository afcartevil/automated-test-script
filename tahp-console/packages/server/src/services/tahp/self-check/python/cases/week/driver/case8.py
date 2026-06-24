"""驱动周版本自检：复用 case5 屏幕顺序测试中的色彩子项结果。"""

from utils.driver.tranfacmode_config import SCREEN_COLOR_ITEM_KEYWORDS
from utils.driver.ui_tranfacmode import run_reuse_screen_touch_group_item


def run(category=None, case_index=None, device_info=None, **context):
    return run_reuse_screen_touch_group_item(
        context,
        SCREEN_COLOR_ITEM_KEYWORDS,
        item_label="色彩",
        step_update=context.get("step_update"),
    )
