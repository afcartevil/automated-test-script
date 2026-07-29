from powertrde.utils.u2_extends.u2_watcher_def import U2WatcherDef
from powertrde.utils.u2_extends.u2_watcher_register import U2WatcherRegister


class U2WatchersWhatsapp(U2WatcherRegister):
    whatsapp_mock_button = U2WatcherDef(
        xpaths=['//android.widget.Button[@text="Mock"]'],
        action="click",
        tags=["whatsapp"],
        priority=100,
        description="模拟whatsapp监测Mock按钮"
    )
