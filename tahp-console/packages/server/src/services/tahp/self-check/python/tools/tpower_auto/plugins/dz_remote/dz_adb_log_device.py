import os
import tempfile
from typing import Union, Callable

from dz_remote.dz_lazy_seat import DzLazySeat
from dz_remote.dz_seat import DzSeat
from powertrde.framework.lazy_device_id import CachedSerialProvider, SerialProvider
from powertrde.framework.tran_logger.log_device import AdbLogDevice
from powertrde.utils.trde import adb


class DzAdbLogDevice(AdbLogDevice):
    def __init__(self, dz_seat: Union[DzSeat, Callable[[], DzSeat]], device_id: Union[None, str, SerialProvider, CachedSerialProvider, Callable[[], str], Callable[[], SerialProvider], Callable[[], CachedSerialProvider]] = None, device_name: str = "", lazy_device_id_call_factory_every_time=False):
        self._dz_lazy_seat = DzLazySeat(dz_seat)
        super().__init__(device_id, device_name, lazy_device_id_call_factory_every_time)

    @property
    def dz_seat(self):
        return self._dz_lazy_seat.dz_seat

    def screenshot(self) -> bytes:
        if self.device_id and adb.is_adb_connected(self.device_id):
            return super().screenshot()
        else:
            # 东舟工位截屏
            screenshot_file = os.path.join(tempfile.gettempdir(), "dz_seat_temp_log_screenshot.png")
            if os.path.exists(screenshot_file):
                os.remove(screenshot_file)
            capture_result = self.dz_seat.capture_screen(screenshot_file)
            if not os.path.exists(screenshot_file):
                raise Exception(
                    f'Can not capture screen from dz seat index {self.dz_seat.seat_index}, capture result is: {capture_result}')
            with open(screenshot_file, "rb") as f:
                png_bytes = f.read()
            return png_bytes
