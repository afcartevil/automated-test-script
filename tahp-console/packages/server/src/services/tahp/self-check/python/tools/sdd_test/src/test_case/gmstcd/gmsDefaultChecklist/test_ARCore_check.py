# -*- coding: utf-8 -*-
import pytest
import logging

from src.utils.adb.adb_utils import (
    get_dumpsys_package,
)


@pytest.mark.require_android_version_min(16)
@pytest.mark.require_spd_feature_support("GS-202601-000005")
def test_ARCore_check(device_serial):
    mARCorePkgName = "com.google.ar.core"
    get_ARCore_versionName = get_dumpsys_package(device_serial, mARCorePkgName, "versionName")

    logging.info(f"get_ARCore_versionName : {get_ARCore_versionName} ")

    if get_ARCore_versionName is None:
        pytest.fail("项目需求: Google ARCore 未安装")


