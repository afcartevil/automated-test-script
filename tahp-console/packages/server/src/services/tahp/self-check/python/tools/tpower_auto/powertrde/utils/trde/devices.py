import asyncio
import time
from abc import ABC, abstractmethod
from typing import List, Optional

from powertrde.utils.trde import adb, control_tran_soc as ctr, trde_utils
from powertrde.utils.trde.logs import log_exception, log


class Device:
    def __init__(self):
        self.ctrl_index = 0

        self.CTR_PC_PORT = 0
        self.CTR_TA_PORT = 1

        self.device_id = ''
        self.model = ''
        self.android_version = ''
        self.rom_version = ''
        self.cpu = ''
        self.status_str = ''
        self.pc_tick_gap = 0  # pc_tick - device_tick
        self.started_sec = 0
        self.is_wifi_device = False
        self.serial_no = ''
        self.brand = ''
        self.is_sprd = False

        self.power_z_index = -1

    def to_dict(self):
        return {
            'device_id': self.device_id,
            'model': self.model,
            'android_version': self.android_version,
            'rom_version': self.rom_version,
            'cpu': self.cpu,
            'pc_tick_gap': self.pc_tick_gap,
            'serial_no': self.serial_no,
            'wifi_device': self.is_wifi_device,
            'brand': self.brand,
            'is_sprd': self.is_sprd,
        }

    def read_device_info(self):
        assert self.device_id
        self.model = adb.device_model(self.device_id)
        self.android_version = adb.device_android_version(self.device_id)
        self.rom_version = adb.get_device_rom_version(self.device_id)
        self.cpu = adb.device_cpu_abi(self.device_id)
        self.pc_tick_gap = adb.pc_time_tick_gap(self.device_id)
        self.started_sec = int(time.time() - adb.started_sec(self.device_id))
        self.serial_no = adb.read_serial_no(self.device_id)
        self.brand = adb.get_device_brand(self.device_id)
        self.is_sprd = adb.is_spreadtrum(self.device_id)

    def connect_ta(self, index=0):
        ctr.connect(self.ctrl_index, self.CTR_TA_PORT + index)
        self.status_str = '已连接TA'

    async def wait_device_connect_pc(self, timeout: int):
        def adb_find_device():
            if self.device_id:
                return adb.device_exist(self.device_id)
            else:
                return len(adb.adb_devices()) > 0

        end_time = asyncio.get_event_loop().time() + timeout
        while True:
            if adb_find_device():
                return
            if asyncio.get_event_loop().time() >= end_time:
                raise Exception(f"设备没有在{timeout}秒内连接到PC")
            await asyncio.sleep(0.5)

    def connect_pc(self, disconnect_first: bool = True):
        if disconnect_first:
            self.disconnect()
            time.sleep(1)
        self.connect_pc_fast()
        if self.device_id:
            adb.wait_device(self.device_id)
        else:
            time.sleep(2)

    def disconnect(self):
        ctr.disconnect(self.ctrl_index)
        self.status_str = '已断开所有'

    def connect_ta_fast(self, index=0):
        ctr.connect_fast(self.ctrl_index, self.CTR_TA_PORT + index)
        self.status_str = '已连接TA'

    def connect_pc_fast(self):
        ctr.connect_fast(self.ctrl_index, self.CTR_PC_PORT)
        self.status_str = '已连接PC'

    def disconnect_fast(self):
        ctr.disconnect_fast(self.ctrl_index)
        self.status_str = '已断开所有'

    def get_summery_str(self):
        s = f'{self.serial_no} / {self.model} / {self.cpu} / android {self.android_version} / {self.rom_version}'
        if self.is_wifi_device:
            s += ' / adb connected with wifi'
        if self.is_sprd:
            s += ' / is sprd'
        return s

    def connect_status_str(self):
        return self.status_str

    def power_z_start_record(self, csv_dir):
        csv = ''
        if self.power_z_index >= 0:
            from powertrde.utils.trde.control_tran_soc import power_z_start_record
            csv = power_z_start_record(self.ctrl_index, csv_dir)
        return csv

    def power_z_stop_record(self):
        if self.power_z_index >= 0:
            from powertrde.utils.trde.control_tran_soc import power_z_stop_record
            power_z_stop_record(self.ctrl_index)


class IBindDevice(ABC):
    @property
    @abstractmethod
    def device(self) -> Optional[Device]:
        pass

    @device.setter
    @abstractmethod
    def device(self, device: Optional[Device]):
        pass

    def set_connected_device_by_id(self, device_id: str, assert_must_found: bool = True) -> Optional[Device]:
        device = get_device(device_id)
        if device is None and assert_must_found:
            raise Exception(f"Device with id '{device_id}' not found.")
        self.device = device
        return self.device

    def set_connected_first_device(self, assert_must_one_device: bool = True) -> Optional[Device]:
        _devices = get_devices()
        if assert_must_one_device:
            if len(_devices) == 0:
                raise Exception("There are no device connected.")
            if len(_devices) > 1:
                raise Exception("There are more than one device connected.")
        if len(_devices) > 0:
            self.device = _devices[0]
        else:
            self.device = None
        return self.device


class DeviceNoCtr(Device):
    def connect_ta(self, index=0):
        self.status_str = '连接PC,无TRDE测试盒'

    def connect_pc(self, disconnect_first: bool = True):
        self.status_str = '连接PC,无TRDE测试盒'

    def disconnect(self):
        self.status_str = '连接PC,无TRDE测试盒'

    def connect_ta_fast(self, index=0):
        self.status_str = '连接PC,无TRDE测试盒'

    def connect_pc_fast(self):
        self.status_str = '连接PC,无TRDE测试盒'

    def disconnect_fast(self):
        self.status_str = '连接PC,无TRDE测试盒'


