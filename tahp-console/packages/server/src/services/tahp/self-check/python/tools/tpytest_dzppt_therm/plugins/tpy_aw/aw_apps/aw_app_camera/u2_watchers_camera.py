from powertrde.utils.u2_extends.u2_watcher_def import U2WatcherDef
from powertrde.utils.u2_extends.u2_watcher_register import U2WatcherRegister


class U2WatchersCamera(U2WatcherRegister):
    camera_black_screen = U2WatcherDef(
        xpaths=['//*[@resource-id="com.android.camera:id/black_screen_logo_icon"]','//*[@resource-id="com.oplus.camera:id/tip_text"]','//*[@text="Tap the screen to wake Camera"]','//*[@resource-id="com.android.camera:id/hint_text"]'],
        action="back",
        tags=["camera"],
        priority=100,
        description="相机进入休眠"
    )
    camera_agree = U2WatcherDef(
        xpaths=['//*[@text="Agree"]'],
        action="click",
        tags=["camera"],
        priority=100,
        description="相机弹窗"
    )


