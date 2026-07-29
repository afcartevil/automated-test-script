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
        xpaths=['//*[@content-desc="Play" or @content-desc="Play video"]'],
        action="click",
        tags=["youtube", 'playvideo'],
        priority=100,
        description="youtube 选择播放视频清晰度"
    )

    youtube_watching_ad = U2WatcherDef(
        xpaths=['//*[@content-desc="Close ad panel" or @text="Skip"]'],
        action="click",
        tags=["youtube", "ad", 'playvideo'],
        priority=100,
        description="youtube 播放视频中途广告"
    )