"""STR4 驱动硬测：灯效（复用器件 case21 单色灯测试结果）。"""

from test.case_reuse import run_reuse_whole_case

SOURCE_CASE_INDEX = 21


def run(category=None, case_index=None, device_info=None, **context):
    return run_reuse_whole_case(
        SOURCE_CASE_INDEX,
        device_info=device_info,
        source_category="str4/driver_component",
        **context,
    )
