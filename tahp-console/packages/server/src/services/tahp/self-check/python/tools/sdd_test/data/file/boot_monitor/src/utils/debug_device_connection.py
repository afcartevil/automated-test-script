#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
设备连接调试脚本

用于分析ADB设备连接问题，特别是check_device_connected方法的逻辑问题

作者: LYH
创建时间: 2025-09-02
"""

import subprocess
import logging
import sys
from pathlib import Path
from typing import List, Dict, Optional, Tuple

# 导入自定义异常和异常处理机制
from src.utils.exceptions import (
    DeviceConnectionError,
    FileOperationError,
    ConfigurationError,
    TestExecutionError,
    global_exception_handler,
    safe_execute,
)

# 设置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@global_exception_handler_decorator
def run_adb_command(command: List[str], timeout: int = 30) -> Tuple[bool, str, str]:
    """
    运行ADB命令

    Args:
        command: ADB命令列表
        timeout: 超时时间（秒）

    Returns:
        Tuple[bool, str, str]: (是否成功, 标准输出, 错误输出)
    """
    try:
        logger.info(f"执行ADB命令: {' '.join(command)}")

        result = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout, encoding="utf-8"
        )

        success = result.returncode == 0
        stdout = result.stdout.strip() if result.stdout else ""
        stderr = result.stderr.strip() if result.stderr else ""

        if success:
            logger.info(f"命令执行成功: {stdout}")
        else:
            logger.error(f"命令执行失败 (返回码: {result.returncode}): {stderr}")

        return success, stdout, stderr

    except subprocess.TimeoutExpired:
        raise DeviceConnectionError(f"ADB命令超时 ({timeout}秒): {' '.join(command)}")

    except FileNotFoundError:
        raise ConfigurationError(
            "ADB命令未找到，请确保Android SDK已正确安装并添加到PATH"
        )

    except Exception as e:
        raise DeviceConnectionError(f"执行ADB命令时发生错误: {e}")


@global_exception_handler_decorator
def test_basic_adb():
    """
    测试基本ADB功能
    """
    logger.info("=== 测试基本ADB功能 ===")

    # 测试adb version
    success, stdout, stderr = run_adb_command(["adb", "version"])
    if success:
        logger.info("✓ ADB版本检查通过")
        logger.info(f"ADB版本信息: {stdout.split()[0] if stdout else '未知'}")
    else:
        raise ConfigurationError("ADB版本检查失败")

    # 测试adb devices
    success, stdout, stderr = run_adb_command(["adb", "devices"])
    if success:
        logger.info("✓ ADB设备列表获取成功")
        devices = [
            line
            for line in stdout.split("\n")
            if line.strip() and not line.startswith("List of devices")
        ]
        logger.info(f"发现设备数量: {len(devices)}")
        for device in devices:
            logger.info(f"设备: {device}")
        if len(devices) == 0:
            raise DeviceConnectionError("未发现任何连接的设备")
        return True
    else:
        raise DeviceConnectionError("ADB设备列表获取失败")


@global_exception_handler_decorator
def test_specific_device_commands(device_id):
    """
    测试特定设备的命令

    Args:
        device_id: 设备ID
    """
    logger.info(f"=== 测试设备 {device_id} 的特定命令 ===")

    # 测试设备属性
    commands = [
        (
            ["adb", "-s", device_id, "shell", "getprop", "ro.build.version.release"],
            "Android版本",
        ),
        (["adb", "-s", device_id, "shell", "getprop", "ro.product.model"], "设备型号"),
        (
            ["adb", "-s", device_id, "shell", "getprop", "ro.product.manufacturer"],
            "制造商",
        ),
        (
            ["adb", "-s", device_id, "shell", "pm", "list", "packages", "-f"],
            "已安装应用列表",
        ),
    ]

    results = {}
    for cmd, description in commands:
        try:
            success, stdout, stderr = run_adb_command(cmd)
            results[description] = {
                "success": success,
                "output": stdout,
                "error": stderr,
            }

            if success:
                logger.info(
                    f"✓ {description}: {stdout[:100]}..."
                    if len(stdout) > 100
                    else f"✓ {description}: {stdout}"
                )
            else:
                logger.error(f"✗ {description}: {stderr}")
        except Exception as e:
            logger.error(f"✗ {description}: 执行失败 - {e}")
            results[description] = {"success": False, "output": "", "error": str(e)}

    return results


@global_exception_handler_decorator
def analyze_check_device_connected_logic(device_id):
    """
    分析check_device_connected逻辑

    Args:
        device_id: 设备ID
    """
    logger.info(f"=== 分析设备连接检查逻辑 (设备: {device_id}) ===")

    # 模拟原始代码的逻辑
    logger.info("步骤1: 执行 adb devices")
    success, stdout, stderr = run_adb_command(["adb", "devices"])

    if not success:
        raise DeviceConnectionError("adb devices 命令失败")

    logger.info("步骤2: 解析设备列表")
    lines = stdout.strip().split("\n")
    logger.info(f"原始输出行数: {len(lines)}")

    for i, line in enumerate(lines):
        logger.info(f"第{i+1}行: {repr(line)}")

    # 跳过标题行
    device_lines = lines[1:] if len(lines) > 1 else []
    logger.info(f"设备行数: {len(device_lines)}")

    logger.info("步骤3: 检查设备ID匹配")
    for line in device_lines:
        if line.strip():
            parts = line.split("\t")
            logger.info(f"解析行: {repr(line)} -> 部分: {parts}")

            if len(parts) >= 1:
                found_device_id = parts[0]
                logger.info(f"找到设备ID: {found_device_id}")

                if found_device_id == device_id:
                    logger.info(f"✓ 设备ID匹配: {device_id}")
                    if len(parts) >= 2:
                        status = parts[1]
                        logger.info(f"设备状态: {status}")
                        return status == "device"
                    else:
                        logger.warning("设备状态信息缺失")
                        return False

    raise DeviceConnectionError(f"未找到设备ID: {device_id}")

    # 建议的修复方案
    logger.info("\n=== 建议的修复方案 ===")
    logger.info("问题分析:")
    logger.info("1. 当前代码使用 'adb -s device_id devices' 命令")
    logger.info("2. 这个命令可能不会返回指定设备的信息")
    logger.info("3. 应该使用 'adb devices' 然后解析结果")

    logger.info("\n建议修复:")
    logger.info("方案1: 修改check_device_connected方法")
    logger.info("  - 始终使用 'adb devices' 获取所有设备")
    logger.info("  - 然后在结果中查找指定的device_id")

    logger.info("方案2: 使用 'adb -s device_id get-state' 检查设备状态")

    # 测试修复方案2
    logger.info("\n测试修复方案2:")
    cmd = ["adb", "-s", device_id, "get-state"]
    returncode, stdout, stderr = run_adb_command(cmd, "使用get-state检查设备状态")

    if returncode == 0 and stdout.strip() == "device":
        logger.info("  ✓ 方案2可行：设备状态正常")
    else:
        logger.warning(
            f"  ✗ 方案2结果：返回码={returncode}, 输出={repr(stdout.strip())}"
        )


@global_exception_handler_decorator
def generate_fix_suggestions():
    """
    生成修复建议
    """
    logger.info("=== 修复建议 ===")

    suggestions = [
        "1. 确保Android SDK已正确安装并添加到PATH环境变量",
        "2. 确保设备已开启USB调试模式",
        "3. 确保设备已授权此计算机进行调试",
        "4. 尝试重新连接USB线缆",
        "5. 尝试重启ADB服务: adb kill-server && adb start-server",
        "6. 检查设备驱动是否正确安装",
        "7. 如果使用模拟器，确保模拟器已完全启动",
    ]

    for suggestion in suggestions:
        logger.info(suggestion)

    logger.info("\n=== 推荐的代码修复 ===")

    # 提供修复后的代码示例
    fixed_code = '''
def check_device_connected(self, device_id: str) -> bool:
    """
    检查设备是否连接
    
    Args:
        device_id: 设备ID
        
    Returns:
        bool: 设备是否连接
    """
    try:
        # 使用正确的命令获取设备列表
        result = subprocess.run(
            ["adb", "devices"],  # 移除 -s device_id
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            raise DeviceConnectionError(f"ADB命令失败: {result.stderr}")
        
        # 解析输出，查找目标设备
        lines = result.stdout.strip().split('\\n')[1:]  # 跳过标题行
        
        for line in lines:
            if line.strip():
                parts = line.split('\\t')
                if len(parts) >= 2:
                    found_device_id = parts[0]
                    status = parts[1]
                    
                    if found_device_id == device_id and status == "device":
                        self.logger.info(f"设备 {device_id} 已连接")
                        return True
        
        raise DeviceConnectionError(f"设备 {device_id} 未连接或状态异常")
        
    except DeviceConnectionError:
        raise
    except Exception as e:
        raise DeviceConnectionError(f"检查设备连接时发生错误: {e}")
'''

    logger.info("修复后的代码:")
    logger.info(fixed_code)
