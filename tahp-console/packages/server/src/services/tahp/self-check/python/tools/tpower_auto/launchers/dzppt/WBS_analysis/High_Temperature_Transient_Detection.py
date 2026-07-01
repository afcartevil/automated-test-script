import sys
import os
import time

def add_path_to_python_env():
    """
    将项目根目录添加到Python环境变量中，确保能导入项目内的模块
    """
    if getattr(sys, 'frozen', False):
        return
    # 计算项目根目录路径
    root_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    if root_path not in sys.path:
        sys.path.insert(0, root_path)
    # 添加plugins目录到路径
    plugins_path = os.path.join(root_path, 'plugins')
    if os.path.exists(plugins_path):
        sys.path.insert(0, plugins_path)

# 添加路径到Python环境
add_path_to_python_env()

# 现在可以导入项目内的模块了
from powertrde.utils.trde import adb
from powertrde.framework.logs_protocol import logs_p
from powertrde.env import PROJ_DIR

# 切换到项目根目录
os.chdir(PROJ_DIR)

class HighTemperatureTransientDetector:
    def __init__(self, device_serial, platform):
        self.serial = device_serial
        self.platform = platform
        self._mylog = logs_p()
    
    def loginfo(self, text):
        self._mylog.log(f"[{self.serial}] - {text}")
    
    def logerror(self, text):
        self._mylog.log_error(f"[{self.serial}] - {text}")
    
    def detect_high_temperature_transient(self):
        """
        高温瞬态检测功能
        1. 设置45°C温度
        2. 检查ThermalUx状态
        3. 根据平台类型执行不同的CPU频率监控
        4. 恢复正常温度
        5. 清理进程
        """
        try:
            # 设置45°C温度
            self.loginfo("开始高温瞬态检测 - 设置45°C温度")
            adb.exec_cmd(self.serial, "dumpsys activity service com.transsion.usf.UsfMainService -thermal temperature_debug_on 45000")
            time.sleep(1)
            
            # 检查ThermalUx状态
            self.loginfo("检查ThermalUx状态")
            thermalux_output = adb._exe_adb_cmd(self.serial, "dumpsys activity service com.transsion.usf.UsfMainService -thermal thermal_engine config | findstr \"ThermalUx\"")
            self.loginfo(f"ThermalUx状态: {thermalux_output}")
            time.sleep(3)
            
            # 根据平台类型执行不同的监控命令
            if self.platform == "qcom":
                self.loginfo("高通平台")
                for _ in range(3):
                    adb.exec_cmd(self.serial, "nohup sh -c 'sleep 1 && am start -n com.android.settings/.Settings && sleep 1 && am force-stop com.android.settings' > /dev/null 2>&1 &")
                    output1 = adb._exe_adb_cmd(self.serial, "for i in $(seq 1 10); do cat /sys/devices/system/cpu/cpufreq/policy*/scaling_max_freq ; echo \"========\"; sleep 0.3 ; done")
                    self.loginfo(output1)

            elif self.platform == "mtk":
                self.loginfo("MTK平台")
                adb.exec_cmd(self.serial, "nohup sh -c 'sleep 2 && am start -n com.android.settings/.Settings && sleep 1 && am force-stop com.android.settings' > /dev/null 2>&1 &")
                output = adb._exe_adb_cmd(self.serial, "for i in $(seq 1 15); do cat /sys/devices/system/cpu/cpufreq/policy*/scaling_cur_freq ; echo \"========\"; sleep 0.3 ; done")
                self.loginfo(output)
            elif self.platform == "sprd":
                self.loginfo("展锐平台 - 不执行监控命令")
            else:
                self.loginfo("未知平台 - 不执行监控命令")
            
            time.sleep(1)
            # 恢复正常温度
            self.loginfo("恢复25°C正常温度")
            adb.exec_cmd(self.serial, "dumpsys activity service com.transsion.usf.UsfMainService -thermal temperature_debug_on 25000")

            # 终止所有相关进程
            self.loginfo("终止监控进程")
            adb.exec_cmd(self.serial, "pkill -f 'while true; do cat'")
            
            self.loginfo("高温瞬态检测完成")
            
        except Exception as e:
            self.logerror(f"高温瞬态检测失败: {str(e)}")

def get_first_device_serial():
    """
    获取第一个连接的设备序列号
    """
    devices = adb.adb_devices()
    if devices:
        return devices[0]
    return None

def get_device_platform(serial):
    """
    获取设备的CPU平台类型
    使用adb模块中现有的平台检测方法，这些方法更加可靠
    """
    try:
        # 使用adb模块中现有的平台检测方法
        if adb.is_mtk(serial):
            return "mtk"
        elif adb.is_qcom(serial):
            return "qcom"
        elif adb.is_sprd(serial):
            return "sprd"
        else:
            # 如果上述方法都无法检测到平台，尝试使用备用方法
            cpu_info = adb._exe_adb_cmd(serial, "getprop ro.product.board")
            cpu_board = ''.join(cpu_info).strip().lower()
            
            # 打印详细的CPU信息用于调试
            print(f"备用平台检测 - CPU Board: {cpu_board}")
            
            if 'msm' in cpu_board or 'sdm' in cpu_board or 'sm' in cpu_board:
                return "qcom"
            elif 'mt' in cpu_board or 'helio' in cpu_board:
                return "mtk"
            elif 'sp' in cpu_board or 'sc' in cpu_board:
                return "sprd"
            else:
                # 尝试更多的设备属性
                try:
                    soc_manufacturer = adb._exe_adb_cmd(serial, "getprop ro.soc.manufacturer")
                    soc_manufacturer = ''.join(soc_manufacturer).strip().lower()
                    print(f"备用平台检测 - SOC Manufacturer: {soc_manufacturer}")
                    
                    if 'qualcomm' in soc_manufacturer:
                        return "qcom"
                    elif 'mediatek' in soc_manufacturer:
                        return "mtk"
                    elif 'spreadtrum' in soc_manufacturer:
                        return "sprd"
                except:
                    pass
                    
                return "unknown"
    except Exception as e:
        print(f"获取平台类型失败: {str(e)}")
        return "unknown"

if __name__ == "__main__":
    # 获取第一个连接的设备
    device_serial = get_first_device_serial()
    
    if not device_serial:
        print("未检测到连接的设备")
        exit(1)
    
    # 获取设备平台
    platform = get_device_platform(device_serial)
    print(f"检测到设备: {device_serial}, 平台: {platform}")
    
    # 创建检测器实例并执行高温瞬态检测
    detector = HighTemperatureTransientDetector(device_serial, platform)
    detector.detect_high_temperature_transient()