# coding=utf-8
import pytest
from src.utils.adb.adb_utils import get_feature


def test_notch_feature(device_serial, optional_pms_info):
    """测试notchfeature功能"""
    if not optional_pms_info.get("is_profiled_screen", False):
        return

    feature = "com.transsion.hardware.display.camera_notch"
    result = get_feature(device_serial, feature)

    if result != "":
        return

    screen_type = optional_pms_info.get("screen_size", "").lower()
    reason_map = {
        "notch": "project macro OS_NOTCH_SUPPORT must equal yes",
        "drop": "project macro OS_WATER_DROP_SUPPORT must equal yes",
        "hole": "project macro OS_HOLE_SCREEN_SUPPORT must equal yes",
    }

    reason = next(
        (msg for key, msg in reason_map.items() if key in screen_type),
        "project macro OS_NOTCH_SUPPORT or OS_WATER_DROP_SUPPORT or "
        "OS_HOLE_SCREEN_SUPPORT config error! and PMS screen_size config error!",
    )

    assert not reason, reason
