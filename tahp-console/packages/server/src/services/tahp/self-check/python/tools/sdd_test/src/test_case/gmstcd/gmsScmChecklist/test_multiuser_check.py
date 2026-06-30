# -*- coding: utf-8 -*-
import pytest
import logging

from src.utils.adb.adb_utils import (
    adb_shell,
)


@pytest.mark.require_android_version_min(16)
@pytest.mark.require_slim_device()
def test_multiuser_check(device_serial):
        cmp_get_max_users_command = "pm get-max-users"
        get_max_users_value  = adb_shell(device_serial, cmp_get_max_users_command, timeout=30, no_retry=False)
        logging.info(f"get_max_users_value : {get_max_users_value['output']} ")

        if "1" not in get_max_users_value['output']:
            pytest.fail("Slim device not support multiuser, test fail")
