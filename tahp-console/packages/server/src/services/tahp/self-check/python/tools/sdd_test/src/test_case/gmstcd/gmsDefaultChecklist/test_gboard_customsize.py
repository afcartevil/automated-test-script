# -*- coding: utf-8 -*-
"""检查gboard内缩配置文件与属性是否一致"""

import logging
import os
import pytest

from src.utils.adb.adb_utils import (
    getprop,
    ls_dir,
)

@pytest.mark.require_spd_feature_support("SF-202508-000031")
def test_gboard_customsize(device_serial):
    """检查曲面屏项目是否完成 Gboard UI 内缩"""
    ime_config_file = getprop("ro.com.google.ime.config_file", sn=device_serial)
    logging.info(f"ro.com.google.ime.config_file={ime_config_file}")

    latin_ime_dir = "/tr_product/etc/asset/LatinImeGoogle/res/"
    dir_entries = ls_dir(device_serial, latin_ime_dir) or []
    logging.info(f"LatinImeGoogle/res/ entries: {dir_entries}")

    valid_configs = {
        "/tr_product/etc/asset/LatinImeGoogle/res/curve48/tran_config.rc": "curve48",
        "/tr_product/etc/asset/LatinImeGoogle/res/curve55/tran_config.rc": "curve55",
    }

    if ime_config_file not in valid_configs:
        pytest.fail(
            f"ro.com.google.ime.config_file 值 '{ime_config_file}' 不正确"
        )

    expected_folder = valid_configs[ime_config_file]
    logging.info(f"check gboard customsize pass, ro.com.google.ime.config_file={ime_config_file}")

    if expected_folder not in dir_entries:
        pytest.fail(
            f"check gboard customsize fail, {expected_folder} folder not found in {latin_ime_dir}"
        )