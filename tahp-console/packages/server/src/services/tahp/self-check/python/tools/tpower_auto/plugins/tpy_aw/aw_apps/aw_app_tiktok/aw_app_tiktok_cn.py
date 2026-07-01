import time

from sympy import false

from powertrde.framework.tran_logger import t_log
from powertrde.utils.u2_extends import u2utils
from tpy_aw.aw_apps.aw_app_tiktok.aw_app_tiktok import AwAppTiktok


class AwAppTiktokCN(AwAppTiktok):
    aw_name = 'TikTokCN'
    default_app_package = 'com.ss.android.ugc.aweme'
    press_back_time = 0

    def check_at_homepage(self):
        icon_exist, _ = self.u2d_helper.assert_icon_exist('xpath', '//*[@text="推荐" or @text="首页"]', click=false)
        if icon_exist:
            t_log.info('已在tiktok主页')
            return True
        else:
            return False

    def back_homepage(self, press_back_time=0):
        if not self.check_at_homepage():
            if press_back_time > 5:
                t_log.info("点击back键超过5次，重启抖音")
                self.restart_app()
                return
            t_log.info('不在主页,点击back键')
            self.u2d_helper.press_back_key(times=1)
            press_back_time += 1
            t_log.info('back次数{}'.format(press_back_time))
            self.back_homepage(press_back_time)
        else:
            t_log.info('已在tiktok主页')

    def brush_Tiktok(self, watch_time: int=15):
        t_log.info("滑动抖音界面")
        self.u2d.swipe(0.5, 0.7, 0.5, 0.3, 0.1)
        t_log.info(f"播放视频{watch_time}s")
        time.sleep(watch_time)

    def view_comments(self):
        t_log.info("点击评论按钮")
        self.u2d_helper.click_wait('//*[@resource-id="com.ss.android.ugc.aweme:id/dyv"]', wait_after_click=2,
                                   no_raise=True)
        d = self.u2d(descriptionContains='评论')
        if d.wait(timeout=3):
            d.click()
            time.sleep(2)
        t_log.info("上下滑动查看评论")
        self.u2d.swipe(0.5, 0.8, 0.5, 0.5, 0.1)
        time.sleep(2)

    def search_video(self):
        time.sleep(5)
        serch_icon, serch_icon_element = self.u2d_helper.assert_icon_exist('xpath',
                                                                           '//*[@resource-id="com.ss.android.ugc.aweme:id/0pn"]')
        serch_icon2, serch_icon_element2 = self.u2d_helper.assert_icon_exist('xpath',
                                                                             '(//*[@resource-id="com.ss.android.ugc.aweme:id/content_container"])[2]')
        if serch_icon:
            t_log.info("点击搜索")
            serch_icon_element.click()
            time.sleep(2)
        elif serch_icon2:
            t_log.info("点击搜索")
            serch_icon_element2.click()
            time.sleep(2)
        else:
            t_log.error("没找到搜索按钮")
        t_log.info("点击搜索框")
        et_search = self.u2d.xpath('//*[@resource-id="com.ss.android.ugc.aweme:id/et_search_kw"]')
        if et_search:
            et_search.click()
            time.sleep(1)
            t_log.info("输入搜索内容")
            u2utils.input_text(self.u2d, 'miu')
            time.sleep(2)
            t_log.info("点击搜索按钮")
            click_serch_icon = self.u2d(descriptionContains='搜索')
            if click_serch_icon.wait(timeout=3):
                click_serch_icon.click()
            else:
                self.u2d_helper.assert_icon_exist('xpath', '//*[@resource-id="com.ss.android.ugc.aweme:id/200"]',
                                                  click=True)
                self.u2d_helper.assert_icon_exist('xpath', '//*[@resource-id="com.ss.android.ugc.aweme:id/2ok"]',
                                                  click=True)

    def search_video_and_play(self):
        self.search_video()
        time.sleep(2)
        t_log.info("点击播放视频")
        try:
            xpath_expression = "//*[@content-desc[contains(., '赞，未选中')]]/../../../*[2]"
            element = self.u2d.xpath(xpath_expression)

            if element.exists:
                element.click()
            else:
                self.u2d.swipe(0.5, 0.8, 0.5, 0.4, 0.1)
                time.sleep(2)
                if element.exists:
                    element.click()
        except Exception as e:
            t_log.error(f'点击播放视频失败')
        self.view_comments()

    def enter_live_broadcast(self):
        live_broadcast = self.u2d(descriptionContains='直播，按钮')
        if live_broadcast.exists:
            t_log.info('找到直播按钮')
            live_broadcast.click()
            time.sleep(1)
        else:
            content_x, content_y = self.u2d(resourceId="com.ss.android.ugc.aweme:id/content_container").center()
            time.sleep(5)
            self.u2d.swipe(200, content_y, 1000, content_y, 0.2)
            self.u2d.swipe(200, content_y, 1000, content_y, 0.2)
            time.sleep(5)
            t_log.info('滑动找到直播按钮')
            live_broadcast.click()
        time.sleep(10)
        self.u2d.swipe(0.5, 0.7, 0.5, 0.3, 0.1)
        time.sleep(5)
        t_log.info('点击进入直播间')
        self.u2d_helper.assert_icon_exist('xpath', '(//*[@resource-id="com.ss.android.ugc.aweme:id/rpc"])[2]',
                                          click=True)
        time.sleep(10)
        exist, _ = self.u2d_helper.assert_icon_exist('xpath', '//*[@text="点击进入直播间"]',
                                                     click=True)
        if exist:
            t_log.info('进入直播间成功')
            time.sleep(5)
        # else:
        #     t_log.info('进入直播间失败')

    def click_message_tab(self):
        """
        点击消息tab
        """
        self.u2d.xpath('//*[@text="消息"]').click(timeout=1)
        time.sleep(2)

    def click_home_tab(self):
        """
        点击首页tab
        """
        self.u2d.xpath('//*[@text="首页"]').click(timeout=1)
        time.sleep(2)
