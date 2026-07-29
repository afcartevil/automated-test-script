import os
from dataclasses import dataclass
from typing import cast, Union

from dz_remote.dz_adb_log_device import DzAdbLogDevice
from dz_remote.dz_client import DzClient
from dz_remote.uni_device_dz_seat import UniDeviceDzSeat
from powertrde import env
from tests.dzppt.aw.dzppt_u2d_helper import DzpptU2DTestHelper
from tpytest.scheme.scheme_test_env import get_scheme_env
from tpytest.u2_serial_provider_factory import U2SerialProviderFactory
from tpytest_extends.scheme.scheme_extend_test_env import SchemeExtendTestEnv


@dataclass
class PhoneStateCache:
    # 东舟工位编号
    seat_index: int
    # 是否开启了屏幕
    is_screen_on = True
    # 是否开启了Wifi
    is_wifi_on = True
    # 是否开启了飞行模式
    is_airplane_mode_on = False
    # 是否开启了vpn
    is_vpn_on = False
    # 是否软拔除了大陆sim卡
    is_china_sim_unplug = False
    # 是否开启了热点
    is_hotspot_on = False

    def reset(self):
        self.is_wifi_on = True
        self.is_airplane_mode_on = False
        self.is_vpn_on = False
        self.is_china_sim_unplug = False
        self.is_hotspot_on = False


class DzPptEnv(SchemeExtendTestEnv):
    option_user_u2d_helper_class_type = DzpptU2DTestHelper

    def __init__(self):
        self.phone_state_caches = {
            1: PhoneStateCache(seat_index=1),
            2: PhoneStateCache(seat_index=2)
        }
        self._selected_dz_seat_index = 1
        self._dz_client = None
        self._uni_device_dz = None
        self._last_power_monitor_handler = None
        super().__init__()

    @property
    def u2d_helper(self) -> DzpptU2DTestHelper:
        return cast(DzpptU2DTestHelper, super().u2d_helper)

    @property
    def c_u2d_helper(self) -> DzpptU2DTestHelper:
        return cast(DzpptU2DTestHelper, super().c_u2d_helper)

    @property
    def selected_dz_seat_index(self):
        return self._selected_dz_seat_index

    @property
    def has_caller_sensor(self):
        return env.get_user_env_arg('has_caller_sensor', False)

    @selected_dz_seat_index.setter
    def selected_dz_seat_index(self, value):
        if value != self._selected_dz_seat_index:
            self._selected_dz_seat_index = value
            self.dz_client.selected_seat_index = value
            _ = self.dz_client.seat
            self._uni_device_dz = None

    @property
    def sim_unplug_mode(self):
        return 1

    @property
    def selected_dz_seat_phone_state_cache(self):
        return self.phone_state_caches[self.selected_dz_seat_index]

    @property
    def dz_client(self):
        if not self._dz_client:
            self._dz_client = DzClient()
            self._dz_client.connect_dz()
            _ = self._dz_client.seat
        return self._dz_client

    @property
    def dz_seat(self):
        return self.dz_client.seat

    @property
    def runtime_phase(self):
        return super().runtime_phase

    @runtime_phase.setter
    def runtime_phase(self, value):
        env.set_user_runtime_phase(value)
        # value 取值目前有：checking, pretest, case
        self.send_vm_event('runtime_phase', value)

    @property
    def is_u2d_debug_mode(self):
        return 'u2d' in self.debug_modes

    @property
    def is_no_unlink_usb_debug_mode(self):
        return 'no_unlink_usb' in self.debug_modes

    def _gen_logger(self):
        super()._gen_logger()
        device_logger = DzAdbLogDevice(device_name='main', dz_seat=lambda: self.dz_seat, device_id=lambda: U2SerialProviderFactory(self))
        self._logger.device.devices[device_logger.device_name] = device_logger

    @property
    def uni_device(self):
        if 'u2d' in env.get_user_env_debug_modes():
            return self.uni_device_u2
        else:
            return self.uni_device_dz

    @property
    def uni_device_u2(self):
        return self.u2d_helper.und_u2

    @property
    def uni_device_dz(self):
        if not self._uni_device_dz:
            self._uni_device_dz = UniDeviceDzSeat(self.dz_seat)
        return self._uni_device_dz

    @property
    def last_power_monitor_handler(self):
        return self._last_power_monitor_handler

    def gen_power_monitor_handler(self, save_file: str, power_tool_class_type: type):
        if self._last_power_monitor_handler:
            self._last_power_monitor_handler.powertoolcmd_stop()
            self._last_power_monitor_handler = None

        os.makedirs(os.path.dirname(save_file), exist_ok=True)
        self._last_power_monitor_handler = power_tool_class_type(save_file)
        return self._last_power_monitor_handler

    def clear_power_monitor_handler(self):
        self._last_power_monitor_handler = None

    @property
    def recorded_search_box_pos_y_or_none(self) -> Union[float, None]:
        return self.preset_record_groups.main().get_with_fallback('search_box_pos_y', None)

    @property
    def recorded_az_pos(self) -> tuple[float, float]:
        return self.preset_record_groups.main().get_with_fallback('az_pos', None)

    @property
    def device_static_info(self):
        from tests.dzppt.aw.phone_static_info import PhoneStaticInfo
        return PhoneStaticInfo.get_default_table().get_info(self.device_model)

# ------------------------------------------------------------------------------


def get_dzppt_env() -> DzPptEnv:
    env_ins = get_scheme_env()
    if not isinstance(env_ins, DzPptEnv):
        raise Exception(f'Current scheme env class is {env_ins.__class__.__name__} but not {DzPptEnv.__name__}')
    return env_ins
