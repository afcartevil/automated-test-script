#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一异常处理模块

作者: LYH
创建时间: 2025-09-03
描述: 提供统一的异常类定义和异常处理机制
"""

import logging
import time
import functools
from typing import Any, Callable, Optional, Type, Union, List
from enum import Enum


class ErrorSeverity(Enum):
    """错误严重程度枚举"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class BaseMonitorException(Exception):
    """监控系统基础异常类"""

    def __init__(
        self,
        message: str,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        error_code: Optional[str] = None,
        details: Optional[dict] = None,
    ):
        super().__init__(message)
        self.message = message
        self.severity = severity
        self.error_code = error_code or self.__class__.__name__
        self.details = details or {}
        self.timestamp = time.time()

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "severity": self.severity.value,
            "error_code": self.error_code,
            "details": self.details,
            "timestamp": self.timestamp,
        }


class DeviceConnectionError(BaseMonitorException):
    """设备连接异常"""

    def __init__(self, message: str, device_id: Optional[str] = None, **kwargs):
        super().__init__(message, severity=ErrorSeverity.HIGH, **kwargs)
        if device_id:
            self.details["device_id"] = device_id


class ADBError(BaseMonitorException):
    """ADB操作异常"""

    def __init__(self, message: str, command: Optional[str] = None, **kwargs):
        super().__init__(message, severity=ErrorSeverity.HIGH, **kwargs)
        if command:
            self.details["command"] = command


class DataParsingError(BaseMonitorException):
    """数据解析异常"""

    def __init__(self, message: str, data_source: Optional[str] = None, **kwargs):
        super().__init__(message, severity=ErrorSeverity.MEDIUM, **kwargs)
        if data_source:
            self.details["data_source"] = data_source


class TimeCalculationError(BaseMonitorException):
    """时间计算异常"""

    def __init__(self, message: str, patch_level: Optional[int] = None, **kwargs):
        super().__init__(message, severity=ErrorSeverity.MEDIUM, **kwargs)
        if patch_level:
            self.details["patch_level"] = patch_level


class ConfigurationError(BaseMonitorException):
    """配置异常"""

    def __init__(self, message: str, config_key: Optional[str] = None, **kwargs):
        super().__init__(message, severity=ErrorSeverity.HIGH, **kwargs)
        if config_key:
            self.details["config_key"] = config_key


class ReportGenerationError(BaseMonitorException):
    """报告生成异常"""

    def __init__(self, message: str, report_type: Optional[str] = None, **kwargs):
        super().__init__(message, severity=ErrorSeverity.MEDIUM, **kwargs)
        if report_type:
            self.details["report_type"] = report_type


class NetworkError(BaseMonitorException):
    """网络异常"""

    def __init__(self, message: str, url: Optional[str] = None, **kwargs):
        super().__init__(message, severity=ErrorSeverity.LOW, **kwargs)
        if url:
            self.details["url"] = url


class PermissionError(BaseMonitorException):
    """权限异常"""

    def __init__(self, message: str, resource: Optional[str] = None, **kwargs):
        super().__init__(message, severity=ErrorSeverity.HIGH, **kwargs)
        if resource:
            self.details["resource"] = resource


class MonitorTimeoutError(BaseMonitorException):
    """监控超时异常"""

    def __init__(
        self, message: str, timeout_duration: Optional[float] = None, **kwargs
    ):
        super().__init__(message, severity=ErrorSeverity.MEDIUM, **kwargs)
        if timeout_duration:
            self.details["timeout_duration"] = timeout_duration


class DataValidationError(BaseMonitorException):
    """数据验证异常"""

    def __init__(self, message: str, field_name: Optional[str] = None, **kwargs):
        super().__init__(message, severity=ErrorSeverity.MEDIUM, **kwargs)
        if field_name:
            self.details["field_name"] = field_name


class FileOperationError(BaseMonitorException):
    """文件操作异常"""

    def __init__(self, message: str, file_path: Optional[str] = None, **kwargs):
        super().__init__(message, severity=ErrorSeverity.MEDIUM, **kwargs)
        if file_path:
            self.details["file_path"] = file_path


