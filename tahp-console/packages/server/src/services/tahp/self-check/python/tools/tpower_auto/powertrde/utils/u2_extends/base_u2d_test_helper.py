from functools import cached_property
from typing import Optional, Union

import uiautomator2

from powertrde.utils.trde import adb
from powertrde.utils.u2_extends import u2utils


class BaseU2DTestHelper:
    def __init__(self, u2d_or_device_id: Union[uiautomator2.Device, str]):
        super().__init__()
        self._u2d: Optional[uiautomator2.Device] = None
        self._bound_wifi_device_id = ''
        if isinstance(u2d_or_device_id, str):
            self._u2d = None
            self._device_id = u2d_or_device_id
        else:
            self._u2d = u2d_or_device_id
            self._device_id = u2d_or_device_id.serial
        self._und_u2 = None
        self._wifi_u2d = None
        self._wifi_und_u2 = None
        self.app_variant_dict = {}
        self.logic_variant_dict = {}
        self._wifi_adb_mode = False

    @property
    def is_wifi_adb_mode(self):
        return self._wifi_adb_mode

    def get_u2d(self):
        if self._wifi_adb_mode:
            if not self._wifi_u2d:
                self._wifi_u2d = u2utils.connect_u2_device(self.bound_wifi_device_id)
            return self._wifi_u2d
        else:
            if not self._u2d:
                assert self.device_id, f'Device ID must not be empty! My you not connect your device!'
                self._u2d = u2utils.connect_u2_device(self.device_id)
            return self._u2d

    @property
    def u2d(self):
        return self.get_u2d()

    @property
    def device_id(self):
        if self._wifi_adb_mode:
            return self._bound_wifi_device_id
        return self._device_id

    @property
    def bound_wifi_device_id(self):
        return self._bound_wifi_device_id

    @property
    def native_device_id(self):
        return self._device_id

    @cached_property
    def device_real_sn(self):
        return adb.read_serial_no(self.device_id)

    @property
    def is_native_wifi_adb(self):
        """原本的Device就是WIFI ADB吗（也就是传入的初始Device ID就是WIFI ADB吗，并非后续绑定的）"""
        return self.device_real_sn != self.device_id

    def bind_wifi_adb_id(self, wifi_adb_id: str):
        if wifi_adb_id:
            if not adb.is_adb_connected(wifi_adb_id):
                raise Exception(f'wifi adb {wifi_adb_id} is disconnected. Can not bind to this helper.')

            wifi_real_sn = adb.read_serial_no(wifi_adb_id)
            usb_real_sn = self._device_id

            if wifi_real_sn != usb_real_sn:
                raise Exception(f'WiFi adb "{wifi_adb_id}“ real sn is "{wifi_real_sn}", but your usb device sn is "{usb_real_sn}", not equals! Can not bind to this helper.')

        if self._bound_wifi_device_id != wifi_adb_id:
            self._wifi_u2d = None
            self._wifi_und_u2 = None
            self._bound_wifi_device_id = wifi_adb_id

    def switch_wifi_adb_mode(self, check_connection=True):
        if self._wifi_adb_mode:
            return
        assert self._bound_wifi_device_id, 'You must bind wifi adb id first!'
        if check_connection:
            assert adb.is_adb_connected(self._bound_wifi_device_id), f'WiFi adb {self._bound_wifi_device_id} is disconnected, can not switch to wifi adb mode.'
        self._wifi_adb_mode = True

    def switch_usb_adb_mode(self, check_connection=True):
        if check_connection:
            assert adb.is_adb_connected(self._device_id), f'USB adb {self._bound_wifi_device_id} is disconnected, can not switch to usb adb mode.'
        self._wifi_adb_mode = False

    @property
    def is_device_connected(self):
        return self.device_id and adb.is_adb_connected(self.device_id)

    def get_aw_app_variant_key(self, name: str, default_value=''):
        return self.app_variant_dict.get(name, default_value)

    def get_aw_logic_variant_key(self, name: str, default_value=''):
        return self.logic_variant_dict.get(name, default_value)
