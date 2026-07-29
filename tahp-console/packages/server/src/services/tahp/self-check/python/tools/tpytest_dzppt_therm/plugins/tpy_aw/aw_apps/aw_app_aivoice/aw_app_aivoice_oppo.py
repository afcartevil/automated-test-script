from powertrde.utils.trde import adb
from powertrde.utils.u2_extends import u2utils
from tpy_aw.aw_apps.aw_app_aivoice.aw_app_aivoice import AwAppAivoice
from tpy_aw.aw_apps.aw_app_calendar.aw_app_calendar import AwAppCalendar
import time


class AwAppAivoiceOppo(AwAppAivoice):
    aw_nickname = "OppoAivoice"
    variant_key = 'Oppo'
    default_app_package = "com.xiaomi.xiaoailite"

    def search(self, input_text):
        """
        点击搜索栏，输入搜索内容
        """
        self.u2d.xpath('//*[@resource-id="com.xiaomi.xiaoailite:id/iv_query_keyboard"]').click(timeout=1)
        time.sleep(1)
        u2utils.input_text(self.u2d, input_text)
        time.sleep(1)
        adb.exec_cmd(self.device_id, 'input keyevent 66')
        time.sleep(1)

    def click_explore_tab(self):
        """
        进入 训练计划 界面
        """
        self.u2d.xpath('//*[@text="训练计划"]').click(timeout=1)
        time.sleep(2)

    def click_dialogue_tab(self):
        """
        进入 小爱推荐 界面
        """
        self.u2d.xpath('//*[@text="小爱推荐"]').click(timeout=1)
        time.sleep(2)