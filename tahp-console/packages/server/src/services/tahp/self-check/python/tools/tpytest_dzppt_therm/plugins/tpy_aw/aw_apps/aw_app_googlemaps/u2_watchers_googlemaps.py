from powertrde.utils.u2_extends.u2_watcher_def import U2WatcherDef
from powertrde.utils.u2_extends.u2_watcher_register import U2WatcherRegister


class U2WatchersGoogleMaps(U2WatcherRegister):
    googlemaps_mock_button = U2WatcherDef(
        xpaths=['//android.widget.Button[@text="Mock"]'],
        action="click",
        tags=["googlemaps"],
        priority=100,
        description="模拟googlemaps监测Mock按钮"
    )

    googlemaps_discard_button = U2WatcherDef(
        xpaths=['//android.widget.Button[@text="Discard"]'],
        action="click",
        tags=["googlemaps"],
        priority=100,
        description="googlemaps退出照相 监测Discard按钮"
    )
