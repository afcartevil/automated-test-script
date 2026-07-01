from powertrde.utils.u2_extends.u2_watcher_def import U2WatcherDef
from powertrde.utils.u2_extends.u2_watcher_register import U2WatcherRegister


class U2WatchersFacebook(U2WatcherRegister):
    facebook_mock_button = U2WatcherDef(
        xpaths=['//android.widget.Button[@text="Mock"]'],
        action="click",
        tags=["facebook"],
        priority=100,
        description="模拟facebook监测Mock按钮"
    )

    facebook_OK_button= U2WatcherDef(
        xpaths=['//*[@text="OK"]'],
        action="click",
        tags=["facebook"],
        priority=100,
        description="模拟facebook监测OK按钮"
    )
    facebook_continue_button = U2WatcherDef(
        xpaths=['//*[@text="Continue"]'],
        action="click",
        tags=["facebook"],
        priority=100,
        description="模拟facebook监测Continue按钮"
    )
