#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Android启动证书监控系统主程序

整合所有模块，提供命令行接口和主要功能入口，包括：
- 命令行参数解析
- 模块初始化和协调
- 监控流程控制
- 错误处理和日志记录
- 用户交互界面

作者: LYH
创建时间: 2025-09-02
"""

import argparse
import logging
import sys
import time
import signal
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
import json

# 导入自定义模块
from src.interfaces.adb_interface import ADBInterface
from src.core.data_parser import BootDataParser
from src.core.time_calculator import TimeCalculator
from src.monitoring.warning_engine import WarningEngine
from src.reporting.report_generator import ReportGenerator
from src.core.config_manager import ConfigManager
from src.utils.console_output_manager import ConsoleOutputManager
from src.utils.exceptions import (
    BaseMonitorException,
    DeviceConnectionError,
    ADBError,
    ConfigurationError,
    DataParsingError,
    TimeCalculationError,
    safe_execute,
    global_exception_handler,
    global_exception_handler_decorator,
    enhanced_exception_handler_decorator,
)
from src.interfaces.api_interface import SmokeTestAPI

# from src.utils.app_manager import AppManager


class SmokeTestMonitor:
    """
    Android启动证书监控系统主类
    """

    def __init__(self, config_file: Optional[str] = None):
        """
        初始化监控系统

        Args:
            config_file: 配置文件路径
        """
        # 初始化配置管理器
        self.config_manager = ConfigManager(config_file)
        self.config = self.config_manager.get_config()

        # 设置日志
        self._setup_logging()

        self.logger = logging.getLogger(__name__)
        self.logger.info("Android启动证书监控系统初始化")

        # 初始化各个模块
        self.adb_interface = ADBInterface()
        self.data_parser = BootDataParser()
        self.time_calculator = TimeCalculator()
        self.warning_engine = WarningEngine(
            warning_threshold_days=self.config.warning_threshold_days,
            critical_threshold_days=self.config.critical_threshold_days,
        )
        self.report_generator = ReportGenerator(self.config.report_output_dir)

        # 初始化控制台输出管理器
        from src.utils.console_output_manager import ConsoleOutputManager

        self.console_output = ConsoleOutputManager()

        # 运行状态
        self.is_running = False
        self.monitoring_active = False

        # APK相关配置
        self.apk_path = None
        self.package_name = None
        self._load_apk_config()

        # 信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        # 设置全局异常处理器的回调函数
        self._setup_global_exception_handler()

    def _setup_global_exception_handler(self):
        """设置全局异常处理器的回调函数"""
        # 注册资源清理回调
        global_exception_handler.register_cleanup_callback(
            self._cleanup_monitoring_resources
        )

        # 设置报告生成器
        global_exception_handler.set_report_generator(self.report_generator)

        # 设置监控实例
        global_exception_handler.set_monitor_instance(self)

    def _cleanup_monitoring_resources(self):
        """清理监控相关资源"""
        try:
            self.logger.info("开始清理监控资源...")

            # 停止监控
            if hasattr(self, "monitoring_active") and self.monitoring_active:
                self.stop_monitoring()

            # 清理ADB接口
            if hasattr(self, "adb_interface") and self.adb_interface:
                self.adb_interface.cleanup()

            self.logger.info("监控资源清理完成")

        except Exception as e:
            self.logger.error(f"清理监控资源时发生错误: {e}")

    def _setup_logging(self):
        """
        设置日志系统 - 使用项目级别的logging配置
        """
        # 确保output/logs目录存在（保留目录创建功能）
        log_dir = Path("output/logs")
        log_dir.mkdir(parents=True, exist_ok=True)

        # 移除重复的logging.basicConfig配置，统一使用sdd_test的pytest logging配置
        # 如果是调试模式，设置更详细的日志
        if hasattr(self.config, "debug_mode") and self.config.debug_mode:
            logging.getLogger().setLevel(logging.DEBUG)

    def _load_apk_config(self):
        """
        加载APK配置信息
        """
        try:
            # 设置默认包名
            self.package_name = "com.example.mytestdemo"

            # 获取脚本所在目录的绝对路径
            script_dir = Path(__file__).parent.absolute()
            apk_dir = script_dir / "APK"

            self.logger.info(f"查找APK目录: {apk_dir}")

            if apk_dir.exists():
                apk_files = list(apk_dir.glob("*.apk"))
                if apk_files:
                    # 优先使用release版本，如果没有则使用第一个找到的APK
                    release_apk = None
                    for apk_file in apk_files:
                        if "release" in apk_file.name.lower():
                            release_apk = apk_file
                            break

                    self.apk_path = release_apk if release_apk else apk_files[0]
                    self.logger.info(f"找到APK文件: {self.apk_path}")
                else:
                    # 如果没有找到APK文件，使用默认路径
                    self.apk_path = apk_dir / "app-release.apk"
                    self.logger.warning(
                        f"APK目录下没有找到APK文件，使用默认路径: {self.apk_path}"
                    )
            else:
                # 如果APK目录不存在，使用默认路径
                self.apk_path = apk_dir / "app-release.apk"
                self.logger.warning(f"APK目录不存在，使用默认路径: {self.apk_path}")

        except Exception as e:
            # 如果配置加载失败，使用默认值
            script_dir = Path(__file__).parent.absolute()
            self.apk_path = script_dir / "APK" / "app-release.apk"
            self.package_name = "com.example.mytestdemo"
            self.logger.error(f"加载APK配置失败: {e}，使用默认配置")

    def _signal_handler(self, signum, frame):
        """
        信号处理器

        Args:
            signum: 信号编号
            frame: 帧对象
        """
        self.logger.info(f"接收到信号 {signum}，正在停止监控...")
        self.stop_monitoring()

    def check_environment(self) -> bool:
        """
        检查运行环境

        Returns:
            bool: 环境是否正常
        """
        self.logger.info("检查运行环境...")

        try:
            # 检查ADB可用性
            success, result = safe_execute(
                self.adb_interface.check_adb_available,
                exception_handler=global_exception_handler,
                context="check_adb_available",
            )
            if not success:
                self.logger.error("ADB不可用，请确保已安装Android SDK并配置PATH")
                return False

            # 检查设备连接
            success, devices = safe_execute(
                self.adb_interface.get_connected_devices,
                exception_handler=global_exception_handler,
                context="get_connected_devices",
            )
            if not success or not devices:
                self.logger.error("未检测到连接的Android设备")
                return False

            self.logger.info(f"检测到 {len(devices)} 个设备: {devices}")

            # 检查输出目录
            output_dir = Path(self.config.report_output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)

            self.logger.info("环境检查通过")
            return True

        except BaseMonitorException as e:
            global_exception_handler.handle_exception(e, "check_environment")
            return False
        except Exception as e:
            global_exception_handler.handle_exception(e, "check_environment")
            return False

    def _initialize_monitoring_system(self) -> None:
        """
        全局初始化监听系统（在APP启动前）

        确保所有监听器在应用启动前就已经准备就绪，避免遗漏监控数据
        """
        try:
            # 启动logcat监控
            self.logger.info("启动logcat监控...")
            if not self.adb_interface.start_logcat_monitor(
                tag_filter=self.config.logcat_tag,
                callback=self.data_parser.parse_log_line,
            ):
                raise MonitorStartError("启动logcat监控失败")

            self.logger.info("监听系统初始化完成，准备就绪")

        except Exception as e:
            self.logger.error(f"监听系统初始化失败: {e}")
            raise MonitorStartError(f"监听系统初始化失败: {e}")

    def install_apk(self, device_id: Optional[str] = None) -> bool:
        """
        安装APK文件

        Args:
            device_id: 设备ID，如果为None则使用第一个可用设备

        Returns:
            bool: 安装是否成功
        """
        try:
            # 检查APK文件是否存在
            if not self.apk_path.exists():
                self.logger.error(f"APK文件不存在: {self.apk_path}")
                return False

            # 选择设备
            if device_id is None:
                success, devices = safe_execute(
                    self.adb_interface.get_connected_devices,
                    exception_handler=global_exception_handler,
                    context="get_connected_devices",
                )
                if not success or not devices:
                    self.logger.error("没有可用的设备")
                    return False
                device_id = devices[0]

            self.logger.info(f"开始在设备 {device_id} 上安装APK: {self.apk_path}")

            # 先卸载旧版本（如果存在）
            self.logger.info(f"卸载旧版本应用: {self.package_name}")
            import subprocess

            uninstall_cmd = ["adb", "-s", device_id, "uninstall", self.package_name]
            subprocess.run(uninstall_cmd, capture_output=True, text=True, timeout=30)

            # 使用ADB安装APK
            cmd = ["adb", "-s", device_id, "install", "-r", str(self.apk_path)]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

            if result.returncode != 0:
                self.logger.error(f"APK安装失败: {result.stderr}")
                return False

            if "Success" not in result.stdout:
                self.logger.error(f"APK安装失败: {result.stdout}")
                return False

            self.logger.info("APK安装成功")
            return True

        except subprocess.TimeoutExpired:
            self.logger.error("APK安装超时")
            return False
        except Exception as e:
            self.logger.error(f"安装APK时发生错误: {e}")
            return False

    def start_android_app(self, device_id: Optional[str] = None) -> bool:
        """
        启动Android应用

        Args:
            device_id: 设备ID，如果为None则使用第一个可用设备

        Returns:
            bool: 启动是否成功
        """
        try:
            # 选择设备
            if device_id is None:
                success, devices = safe_execute(
                    self.adb_interface.get_connected_devices,
                    exception_handler=global_exception_handler,
                    context="get_connected_devices",
                )
                if not success or not devices:
                    self.logger.error("没有可用的设备")
                    return False
                device_id = devices[0]

            self.logger.info(
                f"在设备 {device_id} 上启动Android应用: {self.package_name}"
            )

            # 直接使用ADB启动应用
            try:
                # 构建启动命令
                cmd = [
                    "adb",
                    "-s",
                    device_id,
                    "shell",
                    "monkey",
                    "-p",
                    self.package_name,
                    "-c",
                    "android.intent.category.LAUNCHER",
                    "1",
                ]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

                if result.returncode != 0:
                    self.logger.error(f"应用启动失败: {result.stderr}")
                    return False

            except Exception as e:
                self.logger.error(f"启动应用时发生异常: {e}")
                return False

            self.logger.info("Android应用启动成功")

            # 等待应用完全启动
            time.sleep(3)

            return True

        except Exception as e:
            self.logger.error(f"启动应用时发生错误: {e}")
            return False

    @enhanced_exception_handler_decorator(
        auto_cleanup=True, auto_report=True, device_id_arg="device_id"
    )
    def run_single_check(
        self,
        device_id: str = None,
        no_report: bool = False,
        report_format: str = "html",
        install_apk: bool = True,
    ) -> Dict[str, Any]:
        """
        执行单次检查 - 与auto_integration保持一致的验证流程

        Args:
            device_id: 设备ID，如果为None则选择第一个可用设备
            no_report: 是否跳过报告生成
            report_format: 报告格式 ('html', 'json', 'text')
            install_apk: 是否安装APK

        Returns:
            Dict[str, Any]: 检查结果
        """
        start_time = datetime.now(timezone.utc)
        result = {
            "success": False,
            "device_id": device_id,
            "start_time": start_time.isoformat(),
            "test_type": "single_check",
            "steps": [],
            "errors": [],
            "timestamp": start_time.isoformat(),
        }

        try:
            # 步骤1: 环境检查
            self.logger.info("执行环境检查...")
            try:
                self.check_environment()
                result["steps"].append(
                    {"step": "environment_check", "status": "success"}
                )
                self.logger.info("✓ 环境检查通过")
            except Exception as e:
                result["steps"].append(
                    {"step": "environment_check", "status": "failed", "error": str(e)}
                )
                result["errors"].append(f"环境检查失败: {e}")
                raise RuntimeError(f"环境检查失败: {e}")

            # 步骤2: 设备验证和选择
            self.logger.info("验证设备连接...")
            try:
                if not device_id:
                    success, devices = safe_execute(
                        self.adb_interface.get_connected_devices,
                        exception_handler=global_exception_handler,
                        context="get_connected_devices",
                    )
                    if not success or not devices:
                        raise RuntimeError("未找到可用设备")
                    device_id = devices[0]
                    result["device_id"] = device_id
                    self.logger.info(f"自动选择设备: {device_id}")
                else:
                    # 验证指定设备是否可用
                    success, devices = safe_execute(
                        self.adb_interface.get_connected_devices,
                        exception_handler=global_exception_handler,
                        context="get_connected_devices",
                    )
                    if not success or device_id not in devices:
                        raise RuntimeError(f"指定设备 {device_id} 未连接")
                    self.logger.info(f"使用指定设备: {device_id}")

                result["steps"].append(
                    {
                        "step": "device_verification",
                        "status": "success",
                        "device_id": device_id,
                    }
                )
            except Exception as e:
                result["steps"].append(
                    {"step": "device_verification", "status": "failed", "error": str(e)}
                )
                result["errors"].append(f"设备验证失败: {e}")
                raise

            # 创建特定设备的ADB接口
            device_adb = ADBInterface(device_id=device_id)

            # 步骤3: 全局监听器初始化
            self.logger.info("初始化监听器...")
            try:
                device_adb.start_logcat_monitor(tag_filter=self.config.logcat_tag)
                result["steps"].append(
                    {"step": "listener_initialization", "status": "success"}
                )
            except Exception as e:
                result["steps"].append(
                    {
                        "step": "listener_initialization",
                        "status": "failed",
                        "error": str(e),
                    }
                )
                result["errors"].append(f"监听器初始化失败: {e}")
                raise RuntimeError(f"监听器初始化失败: {e}")

            # 步骤4: APK安装（如果需要）
            if install_apk:
                self.logger.info("执行APK安装...")
                try:
                    if not self.install_apk(device_id):
                        raise RuntimeError("APK安装失败")
                    result["steps"].append({"step": "apk_install", "status": "success"})
                    self.logger.info("✓ APK安装成功")
                except Exception as e:
                    result["steps"].append(
                        {"step": "apk_install", "status": "failed", "error": str(e)}
                    )
                    result["errors"].append(f"APK安装失败: {e}")
                    raise

                # 步骤5: 应用启动
                self.logger.info("启动应用...")
                try:
                    if not self.start_android_app(device_id):
                        raise RuntimeError("应用启动失败")
                    result["steps"].append({"step": "app_start", "status": "success"})
                    self.logger.info("✓ 应用启动成功")
                except Exception as e:
                    result["steps"].append(
                        {"step": "app_start", "status": "failed", "error": str(e)}
                    )
                    result["errors"].append(f"应用启动失败: {e}")
                    raise
            else:
                self.logger.info("跳过APK安装，请手动启动应用")
                print("请手动启动应用，然后按Enter继续...")
                input()
                result["steps"].append(
                    {"step": "manual_app_start", "status": "success"}
                )

            # 步骤6: 数据收集
            self.logger.info("等待启动数据...")
            try:
                max_wait_time = self.config.logcat_timeout
                start_time = time.time()

                boot_data = None
                while time.time() - start_time < max_wait_time:
                    # 计算剩余等待时间
                    remaining_time = max_wait_time - (time.time() - start_time)
                    timeout = min(remaining_time, 60.0)  # 每次最多等待60秒
                    log_entry = device_adb.get_log_data(timeout=timeout)

                    if log_entry:
                        try:
                            # 解析logcat行数据
                            parsed_data = device_adb.parse_logcat_line(log_entry)
                            if parsed_data:
                                # 验证和解析启动数据
                                try:
                                    # 将解析后的数据转换为JSON字符串，然后使用data_parser进行完整处理
                                    import json

                                    json_str = json.dumps(parsed_data)
                                    boot_data = self.data_parser.parse_json_data(
                                        json_str
                                    )
                                    if boot_data:
                                        self.logger.info("成功获取到有效的启动数据")
                                        break
                                except Exception as e:
                                    self.logger.error(f"数据解析时发生未知错误: {e}")
                                    continue
                        except Exception as e:
                            self.logger.debug(f"解析日志条目失败: {e}")
                            continue

                    if boot_data:
                        break

                    time.sleep(1)

                if not boot_data:
                    raise RuntimeError("未获取到启动数据")
                result["steps"].append({"step": "data_collection", "status": "success"})
                self.logger.info("✓ 启动数据收集成功")
            except Exception as e:
                result["steps"].append(
                    {"step": "data_collection", "status": "failed", "error": str(e)}
                )
                result["errors"].append(f"数据收集失败: {e}")
                raise

            # 停止日志监控
            try:
                device_adb.stop_logcat_monitor()
                result["steps"].append({"step": "monitoring_stop", "status": "success"})
            except Exception as e:
                result["steps"].append(
                    {"step": "monitoring_stop", "status": "failed", "error": str(e)}
                )
                # 不阻断流程，继续执行

            # 步骤7: 设备信息获取
            self.logger.info("获取设备信息...")
            try:
                device_build_info = device_adb.get_device_build_info()
                result["steps"].append(
                    {"step": "device_info_collection", "status": "success"}
                )
            except Exception as e:
                result["steps"].append(
                    {
                        "step": "device_info_collection",
                        "status": "failed",
                        "error": str(e),
                    }
                )
                result["errors"].append(f"设备信息获取失败: {e}")
                device_build_info = {}  # 使用空字典继续

            # 步骤8: 时间计算
            self.logger.info("计算时间信息...")
            try:
                time_info = self.time_calculator.calculate_boot_times(
                    boot_data["boot_data"]["raw_boot_patch_level"],
                    device_build_info=device_build_info,
                )

                # 展平时间计算结果以匹配报告生成器期望的格式
                time_calculation = time_info.get("time_calculation", {})

                # 计算基于网络时间的剩余天数
                remaining_days_network = None
                network_time = None
                try:
                    network_time = self.time_calculator.get_network_time()
                    if network_time:
                        remaining_days_network = self.time_calculator.calculate_remaining_days_from_network_time(
                            boot_data["boot_data"]["raw_boot_patch_level"], network_time
                        )
                        self.logger.info(
                            f"基于网络时间的剩余天数: {remaining_days_network}"
                        )
                    else:
                        # 如果无法获取网络时间，使用原有逻辑
                        remaining_days_network = time_calculation.get("remaining_days")
                        self.logger.warning("无法获取网络时间，使用原有计算结果")
                except Exception as e:
                    self.logger.error(f"计算基于网络时间的剩余天数失败: {e}")
                    remaining_days_network = time_calculation.get("remaining_days")

                # 计算基于ROM编译时间的剩余天数
                remaining_days_rom = None
                rom_build_time = None
                try:
                    if device_build_info and "build_date_utc" in device_build_info:
                        # 解析ROM编译时间
                        build_timestamp = int(device_build_info["build_date_utc"])
                        rom_build_time = datetime.fromtimestamp(
                            build_timestamp, tz=timezone.utc
                        )

                        remaining_days_rom = (
                            self.time_calculator.calculate_remaining_days_from_rom_time(
                                boot_data["boot_data"]["raw_boot_patch_level"],
                                rom_build_time,
                            )
                        )
                        self.logger.info(
                            f"基于ROM编译时间的剩余天数: {remaining_days_rom}"
                        )
                    else:
                        self.logger.warning(
                            "无法获取ROM编译时间，无法计算基于ROM时间的剩余天数"
                        )
                        remaining_days_rom = 0
                except Exception as e:
                    self.logger.error(f"计算基于ROM编译时间的剩余天数失败: {e}")
                    remaining_days_rom = 0

                # 获取原有的calculation_result（包含boot_cert_status等字段）
                original_calculation_result = boot_data.get("calculation_result", {})

                # 构建扩展的计算结果，保留原有字段
                flattened_calculation_result = {
                    **original_calculation_result,  # 保留原有字段（包括boot_cert_status）
                    # 基本时间信息（仅在原字段为None或N/A时更新）
                    "boot_date": time_info.get(
                        "formatted_start_date",
                        original_calculation_result.get("boot_date", "N/A"),
                    ),
                    "expiry_date": time_info.get(
                        "formatted_expiry_date",
                        original_calculation_result.get("expiry_date", "N/A"),
                    ),
                    "current_time": time_info.get("formatted_current_time", "N/A"),
                    # 网络时间相关
                    "network_available": network_time is not None,
                    "network_time": (
                        self.time_calculator.format_datetime(network_time)
                        if network_time
                        else "N/A"
                    ),
                    "remaining_days_network": remaining_days_network,
                    # ROM时间相关
                    "remaining_days_rom": remaining_days_rom,
                    "rom_build_time": (
                        self.time_calculator.format_datetime(rom_build_time)
                        if rom_build_time
                        else (
                            device_build_info.get("build_date", "N/A")
                            if device_build_info
                            else "N/A"
                        )
                    ),
                    "rom_build_time_source": (
                        "device_build_date" if rom_build_time else "unknown"
                    ),
                    # 兼容性字段（使用网络时间的结果作为默认值）
                    "remaining_days": (
                        remaining_days_network
                        if remaining_days_network is not None
                        else time_calculation.get("remaining_days")
                    ),
                    "warning_status": time_calculation.get("show_warning", False),
                    # 保留原始数据
                    "raw_time_info": time_info,
                }

                result["steps"].append(
                    {"step": "time_calculation", "status": "success"}
                )
            except Exception as e:
                result["steps"].append(
                    {"step": "time_calculation", "status": "failed", "error": str(e)}
                )
                result["errors"].append(f"时间计算失败: {e}")
                flattened_calculation_result = {}  # 使用空字典继续

            # 合并数据
            complete_data = {
                **boot_data,
                "calculation_result": flattened_calculation_result,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            # 步骤9: 警告分析
            self.logger.info("分析警告信息...")
            try:
                warnings = self.warning_engine.analyze_boot_data(complete_data)
                warning_summary = self.warning_engine.get_warning_summary(warnings)
                result["steps"].append(
                    {"step": "warning_analysis", "status": "success"}
                )
            except Exception as e:
                result["steps"].append(
                    {"step": "warning_analysis", "status": "failed", "error": str(e)}
                )
                result["errors"].append(f"警告分析失败: {e}")
                warnings = []  # 使用空列表继续
                warning_summary = {}

            # 更新结果数据
            result.update(
                {
                    "success": True,
                    "boot_data": complete_data,
                    "device_info": device_build_info,
                    "warnings": [w.to_dict() for w in warnings],
                    "warning_summary": warning_summary,
                    "end_time": datetime.now(timezone.utc).isoformat(),
                }
            )

            # 步骤10: 报告生成
            if not no_report and self.config.auto_generate_report:
                self.logger.info("生成报告...")
                try:
                    report_paths = self.report_generator.generate_comprehensive_report(
                        complete_data,
                        [w.to_dict() for w in warnings],
                        warning_summary,
                        device_id=device_id,
                    )
                    # 提取HTML报告路径作为主要报告路径
                    html_report_path = report_paths.get("html", "")
                    result["report_path"] = html_report_path
                    result["all_report_paths"] = report_paths
                    result["steps"].append(
                        {
                            "step": "report_generation",
                            "status": "success",
                            "report_path": html_report_path,
                        }
                    )
                    self.logger.info(f"✓ 报告已生成: {html_report_path}")
                    self.logger.info(f"✓ 所有格式报告: {report_paths}")
                except Exception as e:
                    result["steps"].append(
                        {
                            "step": "report_generation",
                            "status": "failed",
                            "error": str(e),
                        }
                    )
                    result["errors"].append(f"报告生成失败: {e}")
                    # 不阻断流程

            self.logger.info("✓ 单次检查完成")

            # 使用ConsoleOutputManager输出标准化结果
            try:
                calc_result = complete_data.get("calculation_result", {})
                certificate_info = {
                    "remaining_days": calc_result.get("remaining_days_network")
                    or calc_result.get("remaining_days"),
                    "expiry_date": calc_result.get("expiry_date"),
                    "boot_date": calc_result.get("boot_date"),
                    "warning_status": calc_result.get("warning_status", False),
                }

                self.console_output.print_test_result(
                    success=True,
                    device_id=device_id,
                    certificate_info=certificate_info,
                    report_path=result.get("report_path"),
                    execution_time=(
                        datetime.now(timezone.utc) - start_time
                    ).total_seconds(),
                )
            except Exception as e:
                self.logger.warning(f"输出格式化失败: {e}")

            return result

        except Exception as e:
            error_msg = f"单次检查失败: {e}"
            self.logger.error(error_msg)
            result["error"] = str(e)
            result["end_time"] = datetime.now(timezone.utc).isoformat()

            # 使用ConsoleOutputManager输出失败结果
            try:
                self.console_output.print_test_result(
                    success=False,
                    device_id=device_id or "unknown",
                    error_message=str(e),
                    execution_time=(
                        datetime.now(timezone.utc) - start_time
                    ).total_seconds(),
                )
            except Exception as output_error:
                self.logger.warning(f"输出格式化失败: {output_error}")

            # 生成失败报告
            if not no_report:
                try:
                    failure_report_path = self.report_generator.generate_failure_report(
                        result, "SingleCheckError", str(e)
                    )
                    result["failure_report_path"] = failure_report_path
                    result["steps"].append(
                        {
                            "step": "failure_report_generation",
                            "status": "success",
                            "report_path": failure_report_path,
                        }
                    )
                except Exception as report_error:
                    self.logger.error(f"生成失败报告时发生错误: {report_error}")
                    result["steps"].append(
                        {
                            "step": "failure_report_generation",
                            "status": "failed",
                            "error": str(report_error),
                        }
                    )

            return result

    def run_single_check_api(
        self,
        device_id: str = None,
        install_apk: bool = True,
        no_report: bool = False,
        report_format: str = None,
    ) -> Dict[str, Any]:
        """
        API专用的单次检查方法

        Args:
            device_id: 设备ID
            install_apk: 是否安装APK
            no_report: 是否跳过报告生成
            report_format: 报告格式

        Returns:
            Dict[str, Any]: 标准化的API响应结果
        """
        try:
            # 调用原有的run_single_check方法
            result = self.run_single_check(
                device_id=device_id,
                install_apk=install_apk,
                no_report=no_report,
                report_format=report_format,
            )

            # 标准化API响应格式
            api_result = {
                "success": result.get("success", False),
                "device_id": result.get("device_id"),
                "timestamp": result.get("timestamp"),
                "execution_time": None,
                "data": {},
                "error": None,
            }

            if result.get("start_time") and result.get("end_time"):
                from datetime import datetime

                start = datetime.fromisoformat(
                    result["start_time"].replace("Z", "+00:00")
                )
                end = datetime.fromisoformat(result["end_time"].replace("Z", "+00:00"))
                api_result["execution_time"] = (end - start).total_seconds()

            if result["success"]:
                boot_data = result.get("boot_data", {})
                calc_result = boot_data.get("calculation_result", {})

                # 确保日期字段被转换为字符串
                expiry_date = calc_result.get("expiry_date")
                boot_date = calc_result.get("boot_date")

                if hasattr(expiry_date, "isoformat"):
                    expiry_date = expiry_date.isoformat()
                elif expiry_date is not None:
                    expiry_date = str(expiry_date)

                if hasattr(boot_date, "isoformat"):
                    boot_date = boot_date.isoformat()
                elif boot_date is not None:
                    boot_date = str(boot_date)

                api_result["data"] = {
                    "certificate_info": {
                        "remaining_days": calc_result.get("remaining_days_network")
                        or calc_result.get("remaining_days"),
                        "expiry_date": expiry_date,
                        "boot_date": boot_date,
                        "warning_status": calc_result.get("warning_status", False),
                    },
                    "device_info": result.get("device_info", {}),
                    "warnings": result.get("warnings", []),
                    "warning_summary": result.get("warning_summary", {}),
                    "report_path": result.get("report_path"),
                    "steps": result.get("steps", []),
                }
            else:
                api_result["error"] = result.get("error")
                api_result["data"] = {
                    "steps": result.get("steps", []),
                    "failure_report_path": result.get("failure_report_path"),
                }

            return api_result

        except Exception as e:
            from datetime import datetime, timezone

            return {
                "success": False,
                "device_id": device_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "execution_time": None,
                "data": {},
                "error": str(e),
            }

    @enhanced_exception_handler_decorator(
        auto_cleanup=True, auto_report=True, device_id_arg="device_id"
    )
    def start_continuous_monitoring(
        self, device_id: str = None, install_apk: bool = False
    ) -> None:
        """
        开始连续监控（完整集成测试）

        Args:
            device_id: 设备ID
            install_apk: 是否安装APK并启动应用（连续监控默认为True，执行完整集成测试）
        """
        if not self.config.enable_continuous_monitoring:
            self.logger.error("连续监控未启用，请在配置中启用")
            return

        self.logger.info("开始连续监控（完整集成测试模式）")
        self.monitoring_active = True
        self.is_running = True

        # 连续监控模式：每次都执行完整的集成测试流程
        cycle_count = 0

        try:
            while self.is_running:
                cycle_count += 1
                self.logger.info(f"执行第 {cycle_count} 轮集成测试...")

                # 每轮都执行完整的集成测试（安装APK + 启动应用 + 监控）
                result = self.run_single_check(
                    device_id=device_id, install_apk=install_apk
                )

                if result["success"]:
                    self.logger.info("定期检查完成")

                    # 检查是否有严重警告
                    warning_summary = result.get("warning_summary", {})
                    if warning_summary.get("has_critical", False):
                        self.logger.critical("检测到严重警告！")
                        self.logger.critical(f"摘要: {warning_summary.get('summary')}")
                        self.logger.critical(
                            f"建议: {warning_summary.get('recommendation')}"
                        )
                        # 检测到严重警告时立即退出，避免长时间等待
                        self.logger.info("由于检测到严重警告，监控任务完成，立即退出")
                        self.is_running = False
                        break
                    else:
                        # 数据解析成功且无严重警告，退出脚本
                        self.logger.info("数据解析成功，无严重警告，任务完成")
                        self.logger.info("脚本正常退出")
                        self.is_running = False
                        break
                else:
                    self.logger.error(f"定期检查失败: {result.get('error')}")

                # 等待下次检查
                if self.is_running:
                    self.logger.info(
                        f"等待 {self.config.monitor_interval} 秒后进行下次检查"
                    )
                    time.sleep(self.config.monitor_interval)

        except KeyboardInterrupt:
            self.logger.info("用户中断监控")
        except Exception as e:
            self.logger.error(f"连续监控过程中发生错误: {e}")
        finally:
            self.monitoring_active = False
            self.logger.info("连续监控已停止")

    @global_exception_handler_decorator
    def stop_monitoring(self) -> None:
        """
        停止监控
        """
        self.logger.info("正在停止监控...")
        self.is_running = False

        # 停止ADB监控
        try:
            self.adb_interface.stop_logcat_monitor()
        except Exception as e:
            self.logger.warning(f"停止ADB监控时发生错误: {e}")

    @global_exception_handler_decorator
    def list_devices(self) -> List[str]:
        """
        列出连接的设备

        Returns:
            List[str]: 设备列表
        """
        try:
            devices = self.adb_interface.get_connected_devices()
            self.logger.info(f"发现 {len(devices)} 个设备")
            return devices
        except Exception as e:
            self.logger.error(f"获取设备列表失败: {e}")
            return []

    def show_config(self) -> None:
        """
        显示当前配置
        """
        print("\n=== 当前配置 ===")
        summary = self.config_manager.get_config_summary()

        for section, settings in summary.items():
            print(f"\n{section}:")
            if isinstance(settings, dict):
                for key, value in settings.items():
                    print(f"  {key}: {value}")
            else:
                print(f"  {settings}")

    def export_config(self, output_file: str, format_type: str = "yaml") -> bool:
        """
        导出配置到文件

        Args:
            output_file: 输出文件路径
            format_type: 格式类型

        Returns:
            bool: 是否成功
        """
        try:
            config_content = self.config_manager.export_config(format_type)

            with open(output_file, "w", encoding="utf-8") as f:
                f.write(config_content)

            self.logger.info(f"配置已导出到: {output_file}")
            return True

        except Exception as e:
            self.logger.error(f"导出配置失败: {e}")
            return False


def create_argument_parser() -> argparse.ArgumentParser:
    """
    创建命令行参数解析器

    Returns:
        argparse.ArgumentParser: 参数解析器
    """
    parser = argparse.ArgumentParser(
        description="Android启动证书监控系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  %(prog)s check                    # 执行单次检查（手动启动应用）
  %(prog)s check --install          # 执行单次检查（自动安装APK并启动）
  %(prog)s check -d emulator-5554   # 检查指定设备
  %(prog)s monitor                  # 开始连续监控（完整集成测试）
  %(prog)s monitor --no-install     # 开始连续监控（跳过APK安装）
  %(prog)s test 129065546D000013    # 执行测试并输出JSON结果
  %(prog)s devices                  # 列出连接的设备
  %(prog)s config                   # 显示当前配置
  %(prog)s export-config config.yaml  # 导出配置
        """,
    )

    # 全局选项
    parser.add_argument("-c", "--config", help="配置文件路径 (默认: config.yaml)")
    parser.add_argument("-v", "--verbose", action="store_true", help="启用详细输出")
    parser.add_argument("--debug", action="store_true", help="启用调试模式")

    # 子命令
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # check 命令
    check_parser = subparsers.add_parser("check", help="执行单次检查")
    check_parser.add_argument("-d", "--device", help="指定设备ID")
    check_parser.add_argument("--no-report", action="store_true", help="不生成报告")
    check_parser.add_argument(
        "--format", choices=["html", "json", "txt"], help="报告格式"
    )
    check_parser.add_argument(
        "--install",
        action="store_true",
        help="安装APK并启动应用（默认不安装，提醒用户手动启动）",
    )

    # monitor 命令
    monitor_parser = subparsers.add_parser("monitor", help="开始连续监控")
    monitor_parser.add_argument("-d", "--device", help="指定设备ID")
    monitor_parser.add_argument("-i", "--interval", type=int, help="监控间隔（秒）")
    monitor_parser.add_argument(
        "--no-install",
        action="store_true",
        help="跳过APK安装和应用启动（默认执行完整集成测试）",
    )

    # devices 命令
    subparsers.add_parser("devices", help="列出连接的设备")

    # config 命令
    config_parser = subparsers.add_parser("config", help="配置管理")
    config_subparsers = config_parser.add_subparsers(dest="config_action")

    config_subparsers.add_parser("show", help="显示当前配置")

    export_parser = config_subparsers.add_parser("export", help="导出配置")
    export_parser.add_argument("output_file", help="输出文件路径")
    export_parser.add_argument(
        "--format", choices=["yaml", "json"], default="yaml", help="导出格式"
    )

    # env 命令
    subparsers.add_parser("env", help="检查运行环境")

    # test 命令 (替代test_runner.py的功能)
    test_parser = subparsers.add_parser("test", help="执行测试并输出JSON结果")
    test_parser.add_argument("device_id", help="设备ID")

    return parser


