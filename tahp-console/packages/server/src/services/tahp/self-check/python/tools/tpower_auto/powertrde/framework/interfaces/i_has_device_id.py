from dataclasses import dataclass, field
from typing import Union, Optional, Callable, Any

from powertrde.framework.lazy_device_id import LazyDeviceID
from powertrde.utils.trde import adb


@dataclass
class PhoneDeviceInfo:
    device_id: str = ''
    device_sn: str = ''
    device_model: str = ''
    device_brand: str = ''
    device_rom_version: str = ''
    gap_time_to_pc: float = 0
    other_infos: dict = field(default_factory=dict)

    def __getstate__(self):
        """
        返回一个 dict，作为 pickle 的“状态”。
        在这里把 _thread 字段剔除，就不会尝试序列化它。
        """
        state = self.__dict__.copy()
        # 跳过不可序列化字段
        if "_other_info_factories" in state:
            del state["_other_info_factories"]
        return state

    def __setstate__(self, state):
        """
        pickle 恢复时调用。这里先把原来的字段赋回，
        然后可以重新初始化被跳过的字段。
        """
        self.__dict__.update(state)
        # 恢复或重建 _other_info_factories 字段
        self._other_info_factories = []

    def __post_init__(self):
        self._other_info_factories = []
        self.refresh_with_device_id(self.device_id)

    def register_other_info_factory(self, info_key: str, factory: Callable[[str], Any], perform_factory=False):
        self._other_info_factories.append((info_key, factory))
        if perform_factory and self.device_id:
            self.other_infos[info_key] = factory(self.device_id)

    def refresh_with_device_id(self, device_id: str):
        self.device_id = device_id
        self.refresh()

    def refresh(self):
        if self.device_id:
            if not adb.is_adb_connected(self.device_id):
                raise Exception(f'Phone device {self.device_id} is disconnected...')
            self.device_sn = adb.read_serial_no(self.device_id)
            self.device_model = adb.device_model_simple(self.device_id)
            self.device_brand = adb.get_device_brand(self.device_id)
            self.device_rom_version = adb.get_device_rom_version(self.device_id)
            self.gap_time_to_pc = adb.measure_device_time_offset_ms(self.device_id) / 1000.0
            self.other_infos.clear()
            for info_factory in self._other_info_factories:
                self.other_infos[info_factory[0]] = info_factory[1](self.device_id)
        else:
            self.device_sn = ''
            self.device_model = ''
            self.device_brand = ''
            self.device_rom_version = ''
            self.gap_time_to_pc = 0
            self.other_infos.clear()

    def __str__(self) -> str:
        return f"{self.device_model}|{self.device_sn}|{self.device_rom_version}"


class IHasDeviceID:
    def __init__(self):
        super().__init__()
        self._device_id: Union[str, LazyDeviceID, None] = ''
        self._device_info: Optional[PhoneDeviceInfo] = None

    def get_device_id(self):
        if isinstance(self._device_id, str):
            return self._device_id
        return str(self._device_id)

    def set_device_id(self, value: Union[str, LazyDeviceID, None]):
        self._device_id = value
        if self._device_info:
            self._device_info.device_id = value
            self._device_info.refresh()

    @property
    def device_id(self):
        return self.get_device_id()

    @device_id.setter
    def device_id(self, value: Union[str, LazyDeviceID, None]):
        self.set_device_id(value)

    @property
    def device_info(self):
        if self._device_info is None:
            self._device_info = PhoneDeviceInfo(device_id=self.device_id)
        return self._device_info

    @property
    def device_sn(self):
        return self.device_info.device_sn

    @property
    def device_model(self):
        return self.device_info.device_model

    @property
    def device_brand(self):
        return self.device_info.device_brand

    @property
    def device_rom_version(self):
        return self.device_info.device_rom_version

    @property
    def is_device_connected(self):
        return bool(self.device_id and adb.is_adb_connected(self.device_id))


class IHasCopilotDeviceID:
    def __init__(self):
        super().__init__()
        self._c_device_id: Union[str, LazyDeviceID, None] = ''
        self._c_device_sn: str = ''

    def get_c_device_id(self):
        if isinstance(self._c_device_id, str):
            return self._c_device_id
        return str(self._c_device_id)

    def set_c_device_id(self, value: Union[str, LazyDeviceID, None]):
        self._c_device_id = value
        self._c_device_sn = ''

    @property
    def c_device_id(self):
        return self.get_c_device_id()

    @c_device_id.setter
    def c_device_id(self, value: Union[str, LazyDeviceID]):
        self.set_c_device_id(value)

    @property
    def c_device_sn(self):
        assert self.c_device_id, 'c_device_id must not be empty when use c_device_sn.'
        if not self._c_device_sn:
            self._c_device_sn = adb.read_serial_no(self.c_device_id)
        return self._c_device_sn

    @property
    def is_copilot_connected(self):
        return bool(self.c_device_id and adb.is_adb_connected(self.c_device_id))


class IHasObserveDeviceID:
    def __init__(self):
        super().__init__()
        self._o_device_id: Union[str, LazyDeviceID, None] = ''
        self._o_device_sn: str = ''

    def get_o_device_id(self):
        if isinstance(self._o_device_id, str):
            return self._o_device_id
        return str(self._o_device_id)

    def set_o_device_id(self, value: Union[str, LazyDeviceID, None]):
        self._o_device_id = value
        self._o_device_sn = ''

    @property
    def o_device_id(self):
        return self.get_o_device_id()

    @o_device_id.setter
    def o_device_id(self, value: Union[str, LazyDeviceID]):
        self.set_o_device_id(value)

    @property
    def o_device_sn(self):
        assert self.o_device_id, 'o_device_id must not be empty when use o_device_sn.'
        if not self._o_device_sn:
            self._o_device_sn = adb.read_serial_no(self.o_device_id)
        return self._o_device_sn

    @property
    def is_copilot_connected(self):
        return bool(self.o_device_id and adb.is_adb_connected(self.o_device_id))
