import ctypes
import sys
import os
import winreg

# 存放标记文件，防止重复弹窗
FLAG_FILE = os.path.join(os.getenv("APPDATA"), "longpath_enabled.flag")


def is_admin():
    """判断当前脚本是否有管理员权限"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def _relaunch_as_admin():
    """以管理员权限重启当前脚本"""
    params = " ".join([f'"{x}"' for x in sys.argv])
    ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, params, None, 1
    )
    sys.exit(0)


def is_long_path_enabled():
    """检测系统是否已开启长路径支持"""
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\FileSystem"
        ) as key:
            return winreg.QueryValueEx(key, "LongPathsEnabled")[0] == 1
    except:
        return False

def _enable_long_path():
    """修改注册表开启长路径"""
    with winreg.OpenKey(
        winreg.HKEY_LOCAL_MACHINE,
        r"SYSTEM\CurrentControlSet\Control\FileSystem",
        0,
        winreg.KEY_SET_VALUE
    ) as key:
        winreg.SetValueEx(key, "LongPathsEnabled", 0, winreg.REG_DWORD, 1)


def prompt_reboot():
    """
    弹窗提示用户重启
    返回 True 表示用户点击“是”
    """
    MB_YESNO = 0x04
    IDYES = 6
    result = ctypes.windll.user32.MessageBoxW(
        None,
        "检测到您的电脑尚未启用 Windows 长路径支持，可能导致测试报告写入失败。为保证测试结果的完整性与稳定性，建议重启电脑后再进行测试。",
        "系统提示",
        MB_YESNO
    )
    return result == IDYES

def reboot_now():
    """立即重启系统"""
    os.system("shutdown /r /t 0")


def ensure_long_path_enabled(prompt_reboot_if_needed=True):
    """
    核心函数，一行调用即可：
      - 检测长路径状态
      - 如果未开启，自动提权开启
      - 第一次开启完成后弹窗提示用户重启（可关闭）
    """
    if os.path.exists(FLAG_FILE):
        # 已处理过，直接返回
        return

    if is_long_path_enabled():
        # 系统已经开启长路径
        open(FLAG_FILE, "w").close()
        return

    # 未开启，先提权
    if not is_admin():
        _relaunch_as_admin()

    # 开启长路径
    _enable_long_path()
    open(FLAG_FILE, "w").close()

    # 弹窗提示用户是否立即重启
    if prompt_reboot_if_needed and prompt_reboot():
        reboot_now()
if __name__ == '__main__':
    ensure_long_path_enabled()

    # 后续程序正常启动
    print("程序启动，长路径已开启或已处理完成")
