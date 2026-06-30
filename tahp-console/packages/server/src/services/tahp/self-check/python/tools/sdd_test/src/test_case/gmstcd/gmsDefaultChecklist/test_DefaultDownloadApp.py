# -*- coding: utf-8 -*-
import pytest
import logging

from src.utils.adb.adb_utils import (
    adb_shell,
)

def test_DefaultDownloadApp(device_serial):

    cmp_start_download_intent = "am start -W -a android.intent.action.VIEW_DOWNLOADS"

    # 返回 Home 界面
    cmp_start_home_intent = "input keyevent 3"

    cmd_content_value = adb_shell(device_serial, cmp_start_download_intent)
    # logging.info(f"cmd_content_value : {cmd_content_value}")

    res_all_line = cmd_content_value["output"].split("\n")
    for res_single_line in res_all_line:
        if "Activity:" in res_single_line:
            logging.info(f"{res_single_line}")

            if "com.google.android.apps.nbu.files" not in res_single_line:
                adb_shell(device_serial, cmp_start_home_intent)
                pytest.fail("Default Download App 应该是 FilesByGoogle")

    adb_shell(device_serial, cmp_start_home_intent)


