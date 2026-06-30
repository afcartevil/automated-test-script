# coding: utf-8
import logging
import os
import sys

import pytest

from src.utils.adb.adb_utils import ls_dir, is_dir_exist
from src.utils.common_utils import path_join
from data.res_list import APP_DIRS


def test_apppreinstallation(device_serial):
    exits_name_dict = dict()
    repeat_dict = dict()

    for app_dir in APP_DIRS:
        if not is_dir_exist(device_serial, app_dir):
            logging.warning(f"{app_dir} is not exists")
            continue
        apps = ls_dir(device_serial, app_dir)
        if not apps:
            logging.warning(f"{app_dir} is empty")
            continue
        for app_name in apps:
            if app_name not in exits_name_dict.keys():
                exits_name_dict[app_name] = path_join(app_dir, app_name)
            else:
                if app_name in repeat_dict.keys():
                    repeat_dict[app_name].append(path_join(app_dir, app_name))
                else:
                    repeat_dict[app_name] = [exits_name_dict[app_name]]
                    repeat_dict[app_name].append(path_join(app_dir, app_name))
    # logging.info(f"exits_name_dict: {exits_name_dict.keys()}")
    if len(repeat_dict.keys()) > 0:
        repeat_list = []
        for app_name, value in repeat_dict.items():
            value = list(set(value))
            value_copy = value.copy()
            lens = len(value)
            for item in value_copy:
                # logging.info(f"{app_name}: {ls_dir(device_serial, item)}")
                sub = [f for f in ls_dir(device_serial, item) if f.endswith(".apk")]
                if len(sub) == 0:
                    # logging.info(f"{item} is not have apk file")
                    lens = lens - 1
                    value.remove(item)
            if lens > 1:
                repeat_list.extend(value)

        if len(repeat_list) > 0:
            logging.error(f"repeat_list: {repeat_list}")
            pytest.fail(f"repeat_list: {repeat_list}")
