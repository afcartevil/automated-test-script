import time
import random

from powertrde.framework.tran_logger import t_log
from powertrde.utils.trde import adb
from tpy_aw.aw_app_base import AwAppBase


class AwAppPUBG(AwAppBase):
    aw_name = 'PUBGM'
    default_app_package = 'com.tencent.ig'

    def training_operation(self):
        self._random_swipe()
        time.sleep(1)
        self.u2d.click(0.7, 0.4)    # 捡装备
        time.sleep(1)
        for _ in range(3):
            self._random_swipe()
            time.sleep(1)
            self.u2d.swipe(0.6, 0.5, 0.8, 0.5, 0.5) # 换方向
            time.sleep(1)
            self.u2d.click(0.8, 0.7)    # 开枪
            time.sleep(1)

    def _random_swipe(self):
        random_x = round(random.uniform(0.1, 0.9), 1)
        random_y = round(random.uniform(0.1, 0.9), 1)
        self.u2d.swipe(0.2, 0.7, random_x, random_y, 3)
