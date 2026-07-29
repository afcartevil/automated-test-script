import functools
import warnings
from typing import Optional

import uiautomator2
from uiautomator2 import SCROLL_STEPS

from powertrde.utils.trde import adb

_has_patch_u2_swipe_to_adb_swipe = False

target_u2_module = uiautomator2


def patch_u2_swipe_to_adb_swipe():
    global _has_patch_u2_swipe_to_adb_swipe
    if _has_patch_u2_swipe_to_adb_swipe:
        return
    _has_patch_u2_swipe_to_adb_swipe = True

    # 保存原方法以便需要时仍可调用或恢复
    orig = target_u2_module._Device.swipe

    @functools.wraps(orig)
    def _patched_swipe(self, fx, fy, tx, ty, duration: Optional[float] = None, steps: Optional[int] = None):
        if duration is not None and steps is not None:
            warnings.warn("duration and steps can not be set at the same time, use steps", UserWarning)
            duration = None
        if steps:
            duration = steps / 200
        if not duration:
            duration = SCROLL_STEPS / 200
        duration *= 3.33333
        # logger.debug("swipe from (%s, %s) to (%s, %s), steps: %d", fx, fy, tx, ty, steps)
        rel2abs = self.pos_rel2abs
        fx, fy = rel2abs(fx, fy)
        tx, ty = rel2abs(tx, ty)
        duration = max(0.0333, duration)
        with self._operation_delay("swipe"):
            return adb.input_swipe(self.serial, fx, fy, tx, ty, duration=duration)

    uiautomator2._Device.swipe = _patched_swipe
