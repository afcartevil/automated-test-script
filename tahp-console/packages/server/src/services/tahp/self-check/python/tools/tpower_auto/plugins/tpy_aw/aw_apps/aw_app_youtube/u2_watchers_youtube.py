from powertrde.utils.u2_extends.u2_watcher_def import U2WatcherDef
from powertrde.utils.u2_extends.u2_watcher_register import U2WatcherRegister


class U2WatchersYoutube(U2WatcherRegister):
    youtube_mock_button = U2WatcherDef(
        xpaths=['//android.widget.Button[@text="Mock"]'],
        action="click",
        tags=["youtube"],
        priority=100,
        description="模拟youtube监测Mock按钮"
    )

    youtube_1_month_free_ad = U2WatcherDef(
        xpaths=['//*[@content-desc="1 month free"]'],
        action="back",
        tags=["youtube", 'ad'],
        priority=100,
        description="youtube 1 month free 广告"
    )

    youtube_select_quality_for_video= U2WatcherDef(
        xpaths=['//*[@content-desc="Play"]'],
        action="click",
        tags=["youtube", 'playvideo'],
        priority=100,
        description="youtube 选择播放视频清晰度"
    )
