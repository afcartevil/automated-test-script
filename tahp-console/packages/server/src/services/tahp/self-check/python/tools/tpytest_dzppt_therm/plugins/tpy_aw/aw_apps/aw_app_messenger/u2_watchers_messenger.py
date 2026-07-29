from powertrde.utils.u2_extends.u2_watcher_def import U2WatcherDef
from powertrde.utils.u2_extends.u2_watcher_register import U2WatcherRegister


class U2WatchersMessenger(U2WatcherRegister):
    messenger_mock_button = U2WatcherDef(
        xpaths=['//android.widget.Button[@text="Mock"]'],
        action="click",
        tags=["messenger"],
        priority=100,
        description="模拟messenger监测Mock按钮"
    )

    common_answer_vedio_call_button = U2WatcherDef(
        xpaths=['//android.widget.Button[@text="Video"]'],
        action="click",
        tags=["answer",'video'],
        priority=100,
        description="messenger 接听视频电话按钮"
    )
    common_ok_button = U2WatcherDef(
        xpaths=['//*[@text="OK"]'],
        action='click',
        tags=["ok", 'messenger'],
        priority=100,
        description="messenger打电话弹窗"
    )
    common_cancel_button = U2WatcherDef(
        xpaths=['//*[@text="Cancel"]'],
        action='click',
        tags=["ok", 'messenger'],
        priority=100,
        description="messenger tips"
    )
