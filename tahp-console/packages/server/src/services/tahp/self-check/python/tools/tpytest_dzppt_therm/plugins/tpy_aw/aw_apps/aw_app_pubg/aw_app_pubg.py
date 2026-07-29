import time
import random

from powertrde.framework.tran_logger import t_log
from powertrde.utils.trde import adb
from tpy_aw.aw_app_base import AwAppBase


class AwAppPUBG(AwAppBase):
    aw_name = 'PUBGM'
    default_app_package = 'com.tencent.ig'

    def training_operation(self):
        if self.check_network(False):
            # 等待30s看会不会自动恢复
            time.sleep(30)
            self.check_network(True)
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

    def close_ad(self):
        """
        刚进入时候，退出上轮游戏，且关闭广告
        """
        for _ in range(5):
            time.sleep(5)
            cancel = self.und_u2.match_template(self.tt('cancel'), target_score=0.85)
            if cancel:
                self.und_u2.click_tuple(cancel.center)
            start = self.und_u2.match_template(self.tt('start'), target_score=0.85, limit_area=(0, 0.7, 0.4, 1), match_times=4)
            if not start:
                self.u2d.click(0.94, 0.03)
            else:
                break

        for i in range(5):
            close = self.und_u2.match_template(self.tt('close'), target_score=0.85)
            if close:
                self.und_u2.click_tuple(close.center)
            time.sleep(2)

    def enter_training_camp(self):
        """
        进入训练场
        """
        self.u2d.click(0.10, 0.75)
        time.sleep(3)
        for i in range(4):
            training = self.und_u2.match_template(self.tt('training'), target_score=0.85, match_times=10,
                                            match_interval=1)
            if training:
                self.und_u2.click_tuple(training.center)
                time.sleep(10)
                return
            else:
                self.u2d_helper.press_back_key()
        else:
            raise Exception('有新弹窗，未进入训练营')

    def exit_game(self):
        """
        尝试退出游戏并返回大厅
        """

        def press_back_and_match(template_name, press_count=1):
            """
            按下返回键并匹配指定模板
            :param template_name: 模板名称
            :param press_count: 按返回键的次数
            :param delay: 每次操作后的延迟（秒）
            :return: 匹配到的模板结果
            """
            for _ in range(press_count):
                self.u2d_helper.press_back_key(1)
                time.sleep(1)
            return self.und_u2.match_template(self.tt(template_name), target_score=0.90)

        # 尝试退出对局
        btn_ok = press_back_and_match('ok', press_count=1)
        if btn_ok:
            self.und_u2.click_tuple(btn_ok.center)
            time.sleep(1)
            return
        else:
            btn_ok = press_back_and_match('ok', press_count=2)
            if btn_ok:
                self.und_u2.click_tuple(btn_ok.center)
                time.sleep(1)
                return

        # 点击屏幕上的指定位置
        self.u2d.click(0.06, 0.03)
        time.sleep(1)

        # 尝试返回大厅
        for i in range(5):
            btn_lobby = self.und_u2.match_template(self.tt('training_lobby'), target_score=0.85)
            if btn_lobby:
                self.und_u2.click_tuple(btn_lobby.center)
                time.sleep(1)
                return
            else:
                self.u2d_helper.press_back_key(1)
        else:
            raise Exception('无法退出游戏！')


    def check_network(self, raise_exception=False):
        """
        在游戏循环中途检测ok弹窗
        """
        if self.und_u2.match_template(self.tt('ok'), match_times=2, limit_area=(0.25, 0.431, 0.33, 0.573), target_score=0.92):
            if raise_exception:
                raise Exception('match server did not respond')
            return True
        return False