# -*- coding: utf-8 -*-
from tkinter import N, NO
import pytest
import logging

from data.res_list import CARRIAR_MARKETS
from src.utils.adb.adb_utils import (
    get_feature,
    getprop,
    get_device_android_version,
)


@pytest.mark.require_android_version_min(16)
@pytest.mark.require_non_go_device()
def test_CtS_live_translate_check(device_serial):

    mCtS_live_translate_feature = get_feature(device_serial, 'com.google.android.feature.CONTEXTUAL_SEARCH_LIVE_TRANSLATE')
    logging.info(mCtS_live_translate_feature)

    mIsCircletoSearchSupport = getprop('ro.tr_microIntelligence.circle_to_search.feature.support', sn=device_serial)
    logging.info("mIsCircletoSearchSupport=" + mIsCircletoSearchSupport)

    mDevice_android_version = get_device_android_version(device_serial)
    logging.info("mDevice_android_version=" + mDevice_android_version)


    if mDevice_android_version == "16" :
        if mCtS_live_translate_feature is not None :
            reason = "Don't declare com.google.android.feature.CONTEXTUAL_SEARCH_LIVE_TRANSLATE!"
            pytest.fail(reason)
    else:
        if mIsCircletoSearchSupport == "1" and mCtS_live_translate_feature is None :
            reason = "Must declare com.google.android.feature.CONTEXTUAL_SEARCH_LIVE_TRANSLATE!"
            pytest.fail(reason)
