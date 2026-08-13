---
name: transsion-batt-high-temp-low-cv-eoc
description: "Transsion-高温低CV满充: 分析高温低CV下EOC完成后SOC锁定、高温停充上报、vote停充链路 | CHG_BAT_HT_EOC/EOC/高温停充/不报百/low_CV/满充 | 当用户报告低CV充不到100%、误报/不报高温满充时使用。充电主控走transsion-charger-orchestrator"
funcType: "AI故障分析"
category: "驱动"
---

# Transsion：高温低 CV 满充判定与上报（不报百）

## 业务含义（与代码对应）

高温等场景会按电池表 **降低 CV**。此时电化学上往往 **无法在低 CV 下把 UI SOC 推到 100%**。策略是：当 **充电已按规则判满**（`is_chg_done`，含截止电流 / PE50 taper 等），且当前 **处于低 CV**（`is_low_cv_status`），且 **UISOC 仍小于 100**，则：

1. 通过 **`tc_report_lock_charging(true)`** 置位 **`CHG_BAT_HT_EOC_STATUS`**，并走 **`tc_chgstat_notify()`** 发 **`CHGSTAT=1` uevent**，供 Framework 弹窗「高温停充」类提示（底层到 uevent 为止）。
2. 同时 **`VOTER_BATT_HIGH_TEMP_EOC`** 投票 **`discharge=true`**，在 **`tc_charger_control_check()`** 里 **`tc_enable_charging(false)`**，即 **停充**。
3. **`high_temp_mode=true`** 表示已处于该「高温低 CV 满充/停充」语义，避免重复触发。

**注意**：`tc_high_temp_lock_uisoc_check()` 的 **if 条件里没有直接写「温度高于某阈值」**；**低 CV** 通常来自 **JEITA/电池表**（高温带降 CV），产品侧仍称「高温不报百」。

## 固定代码锚点

| 环节 | 位置 |
|------|------|
| 判定入口 | `tc_charger.c` → `tc_high_temp_lock_uisoc_check()` |
| 上报与 vote | `tc_charger.c` → `tc_report_lock_charging()` |
| 调度 | `charger_check_status()` 内调用 `tc_high_temp_lock_uisoc_check()`，随后 `notify_code != reported_code` 时 `tc_chgstat_notify()` |
| 低 CV 来源 | `tc_chg_update_single_batt_jeita()` / `tc_chg_update_dual_batt_jeita()`：`is_low_cv_status = (vbat_cv < desc->smooth_soc_full_vol)` |
| 充电完成 | `tc_basic_charger.c` → `tc_check_charging_done()` / `check_charging_done()` → `tc_check_sw_eoc()` / PE50 `ALG_TAPER_DONE` 等 → `data->is_chg_done` |
| 总开关 | `desc->disable_high_temp_lock_uisoc`（为 true 则整段判定直接 return） |

## 触发「上报高温停充 + 停充」的条件（全部满足）

```text
!disable_high_temp_lock_uisoc
&& data->is_chg_done
&& data->is_low_cv_status          // vbat_cv < smooth_soc_full_vol
&& tc_get_uisoc() < 100
&& data->high_temp_mode == false
→ tc_report_lock_charging(info, true)
```

### 各条件怎么来的

- **`is_low_cv_status`**  
  - 单电：`tc_chg_update_single_batt_jeita()` 在更新 `vbat_cv` 后：  
    `is_low_cv_status = (vbat_cv < desc->smooth_soc_full_vol)`。  
  - 双电：取 master/slave 合成后的 `vbat_cv` 再同样比较。  
  - **`smooth_soc_full_vol`**：机种 `tc_charger` DTS 属性（默认结构体里有典型值），语义是「认为能对应满电显示」的 CV 门槛；**低于它即「低 CV」**。

