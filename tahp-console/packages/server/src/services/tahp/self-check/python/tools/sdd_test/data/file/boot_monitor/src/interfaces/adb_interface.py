#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ADB接口模块

负责与Android设备的ADB通信，包括：
- 执行adb logcat命令
- 实时监控日志输出
- 过滤特定标签的日志
- 处理ADB连接异常

作者: LYH
创建时间: 2025-09-02
"""

import subprocess
import threading
import time
import logging
import re
from typing import Optional, Callable, List, Dict, Any
from queue import Queue, Empty
import json
from src.utils.exceptions import (
    ADBError,
    DeviceConnectionError,
    MonitorTimeoutError,
    DataParsingError,
    retry_on_exception,
    safe_execute,
    global_exception_handler,
    global_exception_handler_decorator,
)


class ADBInterface:
    """
    ADB接口类，负责与Android设备通信
    """

    def __init__(self, device_id: Optional[str] = None):
        """
        初始化ADB接口

        Args:
            device_id: 设备ID，如果为None则使用默认设备
        """
        self.device_id = device_id
        self.logger = logging.getLogger(__name__)
        self._process = None
        self._monitoring = False
        self._monitor_thread = None
        self._data_queue = Queue()

    @retry_on_exception(
        max_retries=2, delay=1.0, exceptions=(subprocess.TimeoutExpired,)
    )
    def check_adb_available(self) -> bool:
        """
        检查ADB是否可用

        Returns:
            bool: ADB是否可用
        """
        try:
            result = subprocess.run(
                ["adb", "version"], capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                return True
            else:
                raise ADBError(f"ADB不可用: {result.stderr}", command="adb version")
        except subprocess.TimeoutExpired:
            raise MonitorTimeoutError("ADB版本检查超时", timeout_duration=10.0)
        except FileNotFoundError:
            raise ADBError("未找到ADB命令，请确保ADB已安装并添加到PATH", command="adb")
        except Exception as e:
            global_exception_handler.handle_exception(e, "check_adb_available")
            return False

    def is_adb_available(self) -> bool:
        """检查ADB是否可用（check_adb_available的别名）

        Returns:
            bool: ADB是否可用
        """
        return self.check_adb_available()

    def check_device_connected(self) -> bool:
        """
        检查设备是否连接

        Returns:
            bool: 设备是否连接
        """
        try:
            # 方案1: 使用get-state命令检查特定设备状态
            if self.device_id:
                cmd = ["adb", "-s", self.device_id, "get-state"]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

                if result.returncode == 0 and result.stdout.strip() == "device":
                    self.logger.debug(f"设备 {self.device_id} 状态检查通过")
                    return True
                else:
                    raise DeviceConnectionError(
                        f"设备 {self.device_id} 状态异常: returncode={result.returncode}, output={repr(result.stdout.strip())}",
                        device_id=self.device_id,
                    )

            # 方案2: 如果没有指定device_id，使用devices命令获取所有设备
            cmd = ["adb", "devices"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

            if result.returncode != 0:
                raise ADBError(
                    f"ADB devices命令失败: {result.stderr}", command="adb devices"
                )

            # 解析设备列表
            lines = result.stdout.strip().split("\n")[1:]  # 跳过标题行
            for line in lines:
                if line.strip():
                    parts = line.split("\t")
                    if len(parts) >= 2:
                        device_id = parts[0]
                        status = parts[1]
                        # 如果没有指定device_id，返回第一个可用设备
                        if status == "device":
                            self.logger.debug(f"找到可用设备: {device_id}")
                            return True

            raise DeviceConnectionError("未找到任何可用设备")

        except (DeviceConnectionError, ADBError):
            raise
        except subprocess.TimeoutExpired:
            raise MonitorTimeoutError("检查设备连接超时", timeout_duration=10.0)
        except FileNotFoundError:
            raise ADBError("未找到ADB命令", command="adb")
        except Exception as e:
            global_exception_handler.handle_exception(e, "check_device_connected")
            return False

    @retry_on_exception(
        max_retries=2, delay=1.0, exceptions=(subprocess.TimeoutExpired,)
    )
    def get_device_list(self) -> List[Dict[str, str]]:
        """
        获取连接的设备列表

        Returns:
            List[Dict[str, str]]: 设备列表，每个设备包含id和status
        """
        try:
            result = subprocess.run(
                ["adb", "devices"], capture_output=True, text=True, timeout=10
            )

            if result.returncode != 0:
                raise ADBError(
                    f"获取设备列表失败: {result.stderr}", command="adb devices"
                )

            devices = []
            lines = result.stdout.strip().split("\n")[1:]  # 跳过标题行
            for line in lines:
                if line.strip():
                    parts = line.split("\t")
                    if len(parts) >= 2:
                        devices.append({"id": parts[0], "status": parts[1]})
            return devices

        except subprocess.TimeoutExpired:
            raise MonitorTimeoutError("获取设备列表超时", timeout_duration=10.0)
        except FileNotFoundError:
            raise ADBError("未找到ADB命令", command="adb")
        except Exception as e:
            global_exception_handler.handle_exception(e, "get_device_list")
            return []

    def get_connected_devices(self) -> List[str]:
        """
        获取已连接设备的ID列表

        Returns:
            List[str]: 已连接设备的ID列表
        """
        devices = self.get_device_list()
        return [device["id"] for device in devices if device["status"] == "device"]

    @global_exception_handler_decorator
    def get_device_property(self, property_name: str) -> Optional[str]:
        """
        获取设备系统属性

        Args:
            property_name: 属性名称，如 'ro.build.date', 'ro.build.version.release' 等

        Returns:
            Optional[str]: 属性值，如果获取失败则返回None
        """
        if not self.check_adb_available():
            self.logger.error("ADB不可用")
            return None

        if not self.check_device_connected():
            self.logger.error("设备未连接")
            return None

        try:
            # 构建adb shell getprop命令
            cmd = ["adb"]
            if self.device_id:
                cmd.extend(["-s", self.device_id])
            cmd.extend(["shell", "getprop", property_name])

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

            if result.returncode == 0:
                value = result.stdout.strip()
                self.logger.debug(f"获取属性 {property_name}: {value}")
                return value if value else None
            else:
                self.logger.error(f"获取属性失败: {result.stderr}")
                return None

        except subprocess.TimeoutExpired:
            raise MonitorTimeoutError(f"获取属性 {property_name} 超时")
        except Exception as e:
            raise ADBError(f"获取属性 {property_name} 失败: {e}")

    @global_exception_handler_decorator
    def get_device_build_info(self) -> Dict[str, Optional[str]]:
        """
        获取设备构建信息

        Returns:
            Dict[str, Optional[str]]: 包含构建信息的字典
        """
        build_info = {
            "build_date": self.get_device_property("ro.build.date"),
            "build_date_utc": self.get_device_property("ro.build.date.utc"),
            "build_version_release": self.get_device_property(
                "ro.build.version.release"
            ),
            "build_version_sdk": self.get_device_property("ro.build.version.sdk"),
            "build_fingerprint": self.get_device_property("ro.build.fingerprint"),
            "product_model": self.get_device_property("ro.product.model"),
            "product_brand": self.get_device_property("ro.product.brand"),
        }

        self.logger.info(f"设备构建信息: {build_info}")
        return build_info

    @global_exception_handler_decorator
    def start_logcat_monitor(
        self,
        tag_filter: str = "SMOKE_TEST_BOOT_DATA",
        callback: Optional[Callable[[str], None]] = None,
    ) -> bool:
        """
        开始监控logcat输出

        Args:
            tag_filter: 日志标签过滤器
            callback: 接收到日志时的回调函数

        Returns:
            bool: 是否成功开始监控
        """
        if self._monitoring:
            self.logger.warning("已经在监控中")
            return True

        if not self.check_adb_available():
            self.logger.error("ADB不可用")
            return False

        if not self.check_device_connected():
            self.logger.error("设备未连接")
            return False

        try:
            # 构建adb logcat命令
            cmd = ["adb"]
            if self.device_id:
                cmd.extend(["-s", self.device_id])

            # 添加logcat参数：清除缓存并开始监控
            cmd.extend(["logcat", "-c"])  # 先清除日志缓存

            # 执行清除命令
            subprocess.run(cmd, timeout=5)

            # 重新构建监控命令
            cmd = ["adb"]
            if self.device_id:
                cmd.extend(["-s", self.device_id])
            cmd.extend(["logcat", "-s", tag_filter])

            # 启动logcat进程
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=0,  # 无缓冲，立即输出
                universal_newlines=True,
                encoding="utf-8",
                errors="ignore",
            )

            self._monitoring = True

            # 启动监控线程
            self._monitor_thread = threading.Thread(
                target=self._monitor_logcat, args=(callback,), daemon=True
            )
            self._monitor_thread.start()

            self.logger.info(f"开始监控logcat，标签过滤器: {tag_filter}")
            return True

        except subprocess.TimeoutExpired:
            raise MonitorTimeoutError("启动logcat监控超时")
        except Exception as e:
            self._monitoring = False
            raise ADBError(f"启动logcat监控失败: {e}")

    def _monitor_logcat(self, callback: Optional[Callable[[str], None]] = None):
        """
        监控logcat输出的内部方法

        Args:
            callback: 接收到日志时的回调函数
        """
        try:
            while self._monitoring and self._process:
                line = self._process.stdout.readline()
                if line:
                    line = line.strip()
                    if line:
                        # 将数据放入队列
                        self._data_queue.put(line)

                        # 调用回调函数
                        if callback:
                            try:
                                callback(line)
                            except Exception as e:
                                self.logger.error(f"回调函数执行失败: {e}")
                elif self._process.poll() is not None:
                    # 进程已结束
                    break

        except Exception as e:
            self.logger.error(f"监控logcat时发生错误: {e}")
        finally:
            self._monitoring = False

    def stop_logcat_monitor(self):
        """
        停止监控logcat输出
        """
        self._monitoring = False

        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait()
            except Exception as e:
                self.logger.error(f"停止logcat进程失败: {e}")
            finally:
                self._process = None

        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=5)

        self.logger.info("已停止logcat监控")

    def get_log_data(self, timeout: float = 30.0) -> Optional[str]:
        """
        从队列中获取日志数据

        Args:
            timeout: 超时时间（秒）

        Returns:
            Optional[str]: 日志数据，如果超时则返回None
        """
        try:
            return self._data_queue.get(timeout=timeout)
        except Empty:
            return None

    @global_exception_handler_decorator
    def execute_single_logcat(
        self, tag_filter: str = "SMOKE_TEST_BOOT_DATA", timeout: float = 300.0
    ) -> List[str]:
        """
        执行单次logcat命令，获取现有日志

        Args:
            tag_filter: 日志标签过滤器
            timeout: 超时时间（秒）

        Returns:
            List[str]: 日志行列表
        """
        if not self.check_adb_available():
            self.logger.error("ADB不可用")
            return []

        if not self.check_device_connected():
            self.logger.error("设备未连接")
            return []

        try:
            # 构建adb logcat命令
            cmd = ["adb"]
            if self.device_id:
                cmd.extend(["-s", self.device_id])
            cmd.extend(["logcat", "-d", "-s", tag_filter])  # -d表示dump现有日志并退出

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="ignore",
            )

            if result.returncode == 0:
                lines = [
                    line.strip() for line in result.stdout.split("\n") if line.strip()
                ]
                self.logger.info(f"获取到 {len(lines)} 行日志")
                return lines
            else:
                self.logger.error(f"logcat命令执行失败: {result.stderr}")
                return []

        except subprocess.TimeoutExpired:
            raise MonitorTimeoutError(f"logcat命令超时 ({timeout}秒)")
        except Exception as e:
            raise ADBError(f"执行logcat命令失败: {e}")

    @global_exception_handler_decorator
    def parse_logcat_line(self, line: str) -> Optional[Dict[str, Any]]:
        """
        解析logcat行，提取数据

        Args:
            line: logcat输出行

        Returns:
            Optional[Dict[str, Any]]: 解析后的数据，如果解析失败则返回None
        """
        try:
            # logcat格式: 时间戳 进程ID 线程ID 日志级别 标签: 消息
            # 例如: 09-02 10:45:16.389  3287  3287 I BootDataExporter: {message}

            # 使用正则表达式匹配logcat格式并提取消息部分
            pattern = r"^\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3}\s+\d+\s+\d+\s+[VDIWEF]\s+\w+:\s*(.*)$"
            match = re.match(pattern, line)

            if match:
                message = match.group(1).strip()

                # 首先尝试解析为JSON格式
                if message.startswith("{") and message.endswith("}"):
                    try:
                        # 直接尝试解析JSON（Android输出的应该是有效的JSON）
                        data = json.loads(message)
                        return data
                    except json.JSONDecodeError as e:
                        self.logger.debug(f"JSON解析失败: {e}, 尝试修复格式")
                        try:
                            # 修复JSON格式：为键和字符串值添加引号
                            json_str = message

                            # 1. 为所有键添加引号
                            json_str = re.sub(
                                r"([{,])\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:",
                                r'\1"\2":',
                                json_str,
                            )

                            # 2. 为字符串值添加引号（包括时间戳格式）
                            json_str = re.sub(
                                r":\s*([a-zA-Z0-9][a-zA-Z0-9\-_.:TZ]*?)\s*([,}])",
                                r':"\1"\2',
                                json_str,
                            )

                            # 3. 处理嵌套对象的开始
                            json_str = re.sub(r":\s*{", r":{", json_str)

                            # 4. 修复纯数字值（不包括日期格式）
                            json_str = re.sub(r':"(\d+)"([,}])', r":\1\2", json_str)

                            # 尝试解析修复后的JSON
                            data = json.loads(json_str)
                            return data
                        except json.JSONDecodeError:
                            pass

                # 如果JSON解析失败，尝试解析键值对格式
                # 例如: type:boot_data_export timestamp:2025-09-02T10:50:00.123Z boot_data:{raw_boot_patch_level:2024-08-05}
                return self._parse_key_value_format(message)

        except json.JSONDecodeError as e:
            raise DataParsingError(f"JSON解析失败: {e}")
        except Exception as e:
            raise DataParsingError(f"解析logcat行失败: {line[:100]}... 错误: {e}")

    def _parse_key_value_format(self, message: str) -> Optional[Dict[str, Any]]:
        """
        解析键值对格式的消息

        Args:
            message: 消息内容

        Returns:
            Optional[Dict[str, Any]]: 解析后的数据
        """
        try:
            result = {}

            # 使用正则表达式匹配键值对
            # 匹配格式: key:value 或 key:{nested}
            pattern = r"([a-zA-Z_][a-zA-Z0-9_]*):([^\s]+(?:\s+[^:]*?(?=\s+[a-zA-Z_][a-zA-Z0-9_]*:|$))?|\{[^}]*\})"

            matches = re.findall(pattern, message)

            for key, value in matches:
                key = key.strip()
                value = value.strip()

                # 处理嵌套对象
                if value.startswith("{") and value.endswith("}"):
                    # 递归解析嵌套对象
                    nested_content = value[1:-1]  # 移除大括号
                    nested_result = self._parse_key_value_format(nested_content)
                    if nested_result:
                        result[key] = nested_result
                else:
                    # 尝试转换数据类型
                    if value.isdigit():
                        result[key] = int(value)
                    elif value.replace(".", "", 1).isdigit():
                        result[key] = float(value)
                    elif value.lower() in ("true", "false"):
                        result[key] = value.lower() == "true"
                    else:
                        result[key] = value

            return result if result else None

        except Exception as e:
            self.logger.debug(f"解析键值对格式失败: {message[:100]}... 错误: {e}")
            return None

    def __enter__(self):
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.stop_logcat_monitor()

    @retry_on_exception(
        max_retries=2, delay=2.0, exceptions=(subprocess.TimeoutExpired, ADBError)
    )
    def restart_adb_server(self) -> bool:
        """重启ADB服务器

        Returns:
            bool: 重启是否成功
        """
        try:
            self.logger.info("正在重启ADB服务器...")

            # 停止ADB服务器
            result = subprocess.run(
                ["adb", "kill-server"], capture_output=True, text=True, timeout=10
            )

            if result.returncode != 0:
                self.logger.warning(f"停止ADB服务器时出现警告: {result.stderr}")

            # 等待一段时间确保服务器完全停止
            time.sleep(2)

            # 启动ADB服务器
            result = subprocess.run(
                ["adb", "start-server"], capture_output=True, text=True, timeout=15
            )

            if result.returncode == 0:
                self.logger.info("ADB服务器重启成功")
                # 验证ADB是否可用
                if self.check_adb_available():
                    return True
                else:
                    raise ADBError(
                        "ADB服务器重启后仍不可用", command="adb start-server"
                    )
            else:
                raise ADBError(
                    f"启动ADB服务器失败: {result.stderr}", command="adb start-server"
                )

        except subprocess.TimeoutExpired:
            raise MonitorTimeoutError("重启ADB服务器超时", timeout_duration=25.0)
        except FileNotFoundError:
            raise ADBError("未找到ADB命令，请确保ADB已安装并添加到PATH", command="adb")
        except Exception as e:
            global_exception_handler.handle_exception(e, "restart_adb_server")
            return False
