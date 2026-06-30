# coding=utf-8
import pytest

from src.utils.adb.adb_utils import adb_shell


@pytest.mark.require_build_brand("MTK")
def test_smoke_usd_power_aal_app_whitelist(device_serial):
    """
    AAL APP whitelist
    测试步骤: cat /system/etc/ams_aal_config.xml | grep -i launcher
    """
    shell_command = "cat /system/etc/ams_aal_config.xml | grep -i launcher"

    result = adb_shell(device_serial, shell_command, no_retry=True)
    actual_output = result["output"].strip()

    assert actual_output, (
        f"AAL APP whitelist 校验失败: expected non-empty output; actual: {actual_output}"
    )
