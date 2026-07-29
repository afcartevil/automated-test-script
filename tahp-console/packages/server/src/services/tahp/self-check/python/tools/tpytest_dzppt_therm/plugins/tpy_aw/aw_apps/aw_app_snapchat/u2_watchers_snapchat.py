from powertrde.utils.u2_extends.u2_watcher_def import U2WatcherDef
from powertrde.utils.u2_extends.u2_watcher_register import U2WatcherRegister


class U2WatchersSnapchat(U2WatcherRegister):
    snapchat_skip_btn = U2WatcherDef(
        xpaths=['//*[@resource-id="skip_button"]'],
        action="click",
        tags=["snapchat"],
        priority=100,
        description="初次进入的时候的弹窗"
    )

    snapchat_okay_btn = U2WatcherDef(
        xpaths=['//*[@text="Okay"]'],
        action="click",
        tags=["snapchat"],
        priority=100,
        description="Okay 弹窗"
    )

    snapchat_location_btn = U2WatcherDef(
        xpaths=['//*[@resource-id="com.snapchat.android:id/cancel_button"]'],
        action="click",
        tags=["snapchat", "permission", "deny"],
        priority=100,
        description="Allow 弹窗"
    )

