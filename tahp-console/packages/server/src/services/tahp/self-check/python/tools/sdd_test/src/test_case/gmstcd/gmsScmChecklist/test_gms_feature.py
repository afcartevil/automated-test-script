# -*- coding: utf-8 -*-
import pytest
import logging

from data.res_list import CARRIAR_MARKETS
from src.utils.adb.adb_utils import (
    get_feature,
)


@pytest.mark.require_android_version_min(16)
def test_gms_feature_checklist(device_serial):

    mFeature_GoogleRestore = get_feature(
        feature_name="com.google.android.feature.D2D_CABLE_MIGRATION_FEATURE", device_serial=device_serial
    )
    logging.info(f"mFeature_GoogleRestore: {mFeature_GoogleRestore}")

    mFeature_Wellbeing = get_feature(
        feature_name="com.google.android.feature.WELLBEING", device_serial=device_serial
    )
    logging.info(f"mFeature_Wellbeing: {mFeature_Wellbeing}")

    if not mFeature_GoogleRestore \
            or not mFeature_Wellbeing:
        pytest.fail("GMS 相关 feature 未声明")
