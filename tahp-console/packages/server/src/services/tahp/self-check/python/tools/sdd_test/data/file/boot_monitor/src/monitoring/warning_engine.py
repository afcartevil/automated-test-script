#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
警告引擎模块

负责根据启动数据分析结果生成警告，包括：
- 警告条件判断
- 警告级别分类
- 警告消息生成
- 警告历史记录

作者: LYH
创建时间: 2025-09-02
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple
from enum import Enum
import json
from src.utils.exceptions import (
    DataValidationError,
    safe_execute,
    global_exception_handler,
    global_exception_handler_decorator,
)


class WarningLevel(Enum):
    """警告级别枚举"""

    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    ERROR = "ERROR"


class WarningType(Enum):
    """警告类型枚举"""

    EXPIRY_SOON = "EXPIRY_SOON"  # 即将过期
    EXPIRED = "EXPIRED"  # 已过期
    DATA_INVALID = "DATA_INVALID"  # 数据无效
    PARSE_ERROR = "PARSE_ERROR"  # 解析错误
    CALCULATION_ERROR = "CALCULATION_ERROR"  # 计算错误
    DEVICE_ERROR = "DEVICE_ERROR"  # 设备错误


class Warning:
    """警告对象"""

    def __init__(
        self,
        warning_type: WarningType,
        level: WarningLevel,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        timestamp: Optional[datetime] = None,
    ):
        """
        初始化警告对象

        Args:
            warning_type: 警告类型
            level: 警告级别
            message: 警告消息
            details: 详细信息
            timestamp: 时间戳
        """
        self.warning_type = warning_type
        self.level = level
        self.message = message
        self.details = details or {}
        self.timestamp = timestamp or datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "warning_type": self.warning_type.value,
            "level": self.level.value,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
        }

    def __str__(self) -> str:
        """字符串表示"""
        return f"[{self.level.value}] {self.warning_type.value}: {self.message}"


