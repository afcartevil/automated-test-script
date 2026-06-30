#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置管理模块

负责管理监控系统的配置，包括：
- 配置文件加载和保存
- 配置验证
- 默认配置管理
- 环境变量支持
- 配置热更新

作者: LYH
创建时间: 2025-09-02
"""

import logging
import json
import os
from pathlib import Path
from typing import Dict, Any, Optional, Union
from dataclasses import dataclass, asdict
import yaml
from datetime import datetime
from src.utils.exceptions import (
    ConfigurationError,
    safe_execute,
    global_exception_handler,
)


@dataclass
class MonitorConfig:
    """
    监控配置数据类
    """

    # ADB配置
    adb_timeout: int = 300  # 增加到5分钟
    adb_retry_count: int = 3
    adb_retry_delay: float = 1.0

    # 日志监控配置
    logcat_tag: str = "BootDataExport"
    logcat_timeout: int = 1800  # 增加到30分钟
    logcat_buffer_size: int = 1000

    # 警告配置
    warning_threshold_days: int = 90
    critical_threshold_days: int = 30

    # 报告配置
    report_output_dir: str = "output/reports"
    report_format: str = "html"  # html, json, txt
    auto_generate_report: bool = True

    # 监控配置
    monitor_interval: int = 300  # 秒，调整为5分钟提高检查频率
    max_retry_attempts: int = 5
    enable_continuous_monitoring: bool = False

    # 数据存储配置
    data_retention_days: int = 30
    max_history_records: int = 1000

    # 通知配置
    enable_notifications: bool = False
    notification_email: Optional[str] = None
    notification_webhook: Optional[str] = None

    # 调试配置
    debug_mode: bool = False
    log_level: str = "INFO"
    save_raw_data: bool = False


class ConfigManager:
    """
    配置管理器
    """

    def __init__(self, config_file: Optional[str] = None):
        """
        初始化配置管理器

        Args:
            config_file: 配置文件路径
        """
        self.logger = logging.getLogger(__name__)

        # 默认配置文件路径
        if config_file is None:
            config_file = "config.yaml"

        self.config_file = Path(config_file)
        self.config = MonitorConfig()

        # 支持的配置文件格式
        self.supported_formats = {
            ".yaml": self._load_yaml,
            ".yml": self._load_yaml,
            ".json": self._load_json,
        }

        # 加载配置
        self.load_config()

    def load_config(self) -> bool:
        """
        加载配置文件

        Returns:
            bool: 是否成功加载
        """
        try:
            # 如果配置文件不存在，创建默认配置
            if not self.config_file.exists():
                self.logger.info(f"配置文件不存在，创建默认配置: {self.config_file}")
                self.save_config()
                return True

            # 根据文件扩展名选择加载方法
            file_ext = self.config_file.suffix.lower()
            if file_ext not in self.supported_formats:
                raise ConfigurationError(
                    f"不支持的配置文件格式: {file_ext}",
                    config_key=str(self.config_file),
                )

            # 加载配置数据
            config_data = self.supported_formats[file_ext](self.config_file)

            # 验证和应用配置
            if self._validate_config(config_data):
                self._apply_config(config_data)
                self.logger.info(f"配置文件加载成功: {self.config_file}")
                return True
            else:
                raise ConfigurationError(
                    "配置验证失败", config_key=str(self.config_file)
                )

        except ConfigurationError:
            raise
        except FileNotFoundError:
            raise ConfigurationError(
                f"配置文件不存在: {self.config_file}", config_key=str(self.config_file)
            )
        except PermissionError:
            raise ConfigurationError(
                f"没有权限读取配置文件: {self.config_file}",
                config_key=str(self.config_file),
            )
        except Exception as e:
            global_exception_handler.handle_exception(e, "load_config")
            return False

    def save_config(self) -> bool:
        """
        保存配置到文件

        Returns:
            bool: 是否成功保存
        """
        try:
            # 确保目录存在
            self.config_file.parent.mkdir(parents=True, exist_ok=True)

            # 转换为字典
            config_data = asdict(self.config)

            # 添加元数据
            config_data["_metadata"] = {
                "created_at": datetime.now().isoformat(),
                "version": "1.0",
                "description": "Android启动证书监控系统配置文件",
            }

            # 根据文件扩展名选择保存方法
            file_ext = self.config_file.suffix.lower()
            if file_ext in [".yaml", ".yml"]:
                self._save_yaml(self.config_file, config_data)
            elif file_ext == ".json":
                self._save_json(self.config_file, config_data)
            else:
                # 默认使用YAML格式
                self.config_file = self.config_file.with_suffix(".yaml")
                self._save_yaml(self.config_file, config_data)

            self.logger.info(f"配置文件保存成功: {self.config_file}")
            return True

        except PermissionError:
            raise ConfigurationError(
                f"没有权限写入配置文件: {self.config_file}",
                config_key=str(self.config_file),
            )
        except OSError as e:
            raise ConfigurationError(
                f"保存配置文件时发生系统错误: {e}", config_key=str(self.config_file)
            )
        except Exception as e:
            global_exception_handler.handle_exception(e, "save_config")
            return False

    def _load_yaml(self, file_path: Path) -> Dict[str, Any]:
        """
        加载YAML配置文件

        Args:
            file_path: 文件路径

        Returns:
            Dict[str, Any]: 配置数据
        """
        try:
            import yaml

            with open(file_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except ImportError:
            self.logger.error("PyYAML未安装，无法加载YAML配置文件")
            raise
        except Exception as e:
            self.logger.error(f"加载YAML文件失败: {e}")
            raise

    def _load_json(self, file_path: Path) -> Dict[str, Any]:
        """
        加载JSON配置文件

        Args:
            file_path: 文件路径

        Returns:
            Dict[str, Any]: 配置数据
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"加载JSON文件失败: {e}")
            raise

    def _save_yaml(self, file_path: Path, data: Dict[str, Any]) -> None:
        """
        保存YAML配置文件

        Args:
            file_path: 文件路径
            data: 配置数据
        """
        try:
            import yaml

            with open(file_path, "w", encoding="utf-8") as f:
                yaml.dump(
                    data, f, default_flow_style=False, allow_unicode=True, indent=2
                )
        except ImportError:
            self.logger.warning("PyYAML未安装，改用JSON格式保存")
            self._save_json(file_path.with_suffix(".json"), data)
        except Exception as e:
            self.logger.error(f"保存YAML文件失败: {e}")
            raise

    def _save_json(self, file_path: Path, data: Dict[str, Any]) -> None:
        """
        保存JSON配置文件

        Args:
            file_path: 文件路径
            data: 配置数据
        """
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.logger.error(f"保存JSON文件失败: {e}")
            raise

    def _validate_config(self, config_data: Dict[str, Any]) -> bool:
        """
        验证配置数据

        Args:
            config_data: 配置数据

        Returns:
            bool: 是否有效
        """
        try:
            # 移除元数据
            config_data = config_data.copy()
            config_data.pop("_metadata", None)

            # 验证必需的配置项
            validation_rules = {
                "adb_timeout": (int, lambda x: 1 <= x <= 300),
                "adb_retry_count": (int, lambda x: 1 <= x <= 10),
                "adb_retry_delay": ((int, float), lambda x: 0.1 <= x <= 10.0),
                "logcat_timeout": (int, lambda x: 10 <= x <= 3600),
                "logcat_buffer_size": (int, lambda x: 100 <= x <= 10000),
                "warning_threshold_days": (int, lambda x: 1 <= x <= 365),
                "critical_threshold_days": (int, lambda x: 1 <= x <= 90),
                "monitor_interval": (int, lambda x: 60 <= x <= 86400),
                "max_retry_attempts": (int, lambda x: 1 <= x <= 20),
                "data_retention_days": (int, lambda x: 1 <= x <= 365),
                "max_history_records": (int, lambda x: 100 <= x <= 10000),
                "log_level": (
                    str,
                    lambda x: x.upper()
                    in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                ),
                "report_format": (str, lambda x: x.lower() in ["html", "json", "txt"]),
            }

            for key, (expected_type, validator) in validation_rules.items():
                if key in config_data:
                    value = config_data[key]

                    # 类型检查
                    if not isinstance(value, expected_type):
                        raise ConfigurationError(
                            f"配置项 {key} 类型错误: 期望 {expected_type}, 实际 {type(value)}",
                            config_key=key,
                        )

                    # 值验证
                    if not validator(value):
                        raise ConfigurationError(
                            f"配置项 {key} 值无效: {value}", config_key=key
                        )

            # 逻辑验证
            if (
                "critical_threshold_days" in config_data
                and "warning_threshold_days" in config_data
            ):
                if (
                    config_data["critical_threshold_days"]
                    >= config_data["warning_threshold_days"]
                ):
                    raise ConfigurationError(
                        "critical_threshold_days 必须小于 warning_threshold_days",
                        config_key="threshold_validation",
                    )

            return True

        except ConfigurationError:
            raise
        except Exception as e:
            global_exception_handler.handle_exception(e, "_validate_config")
            return False

    def _apply_config(self, config_data: Dict[str, Any]) -> None:
        """
        应用配置数据

        Args:
            config_data: 配置数据
        """
        # 移除元数据
        config_data = config_data.copy()
        config_data.pop("_metadata", None)

        # 更新配置对象
        for key, value in config_data.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
                self.logger.debug(f"应用配置: {key} = {value}")
            else:
                self.logger.warning(f"未知配置项: {key}")

    def get_config(self) -> MonitorConfig:
        """
        获取当前配置

        Returns:
            MonitorConfig: 配置对象
        """
        return self.config

    def update_config(self, **kwargs) -> bool:
        """
        更新配置

        Args:
            **kwargs: 配置项

        Returns:
            bool: 是否成功更新
        """
        try:
            # 验证更新的配置
            if not self._validate_config(kwargs):
                return False

            # 应用更新
            for key, value in kwargs.items():
                if hasattr(self.config, key):
                    old_value = getattr(self.config, key)
                    setattr(self.config, key, value)
                    self.logger.info(f"配置更新: {key} = {old_value} -> {value}")
                else:
                    self.logger.warning(f"未知配置项: {key}")

            return True

        except Exception as e:
            self.logger.error(f"更新配置时发生错误: {e}")
            return False

    def reset_to_default(self) -> None:
        """
        重置为默认配置
        """
        self.config = MonitorConfig()
        self.logger.info("配置已重置为默认值")

    def load_from_env(self, prefix: str = "MONITOR_") -> None:
        """
        从环境变量加载配置

        Args:
            prefix: 环境变量前缀
        """
        try:
            env_config = {}

            # 配置项映射
            env_mapping = {
                f"{prefix}ADB_TIMEOUT": ("adb_timeout", int),
                f"{prefix}ADB_RETRY_COUNT": ("adb_retry_count", int),
                f"{prefix}ADB_RETRY_DELAY": ("adb_retry_delay", float),
                f"{prefix}LOGCAT_TAG": ("logcat_tag", str),
                f"{prefix}LOGCAT_TIMEOUT": ("logcat_timeout", int),
                f"{prefix}LOGCAT_BUFFER_SIZE": ("logcat_buffer_size", int),
                f"{prefix}WARNING_THRESHOLD_DAYS": ("warning_threshold_days", int),
                f"{prefix}CRITICAL_THRESHOLD_DAYS": ("critical_threshold_days", int),
                f"{prefix}REPORT_OUTPUT_DIR": ("report_output_dir", str),
                f"{prefix}REPORT_FORMAT": ("report_format", str),
                f"{prefix}AUTO_GENERATE_REPORT": (
                    "auto_generate_report",
                    lambda x: x.lower() in ["true", "1", "yes"],
                ),
                f"{prefix}MONITOR_INTERVAL": ("monitor_interval", int),
                f"{prefix}MAX_RETRY_ATTEMPTS": ("max_retry_attempts", int),
                f"{prefix}ENABLE_CONTINUOUS_MONITORING": (
                    "enable_continuous_monitoring",
                    lambda x: x.lower() in ["true", "1", "yes"],
                ),
                f"{prefix}DATA_RETENTION_DAYS": ("data_retention_days", int),
                f"{prefix}MAX_HISTORY_RECORDS": ("max_history_records", int),
                f"{prefix}ENABLE_NOTIFICATIONS": (
                    "enable_notifications",
                    lambda x: x.lower() in ["true", "1", "yes"],
                ),
                f"{prefix}NOTIFICATION_EMAIL": ("notification_email", str),
                f"{prefix}NOTIFICATION_WEBHOOK": ("notification_webhook", str),
                f"{prefix}DEBUG_MODE": (
                    "debug_mode",
                    lambda x: x.lower() in ["true", "1", "yes"],
                ),
                f"{prefix}LOG_LEVEL": ("log_level", str),
                f"{prefix}SAVE_RAW_DATA": (
                    "save_raw_data",
                    lambda x: x.lower() in ["true", "1", "yes"],
                ),
            }

            # 读取环境变量
            for env_key, (config_key, converter) in env_mapping.items():
                env_value = os.getenv(env_key)
                if env_value is not None:
                    try:
                        if callable(converter):
                            converted_value = converter(env_value)
                        else:
                            converted_value = converter(env_value)
                        env_config[config_key] = converted_value
                        self.logger.debug(
                            f"从环境变量加载: {config_key} = {converted_value}"
                        )
                    except (ValueError, TypeError) as e:
                        self.logger.warning(f"环境变量 {env_key} 转换失败: {e}")

            # 应用环境变量配置
            if env_config:
                if self._validate_config(env_config):
                    self._apply_config(env_config)
                    self.logger.info(f"从环境变量加载了 {len(env_config)} 个配置项")
                else:
                    self.logger.error("环境变量配置验证失败")

        except Exception as e:
            self.logger.error(f"从环境变量加载配置时发生错误: {e}")

    def export_config(self, format_type: str = "yaml") -> str:
        """
        导出配置为字符串

        Args:
            format_type: 导出格式 (yaml, json)

        Returns:
            str: 配置字符串
        """
        try:
            config_data = asdict(self.config)
            config_data["_metadata"] = {
                "exported_at": datetime.now().isoformat(),
                "version": "1.0",
            }

            if format_type.lower() == "yaml":
                try:
                    import yaml

                    return yaml.dump(
                        config_data,
                        default_flow_style=False,
                        allow_unicode=True,
                        indent=2,
                    )
                except ImportError:
                    self.logger.warning("PyYAML未安装，改用JSON格式")
                    format_type = "json"

            if format_type.lower() == "json":
                return json.dumps(config_data, indent=2, ensure_ascii=False)

            raise ValueError(f"不支持的导出格式: {format_type}")

        except Exception as e:
            self.logger.error(f"导出配置时发生错误: {e}")
            raise

    def cleanup_temp_directory(self, temp_dir: str) -> bool:
        """
        强制清理临时目录

        Args:
            temp_dir: 临时目录路径

        Returns:
            bool: 是否清理成功
        """
        try:
            import shutil

            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
                self.logger.info(f"成功清理临时目录: {temp_dir}")
                return True
            else:
                self.logger.debug(f"临时目录不存在，无需清理: {temp_dir}")
                return True
        except Exception as e:
            self.logger.warning(f"清理临时目录失败: {temp_dir} - {e}")
            return False

    def get(self, key: str, default=None):
        """
        获取配置项的值

        Args:
            key: 配置项名称
            default: 默认值

        Returns:
            配置项的值或默认值
        """
        try:
            if hasattr(self.config, key):
                return getattr(self.config, key)
            else:
                self.logger.warning(f"配置项不存在: {key}")
                return default
        except Exception as e:
            self.logger.error(f"获取配置项时发生错误: {e}")
            return default

    def get_config_summary(self) -> Dict[str, Any]:
        """
        获取配置摘要

        Returns:
            Dict[str, Any]: 配置摘要
        """
        return {
            "config_file": str(self.config_file),
            "file_exists": self.config_file.exists(),
            "adb_settings": {
                "timeout": self.config.adb_timeout,
                "retry_count": self.config.adb_retry_count,
                "retry_delay": self.config.adb_retry_delay,
            },
            "monitoring_settings": {
                "warning_threshold_days": self.config.warning_threshold_days,
                "critical_threshold_days": self.config.critical_threshold_days,
                "monitor_interval": self.config.monitor_interval,
                "continuous_monitoring": self.config.enable_continuous_monitoring,
            },
            "report_settings": {
                "output_dir": self.config.report_output_dir,
                "format": self.config.report_format,
                "auto_generate": self.config.auto_generate_report,
            },
            "debug_settings": {
                "debug_mode": self.config.debug_mode,
                "log_level": self.config.log_level,
                "save_raw_data": self.config.save_raw_data,
            },
        }
