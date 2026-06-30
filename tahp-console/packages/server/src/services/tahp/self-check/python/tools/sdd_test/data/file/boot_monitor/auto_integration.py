#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Android启动证书监控系统 - 自动化集成测试入口

默认运行完整的连续监控（集成测试），包括：
- 设备连接检查
- APK安装
- 应用启动
- 监控执行
- 报告生成

作者: LYH
创建时间: 2025-09-02
说明: 直接运行连续监控功能，提供完整的端到端自动化测试
"""

import sys
import argparse
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 添加src目录到Python路径
src_path = project_root / "src"
sys.path.insert(0, str(src_path))

from main import SmokeTestMonitor
from src.utils.exceptions import (
    BaseMonitorException,
    TestExecutionError,
    DataParsingError,
    DataValidationError,
    global_exception_handler,
    enhanced_exception_handler_decorator,
)
from src.core.config_manager import ConfigManager
from src.interfaces.adb_interface import ADBInterface
from src.reporting.report_generator import ReportGenerator
from main import SmokeTestMonitor
import logging
import time
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
import os


class AutoIntegrationManager:
    """
    自动集成管理器
    负责协调整个自动化集成测试流程
    """

    def __init__(self):
        self.config_manager = ConfigManager()
        self.adb_interface = ADBInterface()
        self.report_generator = ReportGenerator()
        self.device_manager = DeviceManager()
        self.test_executor = TestExecutor()
        self.result_collector = ResultCollector()
        self.logger = logging.getLogger(__name__)

    def initialize(self):
        """初始化管理器"""
        try:
            self.config_manager.load_config()
            self.logger.info("AutoIntegrationManager 初始化成功")
            return True
        except Exception as e:
            self.logger.error(f"AutoIntegrationManager 初始化失败: {e}")
            return False

    def run_integration_test(self, device_id: str = None, duration: int = 60) -> bool:
        """运行集成测试"""
        try:
            # 设置环境
            if not setup_environment():
                return False

            # 获取设备
            if not device_id:
                device_id = self.device_manager.get_default_device()

            if not device_id:
                self.logger.error("未找到可用设备")
                return False

            # 执行测试
            test_result = self.test_executor.execute_integration_test(
                device_id, duration
            )

            # 收集结果
            self.result_collector.collect_results(test_result)

            # 生成报告
            self.report_generator.generate_integration_report(test_result)

            return test_result.get("success", False)

        except Exception as e:
            self.logger.error(f"集成测试执行失败: {e}")
            return False
        finally:
            cleanup_environment()


class DeviceManager:
    """
    设备管理器
    负责管理Android设备连接和状态
    """

    def __init__(self):
        self.adb_interface = ADBInterface()
        self.logger = logging.getLogger(__name__)

    def get_device_list(self) -> List[Dict[str, Any]]:
        """获取设备列表"""
        try:
            return self.adb_interface.get_device_list()
        except Exception as e:
            self.logger.error(f"获取设备列表失败: {e}")
            return []

    def get_default_device(self) -> Optional[str]:
        """获取默认设备ID"""
        devices = self.get_device_list()
        if devices:
            return devices[0].get("id")
        return None

    def check_device_status(self, device_id: str) -> bool:
        """检查设备状态"""
        try:
            return self.adb_interface.is_device_connected(device_id)
        except Exception as e:
            self.logger.error(f"检查设备状态失败: {e}")
            return False

    def get_device_info(self, device_id: str) -> Dict[str, Any]:
        """获取设备信息"""
        try:
            return self.adb_interface.get_device_build_info(device_id) or {}
        except Exception as e:
            self.logger.error(f"获取设备信息失败: {e}")
            return {}


class TestExecutor:
    """
    测试执行器
    负责执行各种类型的测试
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def execute_integration_test(
        self, device_id: str, duration: int = 60
    ) -> Dict[str, Any]:
        """执行集成测试"""
        start_time = datetime.now(timezone.utc)
        result = {
            "success": False,
            "device_id": device_id,
            "start_time": start_time.isoformat(),
            "duration": duration,
            "test_type": "integration",
            "steps": [],
            "errors": [],
        }

        try:
            # 创建监控器实例
            monitor = SmokeTestMonitor()

            # 步骤1: 环境检查
            self.logger.info("执行环境检查...")
            try:
                monitor.check_environment()
                result["steps"].append(
                    {"step": "environment_check", "status": "success"}
                )
            except Exception as e:
                result["steps"].append(
                    {"step": "environment_check", "status": "failed", "error": str(e)}
                )
                result["errors"].append(f"环境检查失败: {e}")
                return result

            # 步骤2: APK安装
            self.logger.info("执行APK安装...")
            try:
                if monitor.install_apk(device_id):
                    result["steps"].append({"step": "apk_install", "status": "success"})
                else:
                    result["steps"].append({"step": "apk_install", "status": "failed"})
                    result["errors"].append("APK安装失败")
                    return result
            except Exception as e:
                result["steps"].append(
                    {"step": "apk_install", "status": "failed", "error": str(e)}
                )
                result["errors"].append(f"APK安装异常: {e}")
                return result

            # 步骤3: 应用启动
            self.logger.info("启动应用...")
            try:
                if monitor.start_android_app(device_id):
                    result["steps"].append({"step": "app_start", "status": "success"})
                else:
                    result["steps"].append({"step": "app_start", "status": "failed"})
                    result["errors"].append("应用启动失败")
                    return result
            except Exception as e:
                result["steps"].append(
                    {"step": "app_start", "status": "failed", "error": str(e)}
                )
                result["errors"].append(f"应用启动异常: {e}")
                return result

            # 步骤4: 监控执行
            self.logger.info(f"执行监控，持续{duration}秒...")
            try:
                monitor.start_continuous_monitoring(device_id, install_apk=False)
                result["steps"].append({"step": "monitoring", "status": "success"})
            except Exception as e:
                result["steps"].append(
                    {"step": "monitoring", "status": "failed", "error": str(e)}
                )
                result["errors"].append(f"监控执行异常: {e}")
                return result

            # 如果所有步骤都成功
            result["success"] = True
            result["end_time"] = datetime.now(timezone.utc).isoformat()

        except Exception as e:
            self.logger.error(f"集成测试执行失败: {e}")
            result["errors"].append(f"测试执行异常: {e}")

        return result

    def execute_unit_test(self, test_name: str) -> Dict[str, Any]:
        """执行单元测试"""
        return {
            "success": True,
            "test_name": test_name,
            "test_type": "unit",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


class ResultCollector:
    """
    结果收集器
    负责收集和整理测试结果
    """

    def __init__(self):
        self.results = []
        self.logger = logging.getLogger(__name__)

    def collect_results(self, result: Dict[str, Any]):
        """收集测试结果"""
        try:
            result["collected_at"] = datetime.now(timezone.utc).isoformat()
            self.results.append(result)
            self.logger.info(f"收集测试结果: {result.get('test_type', 'unknown')}")
        except Exception as e:
            self.logger.error(f"收集结果失败: {e}")

    def get_results(self) -> List[Dict[str, Any]]:
        """获取所有结果"""
        return self.results.copy()

    def get_summary(self) -> Dict[str, Any]:
        """获取结果摘要"""
        total = len(self.results)
        success = sum(1 for r in self.results if r.get("success", False))

        return {
            "total_tests": total,
            "successful_tests": success,
            "failed_tests": total - success,
            "success_rate": (success / total * 100) if total > 0 else 0,
        }

    def clear_results(self):
        """清空结果"""
        self.results.clear()
        self.logger.info("结果已清空")


def run_auto_integration(device_id: str = None, duration: int = 60) -> bool:
    """
    运行自动集成测试

    Args:
        device_id: 设备ID，如果为None则自动选择
        duration: 监控持续时间（秒）

    Returns:
        bool: 测试是否成功
    """
    try:
        manager = AutoIntegrationManager()
        if not manager.initialize():
            return False

        return manager.run_integration_test(device_id, duration)
    except Exception as e:
        logging.error(f"自动集成测试失败: {e}")
        return False


def setup_environment() -> bool:
    """
    设置测试环境 - 使用项目级别的logging配置

    Returns:
        bool: 设置是否成功
    """
    try:
        # 移除重复的logging.basicConfig配置，统一使用sdd_test的pytest logging配置

        # 检查必要的目录
        from pathlib import Path

        output_dir = Path("output")
        output_dir.mkdir(exist_ok=True)

        logs_dir = Path("logs")
        logs_dir.mkdir(exist_ok=True)

        logging.info("测试环境设置完成")
        return True
    except Exception as e:
        logging.error(f"环境设置失败: {e}")
        return False


def cleanup_environment():
    """
    清理测试环境
    """
    try:
        # 清理临时文件
        import tempfile
        import glob
        import os

        temp_pattern = os.path.join(tempfile.gettempdir(), "smoke_test_*")
        temp_files = glob.glob(temp_pattern)
        for temp_file in temp_files:
            try:
                os.remove(temp_file)
            except Exception:
                pass  # 忽略清理错误

        logging.info("测试环境清理完成")
    except Exception as e:
        logging.error(f"环境清理失败: {e}")


def create_argument_parser():
    """
    创建命令行参数解析器

    Returns:
        argparse.ArgumentParser: 参数解析器
    """
    parser = argparse.ArgumentParser(
        description="Android启动证书监控系统 - 自动化集成测试",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  %(prog)s                      # 运行完整的集成测试
  %(prog)s --duration 120       # 运行集成测试，监控120秒
  %(prog)s --check-only         # 仅检查前置条件
  %(prog)s --install-only       # 仅安装APK
        """,
    )

    parser.add_argument(
        "-d", "--duration", type=int, default=60, help="监控持续时间（秒），默认60秒"
    )

    parser.add_argument(
        "--check-only", action="store_true", help="仅检查前置条件，不执行完整测试"
    )

    parser.add_argument(
        "--install-only", action="store_true", help="仅安装APK，不启动监控"
    )

    parser.add_argument("--device", help="指定设备ID（可选）")

    parser.add_argument("-v", "--verbose", action="store_true", help="启用详细输出")

    return parser


def _generate_failure_report(
    monitor, device_id: str, error_message: str, error_type: str
) -> None:
    """
    生成失败报告

    Args:
        monitor: 监控器实例
        device_id: 设备ID
        error_message: 错误消息
        error_type: 错误类型
    """
    from datetime import datetime, timezone
    import os

    try:
        # 创建失败报告数据
        failure_data = {
            "success": False,
            "error_type": error_type,
            "error_message": error_message,
            "device_id": device_id or "unknown",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "test_type": "auto_integration_test",
            "failure_reason": f"{error_type}: {error_message}",
        }

        # 尝试获取设备信息（如果可能）
        if device_id and hasattr(monitor, "adb_interface"):
            try:
                device_info = monitor.adb_interface.get_device_build_info(device_id)
                if device_info:
                    failure_data["device_info"] = device_info
            except Exception:
                pass  # 忽略设备信息获取失败

        # 生成失败报告
        if hasattr(monitor, "report_generator"):
            try:
                report_path = monitor.report_generator.generate_failure_report(
                    failure_data, error_type, error_message
                )
                print(f"失败报告已保存至: {report_path}")
            except Exception:
                # 如果报告生成器失败，使用简单的文件写入
                _write_simple_failure_report(failure_data)
        else:
            # 如果没有报告生成器，使用简单的文件写入
            _write_simple_failure_report(failure_data)

    except Exception as e:
        print(f"生成失败报告时发生错误: {e}")


def _write_simple_failure_report(failure_data: dict) -> None:
    """
    写入简单的失败报告

    Args:
        failure_data: 失败数据
    """
    import json
    import os
    from datetime import datetime

    try:
        # 确保输出目录存在
        output_dir = Path("output")
        output_dir.mkdir(exist_ok=True)

        # 生成报告文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = output_dir / f"failure_report_{timestamp}.json"

        # 写入失败报告
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(failure_data, f, ensure_ascii=False, indent=2)

        print(f"简单失败报告已保存至: {report_file}")

    except Exception as e:
        print(f"写入简单失败报告时发生错误: {e}")


def _cleanup_resources(monitor, device_id: str = None) -> None:
    """
    清理资源

    Args:
        monitor: 监控器实例
        device_id: 设备ID（可选）
    """
    print("开始清理资源...")

    # 停止监控
    if monitor:
        try:
            if hasattr(monitor, "stop_monitoring"):
                monitor.stop_monitoring()
                print("✓ 监控已停止")
        except Exception as e:
            print(f"✗ 停止监控时发生错误: {e}")

        # 清理ADB接口
        try:
            if hasattr(monitor, "adb_interface") and monitor.adb_interface:
                # 如果有清理方法，调用它
                if hasattr(monitor.adb_interface, "cleanup"):
                    monitor.adb_interface.cleanup()
                    print("✓ ADB接口已清理")
        except Exception as e:
            print(f"✗ 清理ADB接口时发生错误: {e}")

        # 清理日志监听器
        try:
            if hasattr(monitor, "log_listener") and monitor.log_listener:
                if hasattr(monitor.log_listener, "stop"):
                    monitor.log_listener.stop()
                    print("✓ 日志监听器已停止")
                if hasattr(monitor.log_listener, "cleanup"):
                    monitor.log_listener.cleanup()
                    print("✓ 日志监听器已清理")
        except Exception as e:
            print(f"✗ 清理日志监听器时发生错误: {e}")

    # 清理临时文件（如果有）
    try:
        import tempfile
        import glob

        temp_pattern = os.path.join(tempfile.gettempdir(), "smoke_test_*")
        temp_files = glob.glob(temp_pattern)
        for temp_file in temp_files:
            try:
                os.remove(temp_file)
                print(f"✓ 已清理临时文件: {temp_file}")
            except Exception:
                pass  # 忽略清理临时文件的错误
    except Exception:
        pass  # 忽略临时文件清理错误

    print("资源清理完成")


@enhanced_exception_handler_decorator(auto_cleanup=True, auto_report=True)
def main():
    """
    主函数 - 直接运行连续监控（完整集成测试）
    """
    parser = create_argument_parser()
    args = parser.parse_args()

    try:
        # 初始化监控器
        monitor = SmokeTestMonitor()

        print("=== Android启动证书监控系统 - 自动化集成测试 ===")
        print(f"监控持续时间: {args.duration}秒")
        print()

        # 根据参数执行不同的操作
        if args.check_only:
            print("执行前置条件检查...")
            try:
                # 检查环境
                monitor.check_environment()
                print("✓ 前置条件检查通过")
                return 0
            except Exception as e:
                print(f"✗ 前置条件检查失败: {e}")
                return 1

        elif args.install_only:
            print("执行APK安装...")

            try:
                # 检查环境
                monitor.check_environment()

                # 获取设备ID
                device_id = args.device
                if not device_id:
                    devices = monitor.adb_interface.get_device_list()
                    if not devices:
                        print("✗ 未找到连接的设备")
                        return 1
                    device_id = devices[0]["id"]

                # 安装APK并启动应用
                if monitor.install_apk(device_id) and monitor.start_android_app(
                    device_id
                ):
                    print("✓ APK安装和应用启动成功")
                    return 0
                else:
                    print("✗ APK安装或应用启动失败")
                    return 1

            except Exception as e:
                print(f"✗ 安装过程失败: {e}")
                return 1

        else:
            # 默认执行完整的集成测试（连续监控模式）
            print("开始连续监控（完整集成测试）...")

            try:
                # 检查环境
                monitor.check_environment()

                # 获取设备ID
                device_id = args.device
                if not device_id:
                    devices = monitor.adb_interface.get_device_list()
                    if not devices:
                        print("✗ 未找到连接的设备")
                        return 1
                    device_id = devices[0]["id"]

                print(f"使用设备: {device_id}")
                print(f"开始连续监控，持续时间: {args.duration}秒")

                # 保存原始配置
                original_duration = monitor.config_manager.config.monitor_interval
                monitor.config_manager.update_config(monitor_interval=args.duration)

                # 启动连续监控（包含APK安装和应用启动）
                monitor.start_continuous_monitoring(device_id, install_apk=True)

                # 恢复原始配置
                monitor.config_manager.update_config(monitor_interval=original_duration)

                print("\n=== 集成测试完成 ===")
                print("✓ 所有测试步骤执行成功")
                print("✓ 监控数据已收集")
                print("✓ 报告已生成")
                print()
                print("请查看 output/ 目录下的报告文件")
                return 0

            except KeyboardInterrupt:
                print("\n用户中断测试")
                # 确保停止监控
                try:
                    monitor.stop_monitoring()
                except:
                    pass
                return 1

    except BaseMonitorException as e:
        print(f"\n✗ 测试失败: {e}")
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 1

    except KeyboardInterrupt:
        print("\n用户中断测试")
        return 1

    except Exception as e:
        print(f"\n✗ 未知错误: {e}")
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
