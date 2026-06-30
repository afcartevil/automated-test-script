import pytest

from src.utils.adb.adb_utils import getprop


MARKER_L2 = "L2"
MARKER_L3 = "L3"


def register_test_level_markers(config):
    """注册测试等级相关 markers。"""
    config.addinivalue_line("markers", "L2: 扩展用例，仅周版本执行")
    config.addinivalue_line("markers", "L3: 占位用例，当前不执行")


def _is_weekly_build(device_serial):
    """
    根据 ro.build.display.id 判断周/日版本。
    以 ')' 结尾判定为周版本，否则为日版本。
    """
    display_id = getprop("ro.build.display.id", sn=device_serial)
    return bool(display_id and display_id.strip().endswith(")"))


def get_is_weekly_build(device_serial):
    """根据设备序列号判断是否为周版本。"""
    return _is_weekly_build(device_serial)


def get_test_level_skip_marker(item, is_weekly_build):
    """
    根据版本类型返回当前用例的等级跳过 marker。

    规则：
    - 日版本：仅执行 L1（未标记），跳过 L2/L3
    - 周版本：执行 L1/L2，跳过 L3
    """
    is_l2_case = item.get_closest_marker(MARKER_L2) is not None
    is_l3_case = item.get_closest_marker(MARKER_L3) is not None

    if is_l3_case:
        return pytest.mark.skip(reason="L3为占位用例，当前不执行")

    if not is_weekly_build and is_l2_case:
        return pytest.mark.skip(reason="日版本仅执行L1级用例，L2已跳过")

    return None
