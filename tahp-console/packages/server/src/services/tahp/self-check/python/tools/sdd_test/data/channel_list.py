# -*- coding: utf-8 -*-

from enum import IntEnum

"""
CP : 检查包名存在，并检查对应渠道号txt文件是否存在
AF : 检查包名存在，并检查af文件中是否有对应渠道号字符串
PC ： 检查包名存在，并获取指定prop对应的文件，检查文件内容是否有指定渠道号字符串
PROP ： 检查包名存在，并直接检查对应prop是否正确
"""


class CHANNEL_TYPE(IntEnum):
    CP = 1
    AF = 2
    PC = 3
    PROP = 4
    CAT = 5


"""
包名：【渠道号类型，渠道号txt/AP中的渠道号字符串/渠道号属性值】

当多个应用同包名时，需要指定应用名
包名：【
    【渠道号类型，渠道号txt/AP中的渠道号字符串/渠道号属性值list，应用名】
    【渠道号类型，渠道号txt/AP中的渠道号字符串/渠道号属性值list，应用名】
】
"""
CHANNEL_DICT = {
    "com.afmobi.boomplayer": [CHANNEL_TYPE.CP, "com.afmobi.boomplayer.txt"],
    "com.transsnet.boomplay.lite": [CHANNEL_TYPE.CP, "com.transsnet.boomplay.lite.txt"],
    "com.transsion.phoenix": [CHANNEL_TYPE.CP, "com.transsion.phoenix.txt"],
    "com.transsnet.palmpay": [CHANNEL_TYPE.CP, "com.transsnet.palmpay.txt"],
    "com.transsnetfinancial.palmcredit": [
        CHANNEL_TYPE.CP,
        "com.transsnetfinancial.palmcredit.txt",
    ],
    "com.yomobigroup.chat": [CHANNEL_TYPE.CP, "com.yomobigroup.chat.txt"],
    "cn.wps.moffice_eng": [CHANNEL_TYPE.CP, "cn.wps.moffice_eng.txt"],
    "com.facemoji.lite.transsion": [
        CHANNEL_TYPE.CP,
        "com.facemoji.lite.for.transstion.txt",
    ],
    "com.transtech.geniex": [CHANNEL_TYPE.CP, "com.transtech.geniex.txt"],
    "ru.vk.store": [CHANNEL_TYPE.CP, "ru.vk.store.txt"],
    "ru.dublgis.dgismobile": [CHANNEL_TYPE.CP, "ru.dublgis.dgismobile.txt"],
    "com.yandex.searchapp": [CHANNEL_TYPE.CP, "com.yandex.searchapp.txt"],
    "com.yandex.browser": [CHANNEL_TYPE.CP, "com.yandex.browser.txt"],
    "ru.yandex.androidkeyboard": [CHANNEL_TYPE.CP, "ru.yandex.androidkeyboard.txt"],
    "com.shopee.ph": [
        [CHANNEL_TYPE.CP, "com.shopee.ph.txt", "Shopee PH.apk"],
        [CHANNEL_TYPE.AF, "com.shopee.ph=transsionpreinstall_int", "Shopee.apk"],
    ],
    "com.spotify.music": [
        [
            CHANNEL_TYPE.PROP,
            ["ro.csc.spotify.music.referrerid", "transsion_preload_2025"],
        ],
        [
            CHANNEL_TYPE.PROP,
            ["ro.csc.spotify.music.partnerid", "transsion_preload_2025"],
        ],
    ],
    "com.zhiliaoapp.musically.go": [
        CHANNEL_TYPE.AF,
        "com.zhiliaoapp.musically.go=transsionpreinstall_int",
    ],
    "com.zhiliaoapp.musically": [
        CHANNEL_TYPE.AF,
        "com.zhiliaoapp.musically=transsionpreinstall_int",
    ],
    "com.kwai.bulldog": [CHANNEL_TYPE.AF, "com.kwai.bulldog=transsionpreinstall_int"],
    "com.kwai.video": [CHANNEL_TYPE.AF, "com.kwai.video=transsionpreinstall_int"],
    "ru.more.play": [CHANNEL_TYPE.AF, "ru.more.play=transsionpreinstall_int"],
    # "com.shopee.ph": [channelType.AF, ""], # 同一包名两个渠道号方案，AF CP 单独处理
    # 修改用例。将两个渠道号作为列表合入，每个类型检查，返回结果值，在外层进行报告。遍历列表检查，or形式获取结果值
    "ru.ivi.client": [CHANNEL_TYPE.AF, "ru.ivi.client=transsionpreinstall_int"],
    "com.phonepe.app": [CHANNEL_TYPE.AF, "com.phonepe.app=transsion_preload_2025"],
    "com.ss.android.ugc.trill": [
        CHANNEL_TYPE.AF,
        "com.ss.android.ugc.trill=transsionpreinstall_int",
    ],
    "com.block.juggle": [
        CHANNEL_TYPE.AF,
        # 'com.block.juggle={"pid":"transsionpreinstall_int", "c":"transsion-blockblast-preload-cpp-250901","af_adset":"transsion-blockblast-preload-cpp-250901"}, "c":"transsion-blockblast-preload-cpp-250901","af_adset":"transsion-blockblast-preload-cpp-250901"}',
        'com.block.juggle={"pid":"transsionpreinstall_int"',  # 渠道号中时间会变化，只取固定部分也可判断
    ],
    "com.lazada.android": [
        CHANNEL_TYPE.PC,
        ["ro.trackingId.com.lzd.appid", "transsion_preinstall"],
    ],
    "com.einnovation.temu": [
        CHANNEL_TYPE.PC,
        ["ro.trilo.channel.com.einnovation.temu", "pre_palm"],
    ],
    "ru.dublgis.dgismobile": [
        CHANNEL_TYPE.PROP,
        ["ro.channel.ru.dublgis.dgismobile", "tecno2023"],
    ],
}
