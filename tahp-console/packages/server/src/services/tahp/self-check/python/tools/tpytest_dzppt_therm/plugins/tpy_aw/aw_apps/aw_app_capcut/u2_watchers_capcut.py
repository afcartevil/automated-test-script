from powertrde.utils.u2_extends.u2_watcher_def import U2WatcherDef
from powertrde.utils.u2_extends.u2_watcher_register import U2WatcherRegister


class U2WatchersCapcut(U2WatcherRegister):
    capcut_accept_button = U2WatcherDef(
        xpaths=['//android.widget.Button[@text="ACCEPT"]'],
        action="click",
        tags=["capcut", "permission", "consent"],
        priority=100,
        description="打开capcut时弹出 ACCEPT 按钮"
    )

    capcut_agree_button = U2WatcherDef(
        xpaths=['//android.widget.Button[@text="Agree and continue"]'],
        action="click",
        tags=["capcut", "permission", "consent"],
        priority=100,
        description="打开capcut时弹出 Agree and continue 按钮"
    )

