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


def test_calender(device_serial):
    google_calendar_path = get_apkpath_by_package(
        device_serial, "com.google.android.calendar"
    )
    calendar_adapter_path = get_apkpath_by_package(
        device_serial, "com.google.android.syncadapters.calendar"
    )
    os_calendar_path = get_apkpath_by_package(device_serial, "com.transsion.calendar")
    logging.info(f"google calendar path: {google_calendar_path}")
    logging.info(f"calendar adapter path: {calendar_adapter_path}")
    logging.info(f"os calendar path: {os_calendar_path}")

    # 两者需满足互斥条件，都存在或都不存在会导致测试失败
    if bool(google_calendar_path) == bool(calendar_adapter_path):
        pytest.fail("google calendar 和 calendar adapter 不能同时安装或同时卸载")

    market = getprop("ro.product.name", device_serial).split("-")[1].upper()
    if market in CARRIAR_MARKETS:
        if not bool(google_calendar_path):
            pytest.fail("运营商市场，google calendar 未安装")
        else:
            return

    ios_like = getprop("ro.os_calendar_ios_widget_support", device_serial)
    if ios_like == "1":
        if not bool(os_calendar_path):
            pytest.fail("类 ios 项目 ，OS calendar 未安装")
        else:
            return

    gmse_plus = get_feature(
        feature_name="com.google.android.feature.GMSEXPRESS_PLUS_BUILD", device_serial=device_serial
    )
    if gmse_plus:
        if not bool(google_calendar_path):
            pytest.fail("GMSE+ 项目，google calendar 未安装")
    else:
        if not bool(os_calendar_path):
            pytest.fail("非 GMSE+ 项目，OS calendar 未安装")
