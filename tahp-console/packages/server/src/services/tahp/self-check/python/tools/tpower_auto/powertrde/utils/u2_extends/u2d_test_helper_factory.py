from typing import Union, Callable, Optional

import uiautomator2

from powertrde import env
from powertrde.framework.tran_logger import t_log
from powertrde.utils.u2_extends.base_u2d_test_helper import BaseU2DTestHelper


class U2DTestHelperFactory:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        super().__init__()
        self.on_create_event: Optional[Callable[[Union[uiautomator2.Device, str]], BaseU2DTestHelper]] = None
        self.default_u2d_test_helper_class_or_factory = None

    def create(self, u2d_or_device_id: Union[uiautomator2.Device, str]):
        if self.on_create_event:
            return self.on_create_event(u2d_or_device_id)
        return self.create_default(u2d_or_device_id)

    def create_default(self, u2d_or_device_id: Union[uiautomator2.Device, str]):
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
