# -*- coding: utf-8 -*-
import pytest
import logging

from data.res_list import CARRIAR_MARKETS
from src.utils.adb.adb_utils import (
    get_feature,
    get_apkpath_by_package,
    getprop,
    is_package_exist,
)

def test_gms_express_calendar(device_serial):
    google_calendar_path = get_apkpath_by_package(
        device_serial, "com.google.android.calendar"
    )
    logging.info(f"google_calendar_path path: {google_calendar_path}")

    google_calendar_syncadapters_path = get_apkpath_by_package(
        device_serial, "com.google.android.syncadapters.calendar"
    )
    logging.info(f"google_calendar_syncadapters_path path: {google_calendar_syncadapters_path}")

    gms_express = get_feature(
        feature_name="com.google.android.feature.GMSEXPRESS_BUILD", device_serial=device_serial
    )

    if gms_express:
        if bool(google_calendar_path):
            pytest.fail("GMS Express 项目，Google Calendar 安装")

        if not bool(google_calendar_syncadapters_path):
            pytest.fail("GMS Express 项目，GoogleCalendarSyncAdapter 未安装")

