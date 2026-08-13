# 柱 3 客制化特性输入表（**可选**）

**口述优先**：柱 3 请直接在任务对话里 **分条说** 要做哪些 `RULE-*` / `SM40-*` 和参数即可（见 **`transsion-sunmao40-customization-features-adapt`** **RULE-0**）。本文件 **不必填**；表格较密，仅适合自愿整理或给第三方留纪要时对照。

**约定路径**：`~/.cursor/skills/adapt/pillar3-customization/transsion-sunmao40-customization-features-adapt/pillar3-customization-input.md`（可复制到项目侧；实际路径不同时须在任务中声明 `Read` 路径。）

## 四列表头说明（若仍使用本表）

| 列 | 谁维护 | 说明 |
|----|--------|------|
| **特性键** | 模板固定 | **勿改、勿删行**，用于跳转到 `transsion-sunmao40-customization-features-adapt` 中对应 `## RULE-x` / `## SM40-xx`。 |
| **是否需要支持** | **你填** | 只填 **是** 或 **否**。仅 **是** 进入柱 3 改码。 |
| **参数（你填）** | **你填** | 除开关外须给的宏、`键=值`、GPIO、DWS、整段 `dtsi: ...`、factory.ini / 代码说明等，**全部写在本列**；多条用英文 **`;`** 分隔。 |
| **示例（格式参考）** | **模板预填** | **请勿覆盖本列**；写 **参数** 时对照本列的**格式与粒度**改数值。 |

**否且无柱 3 工作量**：在 **参数** 列写 **「此项特性无适配工作量」**（可再加分号追加一句说明）。

**KPOC**：**RULE-2** 与 **SM40-16** 二选一填 **是**，勿两行同时为 **是**。

**超长 dtsi**：表内写摘要或 `见任务对话 SM40-xx 全文`；完整片段在对话里按特性键贴出。

---

## 输入表

| 特性键 | 是否需要支持 | 参数（你填） | 示例（格式参考） |
|--------|----------------|--------------|------------------|
| RULE-1 | 否 | | path=vendor/.../overlay/foo.dtsi;node=myfeature;compatible=vendor,myfeat;action=启用 |
| RULE-2 | 否 | | TRAN_CHARGER_KPOC_ANIMATION=yes;CUSTOM_TRAN_LOGO=tran_logo_infinix |
| RULE-3 | 否 | | TRAN_BSP_CHARGE_TYPE_SUPPORT=pe_charge,rfc_charge;factory.ini:删无硬件项如USBTYPEC(A)并注原因 |
| RULE-4 | 否 | | verify=与基线一致仅解注核对;或解注块名support_enhance_mode,port_corrosion |
| SM40-01 | 否 | | burn_max_temp=450;burn_gap_temp=30;burning_interval=5000;normal_interval=10000;control_gpio=<&pio 0 5 0>;KO与DWS见§SM40-01 |
| SM40-02 | 否 | | bat_health_cycle_base=100;bat_health_dec_times=3;ro.tr_battery.health.support=true |
| SM40-03 | 否 | | support_si_bat=yes;si_bat_cycle_def=…;TRAN_LOW_BATTERY_SUPPORT=yes(LK mk);ro.tr_battery.shutdown_lowvolt.feature.support=… |
| SM40-04 | 否 | | pd_reverse_chg_support=yes;otg_revercharge_limit_temp=420;tc_otg_boost_curr_max=…;otg_reverse_chg_curr_lmt=… |
| SM40-05 | 否 | | batt_ht_boot_soc_threshold=95;batt_lt_boot_soc_threshold=10;kpoc_batt_ht_*=…(成组见§SM40-05) |
| SM40-06 | 否 | | TRAN_SHIPPING_MODE_SUPPORT=yes;shipmode sysfs=/sys/devices/platform/charger/shipmode_enable(以实机为准) |
| SM40-07 | 否 | | support_long_life_recharger=yes;single_batt_level=…;tc_pe50 step_ffc_level*矩阵见§SM40-07 |
| SM40-08 | 否 | | 依charger IC填旁路/HZ相关;ro.tr_charge.bypass_def_on.support=true |
| SM40-09 | 否 | | support_allround_bypass=yes;ro.tr_battery.full_scene_bypass_charging.feature.support=true |
| SM40-10 | 否 | | bat_tbat_level_def_3=…;bat_tbat_curlmt_3=…;ro.tr_tce.travel.feature.support=true |
| SM40-11 | 否 | | support_magnetism_fan_bypass=yes;magnetism_fan_bypass_aicr=2000000 |
| SM40-12 | 否 | | dtsi摘要:&tc_misc{…};&pid_chg{pid_array=…};长表见§SM40-12 |
| SM40-13 | 否 | | CONFIG_TC_PHY_INSERT_DET=m;CONFIG_TC_PORT_CORROSION=m;phy_det+port_corrosion节点+ko_order_table见§SM40-13 |
| SM40-14 | 否 | | support_bat_self_repair=true;bat_repair_cycle_threshold=200;bat_repair_done_uisoc=5;bat_repair_done_vbat=3400;dtsi:health_percent_cycle_table=<0 100 200 500>;health_percent_add_table=<0 1 2 5>;(尖括号须规格书确认) |
| SM40-15 | 否 | | pe50三档*_level_def_0..2与*_curlmt_0..2;ro.tr_charging.animation.support=true |
| SM40-16 | 否 | | TRAN_CHARGER_KPOC_ANIMATION=yes;CUSTOM_TRAN_LOGO=tran_logo_tecno;BootLogo路径见§SM40-16 |
| SM40-17 | 否 | | water_detect:scheme=…;polling_interval=…;ko:tc_water_detect.ko,tc_audio.ko |
| SM40-18 | 否 | | single_batt_level_*=…;disable_high_temp_lock_uisoc=…;长表见§SM40-18 |
| SM40-19 | 否 | | ro.tr_battery.ai_charging_event_track.feature.support=true;sysfs tran_aichg_disable_charger路径以实机为准 |
| SM40-20 | 否 | | sysfs=/sys/devices/platform/charger/tran_custom_disable_charger;基线已支持仅核对 |
| SM40-21 | 否 | | 改码说明:tc_trancare.c数组与case(非单行键值) |
| SM40-22 | 否 | | cloud_engine_id=…;register_cloudengine_notifier段须/勿注册说明 |
| SM40-23 | 否 | | owner清单:tc_charger.dtsi+battery_prop+ProjectConfig+Framework(原文EU待补齐) |
| SM40-24 | 否 | | tran_Q_diff=…;support_multi_bat_parameter=yes;bat0_*/bat3_*表见§SM40-24 |
| SM40-25 | 否 | | support_enhance_mode=yes;target_temp_array_enhance=<…>;与常规pid表对齐 |
| SM40-26 | 否 | | 专项作废不应支持;否+此项特性无适配工作量 |
| SM40-27 | 否 | | 支持→柱3无底软工作量，不补ro属性；CMO侧ro.tr_charging.animation_wireless_power |
| SM40-28 | 否 | | 支持→柱3无底软工作量，不补ro属性；CMO侧ro.tr_battery.wireless_reverse_charge.support |
| SM40-29 | 否 | | ro.tr_charging.animation_wire_power=100W |
| SM40-30 | 否 | | ro.tr_charging.animation.support=true |
| SM40-31 | 否 | | charger_voltage_ovp=<u1 u2 u3 u4>(µV以binding为准) |
| SM40-32 | 否 | | 基线已集成仅核对;或wireless_fragment调参说明 |
| SM40-33 | 否 | | ro.tr_game.magnetic_fan.support=true;与SM40-11联调说明 |
