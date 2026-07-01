import os
import subprocess
import json

class TPowerTool:
    # 该类只能初始化一个实例
    def __new__(cls, *args, **kwargs):
        if not hasattr(cls, 'instance'):
            cls.instance = super(TPowerTool, cls).__new__(cls)
        return cls.instance
    
    def __init__(self):
        pass

    def _runapm(self, pmsn, cmd, debug = False):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        apm_path = os.path.join(script_dir, "APM.exe")
        
        if not os.path.exists(apm_path):
            print(f"错误：找不到APM.exe，路径：{apm_path}")
            return None

        # 构建完整的命令行字符串（确保路径和参数正确处理空格）
        command = f'{apm_path} {pmsn} {cmd}'
        
        # 使用subprocess.run替代Popen，更简单可靠
        result = subprocess.run(command, 
                            shell=True,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            encoding='gbk')

        output = result.stdout
        if debug:
            print(f"执行命令: {command}\n输出: {output}")

        if output and "fail" not in output:
            return output
        else:
            return None
    
    # 返回数据为json格式
    '''
    {
    "44491": {"measure": false, "usb": false},
    "12002": {"measure": true, "usb": true}
    }
    '''
    def getdevicelist(self):
        # 调用runapm，执行命令“deviceslist”
        ret = self._runapm("default", "deviceslist")
        # json 不为空，就转为字典
        if ret is not None:
            ret = json.loads(ret)
            return ret
        else:
            print("获取设备列表失败，请检测TPowerTool是否已连接设备")
            return None

    def savefile(self, pmsn, filedir = None):
        # 调用runapm，执行命令“savefile filename”
        command = f"savefile {filedir}" if filedir is not None else "savefile"
        ret = self._runapm(pmsn, command)
        if ret is not None:
            return ret
        else:
            print("保存文件失败，请检测TPowerTool是否已连接设备")
            return False
    
    def setvolt(self, pmsn, volot=4):
        # 调用runapm，执行命令“power 4V”
        ret = self._runapm(pmsn, f"power {volot}V")
        if ret is not None:
            return True
        else:
            print("电压设置失败，请检测TPowerTool是否已连接设备")
            return False

    def connectusb(self, pmsn):
        # 调用runapm，执行命令“usbadb connect”
        ret = self._runapm(pmsn, "usbadb connect")
        if ret is not None:
            return True
        else:
            print("USB连接失败，请检测TPowerTool是否已连接设备")
            return False

    def disconnectusb(self, pmsn):
        # 调用runapm，执行命令“usbadb disconnect”
        ret = self._runapm(pmsn, "usbadb disconnect")
        if ret is not None:
            return True
        else:
            print("USB断开失败，请检测TPowerTool是否已连接设备")
            return False

    def setfilterperiod_s(self, pmsn, time_s):
        command = f'filterperiod {time_s} s'
        ret = self._runapm(pmsn, command)
        if ret is not None:
            return True
        else:
            print("设置滤波周期失败，请检测TPowerTool是否已连接设备")
            return False

    def measurestart(self, pmsn):
        # 调用runapm，执行命令“usbadb disconnect”
        ret = self._runapm(pmsn, "measure start")
        if ret is not None:
            return True
        else:
            print("测量启动失败，请检测TPowerTool是否已连接设备")
            return False

    # 测量成功返回数据格式
    # success
    # time_ms:6500
    # avgcurrent_mA:35.8
    # filterperiod:1000
    # filterstd:4.2
    # filtermax:45.6
    # filtermin:28.5
    # filtermode:35.7
    def measurestop(self, pmsn):
        # 调用runapm，执行命令“usbadb disconnect”
        ret = self._runapm(pmsn, "measure stop")
        if ret is not None and "success" in ret:
            # 解析返回结果
            ret_dict = {}
            for line in ret.splitlines():
                if ':' in line:  # 确保行包含冒号分隔符
                    key, value = line.split(':', 1)  # 只分割第一个冒号
                    ret_dict[key.strip()] = value.strip()
            return ret_dict  # 返回包含所有测量结果的字典
        else:
            print("测量停止失败，请检测TPowerTool是否已连接设备")
            return None