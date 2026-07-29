from powertrde.utils.u2_extends.u2_watcher_def import U2WatcherDef
from powertrde.utils.u2_extends.u2_watcher_register import U2WatcherRegister


class U2WatchersShopee(U2WatcherRegister):
    shopee_ad = U2WatcherDef(
        xpaths=['//*[@resource-id="close-icon"]'],
        action="click",
        tags=["shopee", "ad"],
        priority=100,
        description="刚进入的时候的弹窗广告"
    )

    shopee_log_in_reminder = U2WatcherDef(
        xpaths=['//*[@text="Sign Up / Log In" or @resource-id="com.shopee.sg:id/btnConnectGoogle"]'],
        action="back",
        tags=["shopee", "log_in_reminder"],
        priority=100,
        description="登录弹窗提示"
    )
