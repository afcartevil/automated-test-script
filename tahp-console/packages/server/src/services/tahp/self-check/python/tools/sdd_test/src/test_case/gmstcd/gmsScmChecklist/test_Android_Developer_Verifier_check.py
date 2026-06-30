# -*- coding: utf-8 -*-
from tkinter import N, NO
import pytest
import logging

from src.utils.adb.adb_utils import (
    get_device_android_version,
    get_dumpsys_package,
)


@pytest.mark.require_android_version_min(16)
@pytest.mark.require_non_go_device()
def test_Android_Developer_Verifier_check(device_serial):

    mADVerifierPkgName = "com.google.android.verifier"
    mADVerifier_versionName = get_dumpsys_package(device_serial, mADVerifierPkgName, "versionName")

    mDevice_android_version = get_device_android_version(device_serial)

    if mDevice_android_version == "16":
        if mADVerifier_versionName is not None:
            pytest.fail("测试fail: Android 16平台, ADVerifier 禁止安装")
    else:
        if mADVerifier_versionName is None:
            pytest.fail("测试fail: Android 17平台, ADVerifier 未安装")
        
