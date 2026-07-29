from powertrde.utils.u2_extends.u2_watcher_def import U2WatcherDef
from powertrde.utils.u2_extends.u2_watcher_register import U2WatcherRegister


class U2WatchersMXPlayer(U2WatcherRegister):
    mxplayer_close_btn = U2WatcherDef(
        xpaths=['//*[@resource-id="com.mxtech.videoplayer.ad:id/iv_close"]'],
        action="click",
        tags=["snapchat"],
        priority=100,
        description="更新进入的时候的弹窗"
    )


