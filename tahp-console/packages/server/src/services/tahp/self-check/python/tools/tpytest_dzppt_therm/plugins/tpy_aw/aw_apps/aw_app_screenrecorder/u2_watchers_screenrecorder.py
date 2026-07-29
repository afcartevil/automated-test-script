from powertrde.utils.u2_extends.u2_watcher_def import U2WatcherDef
from powertrde.utils.u2_extends.u2_watcher_register import U2WatcherRegister


class U2WatchersScreenRecorder(U2WatcherRegister):
    start_recording = U2WatcherDef(
        xpaths=['//*[@text="Start recording"]'],
        action="click",
        tags=["screenrecorder"],
        priority=100,
        description="开始录制的弹窗"
    )
