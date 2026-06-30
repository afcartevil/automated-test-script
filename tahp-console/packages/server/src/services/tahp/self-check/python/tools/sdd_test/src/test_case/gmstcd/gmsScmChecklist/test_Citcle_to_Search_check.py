# -*- coding: utf-8 -*-
import pytest
import logging

from data.res_list import CARRIAR_MARKETS
from src.utils.adb.adb_utils import (
    get_feature,
    get_apkpath_by_package,
    getprop,
)


@pytest.mark.require_android_version_min(16)
def test_Citcle_to_Search_check(device_serial):

    mVelvetCtSPkgName = "com.google.android.googlequicksearchbox"
    mVelvetCtS_path = get_apkpath_by_package(
        device_serial, mVelvetCtSPkgName
    )

    logging.info(f"mVelvetCtS_path : {mVelvetCtS_path}")

    ro_os_circle_to_search = getprop('ro.os_circle_to_search', sn=device_serial)
    ro_circle_to_search_support = getprop('ro.tr_microIntelligence.circle_to_search.feature.support', sn=device_serial)
    
    logging.info(f"ro_os_circle_to_search : {ro_os_circle_to_search}")
    logging.info(f"ro_circle_to_search_support : {ro_circle_to_search_support}")

    mContextual_search = get_feature(device_serial,'com.google.android.feature.CONTEXTUAL_SEARCH')
    logging.info(f"mContextual_search : {mContextual_search}")

    mSoftware_Contextualsearch = get_feature(device_serial,'android.software.contextualsearch')
    logging.info(f"mSoftware_Contextualsearch : {mSoftware_Contextualsearch}")

    if ro_os_circle_to_search != "1" \
            and ro_circle_to_search_support != "1" :
        if "VelvetCtS" in mVelvetCtS_path \
                or mContextual_search != "" \
                or mSoftware_Contextualsearch != "":
            reason = "The device doesn't support Circle to Search."
            pytest.fail(reason)

    # Start CtS test
    if "VelvetCtS" not in mVelvetCtS_path \
            or mContextual_search == "" \
            or mSoftware_Contextualsearch == "":
        reason = "The device don't install VelvetCtS!"
        pytest.fail(reason)


