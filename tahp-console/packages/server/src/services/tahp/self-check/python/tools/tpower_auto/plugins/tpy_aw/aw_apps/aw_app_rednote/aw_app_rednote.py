import time

from powertrde.framework.tran_logger import t_log
from powertrde.utils.trde import adb
from powertrde.utils.u2_extends import u2utils
from tpy_aw.aw_app_base import AwAppBase
from tpytest_extends.scheme.cases_scheme import CasesScheme


class AwAppRednote(AwAppBase):
    aw_name = 'Rednote'
    default_app_package = 'com.xingin.xhs'

    def click_note(self):
        """
        点击笔记
        """
        self.u2d(descriptionContains='笔记').click()
        time.sleep(2)

    def click_me_tab(self):
        """
        点击 我的 tab
        """
        self.u2d.xpath('//*[@text="Me"]').click()
        time.sleep(2)

    def click_home_tab(self):
        """
        点击 首页 tab
        """
        self.u2d.xpath('//*[@text="Home"]').click()
        time.sleep(2)
