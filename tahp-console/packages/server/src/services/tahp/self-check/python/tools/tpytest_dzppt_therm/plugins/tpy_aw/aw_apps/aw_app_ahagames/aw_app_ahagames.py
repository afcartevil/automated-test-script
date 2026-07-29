import time

from powertrde.framework.tran_logger import t_log
from powertrde.utils.trde import adb
from powertrde.utils.u2_extends import u2utils
from tpy_aw.aw_app_base import AwAppBase


class AwAppAhagames(AwAppBase):
    aw_name = 'AHAGames'
    default_app_package = 'net.bat.store'

    def search_game(self, game_name):
        """
        点击搜索栏，搜索游戏
        """
        self.u2d.xpath('//*[contains(@resource-id, "search")]').click(timeout=1)
        u2utils.input_text(self.u2d, game_name)
        time.sleep(1)
        adb.exec_cmd(self.device_id, 'input keyevent 66')
        time.sleep(1)

    def click_me_tab(self):
        """
        点击 Me tab
        """
        self.u2d.xpath('//*[@text="Me" or @resource-id="net.bat.store:id/bottom_layout"]/android.view.ViewGroup[4]').click(timeout=1)
        time.sleep(2)

    def click_home_tab(self):
        """
        点击 Home tab
        """
        self.u2d.xpath('//*[@text="Home" or @resource-id="net.bat.store:id/bottom_layout"]/android.view.ViewGroup[1]').click(timeout=1)
        time.sleep(2)