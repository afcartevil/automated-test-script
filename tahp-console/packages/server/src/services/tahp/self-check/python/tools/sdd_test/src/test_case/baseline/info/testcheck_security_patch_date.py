# -*- coding: utf-8 -*-
import pytest
from datetime import datetime
import logging
from utils.adb.adb_utils import is_google_one_product, is_root_product, getprop
import time


def testcheck_security_patch_date(device_serial):
    if is_root_product(device_serial):
        pytest.skip("root设备，跳过测试")

    # 获取当前时间，并转换为时间戳（秒级）
    current_timestamp = int(datetime.now().timestamp())
    # 执行命令，获取安全补丁日期
    # security_patch_date = is_uniform_patchtime(device_serial)
    security_patch_date = getprop("ro.build.version.security_patch", device_serial)

    logging.info(f"security_patch_date: {security_patch_date}")

    # 转换为时间戳（秒级）
    security_patch_timestamp = int(
        time.mktime(time.strptime(security_patch_date, "%Y-%m-%d"))
    )
    # 计算天数差
    delta_days = int((current_timestamp - security_patch_timestamp) / 86400)

    # 计算门槛值
    threshold = 80 if not is_google_one_product(device_serial) else 30

    assert delta_days <= threshold, f"安全补丁日期与当前时间相差超过 {threshold} 天"
