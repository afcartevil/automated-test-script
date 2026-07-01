from typing import Optional, Union

from powertrde.framework.lazy_device_id import LazyDeviceID
from powertrde.utils.u2_extends.base_u2d_test_helper import BaseU2DTestHelper
from powertrde.utils.u2_extends.u2d_test_helper_factory import U2DTestHelperFactory
from powertrde.utils.u2_extends.u2utils import IHasU2D, IHasCopilotU2D, IHasObserveU2D


class IHasU2DHelper(IHasU2D):
    def __init__(self):
        super().__init__()
        self._u2d_helper: Optional[BaseU2DTestHelper] = None

    def set_device_id(self, value: Union[str, LazyDeviceID, None]):
        super().set_device_id(value)
        self._u2d_helper = None

    def get_u2d(self):
        return self.u2d_helper.u2d

    @property
    def u2d_helper(self):
        if not self._u2d_helper:
            self._u2d_helper = U2DTestHelperFactory.get_instance().create(self.device_id)
        return self._u2d_helper

    @u2d_helper.setter
    def u2d_helper(self, value: str):
        self._u2d_helper = value


class IHasCopilotU2DHelper(IHasCopilotU2D):
    def __init__(self):
        super().__init__()
        self._c_u2d_helper: Optional[BaseU2DTestHelper] = None

    def set_c_device_id(self, value: Union[str, LazyDeviceID, None]):
        super().set_c_device_id(value)
        self._c_u2d_helper = None

    def get_c_u2d(self):
        return self.c_u2d_helper.u2d

    @property
    def c_u2d_helper(self):
        if not self._c_u2d_helper:
            self._c_u2d_helper = U2DTestHelperFactory.get_instance().create(self.c_device_id)
        return self._c_u2d_helper

    @c_u2d_helper.setter
    def c_u2d_helper(self, value: str):
        self._c_u2d_helper = value


class IHasObserveU2DHelper(IHasObserveU2D):
    def __init__(self):
        super().__init__()
        self._o_u2d_helper: Optional[BaseU2DTestHelper] = None

    def set_o_device_id(self, value: Union[str, LazyDeviceID, None]):
        super().set_o_device_id(value)
        self._o_u2d_helper = None

    def get_o_u2d(self):
        return self.o_u2d_helper.u2d

    @property
    def o_u2d_helper(self):
        if not self._o_u2d_helper:
            self._o_u2d_helper = U2DTestHelperFactory.get_instance().create(self.o_device_id)
        return self._o_u2d_helper

    @o_u2d_helper.setter
    def o_u2d_helper(self, value: str):
        self._o_u2d_helper = value
