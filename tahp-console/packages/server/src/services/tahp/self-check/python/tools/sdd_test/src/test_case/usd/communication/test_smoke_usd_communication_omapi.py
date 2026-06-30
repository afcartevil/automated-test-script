# coding=utf-8
import pytest

from src.conftests.device import get_device_build_brand
from src.utils.adb.adb_utils import adb_shell


def _split_platform_tokens(platform_field):
    if not platform_field:
        return []
    parts = []
    for part in platform_field.replace('\\', ',').replace('/', ',').split(','):
        token = part.strip().upper()
        if token:
            parts.append(token)
    return parts


def _skip_unless_platform_match(device_serial, platform_field):
    allowed = _split_platform_tokens(platform_field)
    if not allowed:
        return
    brand = get_device_build_brand(device_serial).upper()
    normalized = {'QUALCOMM': 'QCOM', 'QCOM': 'QCOM', 'MTK': 'MTK', 'SPRD': 'SPRD'}
    current = normalized.get(brand, brand)
    mapped_allowed = [normalized.get(x, x) for x in allowed]
    if current not in mapped_allowed:
        pytest.skip(f'需要平台 {mapped_allowed}，当前品牌: {current}')


CASES = [
    {
        "feature": "OMAPI接口功能",
        "spd": "",
        "platform": "MTK",
        "commands": [
            "ls /vendor/bin/hw | grep secure_element"
        ],
        "expected_tokens": [
            "android.hardware.secure_element",
            "1",
            "2"
        ],
        "steps": "adb shell 命令执行：\nls /vendor/bin/hw | grep secure_element",
        "expected_raw": "输出：android.hardware.secure_element@1.2-service-mediatek"
    },
    {
        "feature": "拦截名单管理、已拦截的来电列表、拦截后通知、骚扰短信拦截",
        "spd": "SF-202507-001675",
        "platform": "MTK",
        "commands": [
            "getprop ro.tr_telephony.intercept_v2.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_telephony.intercept_v2.support",
        "expected_raw": "1为支持"
    },
    {
        "feature": "伪基站拦截",
        "spd": "SF-202507-001678",
        "platform": "MTK",
        "commands": [
            "getprop ro.tr_telephony.fake_cell.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_telephony.fake_cell.support",
        "expected_raw": "1为支持"
    },
    {
        "feature": "智能转接",
        "spd": "SF-202508-000123",
        "platform": "MTK",
        "commands": [
            "getprop ro.tr_telephony.smart_call_forward.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_telephony.smart_call_forward.support",
        "expected_raw": "1为支持"
    },
    {
        "feature": "无网通讯1.0",
        "spd": "SF-202507-001741",
        "platform": "MTK",
        "commands": [
            "getprop ro.tr_ultralink.feature.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_ultralink.feature.support",
        "expected_raw": "1为支持"
    },
    {
        "feature": "Geniex底层能力",
        "spd": "SF-202507-001820",
        "platform": "MTK",
        "commands": [
            "getprop ro.tr_telephony.vsim.support = 1",
            "getprop ro.tr_telephony.vsim_pkg.config = geniex",
            "getprop ro.tr_telephony.vsim_geniex_entrance.support =1"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_telephony.vsim.support = 1\nadb shell getprop ro.tr_telephony.vsim_pkg.config = geniex\nadb shell getprop ro.tr_telephony.vsim_geniex_entrance.support =1",
        "expected_raw": "ro.tr_telephony.vsim.support= 1\nro.tr_telephony.vsim_pkg.config = geniex\nro.tr_telephony.vsim_geniex_entrance.support = 1"
    },
    {
        "feature": "Gotii底层能力",
        "spd": "SF-202507-001821",
        "platform": "",
        "commands": [
            "getprop ro.tr_telephony.vsim.support = 1",
            "getprop ro.tr_telephony.vsim_pkg.config = gotii",
            "getprop ro.tr_telephony.vsim_gotii_entrance.support = 1"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_telephony.vsim.support = 1\nadb shell getprop ro.tr_telephony.vsim_pkg.config = gotii\nadb shell getprop ro.tr_telephony.vsim_gotii_entrance.support = 1",
        "expected_raw": "ro.tr_telephony.vsim.support= 1\nro.tr_telephony.vsim_pkg.config = gotii\nro.tr_telephony.vsim_gotii_entrance.support = 1"
    },
    {
        "feature": "M-PESA",
        "spd": "SF-202507-001824",
        "platform": "",
        "commands": [
            "getprop ro.tr_stk.mpesa.feature.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_stk.mpesa.feature.support",
        "expected_raw": "1为支持"
    },
    {
        "feature": "副卡来电可上网(通信智慧管家2.0专项)",
        "spd": "SF-202507-001842",
        "platform": "",
        "commands": [
            "getprop ro.tr_telephony.sdata_switch_v2.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_telephony.sdata_switch_v2.support",
        "expected_raw": "1为支持"
    },
    {
        "feature": "游戏场景来电铃响不断网",
        "spd": "SF-202507-001843",
        "platform": "",
        "commands": [
            "getprop ro.vendor.mtk_gwsd_support = 1",
            "getprop ro.vendor.mtk_gwsd_capability = 1/2 (4G/5G)",
            "getprop ro.tr_telephony.enhanced_gwsd.support = 1 (5G)"
        ],
        "expected_tokens": [
            "1",
            "2"
        ],
        "steps": "adb shell getprop ro.vendor.mtk_gwsd_support = 1\nadb shell getprop ro.vendor.mtk_gwsd_capability = 1/2 (4G/5G)\nadb shell getprop ro.tr_telephony.enhanced_gwsd.support = 1 (5G)",
        "expected_raw": "ro.vendor.mtk_gwsd_support= 1\nro.vendor.mtk_gwsd_capability = 1/2 (4G/5G)\nro.tr_telephony.enhanced_gwsd.support = 1 (5G)"
    },
    {
        "feature": "弱网功率提升",
        "spd": "SF-202507-008750",
        "platform": "",
        "commands": [
            "getprop ro.tr_telephony.swtp.feature.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_telephony.swtp.feature.support",
        "expected_raw": "1为支持"
    },
    {
        "feature": "前台网速优先(智慧分流)",
        "spd": "SF-202507-001844",
        "platform": "",
        "commands": [
            "getprop ro.tr_connectivity.bandwidth_alloc.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_connectivity.bandwidth_alloc.support",
        "expected_raw": "1为支持"
    },
    {
        "feature": "数据网络VIP通道",
        "spd": "SF-202507-001845",
        "platform": "",
        "commands": [
            "getprop ro.tr_connectivity.data_vip.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_connectivity.data_vip.support",
        "expected_raw": "1为支持"
    },
    {
        "feature": "双卡数据网络智能切换",
        "spd": "SF-202507-001846",
        "platform": "",
        "commands": [
            "getprop ro.tr_telephony.sdata.switch.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_telephony.sdata.switch.support",
        "expected_raw": "1为支持"
    },
    {
        "feature": "数据性能增强",
        "spd": "SF-202507-001847",
        "platform": "",
        "commands": [
            "getprop ro.tr_telephony.lte_enhance_afr.support",
            "getprop ro.tr_telephony.lte_enhance_opt.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_telephony.lte_enhance_afr.support\nadb shell getprop ro.tr_telephony.lte_enhance_opt.support",
        "expected_raw": "1为支持"
    },
    {
        "feature": "双卡抢占",
        "spd": "SF-202507-001848",
        "platform": "",
        "commands": [
            "getprop ro.tr_telephony.dsim_opt.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_telephony.dsim_opt.support",
        "expected_raw": "1为支持"
    },
    {
        "feature": "地理围栏",
        "spd": "SF-202507-001849",
        "platform": "",
        "commands": [
            "getprop ro.tr_telephony.signal.predict.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_telephony.signal.predict.support",
        "expected_raw": "1为支持"
    },
    {
        "feature": "wifi+蜂窝LTE/NR多链路并发",
        "spd": "SF-202507-001850",
        "platform": "",
        "commands": [
            "getprop ro.tr_telephony.multilink.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_telephony.multilink.support",
        "expected_raw": "1为支持"
    },
    {
        "feature": "双卡蜂窝多链路并发",
        "spd": "SF-202507-001851",
        "platform": "",
        "commands": [
            "getprop ro.tr_telephony.multilink.v2.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_telephony.multilink.v2.support",
        "expected_raw": "1为支持"
    },
    {
        "feature": "三方应用多链路功耗优化",
        "spd": "SF-202507-008757",
        "platform": "",
        "commands": [
            "getprop ro.tr_telephony.mlp_opt.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_telephony.mlp_opt.support",
        "expected_raw": "1为支持"
    },
    {
        "feature": "灭屏Doze状态下CDRX/TDD小区优选",
        "spd": "SF-202507-008756",
        "platform": "",
        "commands": [
            "getprop ro.tr_telephony.lpm_cell.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_telephony.lpm_cell.support",
        "expected_raw": "1为支持"
    },
    {
        "feature": "modem thermal温升优化",
        "spd": "SF-202507-008755",
        "platform": "",
        "commands": [
            "getprop ro.tr_telephony.md_thermal.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_telephony.md_thermal.support",
        "expected_raw": "1为支持"
    },
    {
        "feature": "飞行场景功耗优化",
        "spd": "SF-202507-008754",
        "platform": "",
        "commands": [
            "getprop ro.tr_telephony.flight_power_opt.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_telephony.flight_power_opt.support",
        "expected_raw": "1为支持"
    },
    {
        "feature": "基于地理位置的漫游无网搜网优化、Oos功耗优化",
        "spd": "SF-202507-008752",
        "platform": "",
        "commands": [
            "getprop ro.tr_telephony.sniffer.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_telephony.sniffer.support",
        "expected_raw": "1为支持"
    },
    {
        "feature": "4G/5G自动切换(Smart5G&Clever5G专项)",
        "spd": "SF-202507-001852",
        "platform": "",
        "commands": [
            "getprop ro.tr_telephony.smart_5g.v3.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_telephony.smart_5g.v3.support",
        "expected_raw": "1为支持"
    },
    {
        "feature": "MDPS通信低功耗优化",
        "spd": "SF-202507-001853",
        "platform": "",
        "commands": [
            "getprop ro.tr_telephony.mdps_afr_restrict.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_telephony.mdps_afr_restrict.support",
        "expected_raw": "1为支持"
    },
    {
        "feature": "灭屏CA Drop方案",
        "spd": "SF-202507-001856",
        "platform": "",
        "commands": [
            "getprop ro.tr_telephony.thermal_cc.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_telephony.thermal_cc.support",
        "expected_raw": "1为支持"
    },
    {
        "feature": "DSDA弱网功耗优化",
        "spd": "SF-202507-001857",
        "platform": "",
        "commands": [
            "getprop ro.tr_telephony.call_poor_signal_dsda.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_telephony.call_poor_signal_dsda.support",
        "expected_raw": "1为支持"
    },
    {
        "feature": "RX&MIMO功耗优化",
        "spd": "SF-202507-001858",
        "platform": "",
        "commands": [
            "getprop ro.tr_mimo_rx.feature.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_mimo_rx.feature.support",
        "expected_raw": "1为支持"
    },
    {
        "feature": "游戏场景蜂窝网络自适应",
        "spd": "SF-202507-001859",
        "platform": "",
        "commands": [
            "getprop ro.tr_telephony.smart_5g_gt.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_telephony.smart_5g_gt.support",
        "expected_raw": "1为支持"
    },
    {
        "feature": "导航场景",
        "spd": "SF-202507-002414",
        "platform": "",
        "commands": [
            "getprop ro.tr_telephony.thermal_navigation.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_telephony.thermal_navigation.support",
        "expected_raw": "1为支持"
    },
    {
        "feature": "电梯模式快速回网",
        "spd": "SF-202507-008759",
        "platform": "",
        "commands": [
            "getprop ro.tr_telephony.ai.elevator.feature.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_telephony.ai.elevator.feature.support",
        "expected_raw": "1为支持"
    },
    {
        "feature": "DSDA快速回网机制",
        "spd": "SF-202507-008760",
        "platform": "",
        "commands": [
            "getprop ro.tr_telephony.ups_dsda_quick_retNR.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_telephony.ups_dsda_quick_retNR.support",
        "expected_raw": "1为支持"
    },
    {
        "feature": "Linkbrush网络问题自动修复",
        "spd": "SF-202507-008761",
        "platform": "",
        "commands": [
            "getprop ro.tr_telephony.ups_datastall.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_telephony.ups_datastall.support",
        "expected_raw": "1为支持"
    },
    {
        "feature": "信号bar显示",
        "spd": "SF-202507-008762",
        "platform": "",
        "commands": [
            "getpropro.tr_telephony.ups_smooth.support",
            "getpropro.tr_telephony.ups_signal.support(支持5g b1)",
            "getprop ro.tr_telephony.ups_datarat_alwaysshow.support",
            "getprop ro.tr_telephony.ups_datarat_plus.suppport"
        ],
        "expected_tokens": [
            "1",
            "2",
            "3",
            "0",
            "4"
        ],
        "steps": "1.平滑方案,adbshell getpropro.tr_telephony.ups_smooth.support\n2.五格信号,adb shell getpropro.tr_telephony.ups_signal.support(支持5g b1)\n3.数据图标分离:adb shell getprop ro.tr_telephony.ups_datarat_alwaysshow.support\n4.H+默认显示:adb shell getprop ro.tr_telephony.ups_datarat_plus.suppport\n注:\n16.2及以后的版本,\"五格信号\"与\"数据图标分离\"已被下架,需将对应属性配置为\"0\"",
        "expected_raw": "1.返回\"1\"代表导入\n2.返回\"1\"代表导入仅导入5g项目\n3.tos16.1及之前项目:返回\"1\"代表导入\ntos16.2及之后项目:返回值为\"0\"\n4.返回\"1\"代表导入"
    },
    {
        "feature": "无业务场景快速驻留高制式网络",
        "spd": "SF-202507-001864",
        "platform": "",
        "commands": [
            "getprop ro.tr_telephony.ups_ratstall.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_telephony.ups_ratstall.support",
        "expected_raw": "1为支持"
    },
    {
        "feature": "数据主卡最优网络选择",
        "spd": "SF-202507-001866",
        "platform": "",
        "commands": [
            "getprop ro.tr_telephony.ups_preferred_nw.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_telephony.ups_preferred_nw.support",
        "expected_raw": "1为支持"
    },
    {
        "feature": "DSDA防ping pong",
        "spd": "SF-202508-000127",
        "platform": "",
        "commands": [
            "getprop ro.tr_telephony.dsda_regulate.support",
            "getprop ro.tr_telephony.ca_regulation.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_telephony.dsda_regulate.support\nadb shell getprop ro.tr_telephony.ca_regulation.support",
        "expected_raw": "@ro.tr_telephony.dsda_regulate.support= 1\n@ro.tr_telephony.ca_regulation.support= 1"
    },
    {
        "feature": "通信基础能力热插拔",
        "spd": "SF-202507-001868",
        "platform": "",
        "commands": [
            "getprop ro.tr_telephony.cloud.basic.abilities.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_telephony.cloud.basic.abilities.support",
        "expected_raw": "1为支持"
    },
    {
        "feature": "云网一体化",
        "spd": "SF-202507-001869",
        "platform": "",
        "commands": [
            "getprop ro.tr_telephony.radioconfig.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_telephony.radioconfig.support",
        "expected_raw": "1为支持"
    },
    {
        "feature": "大数据埋点(RTT延时)",
        "spd": "SF-202507-001876",
        "platform": "",
        "commands": [
            "getprop ro.tr_telephony.hook_rtt.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_telephony.hook_rtt.support",
        "expected_raw": "1为支持"
    },
    {
        "feature": "RRC重建自愈方案",
        "spd": "SF-202508-000128",
        "platform": "",
        "commands": [
            "getprop ro.tr_telephony.careset.feature.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_telephony.careset.feature.support",
        "expected_raw": "1为支持"
    },
    {
        "feature": "大数据通信地图",
        "spd": "SF-202507-008758",
        "platform": "",
        "commands": [
            "getprop ro.tr_telephony.smart.travel.feature.support",
            "getprop ro.tr_telephony.dmf_endc_nr_rat.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_telephony.smart.travel.feature.support\nadb shell getprop ro.tr_telephony.dmf_endc_nr_rat.support",
        "expected_raw": "ro.tr_telephony.smart.travel.feature.support =1\nro.tr_telephony.dmf_endc_nr_rat.support =1"
    },
    {
        "feature": "全场景日志采集系统方案",
        "spd": "SF-202507-001877",
        "platform": "",
        "commands": [
            "getprop ro.tr_dfx_sim.feature.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_dfx_sim.feature.support",
        "expected_raw": "1为支持"
    },
    {
        "feature": "网络频段-泰国定制",
        "spd": "SF-202507-001895",
        "platform": "",
        "commands": [
            "getprop ro.tr_telephony.shield_eg_tha_band.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_telephony.shield_eg_tha_band.support",
        "expected_raw": "1为支持"
    },
    {
        "feature": "网络频段-EE1 MegaFon定制",
        "spd": "SF-202507-001896",
        "platform": "",
        "commands": [
            "getprop ro.tr_telephony.disable.elevator.mode.feature.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_telephony.disable.elevator.mode.feature.support",
        "expected_raw": "1为支持"
    },
    {
        "feature": "频段屏蔽-埃及EDGE屏蔽",
        "spd": "SF-202507-001897",
        "platform": "",
        "commands": [
            "getprop ro.tr_telephony.edge.support",
            "getprop ro.tr_telephony.edge_nr.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "4G配置:adb shell getprop ro.tr_telephony.edge.support\n5G配置:adb shell getprop ro.tr_telephony.edge_nr.support",
        "expected_raw": "1为支持"
    },
    {
        "feature": "频段屏蔽-印尼频段屏蔽",
        "spd": "SF-202507-001898",
        "platform": "",
        "commands": [
            "getprop ro.tr_telephony.global_band.feature.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_telephony.global_band.feature.support",
        "expected_raw": "1为支持"
    },
    {
        "feature": "4.5G",
        "spd": "SF-202507-001899",
        "platform": "",
        "commands": [
            "getprop ro.tr_telephony.always_show_custom_ca_icon.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_telephony.always_show_custom_ca_icon.support",
        "expected_raw": "1为支持"
    },
    {
        "feature": "5.5G",
        "spd": "SF-202507-001900",
        "platform": "",
        "commands": [
            "getprop ro.tr_telephony.nr_advance_icon.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_telephony.nr_advance_icon.support",
        "expected_raw": "1为支持"
    },
    {
        "feature": "5G快捷开关",
        "spd": "SF-202508-000136",
        "platform": "",
        "commands": [
            "getprop ro.tr_telephony.5g_switch.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_telephony.5g_switch.support",
        "expected_raw": "1为支持"
    },
    {
        "feature": "三DBDT天线切换方案",
        "spd": "SF-202507-001902",
        "platform": "",
        "commands": [
            "getprop ro.tr_telephony.antenna_switch.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_telephony.antenna_switch.support",
        "expected_raw": "1为支持"
    },
    {
        "feature": "网络增强设置、游戏网络加速",
        "spd": "SF-202507-001930",
        "platform": "",
        "commands": [
            "getprop ro.tr_game.network_acceleration.support",
            "getprop ro.tr_telephony.comm.game.engine.v2.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_game.network_acceleration.support\nadb shell getprop ro.tr_telephony.comm.game.engine.v2.support\n1.0和2.0不需要同时配置,支持哪个配哪个",
        "expected_raw": "1为支持"
    },
    {
        "feature": "网络检测",
        "spd": "SF-202507-008785",
        "platform": "",
        "commands": [
            "getprop ro.tr_game.network.detection.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_game.network.detection.support",
        "expected_raw": "1为支持"
    },
    {
        "feature": "智能网络双通道",
        "spd": "SF-202507-001964",
        "platform": "",
        "commands": [
            "getprop ro.tr_telephony.multilink.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_telephony.multilink.support",
        "expected_raw": "1为支持"
    },
    {
        "feature": "游戏模式IMS重注册优化",
        "spd": "SF-202507-001967",
        "platform": "",
        "commands": [
            "getprop ro.tr_telephony.game_ims.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_telephony.game_ims.support",
        "expected_raw": "1为支持"
    },
    {
        "feature": "仅使用默认上网卡/游戏时关闭副卡",
        "spd": "SF-202507-001968",
        "platform": "",
        "commands": [
            "getprop ro.tr_telephony.comm.game.engine.v2.support",
            "getprop ro.tr_telephony.cellular.game.engine.v2.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_telephony.comm.game.engine.v2.support\nadb shell getprop ro.tr_telephony.cellular.game.engine.v2.support",
        "expected_raw": "1为支持"
    },
    {
        "feature": "数据卡智能切换",
        "spd": "SF-202507-001969",
        "platform": "",
        "commands": [
            "getprop ro.tr_telephony.sdata_switch_v2.support",
            "getprop ro.tr_telephony.comm.game.engine.v2.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_telephony.sdata_switch_v2.support\nadb shell getprop ro.tr_telephony.comm.game.engine.v2.support",
        "expected_raw": "1为支持"
    },
    {
        "feature": "窜贷识别",
        "spd": "SF-202507-002250",
        "platform": "",
        "commands": [
            "getprop ro.tr_anti-diversion.spec.support"
        ],
        "expected_tokens": [
            "3"
        ],
        "steps": "adb shell getprop ro.tr_anti-diversion.spec.support",
        "expected_raw": "3为支持"
    },
    {
        "feature": "锁机&解锁",
        "spd": "SF-202507-002251",
        "platform": "",
        "commands": [
            "getprop ro.tr_anti-diversion.v2.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_anti-diversion.v2.support",
        "expected_raw": "1为支持"
    },
    {
        "feature": "破解自愈",
        "spd": "SF-202507-002252",
        "platform": "",
        "commands": [
            "getprop ro.tr_anti-diversion.nvrecover.support=3",
            "getprop ro.tr_anti-diversion.timerv2.support=1",
            "getprop ro.tr_anti-diversion.rpmb.support =1"
        ],
        "expected_tokens": [
            "3",
            "1"
        ],
        "steps": "adb shell getprop ro.tr_anti-diversion.nvrecover.support=3\nadb shell getprop ro.tr_anti-diversion.timerv2.support=1\nadb shell getprop ro.tr_anti-diversion.rpmb.support =1",
        "expected_raw": "adb shell getprop ro.tr_anti-diversion.nvrecover.support=3\nadb shell getprop ro.tr_anti-diversion.timerv2.support=1\nadb shell getprop ro.tr_anti-diversion.rpmb.support =1"
    },
    {
        "feature": "埋点监测",
        "spd": "SF-202507-002253",
        "platform": "",
        "commands": [
            "getprop ro.tr_anti-diversion.cracktrack.support =1",
            "getprop ro.tr_anti-diversion.nodetrack.support =1"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_anti-diversion.cracktrack.support =1\nadb shell getprop ro.tr_anti-diversion.nodetrack.support =1",
        "expected_raw": "1为支持"
    },
    {
        "feature": "个人紧急信息查看",
        "spd": "SF-202508-000122",
        "platform": "",
        "commands": [
            "getprop ro.tr_telephony.emergency_message.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_telephony.emergency_message.support",
        "expected_raw": "1为支持"
    },
    {
        "feature": "支付类应用合作",
        "spd": "SF-202507-002460",
        "platform": "",
        "commands": [
            "getprop ro.tr_connectivity.bandwidth_alloc.support"
        ],
        "expected_tokens": [
            "1"
        ],
        "steps": "adb shell getprop ro.tr_connectivity.bandwidth_alloc.support",
        "expected_raw": "1为支持"
    }
]


def _build_marks(case):
    marks = []
    if case.get('spd'):
        marks.append(pytest.mark.require_spd_feature_support(case['spd']))
    return marks


PARAMS = [
    pytest.param(case, id=f"{idx + 1:02d}_{case['feature']}", marks=_build_marks(case))
    for idx, case in enumerate(CASES)
]


@pytest.mark.parametrize('case', PARAMS)
def test_smoke_usd_communication_cases(device_serial, case):
    """来自《底软集成自测冒烟用例》业务领域=底软集成-通信 的自动生成冒烟检查。"""
    if not device_serial:
        pytest.skip('未提供 device_serial，跳过设备侧冒烟检查')

    _skip_unless_platform_match(device_serial, case.get('platform', ''))

    commands = case.get('commands') or []
    if not commands and case.get('steps'):
        for line in case['steps'].splitlines():
            line = line.strip()
            if not line:
                continue
            line = line.replace('adb shell 命令执行：', 'adb shell ')
            if line.lower().startswith('adb shell '):
                commands.append(line[10:].strip())
            elif line.startswith(('ls ', 'getprop ', 'find ', 'cat ')):
                commands.append(line)

    if not commands:
        pytest.skip(f"未能从测试步骤解析 adb shell 命令: {case.get('steps', '')}")

    outputs = []
    for shell_command in commands:
        normalized_command = shell_command.strip()
        if normalized_command.startswith('getprop ') and ' = ' in normalized_command:
            normalized_command = normalized_command.split(' = ', 1)[0].strip()

        result = adb_shell(device_serial, normalized_command, no_retry=True)
        outputs.append(result.get('output', ''))

    merged_output = '\n'.join(outputs)
    expected_tokens = case.get('expected_tokens') or []

    if expected_tokens:
        matched = any(token in merged_output for token in expected_tokens)
        assert matched, (
            f"{case['feature']} 校验失败: expected any of {expected_tokens}; "
            f"actual output: {merged_output!r}; commands={commands}"
        )
    else:
        assert merged_output is not None, (
            f"{case['feature']} 执行失败: output is None; commands={commands}"
        )
