#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
APP管理工具模块

提供APK安装、应用启动、设备管理等公共功能

作者: LYH
创建时间: 2025
"""

import os
import time
import logging
import subprocess
from typing import Optional, List, Dict, Any
from pathlib import Path

from src.interfaces.adb_interface import ADBInterface
from src.utils.exceptions import DeviceConnectionError, TestExecutionError


class AppManager:
    """
    应用管理器

    提供APK安装、应用启动、设备管理等功能
    """

    def __init__(
        self, adb_interface: ADBInterface, logger: Optional[logging.Logger] = None
    ):
        """
        初始化应用管理器

        Args:
            adb_interface: ADB接口实例
            logger: 日志记录器
        """
        self.adb = adb_interface
        self.logger = logger or logging.getLogger(__name__)

    def check_device_connection(self, device_id: Optional[str] = None) -> bool:
        """
        检查设备连接状态

        Args:
            device_id: 设备ID，如果为None则检查是否有任何设备连接

        Returns:
            bool: 设备是否连接
        """
        try:
            if not self.adb.check_adb_available():
                self.logger.error("ADB不可用")
                return False

            devices = self.adb.get_connected_devices()
            if not devices:
                self.logger.error("未发现连接的设备")
                return False

            if device_id:
                if device_id not in devices:
                    self.logger.error(f"指定设备 {device_id} 未连接")
                    return False
                self.logger.info(f"设备 {device_id} 已连接")
            else:
                self.logger.info(f"发现 {len(devices)} 个连接的设备")

            return True

        except Exception as e:
            self.logger.error(f"检查设备连接失败: {e}")
            return False

    def get_target_device(self, device_id: Optional[str] = None) -> Optional[str]:
        """
        获取目标设备ID

        Args:
            device_id: 指定的设备ID

        Returns:
            str: 目标设备ID，如果没有可用设备则返回None
        """
        try:
            devices = self.adb.get_connected_devices()
            if not devices:
                self.logger.error("未发现连接的设备")
                return None

            if device_id:
                if device_id in devices:
                    return device_id
                else:
                    self.logger.error(f"指定设备 {device_id} 未连接")
                    return None
            else:
                # 如果没有指定设备，使用第一个可用设备
                target_device = devices[0]
                self.logger.info(f"使用设备: {target_device}")
                return target_device

        except Exception as e:
            self.logger.error(f"获取目标设备失败: {e}")
            return None

    def install_apk(
        self, apk_path: str, device_id: str, package_name: Optional[str] = None
    ) -> bool:
        """
        在指定设备上安装APK

        Args:
            apk_path: APK文件路径
            device_id: 设备ID
            package_name: 包名，如果提供则先卸载旧版本

        Returns:
            bool: 是否安装成功
        """
        try:
            # 检查APK文件是否存在
            if not os.path.exists(apk_path):
                self.logger.error(f"APK文件不存在: {apk_path}")
                return False

            # 检查设备是否可用
            if not self.check_device_connection(device_id):
                return False

            self.logger.info(f"开始在设备 {device_id} 上安装APK: {apk_path}")

            # 如果提供了包名，先卸载旧版本
            if package_name:
                self.logger.info(f"卸载旧版本应用: {package_name}")
                try:
                    cmd = ["adb", "-s", device_id, "uninstall", package_name]
                    result = subprocess.run(
                        cmd, capture_output=True, text=True, timeout=30
                    )
                    if result.returncode == 0:
                        self.logger.info("旧版本应用卸载成功")
                    else:
                        self.logger.warning(
                            f"卸载旧版本失败（可能未安装）: {result.stderr}"
                        )
                except Exception as e:
                    self.logger.warning(f"卸载旧版本失败: {e}")

            # 安装APK
            try:
                cmd = ["adb", "-s", device_id, "install", "-r", apk_path]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

                if result.returncode == 0:
                    self.logger.info("APK安装成功")
                    return True
                else:
                    self.logger.error(f"APK安装失败: {result.stderr}")
                    return False
            except Exception as e:
                self.logger.error(f"APK安装失败: {e}")
                return False

        except Exception as e:
            self.logger.error(f"安装APK时发生异常: {e}")
            return False

    def start_android_app(
        self, package_name: str, device_id: str, activity_name: Optional[str] = None
    ) -> bool:
        """
        启动Android应用

        Args:
            package_name: 应用包名
            device_id: 设备ID
            activity_name: Activity名称，如果为None则启动主Activity

        Returns:
            bool: 是否启动成功
        """
        try:
            # 检查设备是否可用
            if not self.check_device_connection(device_id):
                return False

            # 如果没有指定Activity，获取主Activity
            if not activity_name:
                activity_name = self._get_main_activity(package_name, device_id)
                if not activity_name:
                    self.logger.error(f"无法获取应用 {package_name} 的主Activity")
                    return False

            # 构建完整的Activity名称
            if not activity_name.startswith(package_name):
                full_activity = f"{package_name}/{activity_name}"
            else:
                full_activity = activity_name

            self.logger.info(f"启动应用: {full_activity}")

            # 启动应用
            try:
                cmd = [
                    "adb",
                    "-s",
                    device_id,
                    "shell",
                    "am",
                    "start",
                    "-n",
                    full_activity,
                ]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

                if result.returncode == 0:
                    self.logger.info("应用启动成功")
                    # 等待应用启动
                    time.sleep(3)
                    return True
                else:
                    self.logger.error(f"应用启动失败: {result.stderr}")
                    return False
            except Exception as e:
                self.logger.error(f"应用启动失败: {e}")
                return False

        except Exception as e:
            self.logger.error(f"启动应用时发生异常: {e}")
            return False

    def _get_main_activity(self, package_name: str, device_id: str) -> Optional[str]:
        """
        获取应用的主Activity

        Args:
            package_name: 应用包名
            device_id: 设备ID

        Returns:
            str: 主Activity名称，如果获取失败则返回None
        """
        try:
            # 方法1: 使用pm resolve-activity获取启动Activity
            cmd = [
                "adb",
                "-s",
                device_id,
                "shell",
                "pm",
                "resolve-activity",
                "--brief",
                f"{package_name}/.MainActivity",
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                encoding="utf-8",
                errors="ignore",
            )

            if result.returncode == 0 and result.stdout.strip():
                self.logger.info(f"使用默认MainActivity启动应用")
                return ".MainActivity"

            # 方法2: 尝试使用monkey命令获取启动Activity
            cmd = [
                "adb",
                "-s",
                device_id,
                "shell",
                "monkey",
                "-p",
                package_name,
                "-c",
                "android.intent.category.LAUNCHER",
                "1",
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                encoding="utf-8",
                errors="ignore",
            )

            if result.returncode == 0:
                self.logger.info(f"使用monkey命令成功启动应用")
                return ".MainActivity"  # monkey成功说明应用可启动

            # 方法3: 使用pm list packages检查应用是否存在
            cmd = [
                "adb",
                "-s",
                device_id,
                "shell",
                "pm",
                "list",
                "packages",
                package_name,
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                encoding="utf-8",
                errors="ignore",
            )

            if result.returncode == 0 and package_name in result.stdout:
                self.logger.info(f"应用已安装，使用默认MainActivity")
                return ".MainActivity"
            else:
                self.logger.error(f"应用 {package_name} 未安装")
                return None

        except Exception as e:
            self.logger.error(f"获取主Activity失败: {e}")
            return ".MainActivity"

    def is_app_installed(self, package_name: str, device_id: str) -> bool:
        """
        检查应用是否已安装

        Args:
            package_name: 应用包名
            device_id: 设备ID

        Returns:
            bool: 应用是否已安装
        """
        try:
            cmd = [
                "adb",
                "-s",
                device_id,
                "shell",
                "pm",
                "list",
                "packages",
                package_name,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode == 0:
                output = result.stdout
                return package_name in output

            return False

        except Exception as e:
            self.logger.error(f"检查应用安装状态失败: {e}")
            return False

    def get_app_version(self, package_name: str, device_id: str) -> Optional[str]:
        """
        获取应用版本信息

        Args:
            package_name: 应用包名
            device_id: 设备ID

        Returns:
            str: 应用版本，如果获取失败则返回None
        """
        try:
            cmd = ["adb", "-s", device_id, "shell", "dumpsys", "package", package_name]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode == 0:
                output = result.stdout
                for line in output.split("\n"):
                    if "versionName" in line:
                        version = line.split("=")[-1].strip()
                        return version

            return None

        except Exception as e:
            self.logger.error(f"获取应用版本失败: {e}")
            return None
