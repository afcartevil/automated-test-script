import time

from powertrde.utils.trde import adb
from powertrde.utils.u2_extends import u2utils
from tpy_aw.aw_app_base import AwAppBase
from tpy_aw.aw_apps.aw_app_aivoice.aw_app_aivoice import AwAppAivoice


class AwAppAivoiceVivo(AwAppAivoice):
    aw_nickname = "VivoAivoice"
    variant_key = 'Vivo'
    default_app_package = 'com.google.android.googlequicksearchbox'

    def search(self, input_text):
        """
        点击搜索栏，输入搜索内容
        """
        self.u2d.xpath('//*[@resource-id="com.google.android.googlequicksearchbox:id/assistant_robin_input_collapsed_text_half_sheet"]').click(timeout=1)
        time.sleep(1)
        u2utils.input_text(self.u2d, input_text)
        time.sleep(1)
        adb.exec_cmd(self.device_id, 'input keyevent 66')
        time.sleep(1)
        if self.u2d.xpath("//*[contains(@resource-id, 'send')]").wait(timeout=1):
            self.u2d.xpath("//*[contains(@resource-id, 'send')]").click(timeout=1)
            time.sleep(1)

    def click_explore_tab(self):
        """
        进入Explore界面
        """
        self.u2d.xpath('//android.widget.ImageButton').click(timeout=1)
        time.sleep(2)
        self.u2d.xpath('//*[@resource-id="com.google.android.googlequicksearchbox:id/assistant_robin_threads_ia_item_explore_gems_text"]').click(timeout=1)
        time.sleep(2)

    def click_dialogue_tab(self):
        """
        进入Dialogue界面
        """
        self.u2d.xpath('//android.widget.ImageButton').click(timeout=1)
        time.sleep(2)
        self.u2d.xpath('//*[@resource-id="com.google.android.googlequicksearchbox:id/assistant_robin_threads_ia_item_new_chat_text"]').click(timeout=1)
        time.sleep(2)

    def click_me_tab(self):
        """
        进入Me界面
        """
        self.click_explore_tab()