class _Devices:
    g_instance = None

    def __init__(self, device_count=-1, empty_device_for_debug=False):
        # 这里有一个BUG，暂时不想查，所以先禁用adb_kill_server，毕竟目前还没有用到 WIFI ADB
        # wifi_devices = adb.adb_kill_server()
        wifi_devices = []
        self.devices: List[Device] = []

        if empty_device_for_debug:
            self.devices.append(DeviceNoCtr())
            return

        try:
            ctr_num = ctr.init_ctrs()
        except AssertionError:
            ctr_num = 0
        except BaseException as e:
            log_exception(e)
            ctr_num = 0

        if not ctr_num:
            self._init_devices_no_ctr()
        elif wifi_devices:
            self._init_wifi_devices(ctr_num, wifi_devices)
        else:
            self._init_devices(ctr_num, device_count)

        log(f'----> read {len(self.devices)} devices: ')
        for d in self.devices:
            d.is_wifi_device = True if d.device_id in wifi_devices else False
            d.read_device_info()
            log(f'  {d.device_id}    {d.get_summery_str()}')

        device_id_list = [d.device_id for d in self.devices]
        trde_utils.save_yml([d.to_dict() for d in self.devices], trde_utils.DEVICES_YML_FILE)

        assert len(set(device_id_list)) == len(device_id_list), \
            f'有至少2台id相同的手机: {str([did for did in set(device_id_list) if device_id_list.count(did) > 1])}'

    def _init_devices_no_ctr(self):
        # devices connect to pc direct without transsion soc
        device_ids = adb.adb_devices()
        assert device_ids, "无TRDE测试盒，请连接手机到电脑"

        for device_id in device_ids:
            log(f'手机直接连接PC，无TRDE测试盒: {device_id}')
            d = DeviceNoCtr()
            d.device_id = device_id
            self.devices.append(d)

    def _init_devices(self, ctr_num, device_count):
        from powertrde.utils.trde.control_tran_soc import power_z_is_charging, power_z_exist

        devices = []
        for i in range(ctr_num):
            log(f'device.init {i}')
            d = Device()
            d.ctrl_index = i
            d.disconnect()
            devices.append(d)

        time.sleep(2)
        powerz_num = device_count if device_count > 0 else ctr_num
        powerz_list = [i for i in range(powerz_num)]
        for i, d in enumerate(devices):
            devices_0 = adb.adb_devices()
            d.connect_pc()
            time.sleep(3)
            devices_1 = adb.adb_devices()
            ds = list(set(devices_1) - set(devices_0))
            if len(ds) == 1:
                self.devices.append(d)
                d.device_id = ds[0]

            if power_z_exist():
                d.power_z_index = [pz_i for pz_i in powerz_list if power_z_is_charging(pz_i)][0]
                powerz_list.remove(d.power_z_index)
                log(f'device {d.device_id} 匹配到了 power-z')

        if device_count > 0:
            assert len(self.devices) == device_count, f'手机数量不对，应该是{device_count}台，实际是{len(self.devices)}台'
        else:
            assert len(self.devices) == ctr_num, \
                f"有{ctr_num}块TRDE测试盒，但是只有{len(self.devices)}台手机!"
        if power_z_exist():
            assert len(powerz_list) == 0, f'有{len(powerz_list)}个 power-z 没有找到对应的手机!'

    def _init_wifi_devices(self, ctr_num, wifi_devices):
        assert len(wifi_devices) == ctr_num, \
            f'存在adb通过wifi连接的手机，但是数量{len(wifi_devices)}，和TRDE测试盒的数量{ctr_num}不一致'

        for i in range(ctr_num):
            log(f'_init_wifi_devices() {i}')
            d = Device()
            d.ctrl_index = i
            d.disconnect()
            self.devices.append(d)

        device_ids = [d for d in wifi_devices]
        for i, d in enumerate(self.devices):
            d.connect_ta()
            for device_id in wifi_devices:
                if adb.is_charging(device_id):
                    d.device_id = device_id
                    device_ids.remove(device_id)
                    break
            d.disconnect()

        assert not device_ids, f"匹配TRDE测试盒和wifi device 出错， {str(device_ids)} 未匹配"


def get_devices(device_count=-1):
    if not _Devices.g_instance:
        try:
            _Devices.g_instance = _Devices(device_count)
        except BaseException as e:
            log_exception(e)
            raise
    return _Devices.g_instance.devices


def get_executed_devices_count():
    cnt = len(_Devices.g_instance.devices) if _Devices.g_instance else 0
    return cnt


def empty_devices_for_debug():
    if not _Devices.g_instance:
        _Devices.g_instance = _Devices(empty_device_for_debug=True)
    d = _Devices.g_instance.devices[0]
    d.device_id = '0000000'
    d.model = 'itel P665L'
    return _Devices.g_instance.devices


def get_device(device_id):
    for d in get_devices():
        if device_id == d.device_id:
            return d
    return None


def purge_instance():
    _Devices.g_instance = None


def check_device_ids_to_purge_instance(device_ids: list):
    if _Devices.g_instance:
        try:
            ds = get_devices(len(device_ids))
            ds_ids = [d.device_id for d in ds]
            for device_id in device_ids:
                if device_id not in ds_ids:
                    purge_instance()
                    break
        except:
            purge_instance()


def _test():
    devices = get_devices()
    # print(devices)
    for d in devices:
        from powertrde.utils.trde.adb import poweron_screen_and_unlock, oobe_exit
        poweron_screen_and_unlock(d.device_id)
        oobe_exit(d.device_id)


if __name__ == '__main__':
    _test()
