import time

from powertrde.framework.tran_logger import t_log
from tpy_aw.aw_app_base import AwAppBase


class AwAppOperaNews(AwAppBase):
    aw_name = 'OperaNews'
    default_app_package = 'com.opera.app.news'

    def tt(self, template_key: str, debug_fallback_value=None):
        """
        同 get_typed_template
        从类级别的“模板录制”中获取录制记录
        """
        return self.get_typed_template(template_key, debug_fallback_value)

    def skip_ads(self, xpath_str):
        """
        跳过广告
        """
        for _ in range(5):
            icon = self.u2d.xpath(xpath_str).wait(timeout=2)
            if not icon:
                self.u2d_helper.press_back_key(1)
                time.sleep(5)
            else:
                break
            icon = self.u2d.xpath(xpath_str).wait(timeout=2)
            if not icon:
                self.u2d_helper.press_back_key(1)
                time.sleep(5)
            else:
                break
            icon = self.u2d.xpath(xpath_str).wait(timeout=2)
            if not icon:
                ads = self.u2d_helper.und_u2.match_template(self.tt('ads'), target_score=0.9)
                if ads:
                    self.u2d_helper.und_u2.click_match_template(self.tt('ads'), target_score=0.9)
                time.sleep(5)
            else:
                break
            icon = self.u2d.xpath(xpath_str).wait(timeout=2)
            if not icon:
                self.u2d.click(0.9, 0.07)
                time.sleep(5)
            else:
                break

    def click_news(self):
        """
        点击新闻
        """
        username = self.u2d.xpath('//*[@resource-id="com.opera.app.news:id/description" or @resource-id="com.opera.app.news:id/title"]').wait(timeout=1)
        for _ in range(3):
            if not username:
                self.u2d_helper.und_u2.swipe_direction('up', speed=200)
                time.sleep(2)
                username = self.u2d.xpath('//*[@resource-id="com.opera.app.news:id/description" or @resource-id="com.opera.app.news:id/title"]').wait(timeout=1)
            else:
                self.u2d.xpath('//*[@resource-id="com.opera.app.news:id/description" or @resource-id="com.opera.app.news:id/title"]').click()
                break
        else:
            raise Exception('News not found')

    def click_me_tab(self):
        """
        点击 Me tab
        """
        self.u2d.xpath('//*[@text="Me"]').click()
        time.sleep(2)

    def click_home_tab(self):
        """
        点击 Home tab
        """
        self.u2d.xpath('//*[@text="Home"]').click()
        time.sleep(2)

    def choose_countery(self, choose:str="Kenya - English"):
        """
        第一次进入会让选择国家
        """
        if self.u2d.xpath('//*[@text="Select country"]').exists:
            for i in range(3):
                if self.u2d.xpath(f'//*[@text="{choose}"]').exists:
                    self.u2d.xpath(f'//*[@text="{choose}"]').click()
                    break
                self.u2d.swipe(0.5, 0.8, 0.5, 0.2)
            time.sleep(5)
            self.u2d.xpath('//*[@text="Don’t allow"]').click_exists(timeout=2)
            self.u2d.xpath('//*[@text="Later"]').click_exists(timeout=2)