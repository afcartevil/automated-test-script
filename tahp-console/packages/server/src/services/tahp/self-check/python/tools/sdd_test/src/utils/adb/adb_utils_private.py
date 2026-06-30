# -*- coding: utf-8 -*-
import logging
import shlex
import subprocess
import time
from typing import Dict, Optional, Union


def _safe_strip(value):
    if value is None:
        return ""

    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").strip()

    return str(value).strip()


def execute_command(
    command: Union[str, list],
    timeout: Optional[float] = None,
    shell: bool = False,
    cwd: Optional[str] = None,
    env: Optional[dict] = None,
    no_retry: bool = False,
    max_attempts: int = 3,
) -> Dict[str, Union[bool, str, int]]:
    """
    私有版命令执行函数。
    用于当前 TargetSdkCheck 用例，避免修改公共 adb_utils.py 影响其他部门。

    返回结构：
    {
        "success": bool,
        "output": str,
        "error": str,
        "return_code": int,
        "exception_type": str,
        "exception_msg": str
    }
    """

    if no_retry:
        max_attempts = 1

    last_result = None

    for attempt in range(1, max_attempts + 1):
        result = {
            "success": False,
            "output": "",
            "error": "",
            "return_code": -1,
            "exception_type": "",
            "exception_msg": "",
        }

        try:
            real_command = command

            if isinstance(real_command, str) and not shell:
                real_command = shlex.split(real_command)

            process = subprocess.run(
                real_command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=shell,
                timeout=timeout,
                cwd=cwd,
                env=env,
                check=False,
                text=False,  # 关键：不要让 Windows 默认用 GBK 解码 adb/logcat 输出
            )

            result.update(
                {
                    "success": process.returncode == 0,
                    "output": _safe_strip(process.stdout),
                    "error": _safe_strip(process.stderr),
                    "return_code": process.returncode,
                    "exception_type": "",
                    "exception_msg": "",
                }
            )

        except subprocess.TimeoutExpired as e:
            result.update(
                {
                    "success": False,
                    "output": _safe_strip(e.stdout),
                    "error": _safe_strip(e.stderr) or f"Timeout after {timeout}s",
                    "return_code": -1,
                    "exception_type": type(e).__name__,
                    "exception_msg": f"Command timed out after {timeout} seconds",
                }
            )

        except FileNotFoundError as e:
            result.update(
                {
                    "success": False,
                    "output": "",
                    "error": "",
                    "return_code": -1,
                    "exception_type": "CommandNotFound",
                    "exception_msg": str(e),
                }
            )

        except Exception as e:
            result.update(
                {
                    "success": False,
                    "output": "",
                    "error": "",
                    "return_code": -1,
                    "exception_type": type(e).__name__,
                    "exception_msg": str(e),
                }
            )

        last_result = result

        if result["success"]:
            return result

        if attempt < max_attempts:
            logging.warning(
                f"execute_command retry {attempt}/{max_attempts}, "
                f"command={command}, result={result}"
            )
            time.sleep(1)

    return last_result


def getprop(prop_key, device_serial=None):
    if device_serial:
        cmd = ["adb", "-s", device_serial, "shell", "getprop", prop_key]
    else:
        logging.warning("未指定设备序列号，默认使用第一个设备")
        cmd = ["adb", "shell", "getprop", prop_key]

    result = execute_command(cmd, timeout=10, no_retry=True)
    return result.get("output") or ""


def get_apkpath_by_package(device_serial, package_name):
    cmd = ["adb", "-s", device_serial, "shell", "pm", "path", package_name]
    result = execute_command(cmd, timeout=15, no_retry=True)

    if not result.get("success"):
        return None

    output = result.get("output") or ""

    for line in output.splitlines():
        line = line.strip()
        if line.startswith("package:"):
            return line.split("package:", 1)[1].strip()

    return None