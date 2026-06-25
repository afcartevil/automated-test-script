"""工模各测试组配置：新增用例时在此扩展。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class TranfacGroup:
    """主界面网格类测试组（顺序执行 + ForegroundActivity + 组结果页）。"""

    key: str
    entry_keywords: tuple[str, ...]
    page_keywords: tuple[str, ...]
    result_keywords: tuple[str, ...]
    entry_by: str = "content_desc"
    # 非空时：在主界面依次点击各组标签（如先 Sensor 再 USB），再顺序执行
    tabs_before_sequence: tuple[tuple[str, ...], ...] = ()


@dataclass(frozen=True)
class OtherTabItem:
    """Other 分类页下的单项测试（TextView 成功/失败判定）。"""

    key: str
    item_text: tuple[str, ...]
    label: str


SCREEN = TranfacGroup(
    key="screen",
    entry_keywords=("屏幕", "Screen"),
    page_keywords=("TouchPanel", "触摸屏"),
    result_keywords=("屏幕", "Screen"),
)

# 屏幕顺序测试中名称含以下关键字的子项视为触摸相关（中英文工模均适用）
SCREEN_TOUCH_ITEM_KEYWORDS: tuple[str, ...] = (
    "TouchSelf",
    "TouchPanel",
    "触摸",
    "触摸屏",
)
SCREEN_TOUCH_SELF_ITEM_KEYWORDS: tuple[str, ...] = (
    "TouchSelf",
    "TouchSelf(Incoming Inspection)",
    "触摸屏自检",
    "触摸屏自检(来料检测)",
)
SCREEN_TOUCH_PANEL_ITEM_KEYWORDS: tuple[str, ...] = (
    "TouchPanel",
    "触摸屏",
)

SCREEN_COLOR_ITEM_KEYWORDS: tuple[str, ...] = ("Color", "色彩")
SCREEN_BACKLIGHT_ITEM_KEYWORDS: tuple[str, ...] = ("Backlight", "背光")

AUDIO = TranfacGroup(
    key="audio",
    entry_keywords=("音频", "Audio"),
    page_keywords=("Audio", "音频"),
    result_keywords=("音频", "Audio"),
)

SENSOR = TranfacGroup(
    key="sensor",
    entry_keywords=("Sensor", "传感器"),
    page_keywords=("Sensor", "传感器"),
    result_keywords=("传感器", "Sensor"),
    entry_by="text",
)

USB = TranfacGroup(
    key="usb",
    entry_keywords=(),
    page_keywords=("USB",),
    result_keywords=("USB", "USB"),
    entry_by="text",
    # 在 group_tab 标签栏横滑点击目标标签（见 ui_tranfacmode._find_and_tap_group_tab）
    tabs_before_sequence=(("USB",),),
)

USB_STANDARD_CHARGE_ITEM_KEYWORDS: tuple[str, ...] = (
    "标准充电",
    "StandardCharge",
    "Standard Charge",
)

LIGHT_SENSOR_ITEM_KEYWORDS: tuple[str, ...] = (
    "光传感器",
    "LightSensor",
)

LIGHT_SENSOR_DATA_COLLECT_ITEM_KEYWORDS: tuple[str, ...] = (
    "光感数据采集",
    "LightSensorDataCollect",
)

LIGHT_SENSOR_DATA_COLLECT_ITEM_LABEL = "光感数据采集"
LIGHT_SENSOR_DATA_COLLECT_START_RAW_RID = "com.transsion.tranfacmode:id/start_get_raw"
LIGHT_SENSOR_DATA_COLLECT_START_RAW_XPATH = (
    f'//*[@resource-id="{LIGHT_SENSOR_DATA_COLLECT_START_RAW_RID}"]'
)

LIGHT_SENSOR_CALI_KEYWORDS: tuple[str, ...] = (
    "光传感器校准",
    "LightSensorCali",
)

SENSOR_CALI_EXCLUDE_KEYWORDS: tuple[str, ...] = (
    "校准",
    "Cali",
    "Calibration",
)

LIGHT_SENSOR_GROUP_LABEL = "光感"
LIGHT_SENSOR_GROUP_ITEM_SPECS: tuple[
    tuple[str, tuple[str, ...], tuple[str, ...]], ...
] = (
    ("光传感器", LIGHT_SENSOR_ITEM_KEYWORDS, SENSOR_CALI_EXCLUDE_KEYWORDS),
    (
        "光感数据采集",
        LIGHT_SENSOR_DATA_COLLECT_ITEM_KEYWORDS,
        SENSOR_CALI_EXCLUDE_KEYWORDS,
    ),
)

COMPASS_ITEM_KEYWORDS: tuple[str, ...] = (
    "指南针",
    "Compass",
    "地磁",
    "Magnetometer",
)

COMPASS_GROUP_LABEL = "指南针"
COMPASS_GROUP_ITEM_SPECS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (COMPASS_GROUP_LABEL, COMPASS_ITEM_KEYWORDS),
)

ACCELEROMETER_ITEM_KEYWORDS: tuple[str, ...] = (
    "加速度",
    "Accelerometer",
    "Acceleration",
    "Accel",
    "Acceler",
)

ACCELEROMETER_GROUP_LABEL = "加速度"
ACCELEROMETER_GROUP_ITEM_SPECS: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    (
        ACCELEROMETER_GROUP_LABEL,
        ACCELEROMETER_ITEM_KEYWORDS,
        SENSOR_CALI_EXCLUDE_KEYWORDS,
    ),
)

GYRO_ITEM_KEYWORDS: tuple[str, ...] = (
    "陀螺仪",
    "Gyroscope",
    "Gyro",
)

INFRARED_ITEM_KEYWORDS: tuple[str, ...] = (
    "红外",
    "Consumerlr",
)

PULSE_OXIMETER_ITEM_KEYWORDS: tuple[str, ...] = (
    "血氧传感器测试",
    "血氧传感器",
    "Pulse Oximeter Test",
    "Pulse Oximeter",
)

HAL_SENSOR_CALI_KEYWORDS: tuple[str, ...] = (
    "hal sensor校准",
    "HAL Sensor Cali",
    "HAL Sensor Calibration",
    "HAL Sensor",
)

FLICKER_ITEM_KEYWORDS: tuple[str, ...] = ("Flicker",)

PROXIMITY_SENSOR_ITEM_KEYWORDS: tuple[str, ...] = (
    "距离传感器",
    "Proximity Sensor",
    "Proximity",
)

PROXIMITY_SENSOR_EXCLUDE_KEYWORDS: tuple[str, ...] = (
    "距离传感器2",
    "Proximity Sensor 2",
    "Proximity2",
    "Proximity 2",
)

PROXIMITY_SENSOR_2_ITEM_KEYWORDS: tuple[str, ...] = (
    "距离传感器2",
    "Proximity Sensor 2",
    "Proximity2",
    "Proximity 2",
)

ULTRASOUND_PROXIMITY_SUPPORT_PROP = "ro.tr_audio.ultrasound.support"

SIDE_FINGERPRINT_SUPPORT_PROP = "ro.tr_fingerprint.side.feature.support"

SIDE_FINGERPRINT_ITEM_KEYWORDS: tuple[str, ...] = (
    "指纹",
    "Fingerprint",
)

SIDE_FINGERPRINT_EXCLUDE_KEYWORDS: tuple[str, ...] = (
    "光学",
    "Optical",
    "录入",
    "屏下",
    "Under-display",
)

OPTICAL_FINGERPRINT_SUPPORT_PROP = "ro.tr_fingerprint.optical.feature.support"

OPTICAL_FINGERPRINT_CALI_KEYWORDS: tuple[str, ...] = (
    "光学指纹校准",
    "OpticalFingerprintCali",
)

OPTICAL_FINGERPRINT_TEST_KEYWORDS: tuple[str, ...] = (
    "光学指纹",
    "FingerprintOptical",
)

OPTICAL_FINGERPRINT_TEST_EXCLUDE_KEYWORDS: tuple[str, ...] = (
    "校准",
    "Cali",
    "录入",
    "Enroll",
)

OPTICAL_FINGERPRINT_ENROLL_KEYWORDS: tuple[str, ...] = (
    "指纹录入",
    "FingerprintEnroll",
)

OPTICAL_FINGERPRINT_ENROLL_EXCLUDE_KEYWORDS: tuple[str, ...] = (
    "校准",
    "Cali",
)

OPTICAL_FINGERPRINT_GROUP_LABEL = "屏下指纹"
OPTICAL_FINGERPRINT_GROUP_ITEM_SPECS: tuple[
    tuple[str, tuple[str, ...], tuple[str, ...]], ...
] = (
    (
        "光学指纹",
        OPTICAL_FINGERPRINT_TEST_KEYWORDS,
        OPTICAL_FINGERPRINT_TEST_EXCLUDE_KEYWORDS,
    ),
    (
        "指纹录入",
        OPTICAL_FINGERPRINT_ENROLL_KEYWORDS,
        OPTICAL_FINGERPRINT_ENROLL_EXCLUDE_KEYWORDS,
    ),
)

# Other 分类页公共参数
OTHER_GROUP_TAB_RID = "com.transsion.tranfacmode:id/group_tab"
OTHER_TAB_TEXT = ("其他", "Other")
# 单项测试结果页：test_status_tv / result_btn_* 常用「通过」「失败」（与组结果页一致）
OTHER_PASS_TEXT = ("通过", "成功", "PASS", "Pass")
OTHER_FAIL_TEXT = ("失败", "FAIL", "Fail")
OTHER_RESULT_STATUS_RID = "com.transsion.tranfacmode:id/test_status_tv"
OTHER_TAB_SWIPE_LEFT_TIMES = 2
# 「其他/Other」分类页常见列表项，用于判断是否已进入该页
OTHER_PAGE_MARKERS = (
    "按键",
    "Keypad",
    "马达",
    "Vibrator",
    "存储卡",
    "线性马达",
    "肩键",
    "ShoulderKey",
)
ADAPTER_TITLE_RID_SUFFIX = "adapter_title"

KEYPAD = OtherTabItem("keypad", ("Keypad", "按键"), "按键")
MONO_LED = OtherTabItem("mono_led", ("单色灯", "Mono LED"), "单色灯")
SRGB_LED = OtherTabItem("srgb_led", ("RGB灯", "RGB LED"), "RGB灯")
LED_ITEMS = (MONO_LED, SRGB_LED)
VIBRATOR_ROTOR = OtherTabItem("vibrator_rotor", ("Vibrator", "马达"), "转子马达")
VIBRATOR_LINEAR = OtherTabItem(
    "vibrator_linear", ("LinearVibrator", "线性马达"), "线性马达"
)
# 合并用例：进入 Other 后按界面识别转子/线性马达（优先转子）
VIBRATOR_ITEMS = (VIBRATOR_ROTOR, VIBRATOR_LINEAR)

SHOULDER_KEY_CALI = OtherTabItem(
    "shoulder_key_cali",
    ("ShoulderKeyCali", "shoulderkeycali", "肩键校准"),
    "肩键校准",
)
SHOULDER_KEY = OtherTabItem(
    "shoulder_key",
    ("ShoulderKey", "shoulderkey", "肩键"),
    "肩键",
)

MAIN_MENU_KEYWORDS: tuple[str, ...] = tuple(
    dict.fromkeys(
        kw for group in (SCREEN, AUDIO, SENSOR) for kw in group.entry_keywords
    )
)
