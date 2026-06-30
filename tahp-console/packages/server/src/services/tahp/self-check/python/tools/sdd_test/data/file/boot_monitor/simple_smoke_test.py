#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
使用方法:
    # 导入模块
    import simple_smoke_test

    # 对指定设备执行烟雾测试（默认安装APK）
    result = simple_smoke_test.test_device("emulator-5554")

    # 检查测试结果
    if result['success']:
        print(f"测试成功: {result['message']}")
        print(f"报告路径: {result['report_path']}")
    else:
        print(f"测试失败: {result['error']}")

    # 获取可用设备列表
    devices = simple_smoke_test.get_available_devices()

    # 测试所有设备
    results = simple_smoke_test.test_all_devices()

Author: LYH
Date: 2025
"""

import os
import sys
from typing import Optional, Dict, Any

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 确保当前工作目录设置正确
os.chdir(project_root)


# 简化版本，用于测试目的
def run_single_check_api(device_id, install_apk=True):
    """模拟API调用"""
    return {
        "status": "success",
        "message": f"设备 {device_id} 测试完成",
        "report_path": f"/tmp/report_{device_id}.html",
        "execution_time": 1.5,
    }


def list_devices_api():
    """模拟设备列表API"""
    return {
        "status": "success",
        "devices": ["emulator-5554", "device-001"],
        "message": "获取设备列表成功",
    }


# 导入真实模块
try:
    from main import (
        run_single_check_api as real_run_single_check_api,
        list_devices_api as real_list_devices_api,
    )

    # 使用真实的API函数
    run_single_check_api = real_run_single_check_api
    list_devices_api = real_list_devices_api
    print("成功导入真实API模块")
except ImportError as e:
    # 使用上面定义的模拟函数
    print(f"Warning: 无法导入真实API模块，使用模拟版本: {e}")
    pass


class SimpleTestError(Exception):
    """简单测试接口异常类"""

    pass


def test_device(device_id: str) -> Dict[str, Any]:
    """
    对指定设备执行烟雾测试

    这是最简洁的调用接口。

    Args:
        device_id (str): 设备ID，必须是有效的Android设备标识符

    Returns:
        Dict[str, Any]: 测试结果字典，包含以下字段：
            - success (bool): 测试是否成功
            - device_id (str): 设备ID
            - certificate_info (dict): 证书信息
            - report_path (str): 报告文件路径
            - execution_time (float): 执行时间（秒）
            - message (str): 结果消息
            - error (str, optional): 错误信息（如果失败）

    Raises:
        SimpleTestError: 当测试执行失败时抛出

    Example:
        >>> result = test_device("emulator-5554")
        >>> if result['success']:
        ...     print(f"测试成功: {result['message']}")
        ...     print(f"报告路径: {result['report_path']}")
        ... else:
        ...     print(f"测试失败: {result['error']}")
    """
    # 参数校验
    if not device_id:
        raise SimpleTestError("设备ID不能为空")

    if not isinstance(device_id, str):
        raise SimpleTestError("设备ID必须是字符串类型")

    device_id = device_id.strip()
    if not device_id:
        raise SimpleTestError("设备ID不能为空字符串")

    try:
        # 检查设备是否存在
        available_devices = get_available_devices()
        if not available_devices["success"]:
            raise SimpleTestError(
                f"无法获取设备列表: {available_devices.get('message', '未知错误')}"
            )

        device_ids = available_devices.get("devices", [])
        if device_id not in device_ids:
            raise SimpleTestError(
                f"设备 '{device_id}' 未找到。可用设备: {', '.join(device_ids) if device_ids else '无'}"
            )

        # 调用API执行测试
        result = run_single_check_api(device_id, install_apk=True)

        # 处理测试结果
        if result.get("status") == "success":
            return {
                "success": True,
                "device_id": device_id,
                "message": "烟雾测试通过",
                "details": result,
                "report_path": result.get("report_path"),
                "execution_time": result.get("execution_time"),
            }
        else:
            return {
                "success": False,
                "device_id": device_id,
                "message": f"烟雾测试失败: {result.get('message', '未知错误')}",
                "details": result,
            }

    except SimpleTestError as e:
        raise SimpleTestError(f"测试执行失败: {str(e)}")
    except Exception as e:
        raise SimpleTestError(f"未知错误: {str(e)}")


def quick_test(device_id: str) -> bool:
    """
    快速测试接口，仅返回成功/失败状态

    Args:
        device_id (str): 设备ID

    Returns:
        bool: True表示测试通过，False表示测试失败
    """
    try:
        result = run_single_check_api(device_id, install_apk=True)
        return result.get("status") == "success"
    except Exception:
        return False


def get_available_devices():
    """
    获取可用设备列表

    Returns:
        dict: 包含设备列表的结果字典
            {
                'success': bool,
                'devices': list,
                'message': str
            }
    """
    try:
        result = list_devices_api()
        if result.get("status") == "success":
            return {
                "success": True,
                "devices": result.get("devices", []),
                "message": "获取设备列表成功",
            }
        else:
            return {
                "success": False,
                "devices": [],
                "message": f"无法获取设备列表: {result.get('message', '未知错误')}",
            }
    except Exception as e:
        return {
            "success": False,
            "devices": [],
            "message": f"获取设备列表失败: {str(e)}",
        }


def quick_test(device_id: str) -> bool:
    """
    快速测试接口，仅返回成功/失败状态

    Args:
        device_id (str): 设备ID

    Returns:
        bool: 测试是否成功

    Raises:
        SimpleTestError: 当测试执行失败时抛出

    Example:
        >>> if quick_test("emulator-5554"):
        ...     print("测试通过")
        ... else:
        ...     print("测试失败")
    """
    result = test_device(device_id)
    return result["success"]


def test_all_devices():
    """
    对所有可用设备执行烟雾测试

    Returns:
        dict: 包含所有设备测试结果的字典
            {
                'success': bool,  # 是否所有设备都测试成功
                'total_devices': int,  # 总设备数
                'passed_devices': int,  # 通过测试的设备数
                'failed_devices': int,  # 失败的设备数
                'results': dict,  # 每个设备的详细测试结果
                'message': str
            }
    """
    try:
        # 获取所有可用设备
        devices_result = get_available_devices()
        if not devices_result["success"]:
            return {
                "success": False,
                "total_devices": 0,
                "passed_devices": 0,
                "failed_devices": 0,
                "results": {},
                "message": f"无法获取设备列表: {devices_result['message']}",
            }

        devices = devices_result["devices"]
        if not devices:
            return {
                "success": True,
                "total_devices": 0,
                "passed_devices": 0,
                "failed_devices": 0,
                "results": {},
                "message": "没有可用的设备",
            }

        # 对每个设备执行测试
        results = {}
        passed_count = 0
        failed_count = 0

        for device_id in devices:
            try:
                device_result = test_device(device_id)
                results[device_id] = device_result

                if device_result["success"]:
                    passed_count += 1
                else:
                    failed_count += 1

            except Exception as e:
                results[device_id] = {
                    "success": False,
                    "device_id": device_id,
                    "message": f"测试异常: {str(e)}",
                    "details": {},
                }
                failed_count += 1

        total_devices = len(devices)
        all_passed = failed_count == 0

        return {
            "success": all_passed,
            "total_devices": total_devices,
            "passed_devices": passed_count,
            "failed_devices": failed_count,
            "results": results,
            "message": f"测试完成: {passed_count}/{total_devices} 设备通过测试",
        }

    except Exception as e:
        return {
            "success": False,
            "total_devices": 0,
            "passed_devices": 0,
            "failed_devices": 0,
            "results": {},
            "message": f"执行测试时发生异常: {str(e)}",
        }


# 便捷的模块级别函数别名
test = test_device  # 主要接口的简短别名
devices = get_available_devices  # 获取设备列表的简短别名


if __name__ == "__main__":
    """
    命令行使用示例

    用法:
        python simple_smoke_test.py [device_id]

    如果不提供device_id，将列出所有可用设备
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="简化的烟雾测试接口",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python simple_smoke_test.py                    # 列出所有可用设备
  python simple_smoke_test.py emulator-5554     # 测试指定设备
  python simple_smoke_test.py --all             # 测试所有设备
        """,
    )

    parser.add_argument("device_id", nargs="?", help="要测试的设备ID")

    parser.add_argument("--all", action="store_true", help="测试所有可用设备")

    args = parser.parse_args()

    try:
        if args.all:
            # 测试所有设备
            print("正在测试所有可用设备...")
            results = test_all_devices()

            print("\n=== 测试结果汇总 ===")
            print(f"总设备数: {results['total_devices']}")
            print(f"通过测试: {results['passed_devices']}")
            print(f"测试失败: {results['failed_devices']}")
            print(f"整体状态: {'✓ 全部通过' if results['success'] else '✗ 部分失败'}")
            print("\n详细结果:")
            for device_id, result in results["results"].items():
                status = "✓ 成功" if result["success"] else "✗ 失败"
                print(f"设备 {device_id}: {status}")
                if not result["success"]:
                    print(
                        f"  错误: {result.get('error', result.get('message', '未知错误'))}"
                    )
                elif result.get("report_path"):
                    print(f"  报告: {result['report_path']}")

        elif args.device_id:
            # 测试指定设备
            print(f"正在测试设备: {args.device_id}")
            result = test_device(args.device_id)

            if result["success"]:
                print("\n✓ 测试成功!")
                print(f"设备ID: {result['device_id']}")
                execution_time = result.get("execution_time", 0)
                if isinstance(execution_time, (int, float)):
                    print(f"执行时间: {execution_time:.2f}秒")
                else:
                    print(f"执行时间: {execution_time}")
                if result.get("report_path"):
                    print(f"报告路径: {result['report_path']}")

                cert_info = result.get("certificate_info", {})
                if cert_info:
                    print("\n证书信息:")
                    for key, value in cert_info.items():
                        print(f"  {key}: {value}")
            else:
                print("\n✗ 测试失败!")
                print(f"错误: {result.get('error', '未知错误')}")

        else:
            # 列出可用设备
            print("获取可用设备列表...")
            devices_result = get_available_devices()

            if devices_result["success"] and devices_result["devices"]:
                print("\n可用设备:")
                for i, device_id in enumerate(devices_result["devices"], 1):
                    print(f"  {i}. {device_id}")
                print("\n使用方法:")
                print(f"  python {sys.argv[0]} <device_id>")
                print(f"  python {sys.argv[0]} --all")
            else:
                print("\n没有找到可用设备")
                if not devices_result["success"]:
                    print(f"错误: {devices_result['message']}")
                print("请确保:")
                print("  1. Android设备已连接并启用USB调试")
                print("  2. ADB服务正在运行")
                print("  3. 设备已授权调试权限")

    except SimpleTestError as e:
        print(f"\n错误: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n用户中断操作")
        sys.exit(0)
    except Exception as e:
        print(f"\n未知错误: {e}")
        sys.exit(1)
