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
