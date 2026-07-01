from powertrde.utils.u2_extends.u2_watcher_def import U2WatcherDef
from powertrde.utils.u2_extends.u2_watcher_register import U2WatcherRegister


class U2WatchersCommon(U2WatcherRegister):
    """
    常见弹窗 Watcher 定义：
    - 属性名自动作为 watcher 名称
    - xpaths 与 action 按原始注册方式对应
    """
    common_ok_button = U2WatcherDef(
        xpaths=['//android.widget.Button[@text="OK"]'],
        action="click",
        tags=["common", "consent","playstore"],
        priority=100,
        description="通用 OK 按钮"
    )

    common_agree_continue_button = U2WatcherDef(
        xpaths=['//*[@text="Agree And Continue"]'],
        action="click",
        tags=["common", "consent"],
        priority=100,
        description="键盘同意弹窗按钮"
    )

    common_next_button = U2WatcherDef(
        xpaths=['//android.widget.Button[@text="Next"]'],
        action="click",
        tags=["common", "consent"],
        priority=90,
        description="键盘 Next 按钮（新系统通知）"
    )

    common_got_it_button = U2WatcherDef(
        xpaths=['//android.widget.Button[@text="Got it"]'],
        action="click",
        tags=["common", "consent"],
        priority=90,
        description="键盘 Got it 按钮（新系统通知）"
    )

    common_agree_button = U2WatcherDef(
        xpaths=['//android.widget.Button[@text="Agree"]'],
        action="click",
        tags=["common", "consent"],
        priority=100,
        description="通用 Agree 按钮"
    )
    common_agree_button2 = U2WatcherDef(
        xpaths=['//android.widget.Button[@text="AGREE"]'],
        action="click",
        tags=["common", "consent"],
        priority=100,
        description="通用 Agree2 按钮"
    )

    common_allow_button = U2WatcherDef(
        xpaths=['//android.widget.Button[@text="Allow"]'],
        action="click",
        tags=["permission", "consent"],
        priority=100,
        description="通用 Allow 按钮"
    )

    common_allow_all_button = U2WatcherDef(
        xpaths=['//android.widget.Button[@text="Allow all"]'],
        action="click",
        tags=["permission", "consent"],
        priority=100,
        description="通用 Allow all 按钮"
    )

    common_confirm_button = U2WatcherDef(
        xpaths=['//android.widget.Button[@text="Confirm"]'],
        action="click",
        tags=["permission", "consent"],
        priority=100,
        description="通用 Confirm 按钮"
    )

    common_dont_allow_button = U2WatcherDef(
        xpaths=['//android.widget.Button[@text="Don\u2019t allow"]'],
        action="click",
        tags=["permission", "denial"],
        priority=100,
        description="通用 Don’t allow 按钮"
    )

    common_cancel_button = U2WatcherDef(
        xpaths=['//android.widget.Button[@text="Cancel"]'],
        action="click",
        tags=["permission", "denial"],
        priority=100,
        description="通用 Cancel 按钮"
    )

    discard_cancel_button = U2WatcherDef(
        xpaths=['//android.widget.Button[@text="Discard"]'],
        action="click",
        tags=["permission", "denial"],
        priority=100,
        description="通用 Discard 按钮"
    )

    common_while_using_app_button = U2WatcherDef(
        xpaths=['//android.widget.Button[@text="While using the app"]'],
        action="click",
        tags=["permission"],
        priority=100,
        description="通用 While using the app 按钮"
    )

    common_answer_button = U2WatcherDef(
        xpaths=['//android.widget.Button[@text="Answer"]'],
        action="click",
        tags=["answer"],
        priority=100,
        description="通用 接听语音视频电话按钮"
    )

    common_answer_video_button = U2WatcherDef(
        xpaths=['//*[@text="Video"]'],
        action="click",
        tags=["answer",'video','common'],
        priority=100,
        description="通用 接听视频电话按钮"
    )

    common_locat_button = U2WatcherDef(
        xpaths=['//*[@text="Turn on location"]'],
        action="click",
        tags=["locate"],
        priority=100,
        description="通用 打开定位按钮"
    )

    common_agree_continue_button2 = U2WatcherDef(
        xpaths=['//*[@text="Continue"]'],
        action="click",
        tags=["continue",'playstore'],
        priority=100,
        description="playstore同意continue按钮"
    )
    common_try_again_button = U2WatcherDef(
        xpaths=['//*[@text="Try again"]'],
        action="click",
        tags=[ "try again",'playstore'],
        priority=100,
        description="playstore重试按钮"
    )
    common_save_button = U2WatcherDef(
        xpaths=['//android.widget.Button[@text="SAVE"]'],
        action="click",
        tags=[ "save",'playstore'],
        priority=100,
        description="playstore不保存登陆信息按钮"
    )
    common_skip_button = U2WatcherDef(
        xpaths=['//*[@text="Skip"]'],
        action="click",
        tags=["Complete account setup", 'playstore'],
        priority=200,
        description="playstore点击skip按钮"
    )

    common_not_now_button = U2WatcherDef(
        xpaths=['//*[@text="Not now"]'],
        action="click",
        tags=["not_now", 'playstore'],
        priority=100,
        description="playstorenotnow信息按钮"
    )


