# -*- coding: utf-8 -*-
import pytest
import logging
import subprocess
import os.path as path
import re
import os
import sys
import importlib

# 配置logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] | %(filename)s:%(lineno)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


@pytest.mark.skip(reason="跳过bootmonitor测试")
def test_bootmonitor(device_serial):
    """测试bootmonitor功能"""
    logging.info("开始执行bootmonitor测试")

    # 保存当前工作目录
    original_cwd = os.getcwd()

    try:
        # 切换到boot_monitor目录
        boot_monitor_dir = os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "..",
            "..",
            "data",
            "file",
            "boot_monitor",
        )
        boot_monitor_dir = os.path.abspath(boot_monitor_dir)
        os.chdir(boot_monitor_dir)

        # 使用真实的设备ID
        device_id = device_serial  # 使用真实的Android设备ID

        # 使用subprocess调用boot_monitor项目，避免模块导入问题
        import subprocess
        import json

        # 首先检查设备是否存在
        devices_cmd = [
            sys.executable,
            "-c",
            "from main import list_devices_api; import json; print(json.dumps(list_devices_api()))",
        ]
        devices_result = subprocess.run(
            devices_cmd,
            cwd=boot_monitor_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )

        if devices_result.returncode != 0:
            raise Exception(f"获取设备列表失败: {devices_result.stderr}")

        try:
            devices_data = json.loads(
                devices_result.stdout.strip().split("\n")[-1]
            )  # 取最后一行JSON输出
        except (json.JSONDecodeError, IndexError) as e:
            raise Exception(f"解析设备列表失败: {e}, 输出: {devices_result.stdout}")

        if devices_data.get("status") != "success":
            raise Exception(
                f"无法获取设备列表: {devices_data.get('message', '未知错误')}"
            )

        device_ids = devices_data.get("devices", [])
        if device_id not in device_ids:
            raise Exception(
                f"设备 '{device_id}' 未找到。可用设备: {', '.join(device_ids) if device_ids else '无'}"
            )

        # 执行测试
        test_cmd = [sys.executable, "main.py", "test", device_id]
        test_result = subprocess.run(
            test_cmd,
            cwd=boot_monitor_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )

        if test_result.returncode != 0:
            raise Exception(f"执行测试失败: {test_result.stderr}")

        try:
            result_data = json.loads(
                test_result.stdout.strip().split("\n")[-1]
            )  # 取最后一行JSON输出
        except (json.JSONDecodeError, IndexError) as e:
            raise Exception(f"解析测试结果失败: {e}, 输出: {test_result.stdout}")

        # 处理测试结果
        if result_data.get("status") == "success":
            res = {
                "success": True,
                "device_id": device_id,
                "message": "烟雾测试通过",
                "details": result_data,
                "report_path": result_data.get("report_path"),
                "execution_time": result_data.get("execution_time"),
            }
        else:
            res = {
                "success": False,
                "device_id": device_id,
                "message": f"烟雾测试失败: {result_data.get('message', '未知错误')}",
                "details": result_data,
            }

        # 根据测试结果记录日志
        if res["success"]:
            logging.info(f"bootmonitor测试通过: {res.get('message', '测试成功')}")

            # 输出详细的测试结果到控制台
            res = (
                "\n"
                + "=" * 60
                + "\n"
                + "BOOTMONITOR 测试结果\n"
                + "=" * 60
                + "\n"
                + f"测试状态: 成功\n"
                + f"设备ID: {device_id}\n"
            )
            logging.info(res)
            # 获取详细数据
            details = result_data.get("details", {})

            # 计算执行时间
            start_time = details.get("start_time")
            end_time = details.get("end_time")
            if start_time and end_time:
                from datetime import datetime

                try:
                    start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                    end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
                    execution_seconds = (end_dt - start_dt).total_seconds()
                    logging.info(f"执行时间: {execution_seconds:.2f} 秒")
                except:
                    logging.info(f"执行时间: N/A")
            else:
                # 尝试从外层获取duration_seconds
                duration = result_data.get("duration_seconds")
                if duration:
                    logging.info(f"执行时间: {duration} 秒")
                else:
                    logging.info(f"执行时间: N/A")

            # 输出证书信息（从warnings中提取）
            warnings = details.get("warnings", [])
            cert_warning = None
            for warning in warnings:
                if warning.get("warning_type") in ["EXPIRED", "EXPIRY_SOON"]:
                    cert_warning = warning
                    break

            if cert_warning:
                warning_details = cert_warning.get("details", {})
                expiry_date = warning_details.get("expiry_date", "N/A")
                remaining_days = warning_details.get("remaining_days", "N/A")
                logging.info(f"证书过期时间: {expiry_date}")
                logging.info(f"证书剩余天数: {remaining_days} 天")
                if remaining_days <= 90:
                    pytest.fail("证书剩余天数小于等于90天", res)
            else:
                logging.info("证书信息: 未获取到警告信息")
                pytest.fail("证书信息异常", res)

            # 输出报告路径
            report_path = details.get("report_path") or result_data.get("report_path")
            if report_path:
                logging.info(f"测试报告: {report_path}")
            else:
                logging.info("测试报告: 未生成")

            # 输出设备信息
            device_info = details.get("device_info", {})
            if device_info:
                model = device_info.get("product_model") or device_info.get(
                    "model", "N/A"
                )
                android_version = device_info.get(
                    "build_version_release"
                ) or device_info.get("android_version", "N/A")
                logging.info(f"设备型号: {model}")
                logging.info(f"Android版本: {android_version}")

            # 输出警告信息（如果有）
            warnings = details.get("warnings", [])
            if warnings:
                logging.info(f"警告数量: {len(warnings)}")
                for i, warning in enumerate(warnings[:2], 1):  # 只显示前2个警告
                    warning_msg = warning.get("message", "N/A")
                    warning_level = warning.get("level", "N/A")
                    logging.info(f"  警告{i}: [{warning_level}] {warning_msg}")
            else:
                logging.info("警告: 无")

            logging.info("=" * 60)
        else:
            logging.error(f"bootmonitor测试失败: {res.get('error', '未知错误')}")

            # 输出失败信息到控制台
            res = (
                "\n"
                + "=" * 60
                + "BOOTMONITOR 测试结果"
                + "=" * 60
                + f"测试状态: 失败"
                + f"设备ID: {device_id}"
                + f"失败原因: {res.get('message', '未知错误')}"
                + "=" * 60
            )
            logging.error(res)

    except Exception as e:
        logging.error(f"bootmonitor测试执行异常: {str(e)}")
        raise
    finally:
        # 恢复原始工作目录
        os.chdir(original_cwd)