def main():
    """
    主函数
    """

    def _main_logic():
        parser = create_argument_parser()
        args = parser.parse_args()

        # 如果没有指定命令，显示帮助
        if not args.command:
            parser.print_help()
            return 1

        # 初始化监控系统
        monitor = SmokeTestMonitor(args.config)

        # 应用命令行参数
        if args.debug:
            monitor.config_manager.update_config(debug_mode=True, log_level="DEBUG")
            monitor._setup_logging()
        elif args.verbose:
            monitor.config_manager.update_config(log_level="DEBUG")
            monitor._setup_logging()

        # 执行命令
        if args.command == "env":
            print("检查运行环境...")
            if monitor.check_environment():
                print("✓ 环境检查通过")
                return 0
            else:
                print("✗ 环境检查失败")
                return 1

        elif args.command == "devices":
            devices = monitor.list_devices()
            if devices:
                print(f"\n发现 {len(devices)} 个设备:")
                for i, device in enumerate(devices, 1):
                    print(f"  {i}. {device}")
            else:
                print("未发现连接的设备")
                return 1
            return 0

        elif args.command == "config":
            if args.config_action == "show" or not args.config_action:
                monitor.show_config()
            elif args.config_action == "export":
                success = monitor.export_config(args.output_file, args.format)
                return 0 if success else 1
            return 0

        elif args.command == "check":
            # 检查环境
            if not monitor.check_environment():
                return 1

            # 应用参数
            if hasattr(args, "no_report") and args.no_report:
                monitor.config_manager.update_config(auto_generate_report=False)
            if hasattr(args, "format") and args.format:
                monitor.config_manager.update_config(report_format=args.format)

            # 执行检查（单次检查默认不安装APK，除非明确指定--install）
            install_apk = getattr(args, "install", False)  # 单次检查默认不安装APK
            result = monitor.run_single_check(
                device_id=args.device, install_apk=install_apk
            )

            if result["success"]:
                print("\n=== 检查结果 ===")
                print(f"设备: {result['device_id']}")

                boot_data = result["boot_data"]
                calc_result = boot_data.get("calculation_result", {})

                print(f"剩余天数: {calc_result.get('remaining_days', 'N/A')}")
                print(
                    f"警告状态: {'是' if calc_result.get('warning_status') else '否'}"
                )

                warning_summary = result["warning_summary"]
                print(f"\n警告摘要: {warning_summary.get('summary', '无警告')}")
                print(f"建议: {warning_summary.get('recommendation', '继续监控')}")

                if result.get("report_path"):
                    print(f"\n报告已生成: {result['report_path']}")

                return 0
            else:
                print(f"检查失败: {result.get('error')}")
                return 1

        elif args.command == "monitor":
            # 检查环境
            if not monitor.check_environment():
                return 1

            # 应用参数
            if hasattr(args, "interval") and args.interval:
                monitor.config_manager.update_config(
                    monitor_interval=args.interval, enable_continuous_monitoring=True
                )
            else:
                monitor.config_manager.update_config(enable_continuous_monitoring=True)

            # 开始监控（连续监控默认安装APK，执行完整集成测试）
            install_apk = not getattr(
                args, "no_install", False
            )  # 连续监控默认no_install=False
            monitor.start_continuous_monitoring(
                device_id=args.device, install_apk=install_apk
            )
            return 0

        elif args.command == "test":
            # test命令：执行测试并输出JSON结果（替代test_runner.py的功能）
            def json_serializer(obj):
                """自定义JSON序列化函数，处理datetime对象"""
                if isinstance(obj, datetime):
                    return obj.isoformat()
                elif hasattr(obj, "__dict__"):
                    return str(obj)
                else:
                    return obj

            try:
                result = run_single_check_api(args.device_id, True)
                print(json.dumps(result, default=json_serializer))
                return 0
            except Exception as e:
                error_result = {
                    "success": False,
                    "error": str(e),
                    "device_id": args.device_id,
                }
                print(json.dumps(error_result, default=json_serializer))
                return 1

        else:
            print(f"未知命令: {args.command}")
            return 1

    success, result = safe_execute(_main_logic, context="主程序执行")
    if success:
        return result if isinstance(result, int) else 0
    else:
        print(f"程序执行失败: {result.get('error', '未知错误')}")
        return 1


