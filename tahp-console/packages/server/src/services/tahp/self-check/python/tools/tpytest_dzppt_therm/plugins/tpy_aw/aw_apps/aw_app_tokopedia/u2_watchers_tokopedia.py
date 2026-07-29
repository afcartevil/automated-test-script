from powertrde.utils.u2_extends.u2_watcher_def import U2WatcherDef
from powertrde.utils.u2_extends.u2_watcher_register import U2WatcherRegister


class U2WatchersTokopedia(U2WatcherRegister):
    tokopedia_ad = U2WatcherDef(
        xpaths=['(//android.widget.Button)[2]'],
        action="click",
        tags=["tokopedia", "ad"],
        priority=100,
        description="刚进入的时候的弹窗广告"
    )
