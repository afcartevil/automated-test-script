# coding=utf-8
from src.utils.adb.adb_utils import getprop


def test_ro_build_id_length(device_serial):
    """
    三方集成冒烟: 检查设备 ro.build.id 属性长度不超过 32。
    测试步骤: adb shell getprop ro.build.id
    预期结果: ro.build.id 长度小于等于 32。
    """
    expected_max_length = 32

    build_id = getprop("ro.build.id", sn=device_serial).strip()
    actual_length = len(build_id)

    assert actual_length <= expected_max_length, (
        f"ro.build.id 长度校验失败: expected <= {expected_max_length}; "
        f"actual length: {actual_length}; actual value: {build_id}"
    )