# API接口便捷函数
def run_single_check_api(
    device_id: str = None, install_apk: bool = True, config_path: str = None
) -> Dict[str, Any]:
    """
    API接口：执行单次检查

    Args:
        device_id: 设备ID
        install_apk: 是否安装APK
        config_path: 配置文件路径

    Returns:
        Dict[str, Any]: 检查结果
    """
    api = SmokeTestAPI(config_path)
    return api.run_single_check_api(
        device_id, install_apk=install_apk, no_report=False, report_format=None
    )


def run_continuous_monitoring_api(
    device_id: str = None, install_apk: bool = True, config_path: str = None
) -> Dict[str, Any]:
    """
    API接口：开始连续监控

    Args:
        device_id: 设备ID
        install_apk: 是否安装APK
        config_path: 配置文件路径

    Returns:
        Dict[str, Any]: 监控结果
    """
    api = SmokeTestAPI(config_path)
    return api.run_continuous_monitoring_api(device_id, install_apk)


def list_devices_api(config_path: str = None) -> Dict[str, Any]:
    """
    API接口：列出连接的设备

    Args:
        config_path: 配置文件路径

    Returns:
        Dict[str, Any]: 设备列表结果
    """
    api = SmokeTestAPI(config_path)
    return api.list_devices_api()


if __name__ == "__main__":
    sys.exit(main())
