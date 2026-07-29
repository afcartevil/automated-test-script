import time

from powertrde.framework.tran_logger import t_log
from powertrde.utils.u2_extends import u2utils
from tpy_aw.aw_apps.aw_app_tiktok.aw_app_tiktok import AwAppTiktok
from deprecated import deprecated


class AwAppTiktokCN(AwAppTiktok):
    aw_name = 'TikTokCN'
    default_app_package = 'com.ss.android.ugc.aweme'
    press_back_time = 0

    def check_at_homepage(self):
        """
        检查是否在首页
        """
        icon_exist, _ = self.u2d_helper.assert_icon_exist('xpath', '//*[@text="推荐" or @text="首页"]', click=False)
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

    def brush_Tiktok(self, watch_time: int = 15):
        """
        播放视频并等待
        """
        t_log.info("滑动抖音界面")
        self.u2d.swipe(0.5, 0.7, 0.5, 0.3, 0.1)
        t_log.info(f"播放视频{watch_time}s")
        time.sleep(watch_time)

    @deprecated("搜索控件名是随机的，加再多个也覆盖不完")
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

    @deprecated("搜索控件名是随机的，加再多个也覆盖不完")
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

    @deprecated("搜索控件名是随机的，加再多个也覆盖不完")
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
        self.u2d.xpath('//*[@text="消息" or @content-desc="消息，按钮"]').click(timeout=1)
        time.sleep(2)

    def click_home_tab(self):
        """
        点击首页tab
        """
        self.u2d.xpath('//*[@text="首页" or @content-desc="首页，按钮"]').click(timeout=1)
        time.sleep(2)

    def click_search(self):
        """
        点击右上角的搜索，自行做判断
        """
        self.u2d.click(0.93, 0.0675)

    def search_user(self, search_name, user_name=None, userpage=False):
        """
        search_name和user_name可能不一致，搜索抖音号会更准确
        @userpage: 是否要点进用户界面再搜索用户，如果search_name是抖音号则不推荐
        """
        self.click_search()
        time.sleep(5)
        search_name_result = False
        for _ in range(5):
            edit_text = self.u2d.xpath('//android.widget.EditText')
            search_name_result = self.u2d.xpath(f'//android.widget.EditText[@text="{search_name}"]').exists
            if not search_name_result:
                if _ > 0:
                    t_log.info(f'第{_}次搜索固定账号失败，重新搜索', ext_event=True)
                    self.u2d_helper.click_wait('//*[@content-desc="清空" or @resource-id="com.ss.android.ugc.aweme:id/btn_clear"]', post_wait=1)
                edit_text.click()
                time.sleep(2)
                try:
                    edit_text.set_text(search_name)
                except:
                    self.u2d_helper.input_text(search_name)
            else:
                t_log.info(f'第{_}次搜索固定账号成功', ext_event=True)
                break
            time.sleep(1)
        if not search_name_result:
            raise Exception('搜索固定账号失败')
        self.u2d_helper.restore_keyboard_ime()
        time.sleep(5)
        # self.u2d_helper.input_text(search_name) 吞字
        #adb.exec_cmd(self.device_id, 'input keyevent 66')
        self.u2d_helper.click_wait('//*[@text="搜索" or @content-desc="搜索"]', pre_wait=2, timeout=5)
        time.sleep(2)
        if userpage:
            self.u2d_helper.click_wait('//*[@text="用户"]', timeout=8, pre_wait=1)
            time.sleep(2)
        try:
            self.u2d_helper.click_wait(f"^{user_name if user_name else search_name}", timeout=10, pre_wait=1)
        except Exception as e:
            t_log.info(f'未能通过名称控件点击账号报错：{e}, 改用坐标点击')
            if userpage:
                self.u2d.click(0.12, 0.20)
            else:
                self.u2d.click(0.12, 0.26)

            # 坐标要断言
            self.u2d_helper.wait_ui_obj(f"^{user_name if user_name else search_name}", timeout=10, raise_on_not_exist=True)


    def enter_user_first_video(self):
        """
        进入用户页面的第一个视频
        """
        self.u2d.click(0.25, 0.50)
        # self.u2d_helper.click_wait('//*[@resource-id="com.ss.android.ugc.aweme:id/container"]', timeout=8, post_wait=1)

    def click_comment(self):
        """
        点击评论
        """
        try:
            self.u2d_helper.click_wait('//*[starts-with(@content-desc, "评论")]', timeout=5)
        except:
            self.u2d.click(0.926, 0.635)
        finally:
            self.u2d_helper.wait_ui_obj('//*[@content-desc="放大评论区"]', timeout=8, raise_on_not_exist=True)