class WarningAnalysisError(BaseMonitorException):
    """警告分析异常"""

    def __init__(self, message: str, warning_type: Optional[str] = None, **kwargs):
        super().__init__(message, severity=ErrorSeverity.MEDIUM, **kwargs)
        if warning_type:
            self.details["warning_type"] = warning_type


class DeviceNotFoundError(BaseMonitorException):
    """设备未找到异常"""

    def __init__(self, message: str, device_id: Optional[str] = None, **kwargs):
        super().__init__(message, severity=ErrorSeverity.HIGH, **kwargs)
        if device_id:
            self.details["device_id"] = device_id


class TestExecutionError(BaseMonitorException):
    """测试执行异常"""

    def __init__(self, message: str, test_name: Optional[str] = None, **kwargs):
        super().__init__(message, severity=ErrorSeverity.HIGH, **kwargs)
        if test_name:
            self.details["test_name"] = test_name


class SmokeTestError(BaseMonitorException):
    """冒烟测试异常"""

    def __init__(self, message: str, test_phase: Optional[str] = None, **kwargs):
        super().__init__(message, severity=ErrorSeverity.HIGH, **kwargs)
        if test_phase:
            self.details["test_phase"] = test_phase


class ExceptionHandler:
    """统一异常处理器"""

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
        self.error_history: List[dict] = []
        self.cleanup_callbacks: List[Callable] = []
        self.report_generator = None
        self.monitor_instance = None

    def handle_exception(
        self, exception: Exception, context: Optional[str] = None
    ) -> dict:
        """处理异常并返回错误信息"""
        error_info = {"timestamp": time.time(), "context": context, "handled": True}

        if isinstance(exception, BaseMonitorException):
            error_info.update(exception.to_dict())
            self._log_exception(exception, context)
        else:
            # 处理标准异常
            error_info.update(
                {
                    "error_type": exception.__class__.__name__,
                    "message": str(exception),
                    "severity": ErrorSeverity.MEDIUM.value,
                    "error_code": exception.__class__.__name__,
                    "details": {},
                }
            )
            self._log_standard_exception(exception, context)

        # 记录错误历史
        self.error_history.append(error_info)

        # 保持错误历史在合理范围内
        if len(self.error_history) > 100:
            self.error_history = self.error_history[-50:]

        return error_info

    def _log_exception(self, exception: BaseMonitorException, context: Optional[str]):
        """记录自定义异常"""
        log_message = f"[{exception.error_code}] {exception.message}"
        if context:
            log_message = f"[{context}] {log_message}"

        if exception.severity == ErrorSeverity.CRITICAL:
            self.logger.critical(
                log_message, extra={"exception_details": exception.details}
            )
        elif exception.severity == ErrorSeverity.HIGH:
            self.logger.error(
                log_message, extra={"exception_details": exception.details}
            )
        elif exception.severity == ErrorSeverity.MEDIUM:
            self.logger.warning(
                log_message, extra={"exception_details": exception.details}
            )
        else:
            self.logger.info(
                log_message, extra={"exception_details": exception.details}
            )

    def _log_standard_exception(self, exception: Exception, context: Optional[str]):
        """记录标准异常"""
        log_message = f"[{exception.__class__.__name__}] {str(exception)}"
        if context:
            log_message = f"[{context}] {log_message}"

        self.logger.error(log_message, exc_info=True)

    def get_error_summary(self) -> dict:
        """获取错误摘要"""
        if not self.error_history:
            return {"total_errors": 0, "by_severity": {}, "by_type": {}}

        by_severity = {}
        by_type = {}

        for error in self.error_history:
            severity = error.get("severity", "unknown")
            error_type = error.get("error_type", "unknown")

            by_severity[severity] = by_severity.get(severity, 0) + 1
            by_type[error_type] = by_type.get(error_type, 0) + 1

        return {
            "total_errors": len(self.error_history),
            "by_severity": by_severity,
            "by_type": by_type,
            "recent_errors": self.error_history[-5:] if self.error_history else [],
        }

    def register_cleanup_callback(self, callback: Callable) -> None:
        """注册资源清理回调函数"""
        if callback not in self.cleanup_callbacks:
            self.cleanup_callbacks.append(callback)

    def set_report_generator(self, report_generator) -> None:
        """设置报告生成器"""
        self.report_generator = report_generator

    def set_monitor_instance(self, monitor) -> None:
        """设置监控器实例"""
        self.monitor_instance = monitor

    def cleanup_resources(self) -> None:
        """执行资源清理"""
        self.logger.info("开始执行资源清理...")

        # 执行注册的清理回调
        for callback in self.cleanup_callbacks:
            try:
                callback()
                self.logger.debug(f"成功执行清理回调: {callback.__name__}")
            except Exception as e:
                self.logger.error(f"执行清理回调 {callback.__name__} 时发生错误: {e}")

        # 如果有监控器实例，执行标准清理
        if self.monitor_instance:
            self._cleanup_monitor_resources()

        self.logger.info("资源清理完成")

    def _cleanup_monitor_resources(self) -> None:
        """清理监控器相关资源"""
        monitor = self.monitor_instance

        # 停止监控
        try:
            if hasattr(monitor, "stop_monitoring"):
                monitor.stop_monitoring()
                self.logger.debug("监控已停止")
        except Exception as e:
            self.logger.error(f"停止监控时发生错误: {e}")

        # 清理ADB接口
        try:
            if hasattr(monitor, "adb_interface") and monitor.adb_interface:
                if hasattr(monitor.adb_interface, "cleanup"):
                    monitor.adb_interface.cleanup()
                    self.logger.debug("ADB接口已清理")
        except Exception as e:
            self.logger.error(f"清理ADB接口时发生错误: {e}")

        # 清理日志监听器
        try:
            if hasattr(monitor, "log_listener") and monitor.log_listener:
                if hasattr(monitor.log_listener, "stop"):
                    monitor.log_listener.stop()
                    self.logger.debug("日志监听器已停止")
                if hasattr(monitor.log_listener, "cleanup"):
                    monitor.log_listener.cleanup()
                    self.logger.debug("日志监听器已清理")
        except Exception as e:
            self.logger.error(f"清理日志监听器时发生错误: {e}")

    def generate_failure_report(
        self,
        exception: Exception,
        context: Optional[str] = None,
        device_id: Optional[str] = None,
    ) -> Optional[str]:
        """生成失败报告"""
        from datetime import datetime, timezone
        import json
        from pathlib import Path

        try:
            # 创建失败报告数据
            error_info = self.handle_exception(exception, context)

            failure_data = {
                "success": False,
                "error_info": error_info,
                "device_id": device_id or "unknown",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "test_type": "automated_test",
                "context": context or "unknown",
            }

            # 尝试获取设备信息（如果可能）
            if (
                device_id
                and self.monitor_instance
                and hasattr(self.monitor_instance, "adb_interface")
            ):
                try:
                    device_info = (
                        self.monitor_instance.adb_interface.get_device_build_info(
                            device_id
                        )
                    )
                    if device_info:
                        failure_data["device_info"] = device_info
                except Exception:
                    pass  # 忽略设备信息获取失败

            # 尝试使用报告生成器生成HTML格式的失败报告
            if hasattr(self, "report_generator") and self.report_generator:
                try:
                    report_path = self.report_generator.generate_failure_report(
                        failure_data,
                        error_info.get("error_type", "UnknownError"),
                        error_info.get("message", str(exception)),
                    )
                    self.logger.info(f"HTML失败报告已保存至: {report_path}")
                    return report_path
                except Exception as e:
                    self.logger.error(f"使用报告生成器生成HTML失败报告时发生错误: {e}")

            # 回退到简单的文件写入（保存在reports目录下）
            return self._write_simple_failure_report(failure_data)

        except Exception as e:
            self.logger.error(f"生成失败报告时发生错误: {e}")
            return None

    def _write_simple_failure_report(self, failure_data: dict) -> Optional[str]:
        """写入简单的失败报告到reports目录"""
        import json
        from datetime import datetime
        from pathlib import Path

        try:
            # 创建output/reports目录
            reports_dir = Path("output/reports")
            reports_dir.mkdir(parents=True, exist_ok=True)

            # 生成文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"failure_report_{timestamp}.html"
            file_path = reports_dir / filename

            # 检查是否为BOOT证书过期情况
            error_message = failure_data.get("error_info", {}).get("message", "")
            is_boot_cert_expired = "BOOT证书" in error_message and (
                "过期" in error_message or "expired" in error_message.lower()
            )

            # 生成简单的HTML报告
            html_content = self._generate_simple_html_report(
                failure_data, is_boot_cert_expired
            )

            # 写入HTML文件
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(html_content)

            self.logger.info(f"简单失败报告已保存至: {file_path}")
            return str(file_path)

        except Exception as e:
            self.logger.error(f"写入简单失败报告时发生错误: {e}")
            return ""

    def _generate_simple_html_report(
        self, failure_data: dict, is_boot_cert_expired: bool = False
    ) -> str:
        """生成简单的HTML失败报告"""
        from datetime import datetime, timezone

        error_info = failure_data.get("error_info", {})
        device_id = failure_data.get("device_id", "N/A")
        timestamp = failure_data.get(
            "timestamp", datetime.now(timezone.utc).isoformat()
        )

        # 特殊处理BOOT证书过期情况
        if is_boot_cert_expired:
            status_class = "critical"
            status_text = "BOOT证书过期 - 直接过期处理"
            recommendations = """
            <div class="recommendations critical">
                <h3>紧急处理建议</h3>
                <ul>
                    <li><strong>立即停止使用该设备</strong></li>
                    <li><strong>BOOT证书已过期，需要重新签发证书</strong></li>
                    <li><strong>联系证书管理部门进行证书更新</strong></li>
                    <li><strong>在证书更新前，该设备无法正常启动</strong></li>
                </ul>
            </div>
            """
        else:
            status_class = "error"
            status_text = "测试失败"
            recommendations = """
            <div class="recommendations">
                <h3>建议操作</h3>
                <ul>
                    <li>检查设备连接状态</li>
                    <li>重新运行测试</li>
                    <li>查看详细错误日志</li>
                    <li>联系技术支持</li>
                </ul>
            </div>
            """

        html_content = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>启动监控失败报告</title>
    <style>
        body {{ font-family: 'Microsoft YaHei', Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        .header {{ text-align: center; margin-bottom: 30px; padding-bottom: 20px; border-bottom: 2px solid #e0e0e0; }}
        .header h1 {{ color: #d32f2f; margin: 0; font-size: 28px; }}
        .header .timestamp {{ color: #666; font-size: 14px; margin-top: 10px; }}
        .section {{ margin-bottom: 25px; }}
        .section h3 {{ color: #333; border-bottom: 2px solid #e0e0e0; padding-bottom: 8px; margin-bottom: 15px; }}
        table {{ width: 100%; border-collapse: collapse; margin-bottom: 15px; }}
        table td {{ padding: 8px 12px; border: 1px solid #ddd; }}
        table td:first-child {{ background-color: #f8f9fa; font-weight: bold; width: 200px; }}
        .error {{ color: #d32f2f; font-weight: bold; }}
        .critical {{ color: #b71c1c; font-weight: bold; background-color: #ffebee; }}
        .warning-summary.{status_class} {{ background-color: #ffebee; border-left: 4px solid #d32f2f; padding: 15px; margin: 15px 0; }}
        .recommendations {{ background-color: #e3f2fd; border-left: 4px solid #1976d2; padding: 15px; margin: 15px 0; }}
        .recommendations.critical {{ background-color: #ffebee; border-left: 4px solid #d32f2f; }}
        .recommendations ul {{ margin: 10px 0; padding-left: 20px; }}
        .recommendations li {{ margin: 5px 0; }}
        .footer {{ text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #e0e0e0; color: #666; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>启动监控失败报告</h1>
            <div class="timestamp">报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
        </div>
        
        <div class="section">
            <h3>设备信息</h3>
            <table>
                <tr><td>设备ID:</td><td>{device_id}</td></tr>
                <tr><td>测试时间:</td><td>{timestamp}</td></tr>
            </table>
        </div>
        
        <div class="warning-summary {status_class}">
            <h3>测试状态: {status_text}</h3>
        </div>
        
        <div class="section">
            <h3>错误信息</h3>
            <table>
                <tr><td>错误类型:</td><td class="{status_class}">{error_info.get('error_type', 'N/A')}</td></tr>
                <tr><td>错误消息:</td><td class="{status_class}">{error_info.get('message', 'N/A')}</td></tr>
                <tr><td>严重程度:</td><td class="{status_class}">{error_info.get('severity', 'N/A')}</td></tr>
            </table>
        </div>
        
        {recommendations}
        
        <div class="footer">
            <p>此报告由启动监控系统自动生成 | 作者: LYH</p>
        </div>
    </div>
</body>
</html>
        """

        return html_content


def retry_on_exception(
    max_retries: int = 3,
    delay: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: tuple = (Exception,),
    logger: Optional[logging.Logger] = None,
):
    """重试装饰器"""

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            _logger = logger or logging.getLogger(func.__module__)
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt == max_retries:
                        _logger.error(
                            f"函数 {func.__name__} 在 {max_retries} 次重试后仍然失败: {e}"
                        )
                        raise

                    wait_time = delay * (backoff_factor**attempt)
                    _logger.warning(
                        f"函数 {func.__name__} 第 {attempt + 1} 次尝试失败: {e}，{wait_time:.1f}秒后重试"
                    )
                    time.sleep(wait_time)

            # 这行代码理论上不会执行到，但为了类型检查
            raise last_exception

        return wrapper

    return decorator


def safe_execute(
    func: Callable,
    *args,
    default_return=None,
    exception_handler: Optional[ExceptionHandler] = None,
    context: Optional[str] = None,
    **kwargs,
) -> tuple:
    """安全执行函数，返回 (success, result_or_error_info)"""
    try:
        result = func(*args, **kwargs)
        return True, result
    except Exception as e:
        if exception_handler:
            error_info = exception_handler.handle_exception(e, context)
            return False, error_info
        else:
            # 简单的错误处理
            logger = logging.getLogger(__name__)
            logger.error(f"执行函数 {func.__name__} 时发生错误: {e}", exc_info=True)
            return False, {"error": str(e), "type": e.__class__.__name__}


# 全局异常处理器实例
global_exception_handler = ExceptionHandler()


def global_exception_handler_decorator(func: Callable) -> Callable:
    """全局异常处理装饰器"""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            global_exception_handler.handle_exception(e, func.__name__)
            raise

    return wrapper


def enhanced_exception_handler_decorator(
    auto_cleanup: bool = False,
    auto_report: bool = False,
    device_id_arg: Optional[str] = None,
) -> Callable:
    """增强的异常处理装饰器，支持自动资源清理和失败报告生成

    Args:
        auto_cleanup: 是否在异常时自动执行资源清理
        auto_report: 是否在异常时自动生成失败报告
        device_id_arg: 设备ID参数名（用于从函数参数中提取设备ID）
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except (DataParsingError, DataValidationError) as e:
                # 处理数据解析/验证异常
                global_exception_handler.handle_exception(e, func.__name__)

                if auto_cleanup:
                    global_exception_handler.cleanup_resources()

                if auto_report:
                    device_id = None
                    if device_id_arg and device_id_arg in kwargs:
                        device_id = kwargs[device_id_arg]
                    elif device_id_arg and len(args) > 0:
                        # 尝试从位置参数中获取设备ID
                        try:
                            import inspect

                            sig = inspect.signature(func)
                            param_names = list(sig.parameters.keys())
                            if device_id_arg in param_names:
                                idx = param_names.index(device_id_arg)
                                if idx < len(args):
                                    device_id = args[idx]
                        except Exception:
                            pass

                    global_exception_handler.generate_failure_report(
                        e, func.__name__, device_id
                    )

                raise
            except Exception as e:
                # 处理其他异常
                global_exception_handler.handle_exception(e, func.__name__)

                if auto_cleanup:
                    global_exception_handler.cleanup_resources()

                if auto_report:
                    device_id = None
                    if device_id_arg and device_id_arg in kwargs:
                        device_id = kwargs[device_id_arg]

                    global_exception_handler.generate_failure_report(
                        e, func.__name__, device_id
                    )

                raise

        return wrapper

    return decorator
