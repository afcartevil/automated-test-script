# coding=utf-8
import pytest

from src.utils.adb.adb_utils import adb_shell


@pytest.mark.require_build_brand("MTK")
def test_smoke_usd_subsys_tran_hwinfo(device_serial):
    """
    HBM功能: tranHwInfo service移植
    测试步骤: ps -e | grep tranHwInfo
    """
    shell_command = 'ps -e | grep tranHwInfo'
    expected_text = "tranHwInfo"

    result = adb_shell(device_serial, shell_command, no_retry=True)
    actual_output = result["output"]

    assert expected_text in actual_output, (
        f"tranHwInfo service 校验失败: expected contains: {expected_text}; actual: {actual_output}"
    )
