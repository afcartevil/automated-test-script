import time
import re

from uiautomator2 import XPathElementNotFoundError

from powertrde.framework.tran_logger import t_log
from powertrde.utils.trde import adb
from powertrde.utils.u2_extends import u2utils
from tpy_aw.aw_app_base import AwAppBase


class AwAppGotube(AwAppBase):
    aw_name = 'Gotube'
    default_app_package = 'premium.gotube.adblock.utube'

    def click_local_tab(self):
        """
        点击Local按钮
        """
        local_btn = self.u2d.xpath('//*[@resource-id="premium.gotube.adblock.utube:id/llBottomRoot"]/android.widget.FrameLayout[2]').wait(timeout=2)
        if local_btn:
            self.u2d.xpath('//*[@resource-id="premium.gotube.adblock.utube:id/llBottomRoot"]/android.widget.FrameLayout[2]').click(timeout=2)
        else:
            raise XPathElementNotFoundError('Local button not found')
        time.sleep(2)

    def click_discover_tab(self):
        """
        点击Discover按钮
        """
        local_btn = self.u2d.xpath('//*[@resource-id="premium.gotube.adblock.utube:id/llBottomRoot"]/android.widget.FrameLayout[1]').wait(timeout=2)
        if local_btn:
            self.u2d.xpath('//*[@resource-id="premium.gotube.adblock.utube:id/llBottomRoot"]/android.widget.FrameLayout[1]').click(timeout=2)
        else:
            raise XPathElementNotFoundError('DISCOVER button not found')
        time.sleep(2)

    def click_video_sheet(self):
        """
        点击Local里的video按钮
        """
        self.u2d.xpath('//*[@text="Video"]').click(timeout=2)
        time.sleep(2)