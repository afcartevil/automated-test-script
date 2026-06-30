#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Console Output Manager
控制台输出管理器

负责标准化测试结果的控制台输出格式
提供统一的成功/失败结果显示
"""

import os
import logging
from datetime import datetime
from typing import Dict, Optional, Any


class ConsoleOutputManager:
    """
    控制台输出管理器

    负责标准化测试结果的控制台输出格式，包括：
    - 测试结果状态显示
    - 设备ID信息
    - 证书有效期信息
    - 报告文件路径
    - 执行时间信息
    """

    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        初始化控制台输出管理器

        Args:
            logger: 日志记录器，可选
        """
        self.logger = logger or logging.getLogger(__name__)

        # 输出格式配置
        self.separator = "=" * 20
        self.title = "=== 测试结果 ==="
        self.end_separator = "=" * 17

    def print_test_result(
        self, result_data: Dict[str, Any], verbose: bool = True
    ) -> None:
        """
        打印标准化的测试结果到控制台

        Args:
            result_data: 结果数据字典，包含测试结果信息
            verbose: 是否显示详细信息，默认True
        """
        try:
            # 获取格式化的输出字符串
            output = self.get_formatted_output(result_data, verbose)

            # 打印到控制台
            print(output)

            # 记录到日志
            if self.logger:
                status = result_data.get("status", "unknown")
                device_id = result_data.get("device_id", "unknown")
                self.logger.info(
                    f"控制台输出测试结果 - 状态: {status}, 设备: {device_id}"
                )

        except Exception as e:
            error_msg = f"打印测试结果失败: {str(e)}"
            print(f"错误: {error_msg}")
            if self.logger:
                self.logger.error(error_msg)

    def get_formatted_output(
        self, result_data: Dict[str, Any], verbose: bool = True
    ) -> str:
        """
        获取格式化的输出字符串（不直接打印）

        Args:
            result_data: 结果数据字典
            verbose: 是否显示详细信息

        Returns:
            str: 格式化的输出字符串
        """
        try:
            status = result_data.get("status", "unknown")

            if status == "success":
                return self.format_success_output(result_data, verbose)
            elif status == "failure":
                return self.format_failure_output(result_data, verbose)
            else:
                return self.format_unknown_output(result_data, verbose)

        except Exception as e:
            return f"格式化输出失败: {str(e)}"

    def format_success_output(
        self, result_data: Dict[str, Any], verbose: bool = True
    ) -> str:
        """
        格式化成功结果输出

        Args:
            result_data: 结果数据字典
            verbose: 是否显示详细信息

        Returns:
            str: 格式化的成功输出字符串
        """
        lines = []
        lines.append(self.title)
        lines.append("状态: 成功")

        # 设备ID
        device_id = result_data.get("device_id", "unknown")
        lines.append(f"设备ID: {device_id}")

        # 证书有效期
        days_remaining = result_data.get("certificate_days_remaining")
        if days_remaining is not None:
            cert_info = self.format_certificate_info(days_remaining)
            lines.append(f"证书有效期剩余: {cert_info}")

        # 报告文件路径
        report_path = result_data.get("report_path")
        if report_path:
            abs_path = os.path.abspath(report_path)
            lines.append(f"报告文件: {abs_path}")

        # 执行时间
        execution_time = result_data.get("execution_time")
        if execution_time:
            lines.append(f"执行时间: {execution_time}")

        # 详细信息（如果启用verbose）
        if verbose:
            duration = result_data.get("duration_seconds")
            if duration is not None:
                lines.append(f"执行耗时: {duration:.2f} 秒")

            boot_time = result_data.get("details", {}).get("boot_time")
            if boot_time is not None:
                lines.append(f"启动时间: {boot_time:.2f} 秒")

        lines.append(self.end_separator)
        return "\n".join(lines)

    def format_failure_output(
        self, result_data: Dict[str, Any], verbose: bool = True
    ) -> str:
        """
        格式化失败结果输出

        Args:
            result_data: 结果数据字典
            verbose: 是否显示详细信息

        Returns:
            str: 格式化的失败输出字符串
        """
        lines = []
        lines.append(self.title)
        lines.append("状态: 失败")

        # 设备ID
        device_id = result_data.get("device_id", "unknown")
        lines.append(f"设备ID: {device_id}")

        # 失败原因
        error_message = result_data.get("error_message", "未知错误")
        lines.append(f"失败原因: {error_message}")

        # 证书有效期（如果可获取）
        days_remaining = result_data.get("certificate_days_remaining")
        if days_remaining is not None:
            cert_info = self.format_certificate_info(days_remaining)
            lines.append(f"证书有效期剩余: {cert_info}")

        # 报告文件路径（如果已生成）
        report_path = result_data.get("report_path")
        if report_path:
            abs_path = os.path.abspath(report_path)
            lines.append(f"报告文件: {abs_path}")

        # 执行时间
        execution_time = result_data.get("execution_time")
        if execution_time:
            lines.append(f"执行时间: {execution_time}")

        # 详细信息（如果启用verbose）
        if verbose:
            duration = result_data.get("duration_seconds")
            if duration is not None:
                lines.append(f"执行耗时: {duration:.2f} 秒")

            error_code = result_data.get("error_code")
            if error_code:
                lines.append(f"错误代码: {error_code}")

            last_step = result_data.get("details", {}).get("last_successful_step")
            if last_step:
                lines.append(f"最后成功步骤: {last_step}")

        lines.append(self.end_separator)
        return "\n".join(lines)

    def format_unknown_output(
        self, result_data: Dict[str, Any], verbose: bool = True
    ) -> str:
        """
        格式化未知状态结果输出

        Args:
            result_data: 结果数据字典
            verbose: 是否显示详细信息

        Returns:
            str: 格式化的未知状态输出字符串
        """
        lines = []
        lines.append(self.title)

        status = result_data.get("status", "unknown")
        lines.append(f"状态: {status}")

        device_id = result_data.get("device_id", "unknown")
        lines.append(f"设备ID: {device_id}")

        execution_time = result_data.get("execution_time")
        if execution_time:
            lines.append(f"执行时间: {execution_time}")

        lines.append(self.end_separator)
        return "\n".join(lines)

    def format_certificate_info(self, days_remaining: int) -> str:
        """
        格式化证书有效期信息

        Args:
            days_remaining: 剩余天数

        Returns:
            str: 格式化的证书信息字符串
        """
        if days_remaining < 0:
            return f"{abs(days_remaining)} 天 (已过期)"
        elif days_remaining == 0:
            return "今天到期"
        elif days_remaining <= 7:
            return f"{days_remaining} 天 (即将到期)"
        elif days_remaining <= 30:
            return f"{days_remaining} 天 (需要关注)"
        else:
            return f"{days_remaining} 天"

    def set_output_format(self, title: str = None, separator: str = None) -> None:
        """
        设置输出格式

        Args:
            title: 标题文本
            separator: 分隔符
        """
        if title:
            self.title = title
        if separator:
            self.separator = separator
            self.end_separator = separator[:17] if len(separator) >= 17 else separator
