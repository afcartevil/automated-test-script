# -*- coding: utf-8 -*-
import pytest
import logging

from src.utils.adb.adb_utils import (
    get_dumpsys_package,
    get_cmd_overlay_lookup,
)


@pytest.mark.require_android_version_min(16)
@pytest.mark.require_markets("IN", "EU")
def test_EEAv2Compliance_check(device_serial):

    mSearchSelectorPkgName = "com.google.android.apps.setupwizard.searchselector"
    get_SearchSelector_versionName = get_dumpsys_package(device_serial, mSearchSelectorPkgName, "versionName")

    logging.info(f"get_SearchSelector_versionName : {get_SearchSelector_versionName} ")

    if get_SearchSelector_versionName is None:
        pytest.fail("项目需求: Google Search Selector 未安装")

    mDefaultSearchSelectorPkgName = get_cmd_overlay_lookup(device_serial, "string", "config_defaultSearchSelectorPackageName")
    logging.info(f"mDefaultSearchSelectorPkgName : {mDefaultSearchSelectorPkgName} ")

    if mDefaultSearchSelectorPkgName == "" \
            or mDefaultSearchSelectorPkgName != "com.google.android.apps.setupwizard.searchselector":
        pytest.fail("IN/EU test_EEAv2Compliance_check check FAIL!")

