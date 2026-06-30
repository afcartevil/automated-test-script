#!/usr/bin/env python3

# -*- coding: utf-8 -*-

"""
时间计算器模块

用于处理Android设备的启动时间计算、证书有效期验证等功能。
支持从补丁级别解析日期、网络时间同步、时间范围验证等操作。

主要功能:
- 解析Android补丁级别日期
- 计算证书有效期
- 网络时间同步
- 时间范围验证
- 启动时间计算

Author: LYH
Date: 2025
"""

import socket
import struct
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from src.utils.exceptions import (
    TimeCalculationError,
    NetworkError,
    global_exception_handler,
    global_exception_handler_decorator,
)


class TimeCalculationError(Exception):
    """时间计算相关的异常类"""

    pass


class TimeCalculator:
    """
    时间计算器类

    负责处理Android设备的时间相关计算，包括:
    - 补丁级别日期解析
    - 证书有效期计算
    - 网络时间获取
    - 时间格式化和验证
    """

    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        初始化时间计算器

        Args:
            logger: 日志记录器，如果为None则创建默认记录器
        """
        self.logger = logger or logging.getLogger(__name__)

        # NTP服务器列表
        self.ntp_servers = [
            "pool.ntp.org",
            "time.nist.gov",
            "time.google.com",
            "time.cloudflare.com",
        ]

        # 证书有效期（天数）
        self.certificate_validity_days = 365

        # 时间格式
        self.default_time_format = "%Y-%m-%d %H:%M:%S %Z"

        self.logger.info("时间计算器初始化完成")

    @global_exception_handler_decorator
    def parse_patch_level_date(self, patch_level: int) -> Optional[datetime]:
        """
        解析Android补丁级别为日期

        Args:
            patch_level: Android补丁级别（格式：YYYYMMDD）

        Returns:
            Optional[datetime]: 解析后的日期，解析失败返回None
        """
        try:
            # 将补丁级别转换为字符串并验证格式
            patch_str = str(patch_level)

            if len(patch_str) != 8:
                self.logger.warning(f"补丁级别格式不正确: {patch_level}，期望8位数字")
                return None

            # 解析年月日
            year = int(patch_str[:4])
            month = int(patch_str[4:6])
            day = int(patch_str[6:8])

            # 验证日期有效性
            if year < 2000 or year > 2100:
                self.logger.warning(f"年份超出合理范围: {year}")
                return None

            if month < 1 or month > 12:
                self.logger.warning(f"月份无效: {month}")
                return None

            if day < 1 or day > 31:
                self.logger.warning(f"日期无效: {day}")
                return None

            # 创建日期对象
            patch_date = datetime(year, month, day, tzinfo=timezone.utc)
            self.logger.debug(f"成功解析补丁级别 {patch_level} 为日期: {patch_date}")

            return patch_date

        except ValueError as e:
            self.logger.error(f"解析补丁级别时发生错误: {e}")
            return None
        except Exception as e:
            self.logger.error(f"解析补丁级别时发生未知错误: {e}")
            return None

    @global_exception_handler_decorator
    def calculate_certificate_expiry(self, start_date: datetime) -> datetime:
        """
        计算证书过期日期

        Args:
            start_date: 证书开始日期

        Returns:
            datetime: 证书过期日期
        """
        if start_date is None:
            raise TimeCalculationError("开始日期不能为空")

        # 确保有时区信息
        if start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=timezone.utc)

        expiry_date = start_date + timedelta(days=self.certificate_validity_days)
        self.logger.debug(
            f"计算证书过期日期: {start_date} + {self.certificate_validity_days}天 = {expiry_date}"
        )

        return expiry_date

    def calculate_remaining_days(
        self, expiry_date: datetime, current_time: Optional[datetime] = None
    ) -> int:
        """
        计算剩余天数

        Args:
            expiry_date: 过期日期
            current_time: 当前时间，如果为None则使用系统时间

        Returns:
            int: 剩余天数（负数表示已过期）
        """
        try:
            if expiry_date is None:
                raise TimeCalculationError("过期日期不能为空")

            if current_time is None:
                current_time = datetime.now(timezone.utc)

            # 确保两个时间都有时区信息
            if expiry_date.tzinfo is None:
                expiry_date = expiry_date.replace(tzinfo=timezone.utc)
            if current_time.tzinfo is None:
                current_time = current_time.replace(tzinfo=timezone.utc)

            # 计算天数差
            time_diff = expiry_date - current_time
            remaining_days = time_diff.days

            self.logger.debug(
                f"计算剩余天数: {expiry_date} - {current_time} = {remaining_days}天"
            )

            return remaining_days

        except TimeCalculationError:
            raise
        except Exception as e:
            global_exception_handler.handle_exception(e, "calculate_remaining_days")
            raise TimeCalculationError(f"计算剩余天数时发生错误: {str(e)}")

    def calculate_remaining_days_from_rom_time(
        self, patch_level: int, rom_build_time: datetime
    ) -> int:
        """
        基于ROM编译时间计算剩余天数
        算法: BOOT补丁时间 + 365天 - ROM编译时间

        Args:
            patch_level: BOOT补丁级别
            rom_build_time: ROM编译时间

        Returns:
            int: 剩余天数（负数表示已过期）
        """
        try:
            if rom_build_time is None:
                raise TimeCalculationError("ROM编译时间不能为空")

            # 解析补丁级别日期
            start_date = self.parse_patch_level_date(patch_level)
            if start_date is None:
                raise TimeCalculationError(f"无法解析补丁级别: {patch_level}")

            # 计算过期时间
            expiry_date = self.calculate_certificate_expiry(start_date)

            # 确保ROM编译时间有时区信息
            if rom_build_time.tzinfo is None:
                rom_build_time = rom_build_time.replace(tzinfo=timezone.utc)

            # 计算基于ROM时间的剩余天数
            time_diff = expiry_date - rom_build_time
            remaining_days = time_diff.days

            self.logger.debug(
                f"基于ROM时间计算剩余天数: {expiry_date} - {rom_build_time} = {remaining_days}天"
            )

            return remaining_days

        except TimeCalculationError:
            raise
        except Exception as e:
            global_exception_handler.handle_exception(
                e, "calculate_remaining_days_from_rom_time"
            )
            raise TimeCalculationError(f"基于ROM时间计算失败: {str(e)}")

    def calculate_remaining_days_from_network_time(
        self, patch_level: int, network_time: Optional[datetime] = None
    ) -> int:
        """
        基于网络时间计算剩余天数
        算法: BOOT补丁时间 + 365天 - 当前网络时间

        Args:
            patch_level: BOOT补丁级别
            network_time: 网络时间，如果为None则尝试获取

        Returns:
            int: 剩余天数（负数表示已过期）
        """
        try:
            # 解析补丁级别日期
            start_date = self.parse_patch_level_date(patch_level)
            if start_date is None:
                raise TimeCalculationError(f"无法解析补丁级别: {patch_level}")

            # 计算过期时间
            expiry_date = self.calculate_certificate_expiry(start_date)

            # 获取网络时间
            if network_time is None:
                network_time = self.get_network_time()
                if network_time is None:
                    # 如果无法获取网络时间，使用系统时间
                    network_time = datetime.now(timezone.utc)
                    self.logger.warning("无法获取网络时间，使用系统时间")

            # 确保网络时间有时区信息
            if network_time.tzinfo is None:
                network_time = network_time.replace(tzinfo=timezone.utc)

            # 计算基于网络时间的剩余天数
            time_diff = expiry_date - network_time
            remaining_days = time_diff.days

            self.logger.debug(
                f"基于网络时间计算剩余天数: {expiry_date} - {network_time} = {remaining_days}天"
            )

            return remaining_days

        except TimeCalculationError:
            raise
        except Exception as e:
            global_exception_handler.handle_exception(
                e, "calculate_remaining_days_from_network_time"
            )
            raise TimeCalculationError(f"基于网络时间计算失败: {str(e)}")

    def calculate_remaining_days_by_network_time(
        self, expiry_date: datetime
    ) -> Optional[int]:
        """
        基于网络时间计算剩余天数（别名方法）

        Args:
            expiry_date: 过期时间

        Returns:
            Optional[int]: 剩余天数，如果无法获取网络时间则返回None
        """
        network_time = self.get_network_time()
        if network_time is None:
            self.logger.warning("无法获取网络时间，使用本地时间计算")
            return None

        return self.calculate_remaining_days(expiry_date, network_time)

    def get_color_status(self, remaining_days: int) -> str:
        """
        根据剩余天数获取颜色状态

        Args:
            remaining_days: 剩余天数

        Returns:
            str: 颜色状态 ('green', 'yellow', 'red')
        """
        if remaining_days < 0:
            return "red"  # 已过期
        elif remaining_days <= 30:
            return "yellow"  # 即将过期
        else:
            return "green"  # 正常

    def get_color_class(self, remaining_days: int) -> str:
        """
        根据剩余天数获取CSS类名

        Args:
            remaining_days: 剩余天数

        Returns:
            str: CSS类名
        """
        color_status = self.get_color_status(remaining_days)
        return f"status-{color_status}"

    def should_show_warning(self, remaining_days: int) -> bool:
        """
        判断是否应该显示警告

        Args:
            remaining_days: 剩余天数

        Returns:
            bool: 是否显示警告
        """
        return remaining_days <= 30

    @global_exception_handler_decorator
    def get_network_time(self, timeout: int = 5) -> Optional[datetime]:
        """
        从网络获取当前时间

        Args:
            timeout: 超时时间（秒）

        Returns:
            Optional[datetime]: 网络时间，获取失败返回None
        """
        for server in self.ntp_servers:
            try:
                ntp_time = self._get_ntp_time(server, timeout)
                if ntp_time:
                    self.logger.info(f"成功从 {server} 获取网络时间: {ntp_time}")
                    return ntp_time
            except socket.error as e:
                raise NetworkError(f"从 {server} 获取网络时间失败: {e}", url=server)
            except (ValueError, struct.error) as e:
                raise TimeCalculationError(f"解析网络时间数据失败: {e}")
            except Exception as e:
                global_exception_handler.handle_exception(
                    e, f"get_network_time_from_{server}"
                )
                continue

        self.logger.warning("无法从任何NTP服务器获取时间")
        return None

    def _get_ntp_time(self, server: str, timeout: int = 5) -> Optional[datetime]:
        """
        从指定NTP服务器获取时间

        Args:
            server: NTP服务器地址
            timeout: 超时时间（秒）

        Returns:
            Optional[datetime]: NTP时间，获取失败返回None
        """
        try:
            # 创建NTP请求包
            ntp_packet = b"\x1b" + 47 * b"\0"

            # 创建UDP套接字
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.settimeout(timeout)
                sock.sendto(ntp_packet, (server, 123))

                response, _ = sock.recvfrom(1024)

                if len(response) >= 48:
                    # 解析NTP响应
                    timestamp = struct.unpack("!I", response[40:44])[0]
                    fraction = int.from_bytes(response[36:40], "big")

                    # NTP时间戳从1900年开始，需要转换为Unix时间戳
                    ntp_epoch = datetime(1900, 1, 1, tzinfo=timezone.utc)
                    unix_epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
                    epoch_diff = (unix_epoch - ntp_epoch).total_seconds()

                    unix_timestamp = timestamp - epoch_diff
                    microseconds = int((fraction / 2**32) * 1000000)

                    return datetime.fromtimestamp(
                        unix_timestamp, tz=timezone.utc
                    ).replace(microsecond=microseconds)

        except Exception as e:
            self.logger.debug(f"NTP服务器失败 {server}: {e}")
            return None

        return None

    def format_datetime(
        self, dt: datetime, format_str: str = "%Y-%m-%d %H:%M:%S %Z"
    ) -> str:
        """
        格式化日期时间

        Args:
            dt: 日期时间对象
            format_str: 格式字符串

        Returns:
            str: 格式化后的时间字符串
        """
        if dt is None:
            return "未知"

        # 确保有时区信息
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.strftime(format_str)

    def validate_time_range(self, start_time: datetime, end_time: datetime) -> bool:
        """
        验证时间范围的有效性

        Args:
            start_time: 开始时间
            end_time: 结束时间

        Returns:
            bool: 时间范围是否有效
        """
        if start_time is None or end_time is None:
            return False

        # 确保两个时间都有时区信息
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=timezone.utc)

        return start_time < end_time

    @global_exception_handler_decorator
    def get_time_summary(
        self, patch_level: int, current_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        获取时间计算摘要

        Args:
            patch_level: 补丁级别
            current_time: 当前时间，如果为None则尝试获取网络时间

        Returns:
            Dict[str, Any]: 时间计算摘要
        """
        result = {
            "patch_level": patch_level,
            "start_date": None,
            "expiry_date": None,
            "current_time": None,
            "remaining_days": None,
            "color_status": "unknown",
            "color_class": "status-unknown",
            "show_warning": False,
            "is_valid": False,
            "error_message": None,
            "network_time_available": False,
        }

        try:
            # 解析补丁级别日期
            start_date = self.parse_patch_level_date(patch_level)
            if start_date is None:
                result["error_message"] = f"无法解析补丁级别: {patch_level}"
                return result

            result["start_date"] = start_date

            # 计算过期时间
            expiry_date = self.calculate_certificate_expiry(start_date)
            result["expiry_date"] = expiry_date

            # 获取当前时间
            if current_time is None:
                network_time = self.get_network_time()
                if network_time:
                    current_time = network_time
                    result["network_time_available"] = True
                else:
                    current_time = datetime.now(timezone.utc)
                    result["network_time_available"] = False

            result["current_time"] = current_time

            # 计算剩余天数
            remaining_days = self.calculate_remaining_days(expiry_date, current_time)
            result["remaining_days"] = remaining_days

            # 获取颜色状态
            result["color_status"] = self.get_color_status(remaining_days)
            result["color_class"] = self.get_color_class(remaining_days)
            result["show_warning"] = self.should_show_warning(remaining_days)

            # 验证时间范围
            result["is_valid"] = self.validate_time_range(start_date, expiry_date)

        except Exception as e:
            result["error_message"] = f"时间计算错误: {str(e)}"
            self.logger.error(f"时间计算摘要生成失败: {e}")

        return result

    @global_exception_handler_decorator
    def calculate_boot_times(
        self,
        raw_boot_patch_level: int,
        device_build_info: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        计算启动时间信息（主要接口方法）

        Args:
            raw_boot_patch_level: 原始启动补丁级别
            device_build_info: 设备构建信息（可选）

        Returns:
            Dict[str, Any]: 启动时间计算结果
        """
        self.logger.info(f"开始计算启动时间，补丁级别: {raw_boot_patch_level}")

        # 获取时间摘要
        time_summary = self.get_time_summary(raw_boot_patch_level)

        # 构建完整的计算结果
        result = {
            "raw_boot_patch_level": raw_boot_patch_level,
            "device_build_info": device_build_info,
            "time_calculation": time_summary,
            "calculation_timestamp": datetime.now(timezone.utc).isoformat(),
            "calculator_version": "1.0.0",
        }

        # 添加设备构建信息的时间相关字段
        if device_build_info:
            try:
                # 解析设备构建时间
                if "build_date_utc" in device_build_info:
                    build_timestamp = int(device_build_info["build_date_utc"])
                    build_date = datetime.fromtimestamp(
                        build_timestamp, tz=timezone.utc
                    )
                    result["device_build_date"] = build_date.isoformat()
                    result["device_build_date_formatted"] = self.format_datetime(
                        build_date
                    )

                # 添加设备信息摘要
                result["device_summary"] = {
                    "model": device_build_info.get("product_model", "未知"),
                    "brand": device_build_info.get("product_brand", "未知"),
                    "android_version": device_build_info.get(
                        "build_version_release", "未知"
                    ),
                    "sdk_version": device_build_info.get("build_version_sdk", "未知"),
                    "build_fingerprint": device_build_info.get(
                        "build_fingerprint", "未知"
                    ),
                }

            except Exception as e:
                self.logger.warning(f"解析设备构建信息时发生错误: {e}")
                result["device_build_error"] = str(e)

        # 添加格式化的时间字符串
        if time_summary.get("start_date"):
            result["formatted_start_date"] = self.format_datetime(
                time_summary["start_date"]
            )

        if time_summary.get("expiry_date"):
            result["formatted_expiry_date"] = self.format_datetime(
                time_summary["expiry_date"]
            )

        if time_summary.get("current_time"):
            result["formatted_current_time"] = self.format_datetime(
                time_summary["current_time"]
            )

        # 添加状态描述
        remaining_days = time_summary.get("remaining_days")
        if remaining_days is not None:
            if remaining_days < 0:
                result["status_description"] = f"证书已过期 {abs(remaining_days)} 天"
            elif remaining_days == 0:
                result["status_description"] = "证书今天过期"
            else:
                result["status_description"] = f"证书还有 {remaining_days} 天过期"
        else:
            result["status_description"] = "无法计算证书状态"

        self.logger.info(f"启动时间计算完成: {result['status_description']}")
        return result
