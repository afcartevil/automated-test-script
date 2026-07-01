import os
import subprocess
from powertrde.utils.trde import adb
from tests.current_analysis.phoneconfig import PhoneConfig
"""
https://transsioner.feishu.cn/wiki/wikcnTlocGBThNxd7xLSJgA6UUf
"""
def oobe_complete(phone :PhoneConfig):
    adb.exec_cmd(phone.serial, 'settings put secure user_setup_complete 1')
    adb.exec_cmd(phone.serial, 'settings put global device_provisioned 1')
    adb.exec_cmd(phone.serial, 'reboot')

def flash_rom(phone :PhoneConfig, path:str, stage='Open', expack=''):
    serial = phone.serial
    script_dir = os.path.dirname(os.path.abspath(__file__))
    update_exe = os.path.join(script_dir, "device_update\device_update.exe")
    if not os.path.exists(update_exe):
        phone.logerror(f"错误：找不到device_update.exe，路径：{update_exe}")
        return False

    phone.u2d_helper.restart_settings_activity()
    
    # 构建完整的命令行字符串（确保路径和参数正确处理空格）
    if expack == '':
        command = f'{update_exe} -p {path} -s {serial} -stage {stage}'
    else:
        command = f'{update_exe} -p {path} -s {serial} -stage {stage} -rp {expack}'

    result = subprocess.run(command, 
                        shell=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        encoding='gbk')

    if phone.debug:
        phone.loginfo(f"执行命令: {command}\n: {result.returncode}")
    
    return True if result.returncode == 0 else False
