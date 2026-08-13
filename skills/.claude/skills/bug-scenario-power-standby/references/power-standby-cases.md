# 功耗待机 — 典型案例长日志（参考）

**数据性质**：本节 **全部数字、包名、UID、日志行** 均 **逐字摘自** `功耗待机问题分析SOP2Skill.md` §六，**仅作教学对照**。**分析当前 defect 时**，结论中 **只能** 使用 **本案工作区** 文件里真实存在的字段与行；**禁止** 把 Steam/微博案例的 mA、包名、UID 当作本案事实复述。

写入 `bug_analysis_report.md` 时，Evidence 仍须指向 **本案相对路径与行号**。

**目录**：案例 1（Steam / 长持锁） · 案例 2（微博 / SPM+alarm）

***

## 案例 1：KN4n — 双卡静态待机 11.24h 耗电 24%，约 137.33 mA

**现象**：灭屏待机平均功耗 **137.33 mA**，超过 SIM 侧常用 **30 mA** 级标准（以项目基线为准）。

**根因（SOP 结论）**：`com.valvesoftware.steamlink` 应用 **`AudioMix`** 异常长持锁（约 **13h**）。

**关键日志（bugreport — partial wake + Estimated power use 节选）**

```text
Wake lock u0a293 AudioMix: 13h 7m 1s 705ms (0 times) max=49338947

Estimated power use (mAh):
    Capacity: 6700, Computed drain: 199, actual drain: 199
    Global
    screen: 0.0669 apps: 0.0669
    CPU: 419 apps: 419 duration: 13h 53m 26s 128ms
    camera: 1.05 apps: 1.05 duration: 3s 845ms
    audio: 486 apps: 0 duration: 13h 49m 41s 505ms
    video: 0.165 apps: 0.165 duration: 8s 551ms
    mobile_radio: 7203 apps: 7094
    sensors: 0.0376 apps: 0.0376
    gnss: 0.355 apps: 0.355 duration: 29s 978ms
    wakelock: 409 apps: 409 duration: 13h 22m 39s 764ms

All partial wake locks:
  Wake lock u0a293 AudioMix: 13h 7m 1s 705ms (0 times) max=49338947 actual=49338947 (running for 49338947ms) realtime
```

**分析要点（可写入报告）**

- **UID `u0a293`** + 锁名 **`AudioMix`** 与 **audio / wakelock** 统计时长同一量级，可支撑 **应用侧长时 partial wake** 结论。  
- 与 **137 mA** 级现象对齐时，优先在「未睡 / 长持锁」分支落地，再谈应用修复与验证方案。

***

## 案例 2：微博 — 夜间待机频繁唤醒（数传 / alarm 类）

**现象**：灭屏待机平均功耗约 **43 mA**，超过常用 **30 mA** 参考线（以项目为准）。

**根因（SOP 结论）**：`com.sina.weibo` 夜间待机 **频繁唤醒**（结合 alarm + connsys 行为）。

**关键日志（kernel — 原文整块）**

```text
<6>[244518.391440] -(0)[5430:Binder:535_2][name:spm&][SPM] suspend wake up by R12_EINT_EVENT_B, timer_out = 4591536, r13 = 0x84006a80, debug_flag = 0xfc1f9bfc 0x4000006e, r12 = 0x40, r12_ext = 0x0, raw_sta = 0x0 0x0 0x0, idle_sta = 0x341b3, req_sta = 0x1c01000 0x0 0x50000017 0x1f0000 0x0, cg_check_sta =0x0, isr = 0x0, rt_req_sta0 = 0x0 rt_req_sta1 = 0x0 rt_req_sta2 = 0xffffffff rt_req_sta3 = 0xffffffff dram_sw_con_3 = 0x0, raw_ext_sta = 0x184255, wake_misc = 0x310000, pcm_flag = 0x488400 0x0 0x488000 0x488000, req = 0x0, clk_settle = 0x60fe, wlk_cntcv_l = 0x94cb344f, wlk_cntcv_h = 0x559, 26M_off_pct = 0
<6>[244518.391597] -(0)[5430:Binder:535_2][name:spm&][SPM] suspend warning:(OneShot) System LPM is blocked by conn 
<6>[244518.391605] -(0)[5430:Binder:535_2][name:spm&][SPM] Suspended for 140.122 seconds
<6>[244518.391615] -(0)[5430:Binder:535_2][name:spm&][SPM] md_slp_duration = 4430012
<6>[244518.391629] -(0)[5430:Binder:535_2][WMT-CONSYS-HW][I]mtk_wmt_resume: mtk_wmt_resume !!
<6>[244518.391719] -(0)[5430:Binder:535_2]alarmtimer_fired.: type=1, count=19, wakeup count=12, func=devalarm_alarmhandler
<6>[244518.392756] -(0)[833:mtk_wmtd][WMT-CONSYS-HW][I]mtk_wcn_consys_sleep_info_read_all_ctrl:TOP:0,0;MCU:305,4384893;BT:0,0;WIFI:507,4472662;GPS:0,4591656
<6>[244518.393447] (0)[833:mtk_wmtd][WMT-CONSYS-HW][I]consys_dump_osc_state:0x180c1340: 0xe010b (BT)
<6>[244518.428292]  (4)[108:irq/143-mt6358-]mt6358-pmic 10026000.pwrap:mt6359-pmic: Reg[0x534]=0x1,name=rtc,hwirq=64,type=4
<6>[244518.544532]  (1)[5430:Binder:535_2][name:scp&][mt_scp_dump_sleep_count:988] - scp_sleep_cnt_0 = 26862754
```

**SOP 解读（写入报告时可压缩为「证据 + 结论」）**

1. **唤醒原因**：**`R12_EINT_EVENT_B`** — 外部中断类唤醒；本段后续 **`mt6359-pmic` / `rtc`**，且 **`alarmtimer_fired`**，属于 **alarm 定时器到期** 路径；需在 **android log / bugreport** 同时间点反查 **`Alarm{... com.sina.weibo}`** 等（SOP 示例：`AlarmManager: Native set alarm :Alarm{42786ea8 type 0 com.sina.weibo}`）。

2. **suspend 时长**：**`timer_out = 4591536`** 为 32k 计数，**≈ 4591536 / 32768 s**；与 **`Suspended for 140.122 seconds`** 对照理解「上一段休眠长度」。

3. **唤醒瞬间子系统**：**`debug_flag = 0xfc1f9bfc`** 若 **末两位非 `ff`**，提示唤醒前子系统仍有活动；**`System LPM is blocked by conn`** — **conn** 为 WiFi/BT/GPS/FM 合一子系统。旧平台若无 block 名称，用 **`r13`** 位 + **`${platform}_pcm_def.h`**。

4. **26M / modem / connsys / SCP**：**`26M_off_pct = 0`** — AP suspend 期 26M 关闭比例极低，子系统 clock 可能常开。**`md_slp_duration`**、**`mtk_wcn_consys_sleep_info_read_all_ctrl`** 各字段为 32k 计数，可算 **modem / MCU / WIFI / BT / GPS** 等与 suspend 的比例；**`consys_dump_osc_state ... (BT)`** 提示交由 **BT 责任方** 继续深挖。**`scp_sleep_cnt_0`** 可与 suspend 前后差分看 **sensorhub** 是否异常唤醒。

***

## 使用说明

- 上述案例 **不可** 替代当前缺陷的实证；仅作 **格式与推理链** 参考。  
- 报告内引用请使用 **本工作区文件** 的 Evidence 行。
