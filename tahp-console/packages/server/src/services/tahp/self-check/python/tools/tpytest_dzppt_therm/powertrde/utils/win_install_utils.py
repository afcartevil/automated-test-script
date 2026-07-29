
import subprocess
import os
import winreg


def is_vc_runtime_ready():
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64") as key:
            return winreg.QueryValueEx(key, "Installed")[0] == 1
    except:
        return False

def silent_install(exe_path: str, args: str = "/install /quiet /norestart"):
    """
    通用 exe 静默安装方法

    :param exe_path: exe 完整路径
    :param args: 安装参数，例如 "/install /quiet /norestart"
    """
    if not os.path.exists(exe_path):
        raise FileNotFoundError(exe_path)

    cmd = f'"{exe_path}" {args}'
    subprocess.run(
        cmd,
        shell=True,
        creationflags=subprocess.CREATE_NO_WINDOW
    )