class WarningEngine:
    """
    警告引擎
    """

    def __init__(
        self, warning_threshold_days: int = 120, critical_threshold_days: int = 90
    ):
        """
        初始化警告引擎

        Args:
            warning_threshold_days: 警告阈值天数（黄色提醒）
            critical_threshold_days: 严重警告阈值天数（红色警告）
        """
        self.logger = logging.getLogger(__name__)
        self.warning_threshold_days = warning_threshold_days
        self.critical_threshold_days = critical_threshold_days
        self.warning_history: List[Warning] = []

        # 配置不同警告类型的消息模板
        self.message_templates = {
            WarningType.EXPIRY_SOON: {
                WarningLevel.WARNING: "启动证书将在 {days} 天内过期，建议尽快更新",
                WarningLevel.CRITICAL: "启动证书将在 {days} 天内过期，需要立即处理",
            },
            WarningType.EXPIRED: {
                WarningLevel.CRITICAL: "启动证书已过期 {days} 天，必须立即更新",
                WarningLevel.ERROR: "启动证书已过期，系统可能存在安全风险",
            },
            WarningType.DATA_INVALID: {
                WarningLevel.ERROR: "启动数据无效: {reason}",
                WarningLevel.WARNING: "启动数据可能不准确: {reason}",
            },
            WarningType.PARSE_ERROR: {WarningLevel.ERROR: "数据解析失败: {error}"},
            WarningType.CALCULATION_ERROR: {
                WarningLevel.ERROR: "时间计算失败: {error}"
            },
            WarningType.DEVICE_ERROR: {
                WarningLevel.ERROR: "设备连接或通信错误: {error}"
            },
        }

    def analyze_boot_data(self, boot_data: Dict[str, Any]) -> List[Warning]:
        """
        分析启动数据并生成警告

        Args:
            boot_data: 启动数据

        Returns:
            List[Warning]: 生成的警告列表
        """
        warnings = []

        try:
            # 验证数据完整性
            validation_warnings = self._validate_data_completeness(boot_data)
            warnings.extend(validation_warnings)

            # 如果数据验证失败，不继续分析
            if any(
                w.level in [WarningLevel.ERROR, WarningLevel.CRITICAL]
                for w in validation_warnings
            ):
                return warnings

            # 分析时间相关警告
            time_warnings = self._analyze_time_warnings(boot_data)
            warnings.extend(time_warnings)

            # 分析设备相关警告
            device_warnings = self._analyze_device_warnings(boot_data)
            warnings.extend(device_warnings)

            # 分析数据质量警告
            quality_warnings = self._analyze_data_quality(boot_data)
            warnings.extend(quality_warnings)

            # 记录警告历史
            self.warning_history.extend(warnings)

            # 限制历史记录长度
            if len(self.warning_history) > 1000:
                self.warning_history = self.warning_history[-500:]

            self.logger.info(f"分析完成，生成 {len(warnings)} 个警告")
            return warnings

        except DataValidationError as e:
            error_warning = Warning(
                WarningType.DATA_INVALID,
                WarningLevel.ERROR,
                e.message,
                {"error_type": type(e).__name__, "error_details": str(e)},
            )
            warnings.append(error_warning)
            global_exception_handler.handle_exception(e, "analyze_boot_data")
            return warnings
        except Exception as e:
            error_info = global_exception_handler.handle_exception(
                e, "analyze_boot_data"
            )
            error_warning = Warning(
                WarningType.CALCULATION_ERROR,
                WarningLevel.ERROR,
                f"分析启动数据时发生错误: {error_info.get('message', str(e))}",
                {"error_type": type(e).__name__, "error_details": str(e)},
            )
            warnings.append(error_warning)
            return warnings

    def _validate_data_completeness(self, boot_data: Dict[str, Any]) -> List[Warning]:
        """
        验证数据完整性

        Args:
            boot_data: 启动数据

        Returns:
            List[Warning]: 验证警告列表
        """
        warnings = []

        # 检查必需字段
        required_fields = [
            "calculation_result.remaining_days",
            "calculation_result.warning_status",
            "boot_data.raw_boot_patch_level",
            "device_info.model",
        ]

        for field_path in required_fields:
            value = self._get_nested_value(boot_data, field_path)
            if value is None:
                warnings.append(
                    Warning(
                        WarningType.DATA_INVALID,
                        WarningLevel.ERROR,
                        f"缺少必需字段: {field_path}",
                        {"missing_field": field_path},
                    )
                )

        # 检查启动补丁级别有效性
        boot_patch_level = self._get_nested_value(
            boot_data, "boot_data.raw_boot_patch_level"
        )
        if boot_patch_level == 0:
            warnings.append(
                Warning(
                    WarningType.DATA_INVALID,
                    WarningLevel.WARNING,
                    "启动补丁级别为0，可能无法获取有效的启动时间",
                    {"boot_patch_level": boot_patch_level},
                )
            )

        return warnings

    @global_exception_handler_decorator
    def _analyze_time_warnings(self, boot_data: Dict[str, Any]) -> List[Warning]:
        """
        分析时间相关警告

        Args:
            boot_data: 启动数据

        Returns:
            List[Warning]: 时间警告列表
        """
        warnings = []

        try:
            remaining_days = self._get_nested_value(
                boot_data, "calculation_result.remaining_days"
            )
            if remaining_days is None:
                return warnings

            # 已过期
            if remaining_days < 0:
                level = WarningLevel.CRITICAL
                message = self.message_templates[WarningType.EXPIRED][level].format(
                    days=abs(remaining_days)
                )
                warnings.append(
                    Warning(
                        WarningType.EXPIRED,
                        level,
                        message,
                        {
                            "remaining_days": remaining_days,
                            "expiry_date": self._get_nested_value(
                                boot_data, "calculation_result.expiry_date"
                            ),
                            "boot_date": self._get_nested_value(
                                boot_data, "calculation_result.boot_date"
                            ),
                        },
                    )
                )

            # 即将过期
            elif 0 <= remaining_days <= self.warning_threshold_days:
                if (
                    remaining_days <= self.critical_threshold_days
                ):  # 0-90天为严重警告（红色）
                    level = WarningLevel.CRITICAL
                else:  # 91-120天为一般警告（黄色）
                    level = WarningLevel.WARNING

                message = self.message_templates[WarningType.EXPIRY_SOON][level].format(
                    days=remaining_days
                )
                warnings.append(
                    Warning(
                        WarningType.EXPIRY_SOON,
                        level,
                        message,
                        {
                            "remaining_days": remaining_days,
                            "warning_threshold": self.warning_threshold_days,
                            "critical_threshold": self.critical_threshold_days,
                            "expiry_date": self._get_nested_value(
                                boot_data, "calculation_result.expiry_date"
                            ),
                        },
                    )
                )

            return warnings

        except Exception as e:
            error_info = global_exception_handler.handle_exception(
                e, "analyze_time_warnings"
            )
            return [
                Warning(
                    WarningType.CALCULATION_ERROR,
                    WarningLevel.ERROR,
                    f"时间分析失败: {error_info.get('message', str(e))}",
                    {"error_details": str(e)},
                )
            ]

    @global_exception_handler_decorator
    def _analyze_device_warnings(self, boot_data: Dict[str, Any]) -> List[Warning]:
        """
        分析设备相关警告

        Args:
            boot_data: 启动数据

        Returns:
            List[Warning]: 设备警告列表
        """
        warnings = []

        try:
            # 检查设备信息
            device_model = self._get_nested_value(boot_data, "device_info.model")
            device_brand = self._get_nested_value(boot_data, "device_info.brand")
            sdk_version = self._get_nested_value(boot_data, "device_info.sdk_version")

            # SDK版本检查
            if sdk_version and sdk_version < 23:  # Android 6.0以下
                warnings.append(
                    Warning(
                        WarningType.DEVICE_ERROR,
                        WarningLevel.WARNING,
                        f"设备Android版本较低 (SDK {sdk_version})，可能影响数据准确性",
                        {
                            "sdk_version": sdk_version,
                            "device_model": device_model,
                            "device_brand": device_brand,
                        },
                    )
                )

            # 设备信息缺失检查
            if not device_model or device_model.strip() == "":
                warnings.append(
                    Warning(
                        WarningType.DATA_INVALID,
                        WarningLevel.WARNING,
                        "设备型号信息缺失",
                        {"device_info": boot_data.get("device_info", {})},
                    )
                )

            return warnings

        except Exception as e:
            error_info = global_exception_handler.handle_exception(
                e, "analyze_device_warnings"
            )
            return [
                Warning(
                    WarningType.DEVICE_ERROR,
                    WarningLevel.ERROR,
                    f"设备分析失败: {error_info.get('message', str(e))}",
                    {"error_details": str(e)},
                )
            ]

    @global_exception_handler_decorator
    def _analyze_data_quality(self, boot_data: Dict[str, Any]) -> List[Warning]:
        """
        分析数据质量警告

        Args:
            boot_data: 启动数据

        Returns:
            List[Warning]: 数据质量警告列表
        """
        warnings = []

        try:
            # 检查时间戳新鲜度
            timestamp_str = boot_data.get("timestamp")
            if timestamp_str:
                try:
                    timestamp = datetime.fromisoformat(
                        timestamp_str.replace("Z", "+00:00")
                    )
                    now = datetime.now(timezone.utc)
                    age_hours = (now - timestamp).total_seconds() / 3600

                    if age_hours > 24:  # 数据超过24小时
                        warnings.append(
                            Warning(
                                WarningType.DATA_INVALID,
                                WarningLevel.WARNING,
                                f"启动数据较旧 ({age_hours:.1f} 小时前)，可能不是最新状态",
                                {
                                    "data_timestamp": timestamp_str,
                                    "age_hours": age_hours,
                                },
                            )
                        )
                except ValueError:
                    warnings.append(
                        Warning(
                            WarningType.DATA_INVALID,
                            WarningLevel.WARNING,
                            f"时间戳格式无效: {timestamp_str}",
                            {"invalid_timestamp": timestamp_str},
                        )
                    )

            # 检查补丁级别一致性
            boot_patch = self._get_nested_value(
                boot_data, "boot_data.raw_boot_patch_level"
            )
            vendor_patch = self._get_nested_value(
                boot_data, "boot_data.raw_vendor_patch_level"
            )

            if boot_patch and vendor_patch and boot_patch != 0 and vendor_patch != 0:
                # 如果两个补丁级别差异很大，可能有问题
                if abs(boot_patch - vendor_patch) > 100:  # 简单的差异检查
                    warnings.append(
                        Warning(
                            WarningType.DATA_INVALID,
                            WarningLevel.INFO,
                            f"启动补丁级别与供应商补丁级别差异较大",
                            {
                                "boot_patch_level": boot_patch,
                                "vendor_patch_level": vendor_patch,
                                "difference": abs(boot_patch - vendor_patch),
                            },
                        )
                    )

            return warnings

        except Exception as e:
            error_info = global_exception_handler.handle_exception(
                e, "analyze_data_quality"
            )
            return [
                Warning(
                    WarningType.DATA_INVALID,
                    WarningLevel.ERROR,
                    f"数据质量分析失败: {error_info.get('message', str(e))}",
                    {"error_details": str(e)},
                )
            ]

    def _get_nested_value(self, data: Dict[str, Any], path: str) -> Any:
        """
        获取嵌套字典中的值

        Args:
            data: 数据字典
            path: 路径，用点分隔（如 'a.b.c'）

        Returns:
            Any: 值，如果路径不存在则返回None
        """
        try:
            keys = path.split(".")
            value = data
            for key in keys:
                if isinstance(value, dict) and key in value:
                    value = value[key]
                else:
                    return None
            return value
        except (KeyError, TypeError):
            return None

    def get_warning_summary(self, warnings: List[Warning]) -> Dict[str, Any]:
        """
        获取警告摘要

        Args:
            warnings: 警告列表

        Returns:
            Dict[str, Any]: 警告摘要
        """
        if not warnings:
            return {
                "total_warnings": 0,
                "has_critical": False,
                "has_errors": False,
                "summary": "无警告",
                "recommendation": "系统状态正常",
            }

        # 统计各级别警告数量
        level_counts = {level.value: 0 for level in WarningLevel}
        type_counts = {wtype.value: 0 for wtype in WarningType}

        for warning in warnings:
            level_counts[warning.level.value] += 1
            type_counts[warning.warning_type.value] += 1

        # 判断最高严重级别
        has_critical = level_counts[WarningLevel.CRITICAL.value] > 0
        has_errors = level_counts[WarningLevel.ERROR.value] > 0

        # 生成摘要和建议
        summary, recommendation = self._generate_summary_and_recommendation(
            warnings, level_counts, type_counts
        )

        return {
            "total_warnings": len(warnings),
            "level_counts": level_counts,
            "type_counts": type_counts,
            "has_critical": has_critical,
            "has_errors": has_errors,
            "summary": summary,
            "recommendation": recommendation,
            "warnings": [w.to_dict() for w in warnings],
        }

    def _generate_summary_and_recommendation(
        self,
        warnings: List[Warning],
        level_counts: Dict[str, int],
        type_counts: Dict[str, int],
    ) -> Tuple[str, str]:
        """
        生成摘要和建议

        Args:
            warnings: 警告列表
            level_counts: 级别统计
            type_counts: 类型统计

        Returns:
            Tuple[str, str]: (摘要, 建议)
        """
        # 生成摘要
        summary_parts = []
        if level_counts[WarningLevel.CRITICAL.value] > 0:
            summary_parts.append(
                f"{level_counts[WarningLevel.CRITICAL.value]}个严重警告"
            )
        if level_counts[WarningLevel.ERROR.value] > 0:
            summary_parts.append(f"{level_counts[WarningLevel.ERROR.value]}个错误")
        if level_counts[WarningLevel.WARNING.value] > 0:
            summary_parts.append(f"{level_counts[WarningLevel.WARNING.value]}个警告")
        if level_counts[WarningLevel.INFO.value] > 0:
            summary_parts.append(f"{level_counts[WarningLevel.INFO.value]}个信息")

        summary = "发现 " + "、".join(summary_parts)

        # 生成建议
        if type_counts[WarningType.EXPIRED.value] > 0:
            recommendation = "证书已过期，必须立即更新系统或重新刷机"
        elif type_counts[WarningType.EXPIRY_SOON.value] > 0:
            recommendation = "证书即将过期，建议尽快更新系统"
        elif level_counts[WarningLevel.ERROR.value] > 0:
            recommendation = "存在数据或系统错误，建议检查设备状态和连接"
        elif level_counts[WarningLevel.WARNING.value] > 0:
            recommendation = "存在潜在问题，建议关注并考虑采取预防措施"
        else:
            recommendation = "系统状态良好，继续监控"

        return summary, recommendation

    def export_warnings_to_json(
        self, warnings: List[Warning], include_summary: bool = True
    ) -> str:
        """
        导出警告为JSON格式

        Args:
            warnings: 警告列表
            include_summary: 是否包含摘要

        Returns:
            str: JSON字符串
        """
        data = {
            "export_timestamp": datetime.now(timezone.utc).isoformat(),
            "warnings": [w.to_dict() for w in warnings],
        }

        if include_summary:
            data["summary"] = self.get_warning_summary(warnings)

        return json.dumps(data, indent=2, ensure_ascii=False)

    def clear_warning_history(self):
        """清除警告历史"""
        self.warning_history.clear()
        self.logger.info("警告历史已清除")

    def get_recent_warnings(self, hours: int = 24) -> List[Warning]:
        """
        获取最近的警告

        Args:
            hours: 小时数

        Returns:
            List[Warning]: 最近的警告列表
        """
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
        return [w for w in self.warning_history if w.timestamp >= cutoff_time]
