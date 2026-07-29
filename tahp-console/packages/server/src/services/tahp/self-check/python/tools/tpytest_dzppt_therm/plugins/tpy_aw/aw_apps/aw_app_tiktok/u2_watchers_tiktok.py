from powertrde.utils.u2_extends.u2_watcher_def import U2WatcherDef
from powertrde.utils.u2_extends.u2_watcher_register import U2WatcherRegister


class U2WatchersTiktok(U2WatcherRegister):
    tiktok_mock_button = U2WatcherDef(
        xpaths=['//android.widget.Button[@text="Mock"]'],
        action="click",
        tags=["tiktok"],
        priority=100,
        description="模拟tiktok监测Mock按钮"
    )

    tiktok_find_new_friend_button = U2WatcherDef(
        xpaths=['//*[@resource-id="com.ss.android.ugc.aweme:id/tv_cancel"]'],
        action="click",
        tags=["tiktok",'new_friend'],
        priority=100,
        description=" 发现抖音朋友弹窗"
    )

    tiktok_update_friend_button = U2WatcherDef(
        xpaths=['//*[@text="Got it"]'],
        action="click",
        tags=["tiktok"],
        priority=100,
        description="更新弹窗"
    )

    tiktokcn_pop_button = U2WatcherDef(
        xpaths=['//*[@text="同意"]'],
        action="click",
        tags=["tiktokcn"],
        priority=100,
        description="弹窗"
    )

    tiktokcn_login_button = U2WatcherDef(
        xpaths=['//*[@text="登录后，体验完整功能"]'],
        action=lambda d: (d.press('back'), d.press('back')), # type: ignore
        tags=["tiktokcn", "login"],
        priority=100,
        description="弹窗"
    )
    tiktokcn_close_button = U2WatcherDef(
        xpaths=['//*[@content-desc="关闭，按钮" or @resource-id="com.ss.android.ugc.aweme:id/close"]'],
        action="click",
        tags=["tiktokcn"],
        priority=100,
        description="登录弹窗"
    )