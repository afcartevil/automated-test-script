from powertrde.utils.u2_extends.u2_watcher_def import U2WatcherDef
from powertrde.utils.u2_extends.u2_watcher_register import U2WatcherRegister


class U2WatchersChrome(U2WatcherRegister):
    chrome_mock_button = U2WatcherDef(
        xpaths=['//android.widget.Button[@text="Mock"]'],
        action="click",
        tags=["chrome"],
        priority=100,
        description="模拟chrome监测Mock按钮"
    )

    chrome_dowload_button = U2WatcherDef(
        xpaths=['//*[@text="Download" or @text="DOWNLOAD"]'],
        action="click",
        tags=["chrome", 'download'],
        priority=100,
        description="chrome点击下载按钮"
    )

    chrome_dowload_again = U2WatcherDef(
        xpaths=['//*[@text="Download again"]'],
        action="click",
        tags=["chrome", 'download'],
        priority=100,
        description="chrome点击下载按钮"
    )

