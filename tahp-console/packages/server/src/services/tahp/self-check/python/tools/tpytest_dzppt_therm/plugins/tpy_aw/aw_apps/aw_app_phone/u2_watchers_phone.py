from powertrde.utils.u2_extends.u2_watcher_def import U2WatcherDef
from powertrde.utils.u2_extends.u2_watcher_register import U2WatcherRegister


class U2WatchersPhone(U2WatcherRegister):
    ok_got_it = U2WatcherDef(
        xpaths=['//*[@text="OK1, Got it"]', '//*[@text="OK, got it"]'],
        action="click",
        tags=["camera"],
        priority=100,
        description="无sim卡拨打电话提示不可用"
    )

    demo = U2WatcherDef(
        xpaths=['//*[@content-desc="Settings"]'],
        action="click",
        tags=["camera"],
        priority=100,
        description="无sim卡拨打电话提示不可用"
    )


