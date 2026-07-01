from powertrde.utils.u2_extends.u2_watcher_def import U2WatcherDef
from powertrde.utils.u2_extends.u2_watcher_register import U2WatcherRegister


class U2WatchersRednote(U2WatcherRegister):
    rednote_mock_button = U2WatcherDef(
        xpaths=['//android.widget.Button[@text="Mock"]'],
        action="click",
        tags=["rednote"],
        priority=100,
        description="模拟rednote监测Mock按钮"
    )

    rednote_not_save_draft = U2WatcherDef(
        xpaths=['//*[@resource-id="com.xingin.xhs:id/btn_unfinished_draft_dialog_exit"]'],
        action="click",
        tags=["rednote"],
        priority=100,
        description="rednote 询问是否保存草稿"
    )
