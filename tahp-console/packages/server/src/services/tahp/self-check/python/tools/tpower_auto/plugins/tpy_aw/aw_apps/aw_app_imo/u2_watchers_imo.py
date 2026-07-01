from powertrde.utils.u2_extends.u2_watcher_def import U2WatcherDef
from powertrde.utils.u2_extends.u2_watcher_register import U2WatcherRegister


class U2WatchersIMO(U2WatcherRegister):
    imo_mock_button = U2WatcherDef(
        xpaths=['//android.widget.Button[@text="Mock"]'],
        action="click",
        tags=["imo"],
        priority=100,
        description="模拟imo监测Mock按钮"
    )
