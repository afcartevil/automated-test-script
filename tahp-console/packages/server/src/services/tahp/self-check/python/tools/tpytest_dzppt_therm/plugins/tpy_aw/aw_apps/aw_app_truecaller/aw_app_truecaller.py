from powertrde.utils.trde import adb
from powertrde.utils.u2_extends.u2_selector import U2Selector
from powertrde.utils.u2_extends.u2_selector_locator import U2SelectorLocator
from tpy_aw.aw_app_base import AwAppBase


class TruecallerLocator(U2SelectorLocator):
    # 广告弹窗关闭按钮
    pop_close = U2Selector().xpath('//*[@resource-id="com.truecaller:id/closeIcon" or @resource-id="com.truecaller:id/closeBtn"]').bind()


class AwAppTruecaller(TruecallerLocator, AwAppBase):
    aw_name = 'Truecaller'
    default_app_package = 'com.truecaller'

    def check_to_close_pop(self, timeout=1):
        self.pop_close.click(timeout=timeout, no_raise=True)

    def set_as_default_dialer(self):
        """
        设置为默认app
        """
        adb.set_dialer(self.device_id, self.app_package)
