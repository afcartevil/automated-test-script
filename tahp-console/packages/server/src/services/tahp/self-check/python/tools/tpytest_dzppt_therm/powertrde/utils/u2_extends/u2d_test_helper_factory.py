from typing import Union, Callable, Optional, Dict

import uiautomator2

from powertrde import env
from powertrde.framework.tran_logger import t_log
from powertrde.utils.u2_extends.base_u2d_test_helper import BaseU2DTestHelper
from powertrde.utils.u2_extends.u2utils import U2DeviceProtocol


class U2DTestHelperFactory:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        super().__init__()
        self.on_create_event: Optional[Callable[[Union[uiautomator2.Device, U2DeviceProtocol, str]], BaseU2DTestHelper]] = None
        self.default_u2d_test_helper_class_or_factory = None
        self._sample_instances: Dict[str, BaseU2DTestHelper] = {}

    def create(self, u2d_or_device_id: Union[uiautomator2.Device, U2DeviceProtocol, str]):
        if self.on_create_event:
            ret = self.on_create_event(u2d_or_device_id)
        else:
            ret = self.create_default(u2d_or_device_id)
        if isinstance(u2d_or_device_id, str):
            device_id = u2d_or_device_id
        else:
            device_id = u2d_or_device_id.serial
        self._sample_instances[device_id] = ret
        return ret

    def get_or_create(self, u2d_or_device_id: Union[uiautomator2.Device, U2DeviceProtocol, str]):
        if isinstance(u2d_or_device_id, str):
            device_id = u2d_or_device_id
        else:
            device_id = u2d_or_device_id.serial
        exist_ins = self._sample_instances.get(device_id)
        if exist_ins is None:
            exist_ins = self.create(u2d_or_device_id)
        return exist_ins

    def create_default(self, u2d_or_device_id: Union[uiautomator2.Device, U2DeviceProtocol, str]):
        if not self.default_u2d_test_helper_class_or_factory:
            try:
                self.default_u2d_test_helper_class_or_factory = env.load_class('tpy_aw.u2d_test_helper.U2DTestHelper')
            except Exception:
                self.default_u2d_test_helper_class_or_factory = 0
                pass
        if isinstance(self.default_u2d_test_helper_class_or_factory, type) or callable(self.default_u2d_test_helper_class_or_factory):
            ins = self.default_u2d_test_helper_class_or_factory(u2d_or_device_id)
            if not ins:
                t_log.warning(
                    "Can not instantiate U2D Test Helper with your FACTORY, Perhaps it's because THE PHONE IS NOT CONNECTED. It will fallback to the default U2DTestHelper.")
                try:
                    _default_u2d_test_helper_class_or_factory = env.load_class('tpy_aw.u2d_test_helper.U2DTestHelper')
                    return _default_u2d_test_helper_class_or_factory(u2d_or_device_id)
                except Exception:
                    t_log.warning("Due to the inability to find the tpy_aw module, it cannot fallback to the default U2DTestHelper.")
            else:
                return ins
        return BaseU2DTestHelper(u2d_or_device_id)
