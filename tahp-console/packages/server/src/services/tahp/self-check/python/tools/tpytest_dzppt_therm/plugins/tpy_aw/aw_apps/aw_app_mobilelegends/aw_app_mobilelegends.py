import time

from powertrde.framework.tran_logger import t_log
from powertrde.utils.trde import adb
from tpy_aw.aw_app_base import AwAppBase


class AwAppMobileLegends(AwAppBase):
    aw_name = 'MLBB'
    default_app_package = 'com.mobile.legends'

    def enter_replay(self):
        """
        进入本地播放的游戏对局
        """
        self.u2d.click(0.07, 0.08)
        time.sleep(1)
        battle_filed = self.und_u2.match_text('Battlefield', limit_area=(0, 0, 0.2, 1),
                                              match_times=4)  # 识别率低，(0.07, 0.05)一般能进入
        if not battle_filed:
            # self.u2d.click(0.07, 0.05)
            self.u2d.click(0.10, 0.55)
            time.sleep(1)
        else:
            self.und_u2.click_match_text('Battlefield', limit_area=(0, 0, 0.2, 1), match_times=4)
        time.sleep(1)
        self.und_u2.click_match_text('Replays', limit_area=(0, 0, 0.2, 1), match_times=4)
        time.sleep(1)
        myreplays = self.und_u2.match_text('My Replays', target_score=0.8, limit_area=(0.3, 0, 0.7, 0.2), match_times=3)
        if myreplays:
            self.und_u2.click_tuple(myreplays.center)
        else:
            self.u2d.click(0.374, 0.122)
        time.sleep(1)
        self.u2d.click(0.5, 0.357)
        time.sleep(1)
        # self.und_u2.click_match_text('Okay')
        self.und_u2.click_match_template(self.tt('okay'), target_score=0.85)
        time.sleep(1)

    def enter_training_camp(self):
        """
        进入训练营
        """
        for i in range(3):
            mode = self.und_u2.match_text('Mode', match_times=4)
            if mode:
                self.und_u2.click_tuple(mode.center)
                break
        else:
            self.u2d.click(0.69, 0.94)

        time.sleep(2)
        self.u2d.click(0.864, 0.862)
        time.sleep(2)
        self.enter_practice_mode()

    def enter_practice_mode(self):
        """
        进入训练
        """
        self.und_u2.click_match_text('PRACTICE', target_score=0.7, match_times=5, scale_factor=2,
                                     limit_area=(0, 0, 0.5, 0.5))
        time.sleep(1)
        try:
            self.und_u2.click_match_text('Enter', target_score=0.65, match_times=5, scale_factor=2, limit_area=(0, 0, 0.5, 0.5))
        except Exception as e:
            t_log.info(f"点击Enter时报错：{e}, 尝试固定坐标")
            self.u2d.click(0.21, 0.627)
            self.und_u2.assert_match_text('Okay', match_times=5, scale_factor=2,
                                         limit_area=(0, 0.7, 0.3, 1))
        time.sleep(2)

    def choose_role(self):
        """
        点击英雄，等待进入游戏
        """
        # 点击英雄 注意，und_u2和u2d点击的位置在横屏状态下时不一样的
        self.u2d.click(0.835, 0.196)
        # self.und_u2.click_tuple((0.804, 0.835))
        for i in range(6):
            time.sleep(1)
            self.u2d.click(0.877, 0.944)
            # self.und_u2.click_tuple((0.056, 0.877))
        time.sleep(10)

    def play_game(self):
        """
        玩游戏，一回合的动作，建议自行穿插等待时间，循环游玩
        """
        # 点击技能123升级和买装备
        # self.und_u2.click_tuple((0.215, 0.671))
        self.u2d.click(0.671, 0.785)
        time.sleep(0.5)
        # self.und_u2.click_tuple((0.4, 0.717))
        self.u2d.click(0.717, 0.6)
        time.sleep(0.5)
        # self.und_u2.click_tuple((0.5, 0.8))
        self.u2d.click(0.8, 0.5)
        time.sleep(0.5)
        #self.und_u2.click_tuple((0.846, 0.874)
        self.u2d.click(0.874, 0.154)
        time.sleep(0.5)
        for j in range(6):
            # 移动
            # self.und_u2.swipe_tuple((0.2, 0.2), (0.2, 0.7))
            self.u2d.swipe(0.2, 0.8, 0.7, 0.8)
            time.sleep(0.5)
            # 普攻
            # self.und_u2.click_tuple((0.16, 0.84))
            self.u2d.click(0.84, 0.84)
            time.sleep(0.5)
            # 技能123
            # self.und_u2.click_tuple((0.122, 0.711))
            self.u2d.click(0.711, 0.878)
            time.sleep(0.5)
            # self.und_u2.click_tuple((0.312, 0.76))
            self.u2d.click(0.76, 0.688)
            time.sleep(0.5)
            # self.und_u2.click_tuple((0.41, 0.84))
            self.u2d.click(0.84, 0.59)
            time.sleep(0.5)
            # 移动
            # self.und_u2.swipe_tuple((0.3, 0.13), (0.3, 0.4))
            self.u2d.swipe(0.13, 0.7, 0.4, 0.7)
            time.sleep(0.5)
        # 回城
        # self.und_u2.click_tuple((0.11, 0.5))
        self.u2d.click(0.5, 0.89)

    def close_ad(self):
        """
        关闭所有广告， 请自行选择循环判断和退出条件
        """
        # 识别准确度太低，不好调整，所以干脆直接连点多次返回键
        # result_check_set = self.und_u2.match_template(self.tt('close_ad_set'), target_score=0.90,
        #                                              limit_area=(0.7, 0, 1, 0.3))
        # if result_check_set:
        #     self.u2d_helper.press_back_key(2)
        #     print(result_check_set.center)
        #     time.sleep(3)
        # else:
        self.u2d_helper.press_back_key(2)
        time.sleep(1)
        # cancel_set = self.und_u2.match_text('Cancel', target_score=0.90, match_times=2, limit_area=(0.1, 0.3, 0.44, 0.8))
        cancel_set = self.und_u2.match_text('Cancel', target_score=0.90, match_times=2, scale_factor=2)
        if cancel_set:
            self.und_u2.click_tuple(cancel_set.center)
        else:
            cancel_set_pic = self.und_u2.match_template(self.tt('cancel_set'), target_score=0.95, match_times=2)
            if cancel_set_pic:
                self.und_u2.click_tuple(cancel_set_pic.center)

        back = self.und_u2.match_template(self.tt('back'), target_score=0.90, match_times=2, limit_area=(0.7, 0, 1, 0.1))
        if back:
            self.und_u2.click_tuple(back.center)
        check = self.und_u2.match_text('Check', match_times=2)
        if check:
            self.u2d_helper.press_back_key()

        time.sleep(5)

    def exit_game(self):
        """
        退出对局
        """

        def try_click_okay():
            """
            尝试匹配并点击 'Okay' 按钮
            :return: 是否成功点击 'Okay' 按钮
            """
            btn_ok_text = self.und_u2.match_text('Okay', target_score=0.90, match_times=4, limit_area=(0.2, 0.5, 0.5, 0.8))
            btn_ok_pic = self.und_u2.match_template(self.tt('okay'), target_score=0.90)

            if btn_ok_text:
                self.und_u2.click_tuple(btn_ok_text.center)
                return True
            if btn_ok_pic:
                self.und_u2.click_tuple(btn_ok_pic.center)
                return True
            return False

        # 第一次尝试退出
        self.u2d_helper.press_back_key(1)
        if not try_click_okay():
            # 第二次尝试退出
            self.u2d_helper.press_back_key(2)
            try_click_okay()

    def is_continue_play(self):
        """
        继续游戏
        """
        quit_button_text = self.und_u2.match_text('Quit', target_score=0.90, match_times=4)
        quit_button_pic = self.und_u2.match_template(self.tt('quit'), target_score=0.90)

        if quit_button_pic:
            t_log.info('quit图片存在')
            self.und_u2.click_tuple(quit_button_pic.center)
            return True
        if quit_button_text:
            t_log.info('quit存在')
            self.und_u2.click_tuple(quit_button_text.center)
            return True
        return False
