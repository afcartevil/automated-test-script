# coding: utf-8

import logging
import os
from typing import Optional

import pytest
import xmltodict

from src.utils.adb.adb_utils import execute_command


class CommonUtil:
    @staticmethod
    def create_dir(device_serial, dir_name=""):
        root_path = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        )
        file_path = os.path.join(
            root_path, dir_name if dir_name != "" else device_serial
        )
        os.makedirs(file_path, exist_ok=True)
        return file_path

    @staticmethod
    def decompile_apk(apk_file: str) -> bool:
        """
        反编译APK文件

        Args:
            apk_file: APK文件路径
            output_dir: 输出目录

        Returns:
            bool: 反编译成功返回True，失败返回False
        """
        project_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        )
        apktool_path = os.path.join(project_root, "data", "file", "apktool.jar")
        os.chmod(apktool_path, 0o777)
        unzip_path = apk_file.rsplit(".apk", 1)[0]
        cmd = f'java -jar "{apktool_path}" -f d "{apk_file}" -o "{unzip_path}"'
        result = execute_command(cmd)
        logging.info(f"反编译结果: {result}")
        return result["success"]

    @staticmethod
    def xml_to_dict(xml_file: str) -> Optional[dict]:
        """
        将XML文件转换为字典

        Args:
            xml_file: XML文件路径

        Returns:
            Optional[dict]: 转换后的字典，转换失败返回None
        """

        with open(xml_file, "r", encoding="utf-8") as f:
            xml_str = f.read()
            return xmltodict.parse(xml_str)
