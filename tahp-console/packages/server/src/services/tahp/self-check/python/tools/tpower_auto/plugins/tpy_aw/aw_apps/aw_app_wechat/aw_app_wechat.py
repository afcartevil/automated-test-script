import time

from uiautomator2 import XPathElementNotFoundError

from powertrde.framework.tran_logger import t_log
from powertrde.utils.trde import adb
from powertrde.utils.u2_extends import u2utils
from tpy_aw.aw_app_base import AwAppBase
from tpytest_extends.scheme.cases_scheme import CasesScheme


class AwAppWechat(AwAppBase):
    aw_name = 'WeChat'
    default_app_package = 'com.tencent.mm'

    def click_discover_tab(self):
        """
        点击发现页
        """
        self.u2d_helper.und_u2.click_match_text("Discover", limit_area=(0, 0.8, 1, 1))
        time.sleep(2)

    def click_chats_tab(self):
        """
        点击聊天页
        """
        self.u2d_helper.und_u2.click_match_text("Chats", limit_area=(0, 0.8, 1, 1))
        time.sleep(2)
