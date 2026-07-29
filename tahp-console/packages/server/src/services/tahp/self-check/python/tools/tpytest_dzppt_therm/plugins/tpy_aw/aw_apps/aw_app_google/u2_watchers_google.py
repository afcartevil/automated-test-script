from powertrde.utils.u2_extends.u2_watcher_def import U2WatcherDef
from powertrde.utils.u2_extends.u2_watcher_register import U2WatcherRegister


class U2WatchersGoogle(U2WatcherRegister):
    google_mock_button = U2WatcherDef(
        xpaths=['//android.widget.Button[@text="Mock"]'],
        action="click",
        tags=["google"],
        priority=100,
        description="模拟google监测Mock按钮"
    )

    google_not_interested_button = U2WatcherDef(
        xpaths=['//*[@text="Not interested"]'],
        action="click",
        tags=["google"],
        priority=100,
        description="跳过弹窗"
    )
