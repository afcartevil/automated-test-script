from powertrde.utils.u2_extends.u2_watcher_def import U2WatcherDef
from powertrde.utils.u2_extends.u2_watcher_register import U2WatcherRegister


class U2WatchersInstagram(U2WatcherRegister):
    instagram_turn_on_button = U2WatcherDef(
        xpaths=['//android.widget.Button[@text="Turn on"]'],
        action="click",
        tags=["instagram", "permission"],
        priority=100,
        description="instagram授权权限"
    )

    instagram_pop = U2WatcherDef(
        xpaths=['//android.view.View[@text="No,thanks" or @text="Continue"]',
                '//*[@text="OK" or @text="Not now"]'],
        action="click",
        tags=["instagram", "ad"],
        priority=100,
        description="instagram弹窗"
    )
