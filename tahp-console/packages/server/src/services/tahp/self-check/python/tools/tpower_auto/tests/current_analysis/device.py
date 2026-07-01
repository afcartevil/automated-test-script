import threading
from time import sleep
from plugins.pytpowertool.tpowertool import TPowerTool
from powertrde.utils.trde import adb
from powertrde.framework.logs_protocol import logs_p

class Device():
    # 类变量，用于存储全局共享的Manager和设备数据
    _lock = threading.RLock()
    
    # 该类只能初始化一个实例
    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if not hasattr(cls, 'instance'):
                cls.instance = super(Device, cls).__new__(cls)
        return cls.instance

    def __init__(self):
        # 添加初始化保护：仅首次实例化时执行
        with self._lock:
            if not hasattr(self, '_initialized'):  # 检查是否已初始化
                self.power_tool = TPowerTool()
                self.pmsn_deviceid_dict = {}
                self.tpmnum = 0
                self._initialized = True  # 标记为已初始化

        
    def update(self):
        with self._lock:
            deviceslist = self.power_tool.getdevicelist()
            if not deviceslist:
                self.pmsn_deviceid_dict = {}
                return {}
            for pmsn, info in list(deviceslist.items()):
                if pmsn in self.pmsn_deviceid_dict:
                    # 正在使用中的设备，直接复制信息
                    if(self.pmsn_deviceid_dict[pmsn]['measure'] == True or self.pmsn_deviceid_dict[pmsn]['busy'] == True):
                        deviceslist[pmsn] = self.pmsn_deviceid_dict[pmsn]
                        continue
                    # 设备空闲，通过serial号校验信息
                    serialno = adb.exec_cmd(self.pmsn_deviceid_dict[pmsn]['serial'] ,"getprop ro.serialno")
                    if serialno and serialno[0].strip() == self.pmsn_deviceid_dict[pmsn]['serial']:
                        deviceslist[pmsn] = self.pmsn_deviceid_dict[pmsn]
                        continue
                # 更新设备serial、model
                self.power_tool.disconnectusb(pmsn)
                sleep(0.5)
                adbsn1 = adb.adb_devices_online()
                self.power_tool.connectusb(pmsn)
                sleep(1.5)
                adbsn2 = adb.adb_devices_online()
                new_serial = None
                new_model = None
                for serial in adbsn2:
                    if serial not in adbsn1:
                        new_serial = serial.split()[0]
                        new_version = adb.get_device_rom_version(new_serial)
                        if new_version:
                            new_model = new_version.split('-')[0]
                            new_version = new_version.strip().replace("(","_").replace(")","")
                        break
                if new_model:
                    deviceslist[pmsn]['serial'] = new_serial
                    deviceslist[pmsn]['model'] = new_model
                    deviceslist[pmsn]['version'] = new_version
                    deviceslist[pmsn]['busy'] = False
                    deviceslist[pmsn]['last_gesture'] = ''  # 上次测量的手势
                    deviceslist[pmsn]['measurecnt'] = 0     # 测量次数
                    deviceslist[pmsn]['excel'] = {}         # 输出信息
                    logs_p().log(f"[{pmsn}] - Add model={new_model} {new_version} serial={new_serial}")
                else:
                    del deviceslist[pmsn]
                    logs_p().log_warning(f"[{pmsn}] - 未检测到手机")
                    
            self.pmsn_deviceid_dict = deviceslist
        return self.pmsn_deviceid_dict
    def test(self, pmsn):
        cnt = 0
        fast = True
        while True:
            cnt += 1
            if(cnt % 100 == 0):
                fast = False
            else:
                fast = True
            logs_p().log(f"测试第 <<< {cnt} >>> 次")
            self.power_tool.connectusb(pmsn)
            if fast:
                self.power_tool.setfilterperiod_s(pmsn, 1)
                sleep(1)
                exec_successfully, exec_out = adb.exec_cmd_timeout("adb shell ls /sdcard/MyAlbums/naxienian/")
                if exec_successfully and "1080.mp4" in exec_out:
                    logs_p().log(f"文件有效")
            else :
                self.power_tool.setfilterperiod_s(pmsn, 120)
                logs_p().log(f"下载视频")
                adb.exec_cmd_timeout("adb pull /sdcard/MyAlbums/naxienian/1080.mp4 ../output/")
            self.power_tool.disconnectusb(pmsn)
            logs_p().log(f"测量功耗")
            self.power_tool.measurestart(pmsn)
            if fast:
                sleep(10)
            else :
                sleep(300)
            self.power_tool.measurestop(pmsn)
        return False

    def usb_connect(self, pmsn):
        if pmsn in self.pmsn_deviceid_dict:
            if(self.pmsn_deviceid_dict[pmsn]['usb'] == True):
                return True
            self.power_tool.connectusb(pmsn)
            sleep(3)
            with self._lock:
                self.pmsn_deviceid_dict[pmsn]['usb'] = True
            return True
        return False
    
    def usb_disconnect(self, pmsn):
        if pmsn in self.pmsn_deviceid_dict:
            self.power_tool.disconnectusb(pmsn)
            with self._lock:
                self.pmsn_deviceid_dict[pmsn]['usb'] = False
            return True
        return False
    
    def start_measure(self, pmsn):
        with self._lock:
            if pmsn in self.pmsn_deviceid_dict:
                self.pmsn_deviceid_dict[pmsn]['measure'] = True
                self.power_tool.disconnectusb(pmsn)
                self.power_tool.measurestart(pmsn)
                return True
        return False
    
    def stop_measure(self, pmsn):
        with self._lock:
            if pmsn in self.pmsn_deviceid_dict:
                self.pmsn_deviceid_dict[pmsn]['measure'] = False
                ret =  self.power_tool.measurestop(pmsn)
                self.power_tool.connectusb(pmsn)
                return ret
        return None
    
    def savefile(self, pmsn, filedir = None):
        if pmsn in self.pmsn_deviceid_dict:
            ret = self.power_tool.savefile(pmsn, filedir)
            if ret is not None:
                return ret
        return False
    
    def set_filterperiod(self, pmsn, filterperiod):
        if pmsn in self.pmsn_deviceid_dict:
            self.power_tool.setfilterperiod_s(pmsn, filterperiod)
            return True
        return False
    
    def get_serial(self, pmsn):
        if pmsn in self.pmsn_deviceid_dict:
            return self.pmsn_deviceid_dict[pmsn]['serial']

        return None
        
    def get_version(self, pmsn):
        if pmsn in self.pmsn_deviceid_dict:
            return self.pmsn_deviceid_dict[pmsn]['version']

        return None
    
    # 模糊匹配model，忽略大小写
    def get_model(self, pmsn):
        if pmsn in self.pmsn_deviceid_dict:
            return self.pmsn_deviceid_dict[pmsn]['model']
        return None
    
    def lock(self, pmsn):
        with self._lock:
            if pmsn in self.pmsn_deviceid_dict:
                self.pmsn_deviceid_dict[pmsn]['busy'] = True
                return True
        return False
    
    def unlock(self, pmsn):
        with self._lock:
            if pmsn in self.pmsn_deviceid_dict:
                self.pmsn_deviceid_dict[pmsn]['busy'] = False
                return True
        return False

    def is_busy(self, pmsn):
        if pmsn in self.pmsn_deviceid_dict:
            return self.pmsn_deviceid_dict[pmsn]['busy']
        return False

    def set_keyvalue(self, pmsn, key, value):
        if pmsn not in self.pmsn_deviceid_dict:
            return False
        if(key is None):
            return False
        key = key.strip().lower()
        with self._lock:
            if key in self.pmsn_deviceid_dict[pmsn]:
                self.pmsn_deviceid_dict[pmsn][key] = value
                return True
            if key in self.pmsn_deviceid_dict[pmsn]['excel']:
                self.pmsn_deviceid_dict[pmsn]['excel'][key] = value
                return True

        return False

    def get_keyvalue(self, pmsn, key):
        if pmsn not in self.pmsn_deviceid_dict:
            return None
        if(key is None):
            return None
        key = key.strip().lower()
        if key  in self.pmsn_deviceid_dict[pmsn]:
            return self.pmsn_deviceid_dict[pmsn][key]
        if key in self.pmsn_deviceid_dict[pmsn]['excel']:
            return self.pmsn_deviceid_dict[pmsn]['excel'][key]

        return None
