import time

from tpy_aw.u2d_test_helper import U2DTestHelper


class U2DWatcherRegister:
    def __init__(self, u2d_helper: U2DTestHelper):
        self.u2d_helper = u2d_helper

    @property
    def u2d(self):
        return self.u2d_helper.u2d

    def start_watcher(self):
        self.u2d.watcher.start()

    def stop_watcher(self):
        self.u2d.watcher.stop()

    def remove_watcher(self, name):
        self.u2d.watcher.remove(name)

    def register_watcher_xpath(self, xpath):
        self.u2d.watcher(xpath).when(xpath).click()

    def register_ok(self):
        self.u2d.watcher("OK_alert").when('//android.widget.Button[@text="OK"]').click()

    def register_keyboard_agree(self):
        """键盘的运行弹窗"""
        self.u2d.watcher("AgreeAndContinue_alert").when('//*[@text="Agree And Continue"]').click()

    def register_next(self):
        """键盘的运行弹窗"""
        self.u2d.watcher("next_alert").when('//android.widget.Button[@text="Next"]').click()  # 新刷机大系统，下来通知时有这个

    def register_gotit(self):
        """键盘的运行弹窗"""
        self.u2d.watcher("gotit_alert").when('//android.widget.Button[@text="Got it"]').click()  # 新刷机大系统，下来通知时有这个

    def register_Agree(self):
        self.u2d.watcher("Agree_alert").when('//android.widget.Button[@text="Agree"]').click()

    def register_allow(self):
        self.u2d.watcher("allow_alert").when('//android.widget.Button[@text="Allow"]').click()

    def register_dont_allow(self):
        self.u2d.watcher("dont_Allow_alert").when('//android.widget.Button[@text="Don’t allow"]').click()

    def register_while_using_the_app(self):
        self.u2d.watcher("while_using_the_app_alert").when(
            '//android.widget.Button[@text="While using the app"]').click()

    def register_facebook_continue(self):
        self.u2d.watcher("facebook_continue_alert").when('//*[@content-desc="Continue in English (US)"]').click()

    def register_close_beautycam_advertisement(self):
        self.u2d.watcher("close_beautyCam_advertisement_alert").when(
            '//*[@resource-id="com.commsource.beautyplus:id/iv_close"]').click()

    def register_close_beautycam_close_festive(self):
        def _close_beautycam_festive():
            time.sleep(5)
            self.u2d.press("back")  # 退出广告
            time.sleep(1)

        self.u2d.watcher("close_beautycam_close_festive").when(
            '//*[@resource-id="com.commsource.beautyplus:id/rl_advert_web"]').call(_close_beautycam_festive)

    def register_close_trueCaller_agreeContinue(self):
        self.u2d.watcher("close_trueCaller_agreeContinue").when('//*[@text="Agree & Continue"]').click()

    def register_close_trueCaller_ad(self):
        self.u2d.watcher("close_trueCaller_ad(").when('//*[@content-desc="Close"]').click()

    def register_close_ins_createSticker(self):
        self.u2d.watcher("close_ins_createSticker").when('//*[@text="Not now"]').click()

    def register_close_boomplay_ad1of2(self):
        self.u2d.watcher("close_boomplay_ad1of2").when('//*[@text="Ad 1 of 2"]').click()

    def register_close_chrome_nothanks(self):
        self.u2d.watcher("close_chrome_nothanks").when('//*[@text="No thanks"]').click()

    def boomplay_custom_watcher(self):
        # 查找特定的节点
        time.sleep(7)
        self.u2d.xpath('//*[@text="Ad 2 of 2"]/preceding-sibling::*[1]').click()

    # 添加 watcher 到 uiautomator
    def register_close_boomplay_ad2of2(self):
        self.u2d.watcher("close_boomplay_ad2of2").when('//*[@text="Ad 2 of 2"]').call(
            self.boomplay_custom_watcher)  # 如果发现了Ad 2 of 2广告，等待5秒，点击它的前一个兄弟节点

    def register_close_boomplay_adColse(self):
        self.u2d.watcher("close_boomplay_close").when('//*[@content-desc="Close"]').click()
        self.u2d.watcher("close_boomplay_close_text").when('//android.widget.Button[@text="Close"]').click()

    def register_close_boomplay_adColsead(self):
        self.u2d.watcher("close_boomplay_closeAD").when('//*[@content-desc="Close Ad"]').click()

    def register_close_boomplay_install_adColsead(self):
        """推广应用的广告，比如推广安装王者容易，一般都有一个install按钮在页面上，然后，会有倒计时，关闭按钮左边和右边都有，但是获取到claass都是//android.widget.Button，
            1、这个button可能是X号，点击完直接消失
            2、也可能是skip Video，点击完会有新弹窗，是否真的close video，我们选择点击//*[@text="CLOSE VIDEO"]
        """
        def _boomplay_install_adColsead_watcher():
            # 查找特定的节点
            time.sleep(10)
            self.u2d_helper.click_and_sleep('//android.widget.Button')
            time.sleep(2)
            self.u2d_helper.click_and_sleep('//*[@text="CLOSE VIDEO"]')
        self.u2d.watcher("close_boomplay_install_adColsead").when('//*[@resource-id="install-button"]').call(_boomplay_install_adColsead_watcher)

    def register_close_b612_adColsead(self):
        self.u2d.watcher("close_b612_adColsead").when(
            '//*[@resource-id="com.linecorp.b612.android:id/close_btn"]').click()

    def register_close_b612_continue(self):
        self.u2d.watcher("close_b612_continue").when('//*[@text="Continue"]').click()
        self.u2d.watcher("close_b612_continue2").when('//*[@text="CONTINUE"]').click()


    def register_close_YTMusic_ad(self):
        self.u2d.watcher("close_YTMusic_ad").when('//*[@text="No thanks"]').click()

    def register_spotify_dismiss(self):
        self.u2d.watcher("spotify_dismiss").when('//*[@text="DISMISS"]').click()

    def register_close_TiktokCN_locate(self):
        self.u2d.watcher('立即开启').when('//*[@text="立即开启"]').click()

    def register_close_TiktokCN_update(self):
        self.u2d.watcher('关闭').when('//*[@text="关闭"]').click()

    def register_close_TiktokCN_agree(self):
        self.u2d.watcher('//*[@resource-id="com.ss.android.ugc.aweme:id/ej1"]').when('//*[@resource-id="com.ss.android.ugc.aweme:id/ej1"]').click()

    def register_close_whatsapp_ok(self):
        self.u2d.watcher('//*[@resource-id="com.whatsapp:id/ephemeral_nux_title"]').when('//*[@resource-id="com.whatsapp:id/ephemeral_nux_ok"]').click()

    def register_amap_agree(self):
        self.u2d.watcher('minimap_agree"]').when('//*[@resource-id="com.autonavi.minimap:id/agree"]').click()
        self.u2d.watcher('minimap_agree2"]').when('//*[@resource-id="com.autonavi.minimap:id/navi_agreement_agree_btn"]').click()

    def register_amap_switch_to_english(self):
        self.u2d.watcher('//*[@resource-id="com.autonavi.minimap:id/parentPanel"]').when('//*[@resource-id="com.autonavi.minimap:id/button2"]').click()

    def register_messenger_video_answer_call(self):
        self.u2d.watcher('video_call_answer').when(
            '//android.widget.Button[@text="Answer"]').click()

    def register_chrome_click_cancel(self):
        self.u2d.watcher('cancel_download').when('//android.widget.Button[@text="取消"]').click()
        self.u2d.watcher('cancel_download2').when('//android.widget.Button[@text="Cancel"]').click()
