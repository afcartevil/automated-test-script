# -*- coding: utf-8 -*-
import pytest
import logging

from data.res_list import CARRIAR_MARKETS
from src.utils.adb.adb_utils import (
    get_dumpsys_package,
)


@pytest.mark.require_android_version_min(15)
def test_CalendarAddAppointment(device_serial):

    # Case: testCalendarAddAppointment
    # ID: TOS1510-38152
    # DESCRIPTION: [CTS]CtsContentTestCases-android.content.cts.AvailableIntentsTest#testCalendarAddAppointment

    mCalendarGoogle_PkgName = "com.google.android.calendar"
    mTranssionCalendar_PkgName = "com.transsion.calendar"

    mCalendarGoogle_versionName = get_dumpsys_package(
        device_serial, mCalendarGoogle_PkgName, "versionName"
    )
    mTranssionCalendar_versionName = get_dumpsys_package(
        device_serial, mTranssionCalendar_PkgName, "versionName"
    )

    logging.info(f"mCalendarGoogle_versionName: {mCalendarGoogle_versionName}")
    logging.info(f"mTranssionCalendar_versionName: {mTranssionCalendar_versionName}")

    if mCalendarGoogle_versionName is None \
            and mTranssionCalendar_versionName  is None:
        pytest.fail("未预置日历应用")


