# -*- coding: utf-8 -*-
import logging

import pytest

from src.utils.adb.adb_utils import adb_shell, getprop

def test_MTULabels_check(device_serial):
    """
    ID: TOS1610-37748
    DESCRIPTION: [VTS]netd_integration_test---NetdSELinuxTest#CheckProperMTULabels
    """
    user_root_support = getprop("persist.user.root.support", sn=device_serial)
    logging.info(f"persist.user.root.support={user_root_support}")

    if not user_root_support:
        pytest.skip("非 user-root 设备，跳过 MTU labels 检查")

    res = adb_shell(device_serial, "ls -Z /sys/class/net/*/mtu")
    lines = [ln.strip() for ln in res["output"].splitlines() if ln.strip()]

    violations = [
        ln for ln in lines
        if not ln.startswith("u:object_r:sysfs_net:s0 /sys/class/net/")
    ]

    if violations:
        pytest.fail("MTU labels mismatch: " + "; ".join(violations))

    logging.info("check MTU labels pass")
