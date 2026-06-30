# coding: utf-8
import sys

import pytest
import os
import re
import logging
from typing import List, Optional, Tuple
from src.utils.adb.adb_utils import execute_command
from src.utils.test_case_util.CommonUtil import CommonUtil


class UninstallChecker:
    """处理应用卸载检查的工具类"""

    def __init__(self, device_serial: str):
        self.device_serial = device_serial
        self.apk_dir_path = "product/operator/app/"

    def get_operator_apks(self) -> List[str]:
        """
        获取product/operator/app目录下的所有APK文件路径

        Returns:
            List[str]: APK文件路径列表
        """
        uninstall_apps: List[str] = []
        cmd = f'adb -s {self.device_serial} shell "ls -R {self.apk_dir_path} | grep \\.apk$"'
        result = execute_command(cmd)
        logging.info(f"result: {result}")
        dir_result = execute_command(
            f"adb -s {self.device_serial} shell ls {self.apk_dir_path}"
        )
        logging.info(f"dir_result: {dir_result}")
        apk_dirs = dir_result["output"].splitlines()
        for apk in result["output"].splitlines():
            for apk_dir in apk_dirs:
                if apk.split(".")[0] in apk_dir:
                    uninstall_apps.append(self.apk_dir_path + apk_dir + "/" + apk)
        return uninstall_apps

    def get_installed_packages(self, apk_path: str) -> Optional[str]:
        """
        获取设备上已安装的应用包信息

        Returns:
            List[Tuple[str, str]]: 包含(路径, 包名)元组的列表
        """
        packages_result = execute_command(
            f"adb -s {self.device_serial} shell pm list packages -f"
        )
        pattern = re.compile(r"package:(/.*?\.apk)=(\S+)")

        matches = pattern.findall(packages_result["output"])
        return next((pkg for path, pkg in matches if path == apk_path), None)

    def create_config_file(self, device_serial: str, file_puller) -> str:
        """
        创建配置文件目录和文件路径

        Args:
            device_serial: 设备序列号
            file_puller: 文件拉取 fixture

        Returns:
            str: 配置文件完整路径
        """
        # file_path = os.getcwd() + "/" + f"{device_serial}" + "/"
        file_path = CommonUtil.create_dir(device_serial)
        config_file = os.path.join(file_path, "pms_sysapp_removable_vendor_list.txt")
        cmd = f"adb -s {device_serial} shell find product/etc/permissions -name pms_sysapp_removable_vendor_list.txt"
        if not file_puller(cmd=cmd):
            pytest.fail(f"Failed to get config file from phone: {config_file}")
        return config_file
