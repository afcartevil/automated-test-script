#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据解析模块

负责解析从Android设备获取的启动数据，包括：
- JSON数据验证和解析
- 数据格式检查
- 异常数据处理
- 数据结构标准化

作者: LYH
创建时间: 2025-09-02
"""

import json
import logging
from typing import Dict, Any, Optional, List, Union
from datetime import datetime, timezone
import re
from src.utils.exceptions import (
    DataParsingError,
    ConfigurationError,
    safe_execute,
    global_exception_handler_decorator,
)


class DataValidationError(Exception):
    """数据验证异常"""

    pass


class BootDataParser:
    """
    启动数据解析器
    """

    def __init__(self):
        """
        初始化数据解析器
        """
        self.logger = logging.getLogger(__name__)

        # 定义必需的字段
        self.required_fields = {
            "timestamp": (str, int),  # 支持字符串和整数时间戳
            "device_info": dict,
            "boot_data": dict,
            "calculation_result": dict,
        }

        # 定义设备信息必需字段
        self.device_info_fields = {"model": str, "brand": str, "sdk_version": int}

        # 定义启动数据必需字段
        self.boot_data_fields = {
            "raw_boot_patch_level": int,
            "raw_vendor_patch_level": int,
            "formatted_boot_patch_level": str,
            "formatted_vendor_patch_level": str,
        }

        # 定义计算结果必需字段
        # 注意：boot_date相关字段允许为None，表示BOOT证书失效
        self.calculation_result_fields = {
            "rom_build_time": str,
            "rom_build_time_millis": int,
            "boot_date": (str, type(None)),  # 允许None，表示BOOT证书失效
            "boot_date_millis": (int, type(None)),  # 允许None，表示BOOT证书失效
            "expiry_date": (str, type(None)),  # 允许None，表示BOOT证书失效
            "expiry_date_millis": (int, type(None)),  # 允许None，表示BOOT证书失效
            "remaining_days": int,
            "is_expired": bool,
            "warning_status": bool,
            "warning_threshold": int,
            "boot_cert_status": str,  # 新增字段：BOOT证书状态
        }

    @global_exception_handler_decorator
    def parse_json_data(self, json_str: str) -> Dict[str, Any]:
        """
        解析JSON字符串

        Args:
            json_str: JSON字符串

        Returns:
            Dict[str, Any]: 解析后的数据

        Raises:
            DataParsingError: 数据解析或验证失败
        """
        try:
            # 解析JSON
            data = json.loads(json_str)

            # 先标准化数据（字段名映射）
            normalized_data = self.normalize_data(data)

            # 然后验证数据结构
            self.validate_data_structure(normalized_data)

            self.logger.debug("JSON数据解析成功")
            return normalized_data

        except json.JSONDecodeError as e:
            raise DataParsingError(f"JSON解析失败: {e}")
        except DataValidationError as e:
            raise DataParsingError(f"数据验证失败: {e}")
        except Exception as e:
            raise DataParsingError(f"数据解析时发生未知错误: {e}")

    def validate_data_structure(self, data: Dict[str, Any]) -> bool:
        """
        验证数据结构

        Args:
            data: 要验证的数据

        Returns:
            bool: 验证是否成功

        Raises:
            DataValidationError: 数据结构验证失败
        """
        # 检查顶级字段
        self._validate_fields(data, self.required_fields, "根级别")

        # 检查设备信息字段
        self._validate_fields(
            data["device_info"], self.device_info_fields, "device_info"
        )

        # 检查启动数据字段
        self._validate_fields(data["boot_data"], self.boot_data_fields, "boot_data")

        # 检查计算结果字段
        self._validate_fields(
            data["calculation_result"],
            self.calculation_result_fields,
            "calculation_result",
        )

        # 验证特定字段的值
        self._validate_field_values(data)

        return True

    def _validate_fields(
        self, data: Dict[str, Any], required_fields: Dict[str, Any], section_name: str
    ) -> None:
        """
        验证字段存在性和类型

        Args:
            data: 要验证的数据
            required_fields: 必需字段及其类型
            section_name: 节名称（用于错误消息）

        Raises:
            DataValidationError: 字段验证失败
        """
        for field_name, field_type in required_fields.items():
            if field_name not in data:
                raise DataValidationError(f"{section_name}缺少必需字段: {field_name}")

            # 支持多种类型验证
            if isinstance(field_type, tuple):
                if not isinstance(data[field_name], field_type):
                    type_names = [t.__name__ for t in field_type]
                    raise DataValidationError(
                        f"{section_name}字段类型错误: {field_name} 应为 {' 或 '.join(type_names)}, "
                        f"实际为 {type(data[field_name]).__name__}"
                    )
            else:
                if not isinstance(data[field_name], field_type):
                    raise DataValidationError(
                        f"{section_name}字段类型错误: {field_name} 应为 {field_type.__name__}, "
                        f"实际为 {type(data[field_name]).__name__}"
                    )

    def _validate_field_values(self, data: Dict[str, Any]) -> None:
        """
        验证特定字段的值

        Args:
            data: 要验证的数据

        Raises:
            DataValidationError: 字段值验证失败
        """
        # 验证时间戳格式
        timestamp = data["timestamp"]
        if isinstance(timestamp, int):
            # 整数时间戳，验证范围合理性
            if timestamp < 0 or timestamp > 2147483647:  # Unix时间戳范围
                raise DataValidationError(f"整数时间戳超出有效范围: {timestamp}")
        elif isinstance(timestamp, str):
            # 字符串时间戳，验证ISO格式
            try:
                datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            except ValueError:
                raise DataValidationError(f"时间戳格式无效: {timestamp}")
        else:
            raise DataValidationError(f"时间戳类型无效: {type(timestamp).__name__}")

        # 验证SDK版本范围
        sdk_version = data["device_info"]["sdk_version"]
        if not (21 <= sdk_version <= 35):  # Android 5.0 到未来版本
            self.logger.warning(f"SDK版本超出预期范围: {sdk_version}")

        # 验证补丁级别格式
        boot_patch = data["boot_data"]["raw_boot_patch_level"]
        vendor_patch = data["boot_data"]["raw_vendor_patch_level"]

        if boot_patch != 0 and not self._is_valid_patch_level(boot_patch):
            self.logger.warning(f"启动补丁级别格式可能无效: {boot_patch}")

        if vendor_patch != 0 and not self._is_valid_patch_level(vendor_patch):
            self.logger.warning(f"供应商补丁级别格式可能无效: {vendor_patch}")

        # 验证剩余天数合理性
        remaining_days = data["calculation_result"]["remaining_days"]
        if remaining_days < -365 or remaining_days > 730:  # 允许-1年到+2年的范围
            self.logger.warning(f"剩余天数超出预期范围: {remaining_days}")

        # 验证警告状态逻辑
        warning_status = data["calculation_result"]["warning_status"]
        expected_warning = remaining_days >= 0 and remaining_days <= 90
        if warning_status != expected_warning:
            self.logger.warning(
                f"警告状态与剩余天数不匹配: warning_status={warning_status}, "
                f"remaining_days={remaining_days}"
            )

    def _is_valid_patch_level(self, patch_level: int) -> bool:
        """
        验证补丁级别格式是否有效

        Args:
            patch_level: 补丁级别

        Returns:
            bool: 是否有效
        """
        patch_str = str(patch_level)

        # YYYYMM格式 (6位数)
        if len(patch_str) == 6:
            year = int(patch_str[:4])
            month = int(patch_str[4:6])
            return 2020 <= year <= 2030 and 1 <= month <= 12

        # YYYYMMDD格式 (8位数)
        elif len(patch_str) == 8:
            year = int(patch_str[:4])
            month = int(patch_str[4:6])
            day = int(patch_str[6:8])
            return 2020 <= year <= 2030 and 1 <= month <= 12 and 1 <= day <= 31

        # 其他格式（可能是十六进制或其他编码）
        else:
            return patch_level > 0

    @global_exception_handler_decorator
    def normalize_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        标准化数据格式

        Args:
            data: 原始数据

        Returns:
            Dict[str, Any]: 标准化后的数据
        """
        normalized = data.copy()

        # 字段名映射：将驼峰命名转换为下划线命名
        field_mapping = {
            "deviceInfo": "device_info",
            "bootData": "boot_data",
            "calculationResult": "calculation_result",
        }

        # 应用字段名映射
        for old_name, new_name in field_mapping.items():
            if old_name in normalized:
                normalized[new_name] = normalized.pop(old_name)
                self.logger.debug(f"字段映射: {old_name} -> {new_name}")

        # 调试：打印映射后的顶级字段
        self.logger.debug(f"映射后的顶级字段: {list(normalized.keys())}")

        # 映射嵌套字段名
        if "device_info" in normalized:
            device_mapping = {
                "sdkVersion": "sdk_version",
                "androidVersion": "android_version",
            }
            device_info = normalized["device_info"]
            for old_name, new_name in device_mapping.items():
                if old_name in device_info:
                    device_info[new_name] = device_info.pop(old_name)
                    self.logger.debug(f"设备信息字段映射: {old_name} -> {new_name}")

        # 映射boot_data字段名
        if "boot_data" in normalized:
            boot_mapping = {
                "bootPatchLevelRaw": "raw_boot_patch_level",
                "vendorPatchLevelRaw": "raw_vendor_patch_level",
                "bootPatchLevelFormatted": "formatted_boot_patch_level",
                "vendorPatchLevelFormatted": "formatted_vendor_patch_level",
            }
            boot_data = normalized["boot_data"]
            for old_name, new_name in boot_mapping.items():
                if old_name in boot_data:
                    boot_data[new_name] = boot_data.pop(old_name)

        # 映射calculation_result字段名
        if "calculation_result" in normalized:
            calc_mapping = {
                "bootExpiryDate": "expiry_date",
                "needsWarning": "warning_status",
                "romBuildTime": "rom_build_time",
                "romBuildTimeMillis": "rom_build_time_millis",
                "bootDate": "boot_date",
                "bootDateMillis": "boot_date_millis",
                "bootExpiryDateMillis": "expiry_date_millis",
                "remainingDays": "remaining_days",
                "isExpired": "is_expired",
                "warningThreshold": "warning_threshold",
            }
            calc_result = normalized["calculation_result"]
            for old_name, new_name in calc_mapping.items():
                if old_name in calc_result:
                    old_value = calc_result[old_name]
                    calc_result[new_name] = calc_result.pop(old_name)
                    self.logger.debug(
                        f"计算结果字段映射: {old_name} -> {new_name}, 值: {old_value} (类型: {type(old_value).__name__})"
                    )

            # 检测并处理BOOT证书失效情况
            boot_date = calc_result.get("boot_date")
            if boot_date is None:
                # BOOT证书失效，设置相应状态
                calc_result["boot_cert_status"] = "INVALID"
                self.logger.warning("检测到BOOT证书失效：boot_date为None")

                # 确保相关字段也为None以保持一致性
                if calc_result.get("boot_date_millis") is None:
                    calc_result["boot_date_millis"] = None
                if calc_result.get("expiry_date") is None:
                    calc_result["expiry_date"] = None
                if calc_result.get("expiry_date_millis") is None:
                    calc_result["expiry_date_millis"] = None
            else:
                # BOOT证书有效
                calc_result["boot_cert_status"] = "VALID"
                self.logger.debug(f"BOOT证书有效：boot_date={boot_date}")

        # 标准化时间戳格式
        try:
            timestamp = normalized["timestamp"]
            if isinstance(timestamp, int):
                # 整数时间戳，转换为ISO格式
                dt = datetime.fromtimestamp(
                    timestamp / 1000, tz=timezone.utc
                )  # 假设是毫秒时间戳
                normalized["timestamp"] = dt.isoformat().replace("+00:00", "Z")
            elif isinstance(timestamp, str):
                if timestamp.endswith("Z"):
                    # 已经是UTC格式，保持不变
                    pass
                elif "+" in timestamp or "-" in timestamp[-6:]:
                    # 包含时区信息，转换为UTC
                    dt = datetime.fromisoformat(timestamp)
                    normalized["timestamp"] = dt.isoformat() + "Z"
                else:
                    # 假设是本地时间，添加Z后缀
                    if not timestamp.endswith("Z"):
                        normalized["timestamp"] = timestamp + "Z"
        except Exception as e:
            raise DataParsingError(f"时间戳转换失败: {e}, 原始值: {timestamp}")

        # 标准化设备信息
        if "device_info" in normalized:
            device_info = normalized["device_info"]
            if "model" in device_info:
                device_info["model"] = device_info["model"].strip()
            if "brand" in device_info:
                device_info["brand"] = device_info["brand"].strip().lower()

        # 标准化格式化的补丁级别
        if "boot_data" in normalized:
            boot_data = normalized["boot_data"]
            if "formatted_boot_patch_level" in boot_data:
                boot_data["formatted_boot_patch_level"] = self._normalize_patch_format(
                    boot_data["formatted_boot_patch_level"]
                )
            if "formatted_vendor_patch_level" in boot_data:
                boot_data["formatted_vendor_patch_level"] = (
                    self._normalize_patch_format(
                        boot_data["formatted_vendor_patch_level"]
                    )
                )

        return normalized

    def _normalize_patch_format(self, patch_str: str) -> str:
        """
        标准化补丁级别格式

        Args:
            patch_str: 补丁级别字符串

        Returns:
            str: 标准化后的格式
        """
        if not patch_str or patch_str in ["未知", "Unknown", "0"]:
            return "未知"

        # 移除多余的空格
        patch_str = patch_str.strip()

        # 标准化日期格式 (YYYY-MM 或 YYYY-MM-DD)
        if re.match(r"^\d{4}-\d{2}$", patch_str):
            return patch_str  # 已经是标准格式
        elif re.match(r"^\d{4}-\d{2}-\d{2}$", patch_str):
            return patch_str  # 已经是标准格式
        elif re.match(r"^\d{6}$", patch_str):
            # YYYYMM格式，转换为YYYY-MM
            return f"{patch_str[:4]}-{patch_str[4:6]}"
        elif re.match(r"^\d{8}$", patch_str):
            # YYYYMMDD格式，转换为YYYY-MM-DD
            return f"{patch_str[:4]}-{patch_str[4:6]}-{patch_str[6:8]}"
        else:
            # 其他格式，保持原样
            return patch_str

    def extract_boot_info(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        提取关键的启动信息

        Args:
            data: 解析后的数据

        Returns:
            Dict[str, Any]: 提取的启动信息
        """
        calc_result = data["calculation_result"]
        boot_info = {
            "timestamp": data["timestamp"],
            "device_model": data["device_info"]["model"],
            "device_brand": data["device_info"]["brand"],
            "boot_patch_level": data["boot_data"]["raw_boot_patch_level"],
            "vendor_patch_level": data["boot_data"]["raw_vendor_patch_level"],
            "formatted_boot_patch": data["boot_data"]["formatted_boot_patch_level"],
            "formatted_vendor_patch": data["boot_data"]["formatted_vendor_patch_level"],
            "remaining_days": calc_result["remaining_days"],
            "warning_status": calc_result["warning_status"],
            "boot_cert_status": calc_result["boot_cert_status"],  # 新增BOOT证书状态
        }

        # 根据BOOT证书状态处理相关字段
        if calc_result["boot_cert_status"] == "VALID":
            boot_info["boot_date"] = calc_result["boot_date"]
            boot_info["expiry_date"] = calc_result["expiry_date"]
        else:
            # BOOT证书失效时，这些字段为None或提供默认值
            boot_info["boot_date"] = None
            boot_info["expiry_date"] = None

        return boot_info

    @global_exception_handler_decorator
    def parse_multiple_entries(self, json_lines: List[str]) -> List[Dict[str, Any]]:
        """
        解析多个JSON条目

        Args:
            json_lines: JSON字符串列表

        Returns:
            List[Dict[str, Any]]: 解析成功的数据列表
        """
        parsed_data = []
        errors = []

        for i, line in enumerate(json_lines):
            try:
                data = self.parse_json_data(line)
                parsed_data.append(data)
            except (DataParsingError, DataValidationError) as e:
                error_info = {
                    "line_number": i + 1,
                    "error": str(e),
                    "raw_data": line[:200] + "..." if len(line) > 200 else line,
                }
                errors.append(error_info)
                self.logger.error(f"第{i+1}行解析失败: {e}")

        if errors:
            self.logger.warning(
                f"共{len(errors)}行解析失败，成功解析{len(parsed_data)}行"
            )

        return parsed_data

    @global_exception_handler_decorator
    def parse_boot_data(self, raw_data: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
        """
        解析BOOT证书数据

        Args:
            raw_data: 原始数据，可以是JSON字符串或字典

        Returns:
            Dict[str, Any]: 解析后的BOOT数据，包含证书状态信息

        Raises:
            DataParsingError: 数据解析失败
        """
        try:
            # 如果是字符串，先解析为字典
            if isinstance(raw_data, str):
                data = self.parse_json_data(raw_data)
            elif isinstance(raw_data, dict):
                # 如果已经是字典，进行标准化和验证
                data = self.normalize_data(raw_data)
                self.validate_data_structure(data)
            else:
                raise DataParsingError(f"不支持的数据类型: {type(raw_data).__name__}")

            # 提取BOOT相关信息
            boot_info = self.extract_boot_info(data)

            # 构建返回结果
            result = {
                "success": True,
                "data": data,
                "boot_info": boot_info,
                "cert_status": data["calculation_result"]["boot_cert_status"],
                "error": None,
            }

            # 如果BOOT证书失效，添加失效信息
            if data["calculation_result"]["boot_cert_status"] == "INVALID":
                result["cert_invalid_reason"] = "BOOT证书解析失败，boot_date为None"
                self.logger.warning("BOOT证书解析结果：证书失效")
            else:
                self.logger.info("BOOT证书解析结果：证书有效")

            return result

        except (DataParsingError, DataValidationError) as e:
            # 数据解析或验证失败，返回失败结果但不抛出异常
            error_msg = f"BOOT证书解析失败: {e}"
            self.logger.error(error_msg)

            return {
                "success": False,
                "data": None,
                "boot_info": None,
                "cert_status": "INVALID",
                "cert_invalid_reason": error_msg,
                "error": str(e),
            }
        except Exception as e:
            # 其他未知错误
            error_msg = f"BOOT证书解析时发生未知错误: {e}"
            self.logger.error(error_msg)

            return {
                "success": False,
                "data": None,
                "boot_info": None,
                "cert_status": "INVALID",
                "cert_invalid_reason": error_msg,
                "error": str(e),
            }

    @global_exception_handler_decorator
    def get_latest_entry(
        self, parsed_data: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """
        获取最新的数据条目

        Args:
            parsed_data: 解析后的数据列表

        Returns:
            Optional[Dict[str, Any]]: 最新的数据条目，如果列表为空则返回None
        """
        if not parsed_data:
            return None

        # 按时间戳排序，获取最新的
        try:
            sorted_data = sorted(
                parsed_data,
                key=lambda x: datetime.fromisoformat(
                    x["timestamp"].replace("Z", "+00:00")
                ),
                reverse=True,
            )
            return sorted_data[0]
        except (ValueError, KeyError) as e:
            raise DataParsingError(f"排序数据时发生错误: {e}")
        except Exception as e:
            raise DataParsingError(f"获取最新条目时发生未知错误: {e}")
