#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
报告生成模块

负责生成各种格式的监控报告，包括：
- HTML格式报告
- JSON格式报告
- 文本格式报告
- 报告模板管理
- 数据可视化

作者: LYH
创建时间: 2025-09-02
"""

import logging
import json
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from pathlib import Path
import os

from src.utils.exceptions import (
    ReportGenerationError,
    FileOperationError,
    safe_execute,
    global_exception_handler,
    global_exception_handler_decorator,
)


class DateTimeEncoder(json.JSONEncoder):
    """自定义JSON编码器，处理datetime对象"""

    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


class ReportGenerator:
    """
    报告生成器
    """

    def __init__(self, output_dir: str = "output/reports"):
        """
        初始化报告生成器

        Args:
            output_dir: 输出目录
        """
        self.logger = logging.getLogger(__name__)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # HTML模板
        self.html_template = self._get_html_template()

    @global_exception_handler_decorator
    def generate_comprehensive_report(
        self,
        boot_data: Dict[str, Any],
        warnings: List[Dict[str, Any]],
        warning_summary: Dict[str, Any],
        device_id: str = None,
    ) -> Dict[str, str]:
        """
        生成综合报告（所有格式）

        Args:
            boot_data: 启动数据
            warnings: 警告列表
            warning_summary: 警告摘要
            device_id: 设备ID（可选，用于向后兼容）

        Returns:
            Dict[str, str]: 包含所有格式报告文件路径的字典
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 生成所有格式的报告
        html_path = self._generate_html_report(
            boot_data, warnings, warning_summary, timestamp, device_id
        )
        json_path = self._generate_json_report(
            boot_data, warnings, warning_summary, timestamp, device_id
        )
        text_path = self._generate_text_report(
            boot_data, warnings, warning_summary, timestamp, device_id
        )

        return {"html": html_path, "json": json_path, "text": text_path}

    @global_exception_handler_decorator
    def _generate_html_report(
        self,
        boot_data: Dict[str, Any],
        warnings: List[Dict[str, Any]],
        warning_summary: Dict[str, Any],
        timestamp: str,
        device_id: str = None,
    ) -> str:
        """
        生成HTML格式报告

        Args:
            boot_data: 启动数据
            warnings: 警告列表
            warning_summary: 警告摘要
            timestamp: 时间戳

        Returns:
            str: 报告文件路径
        """
        # 准备数据
        report_data = self._prepare_report_data(boot_data, warnings, warning_summary)

        # 生成HTML内容
        html_content = self.html_template.format(
            report_title="启动监控报告",
            generation_time=datetime.now().strftime("%Y-%m-%d"),
            device_info_html=self._generate_device_info_html(
                report_data["device_info"]
            ),
            boot_data_html=self._generate_boot_data_html(report_data["boot_data"]),
            calculation_html=self._generate_calculation_html(
                report_data["calculation_result"]
            ),
            warning_summary_html=self._generate_warning_summary_html(warning_summary),
            warnings_html=self._generate_warnings_html(warnings),
            recommendations_html=self._generate_recommendations_html(warning_summary),
        )

        # 保存文件
        filename = self.generate_report_filename(device_id, "html")
        filepath = self.output_dir / filename

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(html_content)
        except (OSError, IOError, PermissionError) as e:
            raise FileOperationError(f"无法写入HTML报告文件 {filepath}: {e}")

        self.logger.info(f"HTML报告已生成: {filepath}")
        return str(filepath)

    @global_exception_handler_decorator
    def _generate_json_report(
        self,
        boot_data: Dict[str, Any],
        warnings: List[Dict[str, Any]],
        warning_summary: Dict[str, Any],
        timestamp: str,
        device_id: str = None,
    ) -> str:
        """
        生成JSON格式报告

        Args:
            boot_data: 启动数据
            warnings: 警告列表
            warning_summary: 警告摘要
            timestamp: 时间戳

        Returns:
            str: 报告文件路径
        """
        report_data = {
            "report_metadata": {
                "title": "Android BOOT证书监控报告",
                "generation_time": datetime.now(timezone.utc).isoformat(),
                "format": "json",
                "version": "1.0",
            },
            "boot_data": boot_data,
            "warnings": warnings,
            "warning_summary": warning_summary,
        }

        # 保存文件
        filename = self.generate_report_filename(device_id, "json")
        filepath = self.output_dir / filename

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(
                    report_data, f, indent=2, ensure_ascii=False, cls=DateTimeEncoder
                )
        except (OSError, IOError, PermissionError) as e:
            raise FileOperationError(f"无法写入JSON报告文件 {filepath}: {e}")
        except (TypeError, ValueError) as e:
            raise ReportGenerationError(f"JSON序列化失败: {e}")

        self.logger.info(f"JSON报告已生成: {filepath}")
        return str(filepath)

    @global_exception_handler_decorator
    def _generate_text_report(
        self,
        boot_data: Dict[str, Any],
        warnings: List[Dict[str, Any]],
        warning_summary: Dict[str, Any],
        timestamp: str,
        device_id: str = None,
    ) -> str:
        """
        生成文本格式报告

        Args:
            boot_data: 启动数据
            warnings: 警告列表
            warning_summary: 警告摘要
            timestamp: 时间戳

        Returns:
            str: 报告文件路径
        """
        report_lines = []
        report_lines.append("=" * 60)
        report_lines.append("启动监控报告")
        report_lines.append("=" * 60)
        report_lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d')}")
        report_lines.append("")

        # 设备信息
        report_lines.append("设备信息:")
        report_lines.append("-" * 30)
        device_info = boot_data.get("device_info", {})
        boot_info = boot_data.get("boot_info", {})
        report_lines.append(f"设备ID: {boot_info.get('device_id', 'N/A')}")
        report_lines.append(f"设备型号: {device_info.get('model', 'N/A')}")
        report_lines.append(f"设备品牌: {device_info.get('brand', 'N/A')}")
        report_lines.append(f"SDK版本: {device_info.get('sdk_version', 'N/A')}")
        report_lines.append(f"Android版本: {device_info.get('android_version', 'N/A')}")
        report_lines.append("")

        # 启动性能
        report_lines.append("启动性能:")
        report_lines.append("-" * 30)
        report_lines.append(f"启动时间: {boot_info.get('boot_duration', 'N/A')}秒")
        report_lines.append(f"系统版本: {boot_info.get('system_version', 'N/A')}")

        # 性能指标
        performance_metrics = boot_data.get("performance_metrics", {})
        if performance_metrics:
            report_lines.append(
                f"CPU使用率: {performance_metrics.get('cpu_usage', 'N/A')}%"
            )
            report_lines.append(
                f"内存使用率: {performance_metrics.get('memory_usage', 'N/A')}%"
            )
            report_lines.append(f"磁盘IO: {performance_metrics.get('disk_io', 'N/A')}")

        # 服务信息
        services = boot_data.get("services", [])
        if services:
            report_lines.append("")
            report_lines.append("服务启动信息:")
            for service in services:
                name = service.get("name", "N/A")
                start_time = service.get("start_time", "N/A")
                status = service.get("status", "N/A")
                report_lines.append(f"  {name}: {start_time}秒 ({status})")

        report_lines.append("")

        # 启动数据
        report_lines.append("BOOT与Vendor数据:")
        report_lines.append("-" * 30)
        boot_data_info = boot_data.get("boot_data", {})
        report_lines.append(
            f"原始BOOT补丁级别: {boot_data_info.get('raw_boot_patch_level', 'N/A')}"
        )
        report_lines.append(
            f"格式化BOOT补丁级别: {boot_data_info.get('formatted_boot_patch_level', 'N/A')}"
        )
        report_lines.append(
            f"原始Vendor补丁级别: {boot_data_info.get('raw_vendor_patch_level', 'N/A')}"
        )
        report_lines.append(
            f"格式化Vendor补丁级别: {boot_data_info.get('formatted_vendor_patch_level', 'N/A')}"
        )
        report_lines.append("")

        # 计算结果
        report_lines.append("计算结果:")
        report_lines.append("-" * 30)
        calc_result = boot_data.get("calculation_result", {})

        # 获取ROM构建时间来源信息
        rom_build_time_source = calc_result.get("rom_build_time_source", "unknown")
        source_descriptions = {
            "device_utc_timestamp": "设备UTC时间戳",
            "device_build_date": "设备构建日期",
            "boot_patch_level": "BOOT补丁级别日期",
            "current_time": "当前时间（默认值）",
            "unknown": "未知来源",
        }
        source_description = source_descriptions.get(rom_build_time_source, "未知来源")

        report_lines.append(f"ROM构建时间: {calc_result.get('rom_build_time', 'N/A')}")
        report_lines.append(f"ROM构建时间来源: {source_description}")
        report_lines.append(f"BOOT日期: {calc_result.get('boot_date', 'N/A')}")
        report_lines.append(f"过期日期: {calc_result.get('expiry_date', 'N/A')}")
        report_lines.append(f"剩余天数: {calc_result.get('remaining_days', 'N/A')}")
        report_lines.append(
            f"警告状态: {'是' if calc_result.get('warning_status') else '否'}"
        )
        report_lines.append("")

        # 警告摘要
        report_lines.append("警告摘要:")
        report_lines.append("-" * 30)
        report_lines.append(f"总警告数: {warning_summary.get('total_warnings', 0)}")
        report_lines.append(
            f"严重警告: {'是' if warning_summary.get('has_critical') else '否'}"
        )
        report_lines.append(
            f"错误: {'是' if warning_summary.get('has_errors') else '否'}"
        )
        report_lines.append(f"摘要: {warning_summary.get('summary', 'N/A')}")
        report_lines.append(f"建议: {warning_summary.get('recommendation', 'N/A')}")
        report_lines.append("")

        # 详细警告
        if warnings:
            report_lines.append("详细警告:")
            report_lines.append("-" * 30)
            for i, warning in enumerate(warnings, 1):
                report_lines.append(
                    f"{i}. [{warning.get('level', 'N/A')}] {warning.get('warning_type', 'N/A')}"
                )
                report_lines.append(f"   消息: {warning.get('message', 'N/A')}")
                report_lines.append(f"   时间: {warning.get('timestamp', 'N/A')}")
                if warning.get("details"):
                    report_lines.append(f"   详情: {warning['details']}")
                report_lines.append("")

        report_lines.append("=" * 60)

        # 保存文件
        filename = self.generate_report_filename(device_id, "txt")
        filepath = self.output_dir / filename

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write("\n".join(report_lines))
        except (OSError, IOError, PermissionError) as e:
            raise FileOperationError(f"无法写入文本报告文件 {filepath}: {e}")

        self.logger.info(f"文本报告已生成: {filepath}")
        return str(filepath)

    def _prepare_report_data(
        self,
        boot_data: Dict[str, Any],
        warnings: List[Dict[str, Any]],
        warning_summary: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        准备报告数据

        Args:
            boot_data: 启动数据
            warnings: 警告列表
            warning_summary: 警告摘要

        Returns:
            Dict[str, Any]: 处理后的报告数据
        """
        # 合并设备信息，确保包含boot_info中的设备ID
        device_info = boot_data.get("device_info", {}).copy()
        boot_info = boot_data.get("boot_info", {})
        if "device_id" in boot_info:
            device_info["device_id"] = boot_info["device_id"]

        return {
            "device_info": device_info,
            "boot_data": {
                "boot_info": boot_data.get("boot_info", {}),
                "boot_data": boot_data.get("boot_data", {}),
                "performance_metrics": boot_data.get("performance_metrics", {}),
                "services": boot_data.get("services", []),
            },
            "calculation_result": boot_data.get("calculation_result", {}),
            "warnings": warnings,
            "warning_summary": warning_summary,
        }

    def _generate_device_info_html(self, device_info: Dict[str, Any]) -> str:
        """
        生成设备信息HTML

        Args:
            device_info: 设备信息

        Returns:
            str: HTML内容
        """
        return f"""
        <div class="info-section">
            <h3>设备信息</h3>
            <table class="info-table">
                <tr><td>设备ID</td><td>{device_info.get('device_id', 'N/A')}</td></tr>
                <tr><td>设备型号</td><td>{device_info.get('model', 'N/A')}</td></tr>
                <tr><td>设备品牌</td><td>{device_info.get('brand', 'N/A')}</td></tr>
                <tr><td>SDK版本</td><td>{device_info.get('sdk_version', 'N/A')}</td></tr>
                <tr><td>Android版本</td><td>{device_info.get('android_version', 'N/A')}</td></tr>
            </table>
        </div>
        """

    def _generate_boot_data_html(self, boot_data: Dict[str, Any]) -> str:
        """
        生成启动数据HTML

        Args:
            boot_data: 启动数据

        Returns:
            str: HTML内容
        """
        # 获取启动信息
        boot_info = boot_data.get("boot_info", {})
        boot_data_info = boot_data.get("boot_data", {})

        # 获取性能指标和服务信息
        performance_metrics = boot_data.get("performance_metrics", {})
        services = boot_data.get("services", [])

        html_content = f"""
        <div class="info-section">
            <h3>启动性能</h3>
            <table class="info-table">
                <tr><td>启动时间</td><td>{boot_info.get('boot_duration', 'N/A')}秒</td></tr>
                <tr><td>系统版本</td><td>{boot_info.get('system_version', 'N/A')}</td></tr>
            </table>
        </div>
        """

        # 添加性能指标
        if performance_metrics:
            html_content += f"""
        <div class="info-section">
            <h3>性能指标</h3>
            <table class="info-table">
                <tr><td>CPU使用率</td><td>{performance_metrics.get('cpu_usage', 'N/A')}%</td></tr>
                <tr><td>内存使用率</td><td>{performance_metrics.get('memory_usage', 'N/A')}%</td></tr>
                <tr><td>磁盘IO</td><td>{performance_metrics.get('disk_io', 'N/A')}</td></tr>
            </table>
        </div>
        """

        # 添加服务信息
        if services:
            html_content += """
        <div class="info-section">
            <h3>服务启动信息</h3>
            <table class="info-table">
            """
            for service in services:
                name = service.get("name", "N/A")
                start_time = service.get("start_time", "N/A")
                status = service.get("status", "N/A")
                html_content += (
                    f"<tr><td>{name}</td><td>{start_time}秒</td><td>{status}</td></tr>"
                )
            html_content += """
            </table>
        </div>
        """

        # 添加BOOT与Vendor数据
        html_content += f"""
        <div class="info-section">
            <h3>BOOT与Vendor数据</h3>
            <table class="info-table">
                <tr><td>原始BOOT补丁级别</td><td>{boot_data_info.get('raw_boot_patch_level', 'N/A')}</td></tr>
                <tr><td>格式化BOOT补丁级别</td><td>{boot_data_info.get('formatted_boot_patch_level', 'N/A')}</td></tr>
                <tr><td>原始Vendor补丁级别</td><td>{boot_data_info.get('raw_vendor_patch_level', 'N/A')}</td></tr>
                <tr><td>格式化Vendor补丁级别</td><td>{boot_data_info.get('formatted_vendor_patch_level', 'N/A')}</td></tr>
            </table>
        </div>
        """

        return html_content

    def _generate_calculation_html(self, calculation_result: Dict[str, Any]) -> str:
        """
        生成计算结果HTML（支持双重时间显示和BOOT证书失效状态）

        Args:
            calculation_result: 计算结果

        Returns:
            str: HTML内容
        """
        # 检查BOOT证书状态
        boot_cert_status = calculation_result.get("boot_cert_status", "VALID")

        if boot_cert_status == "INVALID":
            # BOOT证书失效时的显示
            return f"""
<div class="info-section">
    <h3>🚨 BOOT证书状态检查结果</h3>
    <table class="info-table">
        <tr><td>BOOT证书状态</td><td>❌ 证书失效</td></tr>
        <tr><td>BOOT补丁时间</td><td>无法解析</td></tr>
        <tr><td>BOOT证书过期时间</td><td>无法计算</td></tr>
        <tr class="divider"><td colspan="2"><hr></td></tr>
        <tr><td>问题描述</td><td>系统无法解析BOOT证书信息，可能是证书损坏或格式不正确</td></tr>
        <tr><td>建议处理</td><td>联系技术支持检查设备BOOT分区或重新刷机</td></tr>
    </table>
</div>
            """

        # BOOT证书有效时的正常显示
        # 获取双重时间计算结果
        remaining_days_network = calculation_result.get("remaining_days_network")
        remaining_days_rom = calculation_result.get("remaining_days_rom", 0)
        network_available = calculation_result.get("network_available", False)
        network_time = calculation_result.get("network_time")

        # 获取ROM构建时间来源信息
        rom_build_time_source = calculation_result.get(
            "rom_build_time_source", "unknown"
        )
        source_descriptions = {
            "device_utc_timestamp": "设备UTC时间戳",
            "device_build_date": "设备构建日期",
            "boot_patch_level_date": "BOOT补丁级别日期",
            "provided": "外部提供",
            "unknown": "未知来源",
        }
        source_description = source_descriptions.get(rom_build_time_source, "未知来源")

        # 格式化网络时间显示
        if network_available and remaining_days_network is not None:
            network_time_display = network_time if network_time else "N/A"
            if remaining_days_network > 30:
                network_remaining_display = (
                    f"✅ {self._format_remaining_days_display(remaining_days_network)}"
                )
            elif remaining_days_network > 0:
                network_remaining_display = (
                    f"⚠️ {self._format_remaining_days_display(remaining_days_network)}"
                )
            else:
                network_remaining_display = (
                    f"❌ {self._format_remaining_days_display(remaining_days_network)}"
                )
        else:
            network_time_display = "网络异常无法获取"
            network_remaining_display = "🔌 网络异常无法计算"

        # 格式化ROM时间显示
        if remaining_days_rom > 30:
            rom_remaining_display = (
                f"✅ {self._format_remaining_days_display(remaining_days_rom)}"
            )
        elif remaining_days_rom > 0:
            rom_remaining_display = (
                f"⚠️ {self._format_remaining_days_display(remaining_days_rom)}"
            )
        else:
            rom_remaining_display = (
                f"❌ {self._format_remaining_days_display(remaining_days_rom)}"
            )

        return f"""
<div class="info-section">
    <h3>✅ BOOT证书过期时间计算结果</h3>
    <table class="info-table">
        <tr><td>BOOT证书状态</td><td>✅ 证书有效</td></tr>
        <tr><td>BOOT补丁时间</td><td>{calculation_result.get('boot_date', 'N/A')}</td></tr>
        <tr><td>BOOT证书过期时间</td><td>{calculation_result.get('expiry_date', 'N/A')}</td></tr>
        <tr class="divider"><td colspan="2"><hr></td></tr>
        <tr><td>当前网络时间</td><td>{network_time_display}</td></tr>
        <tr><td>基于当前网络时间剩余有效天数</td><td>{network_remaining_display}</td></tr>
        <tr class="divider"><td colspan="2"><hr></td></tr>
        <tr><td>ROM编译时间</td><td>{calculation_result.get('rom_build_time', 'N/A')}</td></tr>
        <tr><td>ROM编译时间来源</td><td>{source_description}</td></tr>
        <tr><td>基于ROM编译时间剩余有效天数</td><td>{rom_remaining_display}</td></tr>
    </table>
</div>
        """

    def _format_remaining_days_display(self, remaining_days: int) -> str:
        """
        格式化剩余天数显示（符合MyTestDemo要求）

        Args:
            remaining_days: 剩余天数

        Returns:
            str: 格式化后的显示文本
        """
        if remaining_days > 0:
            return f"剩余 {remaining_days} 天"
        elif remaining_days == 0:
            return "今天到期"
        else:
            return f"已过期{abs(remaining_days)}天"

    def _generate_warning_summary_html(self, warning_summary: Dict[str, Any]) -> str:
        """
        生成警告摘要HTML

        Args:
            warning_summary: 警告摘要

        Returns:
            str: HTML内容
        """
        # 使用图标代替颜色状态
        if warning_summary.get("has_critical"):
            status_icon = "🚨"
            status_text = "严重警告"
        elif warning_summary.get("has_errors"):
            status_icon = "⚠️"
            status_text = "一般警告"
        else:
            status_icon = "✅"
            status_text = "状态正常"

        return f"""
<div class="warning-summary">
    <h3>{status_icon} 警告摘要 - {status_text}</h3>
    <p><strong>总警告数:</strong> {warning_summary.get('total_warnings', 0)}</p>
    <p><strong>摘要:</strong> {warning_summary.get('summary', 'N/A')}</p>
    <p><strong>建议:</strong> {warning_summary.get('recommendation', 'N/A')}</p>
</div>
        """

    def _generate_warnings_html(self, warnings: List[Dict[str, Any]]) -> str:
        """
        生成警告列表HTML

        Args:
            warnings: 警告列表

        Returns:
            str: HTML内容
        """
        if not warnings:
            return '<div class="info-section"><h3>详细警告</h3><p>无警告</p></div>'

        warnings_html = (
            '<div class="info-section"><h3>详细警告</h3><div class="warnings-list">'
        )

        for warning in warnings:
            level = warning.get("level", "INFO")
            # 使用图标代替颜色样式
            if level.upper() == "CRITICAL":
                level_icon = "🚨"
            elif level.upper() == "ERROR":
                level_icon = "❌"
            elif level.upper() == "WARNING":
                level_icon = "⚠️"
            else:
                level_icon = "ℹ️"

            warnings_html += f"""
<div class="warning-item">
    <div class="warning-header">
        <span class="warning-level">{level_icon} [{level}]</span>
        <span class="warning-type">{warning.get('warning_type', 'N/A')}</span>
        <span class="warning-time">{warning.get('timestamp', 'N/A')}</span>
    </div>
    <div class="warning-message">{warning.get('message', 'N/A')}</div>
</div>
"""

        warnings_html += "</div></div>"
        return warnings_html

    def _generate_recommendations_html(self, warning_summary: Dict[str, Any]) -> str:
        """
        生成建议HTML

        Args:
            warning_summary: 警告摘要

        Returns:
            str: HTML内容
        """
        recommendation = warning_summary.get("recommendation", "系统状态正常")

        # 根据建议内容生成具体的操作建议
        action_items = []
        if "立即更新" in recommendation:
            action_items.append("立即联系系统管理员或技术支持")
            action_items.append("准备系统更新或重新刷机")
            action_items.append("备份重要数据")
        elif "尽快更新" in recommendation:
            action_items.append("计划在近期进行系统更新")
            action_items.append("监控证书状态变化")
            action_items.append("准备更新方案")
        elif "检查设备" in recommendation:
            action_items.append("检查设备连接状态")
            action_items.append("验证ADB调试功能")
            action_items.append("重新运行监控程序")
        else:
            action_items.append("继续定期监控")
            action_items.append("保持系统更新")

        actions_html = "".join([f"<li>{item}</li>" for item in action_items])

        return f"""
<div class="recommendations">
    <h3>操作建议</h3>
    <p><strong>主要建议:</strong> {recommendation}</p>
    <h4>具体操作:</h4>
    <ul>{actions_html}</ul>
</div>
"""

    def _get_html_template(self) -> str:
        """
        获取HTML模板

        Returns:
            str: HTML模板
        """
        return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{report_title}</title>
<style>
body {{
font-family: 'Microsoft YaHei', Arial, sans-serif;
line-height: 1.6;
margin: 0;
padding: 20px;
background-color: #f5f5f5;
}}
.container {{
max-width: 1200px;
margin: 0 auto;
background-color: white;
padding: 30px;
border-radius: 8px;
box-shadow: 0 2px 10px rgba(0,0,0,0.1);
}}
.header {{
text-align: center;
border-bottom: 2px solid #007bff;
padding-bottom: 20px;
margin-bottom: 30px;
}}
.header h1 {{
color: #007bff;
margin: 0;
}}
.generation-time {{
color: #666;
font-size: 14px;
margin-top: 10px;
}}
.info-section {{
margin-bottom: 30px;
padding: 20px;
border: 1px solid #ddd;
border-radius: 5px;
background-color: #fafafa;
}}
.info-section h3 {{
color: #333;
margin-top: 0;
border-bottom: 1px solid #ddd;
padding-bottom: 10px;
}}
.info-table {{
width: 100%;
border-collapse: collapse;
}}
.info-table td {{
padding: 8px 12px;
border: 1px solid #ddd;
}}
.info-table td:first-child {{
background-color: #f8f9fa;
font-weight: bold;
width: 200px;
}}
.warning-summary {{
padding: 20px;
border-radius: 5px;
margin-bottom: 30px;
}}
.warning-summary.normal {{
background-color: #d4edda;
border: 1px solid #c3e6cb;
color: #155724;
}}
.warning-summary.warning {{
background-color: #fff3cd;
border: 1px solid #ffeaa7;
color: #856404;
}}
.warning-summary.critical {{
background-color: #f8d7da;
border: 1px solid #f5c6cb;
color: #721c24;
}}
.warnings-list {{
margin-top: 15px;
}}
.warning-item {{
margin-bottom: 15px;
padding: 15px;
border-radius: 5px;
border-left: 4px solid;
}}
.warning-item.info {{
background-color: #e7f3ff;
border-left-color: #007bff;
}}
.warning-item.warning {{
background-color: #fff8e1;
border-left-color: #ff9800;
}}
.warning-item.critical {{
background-color: #ffebee;
border-left-color: #f44336;
}}
.warning-item.error {{
background-color: #fce4ec;
border-left-color: #e91e63;
}}
.warning-header {{
display: flex;
justify-content: space-between;
align-items: center;
margin-bottom: 8px;
}}
.warning-level {{
font-weight: bold;
padding: 2px 8px;
border-radius: 3px;
background-color: rgba(0,0,0,0.1);
}}
.warning-type {{
font-weight: bold;
}}
.warning-time {{
font-size: 12px;
color: #666;
}}
.warning-message {{
font-size: 14px;
}}
.recommendations {{
background-color: #e8f5e8;
border: 1px solid #c3e6cb;
border-radius: 5px;
padding: 20px;
margin-top: 30px;
}}
.recommendations h3 {{
color: #155724;
margin-top: 0;
}}
.recommendations ul {{
margin: 10px 0;
padding-left: 20px;
}}
.recommendations li {{
margin-bottom: 5px;
}}
.normal {{
color: #28a745;
font-weight: bold;
}}
.warning {{
color: #ff9800;
font-weight: bold;
}}
.critical {{
color: #dc3545;
font-weight: bold;
}}
.status-normal {{
color: #28a745;
font-weight: bold;
}}
.status-warning {{
color: #ff9800;
font-weight: bold;
}}
.status-critical {{
color: #dc3545;
font-weight: bold;
}}
.footer {{
text-align: center;
margin-top: 40px;
padding-top: 20px;
border-top: 1px solid #ddd;
color: #666;
font-size: 12px;
}}
.section {{
margin-bottom: 20px;
padding: 15px;
border: 1px solid #ddd;
border-radius: 5px;
background-color: #fafafa;
}}
</style>
</head>
<body>
<div class="container">
<div class="header">
<h1>{report_title}</h1>
<div class="generation-time">生成时间: {generation_time}</div>
</div>
        
        {device_info_html}
        
        {boot_data_html}
        
        {calculation_html}
        
        {warning_summary_html}
        
        {warnings_html}
        
        {recommendations_html}
        
        <div class="footer">
            <p>此报告由Android BOOT证书监控系统自动生成</p>
            <p>作者: LYH</p>
        </div>
    </div>
</body>
</html>
        """

    @global_exception_handler_decorator
    def generate_summary_report(
        self, multiple_reports: List[Dict[str, Any]], format_type: str = "html"
    ) -> str:
        """
        生成多次监控的汇总报告

        Args:
            multiple_reports: 多个报告数据
            format_type: 报告格式

        Returns:
            str: 报告文件路径
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if format_type.lower() == "html":
            return self._generate_summary_html_report(multiple_reports, timestamp)
        elif format_type.lower() == "json":
            return self._generate_summary_json_report(multiple_reports, timestamp)
        else:
            raise ReportGenerationError(f"汇总报告不支持格式: {format_type}")

    @global_exception_handler_decorator
    def _generate_summary_html_report(
        self, multiple_reports: List[Dict[str, Any]], timestamp: str
    ) -> str:
        """
        生成HTML汇总报告

        Args:
            multiple_reports: 多个报告数据
            timestamp: 时间戳

        Returns:
            str: 报告文件路径
        """
        # 分析趋势和统计
        stats = self._analyze_report_statistics(multiple_reports)

        # 生成HTML内容（简化版）
        html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>Android BOOT证书监控汇总报告</title>
<style>
body {{ font-family: 'Microsoft YaHei', Arial, sans-serif; margin: 20px; }}
.summary-stats {{ background: #f8f9fa; padding: 20px; border-radius: 5px; margin: 20px 0; }}
.trend-chart {{ margin: 20px 0; }}
</style>
</head>
<body>
<h1>Android BOOT证书监控汇总报告</h1>
<p>生成时间: {datetime.now().strftime('%Y-%m-%d')}</p>
<div class="summary-stats">
<h2>统计摘要</h2>
<p>监控次数: {stats['total_reports']}</p>
<p>平均剩余天数: {stats['avg_remaining_days']:.1f}</p>
<p>警告次数: {stats['warning_count']}</p>
<p>严重警告次数: {stats['critical_count']}</p>
</div>
<div class="trend-chart">
<h2>趋势分析</h2>
<p>最新剩余天数: {stats['latest_remaining_days']}</p>
<p>趋势: {stats['trend']}</p>
</div>
</body>
</html>"""

        # 保存文件
        filename = f"boot_monitor_summary_{timestamp}.html"
        filepath = self.output_dir / filename

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(html_content)
        except (OSError, IOError, PermissionError) as e:
            raise FileOperationError(f"无法写入HTML汇总报告文件 {filepath}: {e}")

        self.logger.info(f"HTML汇总报告已生成: {filepath}")
        return str(filepath)

    @global_exception_handler_decorator
    def _generate_summary_json_report(
        self, multiple_reports: List[Dict[str, Any]], timestamp: str
    ) -> str:
        """
        生成JSON汇总报告

        Args:
            multiple_reports: 多个报告数据
            timestamp: 时间戳

        Returns:
            str: 报告文件路径
        """
        stats = self._analyze_report_statistics(multiple_reports)

        summary_data = {
            "report_metadata": {
                "title": "Android BOOT证书监控汇总报告",
                "generation_time": datetime.now(timezone.utc).isoformat(),
                "format": "json",
                "version": "1.0",
            },
            "statistics": stats,
            "reports": multiple_reports,
        }

        # 保存文件
        filename = f"boot_monitor_summary_{timestamp}.json"
        filepath = self.output_dir / filename

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(summary_data, f, indent=2, ensure_ascii=False)
        except (OSError, IOError, PermissionError) as e:
            raise FileOperationError(f"无法写入JSON汇总报告文件 {filepath}: {e}")
        except (TypeError, ValueError) as e:
            raise ReportGenerationError(f"JSON序列化失败: {e}")

        self.logger.info(f"JSON汇总报告已生成: {filepath}")
        return str(filepath)

    def _analyze_report_statistics(
        self, multiple_reports: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        分析报告统计信息

        Args:
            multiple_reports: 多个报告数据

        Returns:
            Dict[str, Any]: 统计信息
        """
        if not multiple_reports:
            return {
                "total_reports": 0,
                "avg_remaining_days": 0,
                "warning_count": 0,
                "critical_count": 0,
                "latest_remaining_days": 0,
                "trend": "无数据",
            }

        # 提取剩余天数
        remaining_days_list = []
        warning_count = 0
        critical_count = 0

        for report in multiple_reports:
            boot_data = report.get("boot_data", {})
            calc_result = boot_data.get("calculation_result", {})
            remaining_days = calc_result.get("remaining_days")

            if remaining_days is not None:
                remaining_days_list.append(remaining_days)

            # 统计警告
            warning_summary = report.get("warning_summary", {})
            if warning_summary.get("total_warnings", 0) > 0:
                warning_count += 1
            if warning_summary.get("has_critical", False):
                critical_count += 1

        # 计算统计值
        avg_remaining_days = (
            sum(remaining_days_list) / len(remaining_days_list)
            if remaining_days_list
            else 0
        )
        latest_remaining_days = remaining_days_list[-1] if remaining_days_list else 0

        # 简单趋势分析
        trend = "稳定"
        if len(remaining_days_list) >= 2:
            if remaining_days_list[-1] < remaining_days_list[0]:
                trend = "下降"
            elif remaining_days_list[-1] > remaining_days_list[0]:
                trend = "上升"

        return {
            "total_reports": len(multiple_reports),
            "avg_remaining_days": avg_remaining_days,
            "warning_count": warning_count,
            "critical_count": critical_count,
            "latest_remaining_days": latest_remaining_days,
            "trend": trend,
            "remaining_days_history": remaining_days_list,
        }

    @global_exception_handler_decorator
    def validate_report_data(
        self,
        boot_data: Dict[str, Any],
        warnings: List[Dict[str, Any]],
        warning_summary: Dict[str, Any],
    ) -> bool:
        """
        验证报告数据的有效性

        Args:
            boot_data: 启动数据
            warnings: 警告列表
            warning_summary: 警告摘要

        Returns:
            bool: 数据是否有效

        Raises:
            ReportGenerationError: 数据验证失败
        """
        # 验证启动数据
        if not boot_data:
            raise ReportGenerationError("启动数据不能为空")

        # 检查必需的字段（适应实际数据结构）
        if "boot_info" not in boot_data:
            raise ReportGenerationError("缺少启动信息")

        boot_info = boot_data["boot_info"]
        if not isinstance(boot_info, dict):
            raise ReportGenerationError("启动信息格式错误")

        # 检查启动信息的必需字段
        required_fields = ["device_id", "boot_duration", "timestamp"]
        for field in required_fields:
            if field not in boot_info:
                raise ReportGenerationError(f"启动信息缺少必需字段: {field}")

        # 验证警告数据
        if not isinstance(warnings, list):
            raise ReportGenerationError("警告数据必须是列表")

        for warning in warnings:
            if not isinstance(warning, dict):
                raise ReportGenerationError("警告项必须是字典")
            if "level" not in warning or "message" not in warning:
                raise ReportGenerationError("警告项缺少必需字段")

        # 验证警告摘要
        if not isinstance(warning_summary, dict):
            raise ReportGenerationError("警告摘要必须是字典")

        return True

    @global_exception_handler_decorator
    def get_report_metadata(self) -> Dict[str, Any]:
        """
        获取报告元数据

        Returns:
            Dict[str, Any]: 报告元数据
        """
        return {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "generator_version": "1.0.0",
            "report_type": "boot_monitor",
            "format_version": "1.0",
        }

    @global_exception_handler_decorator
    def sanitize_device_id(self, device_id: str) -> str:
        """
        清理设备ID中的特殊字符，确保文件名合法

        Args:
            device_id: 原始设备ID

        Returns:
            str: 清理后的设备ID
        """
        if not device_id:
            return "unknown_device"

        # 移除或替换文件名中不允许的字符
        import re

        # 保留字母、数字、下划线和连字符
        clean_id = re.sub(r"[^a-zA-Z0-9_-]", "_", str(device_id))
        # 移除连续的下划线
        clean_id = re.sub(r"_+", "_", clean_id)
        # 移除开头和结尾的下划线
        clean_id = clean_id.strip("_")

        # 如果清理后为空，使用默认值
        if not clean_id:
            clean_id = "unknown_device"

        return clean_id

    @global_exception_handler_decorator
    def generate_report_filename(
        self, device_id: str = None, format_type: str = "html"
    ) -> str:
        """
        生成报告文件名

        Args:
            device_id: 设备ID（可选，用于向后兼容）
            format_type: 报告格式

        Returns:
            str: 文件名
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 确定文件扩展名
        if format_type.lower() == "html":
            ext = "html"
        elif format_type.lower() == "json":
            ext = "json"
        elif format_type.lower() in ["txt", "text"]:
            ext = "txt"
        else:
            raise ReportGenerationError(f"不支持的报告格式: {format_type}")

        # 如果提供了设备ID，使用新格式；否则使用原格式（向后兼容）
        if device_id:
            clean_device_id = self.sanitize_device_id(device_id)
            return f"{clean_device_id}_boot_monitor_report_{timestamp}.{ext}"
        else:
            return f"boot_monitor_report_{timestamp}.{ext}"

    @global_exception_handler_decorator
    def cleanup_old_reports(self, keep_count: int = 10) -> int:
        """
        清理旧报告文件

        Args:
            keep_count: 保留的报告数量

        Returns:
            int: 清理的文件数量
        """
        try:
            # 获取所有报告文件
            report_files = []
            # 匹配两种文件名格式：boot_monitor_report_* 和 report_*
            for pattern in ["boot_monitor_report_*.html", "report_*.html"]:
                for file_path in self.output_dir.glob(pattern):
                    report_files.append(file_path)
            for pattern in ["boot_monitor_report_*.json", "report_*.json"]:
                for file_path in self.output_dir.glob(pattern):
                    report_files.append(file_path)
            for pattern in ["boot_monitor_report_*.txt", "report_*.txt"]:
                for file_path in self.output_dir.glob(pattern):
                    report_files.append(file_path)

            # 按修改时间排序
            report_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

            # 删除多余的文件
            cleaned_count = 0
            for file_path in report_files[keep_count:]:
                try:
                    file_path.unlink()
                    cleaned_count += 1
                    self.logger.info(f"已删除旧报告: {file_path}")
                except OSError as e:
                    self.logger.warning(f"删除文件失败 {file_path}: {e}")

            return cleaned_count

        except Exception as e:
            self.logger.error(f"清理旧报告失败: {e}")
            return 0

    @global_exception_handler_decorator
    def generate_json_report(
        self,
        boot_data: Dict[str, Any],
        warnings: List[Dict[str, Any]],
        warning_summary: Dict[str, Any],
    ) -> str:
        """
        生成JSON格式报告

        Args:
            boot_data: 启动数据
            warnings: 警告列表
            warning_summary: 警告摘要

        Returns:
            str: 报告文件路径
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return self._generate_json_report(
            boot_data, warnings, warning_summary, timestamp
        )

    @global_exception_handler_decorator
    def generate_text_report(
        self,
        boot_data: Dict[str, Any],
        warnings: List[Dict[str, Any]],
        warning_summary: Dict[str, Any],
    ) -> str:
        """
        生成文本格式报告

        Args:
            boot_data: 启动数据
            warnings: 警告列表
            warning_summary: 警告摘要

        Returns:
            str: 报告文件路径
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return self._generate_text_report(
            boot_data, warnings, warning_summary, timestamp
        )

    @global_exception_handler_decorator
    def generate_failure_report(
        self, failure_data: Dict[str, Any], error_type: str, error_message: str
    ) -> str:
        """
        生成失败报告（HTML格式）

        Args:
            failure_data: 失败数据
            error_type: 错误类型
            error_message: 错误消息

        Returns:
            str: 报告文件路径
        """
        try:
            # 创建output/reports目录
            reports_dir = Path("output/reports")
            reports_dir.mkdir(parents=True, exist_ok=True)

            # 生成文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"failure_report_{timestamp}.html"
            file_path = reports_dir / filename

            # 准备失败报告数据
            report_data = self._prepare_failure_report_data(
                failure_data, error_type, error_message
            )

            # 生成HTML内容
            html_content = self._generate_failure_html_report(report_data)

            # 写入文件
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(html_content)

            self.logger.info(f"失败报告已生成: {file_path}")
            return str(file_path)

        except Exception as e:
            self.logger.error(f"生成失败报告时发生错误: {e}")
            raise ReportGenerationError(f"生成失败报告失败: {e}", report_type="failure")

    def _prepare_failure_report_data(
        self, failure_data: Dict[str, Any], error_type: str, error_message: str
    ) -> Dict[str, Any]:
        """
        准备失败报告数据

        Args:
            failure_data: 失败数据
            error_type: 错误类型
            error_message: 错误消息

        Returns:
            Dict[str, Any]: 准备好的报告数据
        """
        # 获取当前时间
        current_time = datetime.now()

        # 提取设备信息（如果有的话）
        device_info = failure_data.get("device_info", {})
        if not device_info and "device_id" in failure_data:
            device_info = {"device_id": failure_data["device_id"]}

        # 提取错误信息
        error_info = failure_data.get("error_info", {})

        # 构建报告数据
        report_data = {
            "report_title": "启动监控失败报告",
            "generation_time": current_time.strftime("%Y-%m-%d %H:%M:%S"),
            "device_info": {
                "device_id": device_info.get("device_id", "N/A"),
                "device_model": device_info.get("device_model", "N/A"),
                "android_version": device_info.get("android_version", "N/A"),
                "build_number": device_info.get("build_number", "N/A"),
                "security_patch": device_info.get("security_patch", "N/A"),
            },
            "error_summary": {
                "error_type": error_type,
                "error_message": error_message,
                "timestamp": failure_data.get("timestamp", current_time.isoformat()),
                "test_type": failure_data.get("test_type", "automated_test"),
            },
            "error_details": error_info,
            "boot_data": failure_data.get("boot_data", {}),
            "partial_warnings": failure_data.get("warnings", []),
            "status": "FAILED",
        }

        return report_data

    def _generate_failure_html_report(self, report_data: Dict[str, Any]) -> str:
        """
        生成失败报告的HTML内容

        Args:
            report_data: 报告数据

        Returns:
            str: HTML内容
        """
        # 获取HTML模板
        template = self._get_html_template()

        # 检查report_data结构
        if "device_info" not in report_data:
            raise KeyError("report_data中缺少device_info字段")

        # 生成设备信息HTML
        device_info_html = self._generate_failure_device_info_html(
            report_data["device_info"]
        )

        # 生成错误信息HTML
        error_info_html = self._generate_failure_error_info_html(
            report_data["error_summary"], report_data["error_details"]
        )

        # 生成启动数据HTML（如果有的话）
        boot_data_html = self._generate_failure_boot_data_html(report_data["boot_data"])

        # 生成警告信息HTML（如果有的话）
        warnings_html = self._generate_failure_warnings_html(
            report_data["partial_warnings"]
        )

        # 替换模板中的占位符
        html_content = template.format(
            report_title=report_data["report_title"],
            generation_time=report_data["generation_time"],
            device_info_html=device_info_html,
            boot_data_html=boot_data_html,
            calculation_html=error_info_html,  # 修正字段名
            warning_summary_html='<div class="warning-summary error"><h3>测试状态: 失败</h3></div>',  # 修正字段名
            warnings_html=warnings_html,  # 修正字段名
            recommendations_html='<div class="recommendations"><h3>建议操作</h3><ul><li>检查设备连接状态</li><li>重新运行测试</li><li>查看详细错误日志</li></ul></div>',  # 修正字段名
        )

        return html_content

    def _generate_failure_device_info_html(self, device_info: Dict[str, Any]) -> str:
        """
        生成失败报告的设备信息HTML

        Args:
            device_info: 设备信息

        Returns:
            str: 设备信息HTML
        """
        return f"""
        <div class="device-info">
            <h3>设备信息</h3>
            <table>
                <tr><td>设备ID:</td><td>{device_info.get('device_id', 'N/A')}</td></tr>
                <tr><td>设备型号:</td><td>{device_info.get('device_model', 'N/A')}</td></tr>
                <tr><td>Android版本:</td><td>{device_info.get('android_version', 'N/A')}</td></tr>
                <tr><td>构建号:</td><td>{device_info.get('build_number', 'N/A')}</td></tr>
                <tr><td>安全补丁:</td><td>{device_info.get('security_patch', 'N/A')}</td></tr>
            </table>
        </div>
        """

    def _generate_failure_error_info_html(
        self, error_summary: Dict[str, Any], error_details: Dict[str, Any]
    ) -> str:
        """
        生成失败报告的错误信息HTML

        Args:
            error_summary: 错误摘要
            error_details: 错误详情

        Returns:
            str: 错误信息HTML
        """
        error_html = f"""
        <div class="calculation-results error">
            <h3>错误信息</h3>
            <table>
                <tr><td>错误类型:</td><td class="error">{error_summary.get('error_type', 'N/A')}</td></tr>
                <tr><td>错误消息:</td><td class="error">{error_summary.get('error_message', 'N/A')}</td></tr>
                <tr><td>发生时间:</td><td>{error_summary.get('timestamp', 'N/A')}</td></tr>
                <tr><td>测试类型:</td><td>{error_summary.get('test_type', 'N/A')}</td></tr>
            </table>
        """

        # 添加错误详情
        if error_details:
            error_html += "<h4>错误详情</h4><table>"
            for key, value in error_details.items():
                if key not in ["traceback", "stack_trace"]:  # 避免显示过长的堆栈信息
                    error_html += f"<tr><td>{key}:</td><td>{value}</td></tr>"
            error_html += "</table>"

        error_html += "</div>"
        return error_html

    def _generate_failure_boot_data_html(self, boot_data: Dict[str, Any]) -> str:
        """
        生成失败报告的启动数据HTML

        Args:
            boot_data: 启动数据

        Returns:
            str: 启动数据HTML
        """
        if not boot_data:
            return (
                '<div class="boot-data"><h3>启动数据</h3><p>无可用的启动数据</p></div>'
            )

        boot_html = '<div class="boot-data"><h3>启动数据（部分）</h3><table>'

        # 显示可解析的启动数据字段
        for key, value in boot_data.items():
            if isinstance(value, (str, int, float, bool)):
                boot_html += f"<tr><td>{key}:</td><td>{value}</td></tr>"
            elif (
                isinstance(value, dict) and len(str(value)) < 200
            ):  # 避免显示过长的数据
                boot_html += f"<tr><td>{key}:</td><td>{value}</td></tr>"

        boot_html += "</table></div>"
        return boot_html

    def _generate_failure_warnings_html(self, warnings: List[Dict[str, Any]]) -> str:
        """
        生成失败报告的警告信息HTML

        Args:
            warnings: 警告列表

        Returns:
            str: 警告信息HTML
        """
        if not warnings:
            return '<div class="warnings"><h3>警告信息</h3><p>无警告信息</p></div>'

        warnings_html = '<div class="warnings"><h3>部分警告信息</h3>'

        for warning in warnings[:5]:  # 最多显示5个警告
            level = warning.get("level", "info")
            message = warning.get("message", "未知警告")
            warnings_html += f'<div class="warning-item {level}"><span class="warning-level">[{level.upper()}]</span> {message}</div>'

        if len(warnings) > 5:
            warnings_html += f"<p>还有 {len(warnings) - 5} 个警告未显示...</p>"

        warnings_html += "</div>"
        return warnings_html

    @global_exception_handler_decorator
    def generate_html_report(
        self,
        boot_data: Dict[str, Any],
        warnings: List[Dict[str, Any]],
        warning_summary: Dict[str, Any],
    ) -> str:
        """
        生成HTML格式报告

        Args:
            boot_data: 启动数据
            warnings: 警告列表
            warning_summary: 警告摘要

        Returns:
            str: 报告文件路径
        """
        # 验证数据
        if not boot_data or not boot_data.get("boot_info"):
            raise ReportGenerationError("缺少启动数据")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return self._generate_html_report(
            boot_data, warnings, warning_summary, timestamp
        )

    def format_boot_info_html(self, boot_info: Dict[str, Any]) -> str:
        """
        格式化HTML启动信息

        Args:
            boot_info: 启动信息

        Returns:
            str: HTML格式的启动信息
        """
        html = f"""
         <div class="boot-info">
             <h3>设备信息</h3>
             <p><strong>设备ID:</strong> {boot_info.get('device_id', 'N/A')}</p>
             <p><strong>启动时间:</strong> {boot_info.get('boot_duration', 0)}秒</p>
             <p><strong>系统版本:</strong> {boot_info.get('system_version', boot_info.get('android_version', 'N/A'))}</p>
             <p><strong>时间戳:</strong> {boot_info.get('timestamp', 'N/A')}</p>
         </div>
         """
        return html

    def format_services_html(self, services: List[Dict[str, Any]]) -> str:
        """
        格式化HTML服务信息

        Args:
            services: 服务列表

        Returns:
            str: HTML格式的服务信息
        """
        html = "<table class='services-table'><tr><th>服务名称</th><th>启动时间</th><th>状态</th></tr>"
        for service in services:
            html += f"<tr><td>{service.get('name', 'N/A')}</td><td>{service.get('start_time', 0)}秒</td><td>{service.get('status', 'unknown')}</td></tr>"
        html += "</table>"
        return html

    def format_warnings_html(self, warnings: List[Dict[str, Any]]) -> str:
        """
        格式化HTML警告信息

        Args:
            warnings: 警告列表

        Returns:
            str: HTML格式的警告信息
        """
        html = "<div class='warnings'>"
        for warning in warnings:
            level = warning.get("level", "info")
            message = warning.get("message", "")
            html += f"<div class='warning {level}'><span class='level'>[{level.upper()}]</span> {message}</div>"
        html += "</div>"
        return html

    def format_boot_info_text(self, boot_info: Dict[str, Any]) -> str:
        """
        格式化文本启动信息

        Args:
            boot_info: 启动信息

        Returns:
            str: 文本格式的启动信息
        """
        text = "设备信息:\n"
        text += f"设备ID: {boot_info.get('device_id', 'N/A')}\n"
        text += f"启动时间: {boot_info.get('boot_duration', 0)}秒\n"
        text += f"系统版本: {boot_info.get('system_version', boot_info.get('android_version', 'N/A'))}\n"
        text += f"时间戳: {boot_info.get('timestamp', 'N/A')}\n"
        return text

    def format_services_text(self, services: List[Dict[str, Any]]) -> str:
        """
        格式化文本服务信息

        Args:
            services: 服务列表

        Returns:
            str: 文本格式的服务信息
        """
        text = "服务信息:\n"
        for service in services:
            text += f"- {service.get('name', 'N/A')}: {service.get('start_time', 0)}秒 ({service.get('status', 'unknown')})\n"
        return text

    def format_warnings_text(self, warnings: List[Dict[str, Any]]) -> str:
        """
        格式化文本警告信息

        Args:
            warnings: 警告列表

        Returns:
            str: 文本格式的警告信息
        """
        text = "警告信息:\n"
        for warning in warnings:
            level = warning.get("level", "info")
            message = warning.get("message", "")
            text += f"[{level.upper()}] {message}\n"
        return text

    @global_exception_handler_decorator
    def generate_integration_report(self, test_result: Dict[str, Any]) -> str:
        """
        生成集成测试报告

        Args:
            test_result: 集成测试结果

        Returns:
            str: 报告文件路径
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 生成HTML报告
        html_content = self._generate_integration_html_report(test_result)

        # 保存文件
        filename = f"integration_test_report_{timestamp}.html"
        filepath = self.output_dir / filename

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(html_content)
        except (OSError, IOError, PermissionError) as e:
            raise FileOperationError(f"无法写入集成测试报告文件 {filepath}: {e}")

        self.logger.info(f"集成测试报告已生成: {filepath}")
        return str(filepath)

    def _generate_integration_html_report(self, test_result: Dict[str, Any]) -> str:
        """
        生成集成测试HTML报告

        Args:
            test_result: 测试结果

        Returns:
            str: HTML内容
        """
        success = test_result.get("success", False)
        device_id = test_result.get("device_id", "N/A")
        start_time = test_result.get("start_time", "N/A")
        end_time = test_result.get("end_time", "N/A")
        duration = test_result.get("duration", 0)
        steps = test_result.get("steps", [])
        errors = test_result.get("errors", [])

        # 生成步骤HTML
        steps_html = ""
        for step in steps:
            step_name = step.get("step", "unknown")
            step_status = step.get("status", "unknown")
            step_error = step.get("error", "")

            status_class = "success" if step_status == "success" else "failed"
            steps_html += f"""
            <tr class="{status_class}">
                <td>{step_name}</td>
                <td>{step_status}</td>
                <td>{step_error}</td>
            </tr>
            """

        # 生成错误HTML
        errors_html = ""
        for error in errors:
            errors_html += f"<li class='error'>{error}</li>"

        # 生成完整的HTML报告
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>集成测试报告</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .header {{ background-color: #f0f0f0; padding: 20px; border-radius: 5px; }}
                .summary {{ margin: 20px 0; padding: 15px; border-radius: 5px; }}
                .success {{ background-color: #d4edda; color: #155724; }}
                .failed {{ background-color: #f8d7da; color: #721c24; }}
                table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #f2f2f2; }}
                .error {{ color: #dc3545; }}
                .success-text {{ color: #28a745; }}
                ul {{ margin: 10px 0; }}
                li {{ margin: 5px 0; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>集成测试报告</h1>
                <p>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            </div>
            
            <div class="summary {'success' if success else 'failed'}">
                <h2>测试摘要</h2>
                <p><strong>测试结果:</strong> {'成功' if success else '失败'}</p>
                <p><strong>设备ID:</strong> {device_id}</p>
                <p><strong>开始时间:</strong> {start_time}</p>
                <p><strong>结束时间:</strong> {end_time}</p>
                <p><strong>持续时间:</strong> {duration}秒</p>
            </div>
            
            <div class="steps">
                <h2>测试步骤</h2>
                <table>
                    <thead>
                        <tr>
                            <th>步骤</th>
                            <th>状态</th>
                            <th>错误信息</th>
                        </tr>
                    </thead>
                    <tbody>
                        {steps_html}
                    </tbody>
                </table>
            </div>
            
            {f'<div class="errors"><h2>错误信息</h2><ul>{errors_html}</ul></div>' if errors else ''}
            
        </body>
        </html>
        """

        return html_content