- **`is_chg_done`**  
  - 在 `tc_basic_charger.c` 的充电完成检测中置位：非 PE5 走 SW EOC（电压近 CV、电流 ≤ 截止且计数满足等）或 HW EOC；PE5 可走 **`ALG_TAPER_DONE`**（taper 完成）等路径。  
  - 即产品说的 **「电流走到截止电流之后」** 在 SW EOC 路径里对应 **`ibat <= sw_eoc_cur`** 等逻辑（与 `pdata->cv` 一致）。

- **`uisoc < 100`**  
  - `tc_get_uisoc()`：与电量计/UI 侧 SOC 一致；低 CV 下通常 **达不到 100**。

- **`high_temp_mode == false`**  
  - 首次进入；置 true 后本分支不再重复进，直到恢复分支清掉。

## 恢复充电（清标志 + 允许再充）的条件

```text
!is_low_cv_status                    // CV 已回到「非低 CV」（≥ smooth_soc_full_vol 语义）
&& data->high_temp_mode == true
&& data->battery_temp <= BATT_HT_EOC_REC_TEMP   // 头文件中为 43（°C）
→ tc_report_lock_charging(info, false)
```

- 清 **`CHG_BAT_HT_EOC_STATUS`**，**`high_temp_mode=false`**，并再次 vote；随后 **`tc_charger_control_check()`** 若不再被 discharge 投票，会 **`tc_enable_charging(true)`** 恢复充电（与其它 vote 合成结果一致）。

## 上报路径（底层到 Framework）

1. `tc_report_lock_charging(true)`：`notify_code |= CHG_BAT_HT_EOC_STATUS`，`tc_charger_control_vote(..., VOTER_BATT_HIGH_TEMP_EOC, discharge=true, icon_disappeared=true)`。  
2. 同一次或后续 `charger_check_status()`：`tc_chgstat_notify()`。  
3. **`misc_notify_code[]` 中 `CHG_BAT_HT_EOC_STATUS` 优先级较高**；`tc_check_report_condition()` 对 HT EOC 等与 **其它 discharge voter（水检测、烧口等）** 有互斥，避免重复/错误上报。  
4. 成功时 **`kobject_uevent_env(..., "CHGSTAT=1")`**。

日志关键字：`high temp charger full, report uevent`、`high temp recharger, report uevent`。

## 分析步骤（log-first）

```text
高温低 CV / 不报百 排查
- [ ] 是否关闭特性：`disable_high_temp_lock_uisoc`
- [ ] 是否低 CV：`is_low_cv_status` / 日志里 single/dual batt 的 cv 与 smooth_soc_full_vol
- [ ] 是否已判满：`is_chg_done` / `tc_check_charging_done` / SW EOC 或 PE50 taper 日志
- [ ] UISOC：`tc_get_uisoc()` 或 gauge 日志是否 < 100
- [ ] 是否已进 high_temp_mode：避免重复触发
- [ ] 恢复条件：温度是否 ≤ BATT_HT_EOC_REC_TEMP、是否已非低 CV
- [ ] 若未上报：查 `tc_check_report_condition` 是否被其它 voter discharge 挡住
```

## 与其它 skill 的边界

- **电池 CV/CC/EOC 表、JEITA 为何把 CV 压低**：跟 `tc_charger` DTS 的 `single_batt`/`dual` 与 `smooth_soc_full_vol`，属 **主控 + 电池表**；若需追 PE5 侧 taper，可再转 `transsion-pe5-vi-tuning`。  
- **协议/算法未跑 PE5**：`is_chg_done` 仍可能走 SW EOC，本特性 **不依赖 PE5**，但日志表现不同。  
- **纯高温停充、无低 CV**：可能走 **`batt_ht_notify_check`** 等其它 notify 链，**不是**本 skill 主路径。

## 约束

- 不得把「未判满」误判为「不报百」；必须先确认 **`is_chg_done` 与 EOC 路径**。  
- **`BATT_HT_EOC_REC_TEMP` 为代码常量**，若机种需不同阈值，应以 **实际合入分支** 为准。  
- 分析 UI 文案与弹窗逻辑属 Framework，本 skill **只到 uevent / notify_code**。
