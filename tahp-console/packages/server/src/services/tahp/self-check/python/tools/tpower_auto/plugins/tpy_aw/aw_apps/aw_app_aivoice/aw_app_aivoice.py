import time

from powertrde.utils.trde import adb
from powertrde.utils.u2_extends import u2utils
from tpy_aw.aw_app_base import AwAppBase


class AwAppAivoice(AwAppBase):
    aw_name = 'Aivoice'
    default_app_package = 'com.transsion.aivoiceassistant'

    def search(self, input_text):
        """
        点击搜索栏，输入搜索内容
        """
        self.u2d.xpath('//*[@resource-id="com.transsion.aivoiceassistant:id/fl_input"]').click(timeout=1)
        time.sleep(1)
        u2utils.input_text(self.u2d, input_text)
        time.sleep(1)
        adb.exec_cmd(self.device_id, 'input keyevent 66')
        time.sleep(1)

    def click_explore_tab(self):
        """
        进入Explore界面
        """
        self.u2d.xpath('//*[@text="Explore"]').click(timeout=1)
        time.sleep(2)

    def click_dialogue_tab(self):
        """
        进入Dialogue界面
        """
        self.u2d.xpath('//*[@text="Dialogue"]').click(timeout=1)
        time.sleep(2)