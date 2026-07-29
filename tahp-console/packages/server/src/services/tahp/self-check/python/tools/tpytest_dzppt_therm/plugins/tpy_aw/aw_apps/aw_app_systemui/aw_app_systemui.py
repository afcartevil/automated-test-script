import time

from uiautomator2 import XPathElementNotFoundError

from powertrde.framework.tran_logger import t_log
from powertrde.utils.u2_extends import u2utils
from powertrde.utils.u2_extends.u2_selector import U2Selector
from powertrde.utils.u2_extends.u2_selector_locator import U2SelectorLocator
from tpy_aw.aw_app_base import AwAppBase


class SystemUILocator(U2SelectorLocator):
    btn_quick_center_more = U2Selector().xpath('//*[@resource-id="com.android.systemui:id/quick_center_more"]').bind()  # quick settings 右上角的编辑按钮
    btn_edit_short_switch = U2Selector().xpath('//*[@text="Edit Shortcut Switch"]').bind()  # quick settings 右上角点击编辑按钮后展开的有一个Edit shortcut switch的按钮
    btn_func = U2Selector().xpath('(//*[@content-desc="{btn}"])[2]').bind()  # quick settings 的各种功能按钮,例如手电筒：(//*[@content-desc="Flashlight"])[2]
    btn_arrow = U2Selector().xpath('//*[@resource-id="com.android.systemui:id/arrow_view"]').bind()  # 下拉箭头展示更多


class AwAppSystemUI(SystemUILocator, AwAppBase):
    aw_name = 'SystemUI'
    default_app_package = 'com.android.systemui'

    def check_system_ui_button_exist(self, btn_desc):
        """
        @param choose: btn_desc 按钮描述
        检查某个功能按钮是否存在
        """
        if self.btn_arrow.exists():
            self.btn_arrow.click()  # 展开更多功能
            time.sleep(1)
        return self.btn_func.with_params(btn=btn_desc).exists()

    def edit_and_add_func(self, btn_desc: str):
        """
        @param btn_desc: 按钮描述
        不分隐藏功能需要自己手动的增加到首页
        """
        if self.check_system_ui_button_exist(btn_desc):
            return True

        self.btn_quick_center_more.click()
        time.sleep(1)
        self.btn_edit_short_switch.click()
        time.sleep(1)
        u2utils.scroll_find_by_xpath(self.u2d, f'//*[@text="{btn_desc}"]')
        btn_add = self.u2d_helper.xpath_get(f'//*[@text="{btn_desc}"]/parent::*/parent::*')  # 根据文字找到图标右上角的加号
        x, y = btn_add.get().center()
        self.u2d_helper.drag_with_pause(
            start=(x, y),
            mid=(100, 10),
            end=(100, 10),
            pause_time=3,
            fast_steps=5,
            slow_steps=10,
            hold_time=1.0
        )
        self.u2d_helper.click_wait('//*[@text="Done"]', timeout=3)
        time.sleep(1)
        assert self.check_system_ui_button_exist(btn_desc), "添加功能失败"

    def clear_notifications(self):
        """
        清除通知
        """
        clear_btn = self.u2d.xpath('//*[@content-desc="Clear all notifications."]').wait(timeout=2)
        if clear_btn:
            self.u2d.xpath('//*[@content-desc="Clear all notifications."]').click()
        else:
            self.u2d_helper.press_back_key()
            self.u2d_helper.press_home_key()
            raise XPathElementNotFoundError('未找到清除通知按钮')
        time.sleep(2)