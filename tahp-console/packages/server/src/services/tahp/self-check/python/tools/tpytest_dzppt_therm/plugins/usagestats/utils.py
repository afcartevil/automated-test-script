import logging
import os
import sys
import subprocess
import uuid

USAGE_SDK_LOGGER_NAME_GLOBAL = 'USAGE_SDK_log_Global'


def usage_sdk_log_init():
    shell_handler = logging.StreamHandler()  # 往屏幕上输出
    format_str = logging.Formatter('%(asctime)s: %(message)s')
    shell_handler.setFormatter(format_str)  # 设置屏幕上显示的格式

    logger = logging.getLogger(USAGE_SDK_LOGGER_NAME_GLOBAL)
    logger.setLevel(logging.DEBUG)  # 设置日志级别
    logger.addHandler(shell_handler)


def usage_sdk_log(msg):
    logger = logging.getLogger(USAGE_SDK_LOGGER_NAME_GLOBAL)
    logger.info(f'UsageStats, {msg}')


def usage_sdk_log_exception(e):
    logger = logging.getLogger(USAGE_SDK_LOGGER_NAME_GLOBAL)
    logger.exception(e)


# 不能通过IP地址，公司电脑的网络做了特殊处理，网络出口在国外
def get_county():
    country = None

    # 1. 针对 Windows 系统，使用 ctypes 调用系统 API
    if sys.platform == 'win32':
        try:
            import ctypes
            # 获取用户默认的 Locale 名称 (例如 "zh-CN", "en-US")
            # 预分配缓冲区
            geo_name = ctypes.create_unicode_buffer(85)
            # 调用 Windows Kernel32 API
            result = ctypes.windll.kernel32.GetUserDefaultLocaleName(geo_name, 85)

            if result > 0:
                code = geo_name.value  # 例如 "zh-CN"
                if '-' in code:
                    country = code.split('-')[-1]
                elif '_' in code:
                    country = code.split('_')[-1]
        except Exception as e:
            usage_sdk_log(f"usage stats get_county() failed: {e}")

    # 2. 针对 Linux / macOS 或 Windows API 失败的情况
    # 尝试读取环境变量
    if not country:
        for env_var in ['LC_ALL', 'LC_CTYPE', 'LANG']:
            val = os.environ.get(env_var)
            if val:
                # 环境变量通常格式为 "zh_CN.UTF-8"
                # 去掉编码部分
                base = val.split('.')[0]
                if '_' in base:
                    country = base.split('_')[-1]
                    break

    if country:
        country = country.lower()
        return country
    else:
        return "Unknown"


def create_session_id():
    s = str(uuid.uuid4())
    return s


def get_pc_user_name():
    n = os.getlogin().strip()
    return n


def get_machine_uuid():
    """
    跨平台获取电脑的主板UUID（硬件唯一标识）
    """
    platform = sys.platform
    uuid = None

    try:
        if platform == 'win32':
            # Windows: 使用 wmic 命令读取 UUID
            cmd = "wmic csproduct get uuid"
            # shell=True 隐藏控制台窗口
            output = subprocess.check_output(cmd, shell=True).decode()
            # 输出格式通常是 "UUID\nXXXXXXXX-XXXX-..."，我们需要分割取第二行
            uuid = output.split('\n')[1].strip()

        elif platform == 'darwin':
            # macOS: 使用 ioreg 命令
            cmd = "ioreg -d2 -c IOPlatformExpertDevice | awk -F\\\" '/IOPlatformUUID/{print $(NF-1)}'"
            uuid = subprocess.check_output(cmd, shell=True).decode().strip()

        elif platform.startswith('linux'):
            # Linux: 尝试从系统文件读取 DMI 信息 (通常需要 root 权限)
            # 如果没有 root 权限，可以回退读取 /etc/machine-id (软件层面唯一)
            try:
                # 优先读取硬件 UUID
                with open('/sys/class/dmi/id/product_uuid', 'r') as f:
                    uuid = f.read().strip()
            except Exception:
                # 回退方案：读取系统生成的 machine-id
                try:
                    with open('/etc/machine-id', 'r') as f:
                        uuid = f.read().strip()
                except:
                    pass
    except Exception as e:
        usage_sdk_log(f"get pc mac failed!")
        usage_sdk_log_exception(e)

    # 如果获取不到（极少数山寨主板可能为空），使用备用方案
    if not uuid:
        uuid = "UNKNOWN_DEVICE"

    return uuid


# --- 测试运行 ---
# if __name__ == "__main__":
#     print(get_pc_user_name())
