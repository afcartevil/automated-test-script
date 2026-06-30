import os
import re
from datetime import datetime
from src.utils.adb.adb_utils import execute_command,getprop
import pytest
import logging

@pytest.mark.require_non_cuttlefish
def test_kernel_version_check(device_serial):
    logging.info("开始测试: test_kernel_version_check")
    try:
        # EOL 日期信息
        dict1 = {
            "android12-5.10.198": "2024-11-01",
            "android12-5.10.205": "2024-11-01",
            "android12-5.10.209": "2025-06-01",
            "android12-5.10.218": "2025-12-01",
            "android12-5.10.226": "2026-03-01",
            "android12-5.10.233": "2026-06-01",
            "android12-5.10.236": "2026-09-01",
            "android12-5.10.237": "2026-10-01",

            "android13-5.10.189": "2024-11-01",
            "android13-5.10.198": "2024-11-01",
            "android13-5.10.205": "2024-11-01",
            "android13-5.10.209": "2025-06-01",
            "android13-5.10.210": "2025-07-01",
            "android13-5.10.214": "2025-08-01",
            "android13-5.10.218": "2025-09-01",
            "android13-5.10.223": "2025-12-01",
            "android13-5.10.228": "2026-02-01",
            "android13-5.10.234": "2026-04-01",
            "android13-5.10.236": "2026-06-01",
            "android13-5.10.238": "2026-11-01",

            "android13-5.15.123": "2024-11-01",
            "android13-5.15.137": "2024-11-01",
            "android13-5.15.144": "2024-11-01",
            "android13-5.15.148": "2025-06-01",
            "android13-5.15.149": "2025-08-01",
            "android13-5.15.151": "2025-12-01",
            "android13-5.15.153": "2026-01-01",
            "android13-5.15.167": "2026-03-01",
            "android13-5.15.170": "2026-03-01",
            "android13-5.15.178": "2026-07-01",
            "android13-5.15.180": "2026-09-01",
            "android13-5.15.185": "2026-11-01",

            "android14-5.15.123": "2024-11-01",
            "android14-5.15.131": "2024-11-01",
            "android14-5.15.137": "2024-11-01",
            "android14-5.15.144": "2024-11-01",
            "android14-5.15.148": "2025-06-01",
            "android14-5.15.149": "2025-07-01",
            "android14-5.15.153": "2025-08-01",
            "android14-5.15.158": "2025-09-01",
            "android14-5.15.164": "2025-10-01",
            "android14-5.15.167": "2025-12-01",
            "android14-5.15.170": "2026-02-01",
            "android14-5.15.178": "2026-04-01",
            "android14-5.15.180": "2026-06-01",
            "android14-5.15.185": "2026-11-01",

            "android14-6.1.43": "2024-11-01",
            "android14-6.1.57": "2024-11-01",
            "android14-6.1.68": "2024-11-01",
            "android14-6.1.75": "2025-06-01",
            "android14-6.1.78": "2025-07-01",
            "android14-6.1.84": "2025-08-01",
            "android14-6.1.90": "2025-09-01",
            "android14-6.1.93": "2026-01-01",
            "android14-6.1.99": "2026-01-01",
            "android14-6.1.112": "2026-01-01",
            "android14-6.1.115": "2026-01-01",
            "android14-6.1.118": "2026-02-01",
            "android14-6.1.124": "2026-03-01",
            "android14-6.1.128": "2026-07-01",
            "android14-6.1.129": "2026-08-01",
            "android14-6.1.134": "2026-08-01",
            "android14-6.1.138": "2026-10-01",
            "android14-6.1.141": "2026-11-01",
            "android14-6.1.145": "2026-12-01",

            "android15-6.6.30": "2025-11-01",
            "android15-6.6.46": "2025-11-01",
            "android15-6.6.50": "2026-02-01",
            "android15-6.6.56": "2026-02-01",
            "android15-6.6.57": "2026-04-01",
            "android15-6.6.58": "2026-04-01",
            "android15-6.6.66": "2026-06-01",
            "android15-6.6.77": "2026-07-01",
            "android15-6.6.82": "2026-08-01",
            "android15-6.6.87": "2026-08-01",
            "android15-6.6.89": "2026-08-01",
            "android15-6.6.92": "2026-11-01",
            "android15-6.6.98": "2026-12-01",

            "android16-6.12.23": "2026-10-01",
            "android16-6.12.30": "2026-11-01",
            "android16-6.12.38": "2026-12-01",
        }

        # 获取kernel版本
        cmd = "adb -s " + device_serial + " shell uname -a"
        res = execute_command(cmd)
        if not res["success"]:
            logging.warning("test_kernel_version_check:adb命令执行失败")
            return None
        prop_value = res["output"]
        pattern = r'(\d+\.\d+\.\d+)-(android\d+)'
        match = re.search(pattern, prop_value)
        kernel_version = match.group(1)
        android_version = match.group(2)

        # 过滤CL8/A671N
        product_name = getprop('ro.product.name',device_serial)
        if "CL8".lower() in product_name.lower() and kernel_version == "5.10.218" or "A671N".lower() in product_name.lower() and getprop(
                "ro.build.version.release") == "14":
            logging.warning(f"test_kernel_version_check:kernelVersion = {android_version}-{kernel_version}\n CL8 Abandoned Branch, No Need to Process")
            return None

        # 获取EOL
        eol = dict1.get(android_version + "-" + kernel_version)
        # 判断是否正确获取eol日期
        if not eol:
            logging.info(f"test_kernel_version_check: No corresponding eol information for the {android_version}-{kernel_version} version was found ")
            return None
        # 获取当前系统时间
        current_date = datetime.now().date()
        eol_date = datetime.strptime(eol, "%Y-%m-%d").date()

        # 比较日期
        if current_date > eol_date:
            logging.error(f"test_kernel_version_check:{android_version}-{kernel_version}This kernel version has expired! EOL date:{eol}")
            return None
        else:
            days_remaining = (eol_date - current_date).days
            if days_remaining < 30:
                logging.info(f"test_kernel_version_check:{android_version}-{kernel_version} The valid period of the kernel version is less than one month, please arrange for a kernel upgrade ")
                return None
            else:
                return None
    except Exception as e:
        logging.info(f"test_kernel_version_check:Test failed due to error: {str(e)}")
        return None
