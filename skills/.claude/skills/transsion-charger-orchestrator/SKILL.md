---
funcType: "AI故障分析"
category: "驱动"
---
name: transsion-charger-orchestrator
description: "Transsion-充电主控: 分析tc_charger统一编排流程、vote聚合与主策略线程 | tc_charger/plug_in/vote/charging_disable/hiz/JEITA | 当用户报告充电异常、plug in/out问题、多充电IC编排异常时使用。高温低CV满充走transsion-batt-high-temp-low-cv-eoc"
---

# Transsion 充电主控编排

## 适用范围

只分析 `tc_charger.c` 为中心的充电主控编排层。

包含：
- `drivers/power/supply/transsion/tc_charger.c` 主流程
- 算法与辅助接口：
  - `drivers/power/supply/transsion/tc_basic_charger.c`
  - `drivers/power/supply/transsion/tc_misc_intf.c`
  - `drivers/power/supply/transsion/tc_common_class.c`
- 插拔事件、投票（vote）与策略分发

不包含：
- `tc_chg_type_det.c` 的 BC1.2 / type detect 内部流程
- `tc_charger_class.c` 的具体 type detect ops 细节
- PD 协议状态机细节（`typec/tcpc`）
- USB 枚举核心（`drivers/usb/mtu3`）
- 电量计/SOC 算法细节（`mtk_battery*`、`*-gauge.c`）

## 固定入口

优先从以下函数开始：
1. `tc_charger_probe()`
2. `tc_charger_plug_in()` / `tc_charger_plug_out()`
3. `tc_charger_control_vote()` 及其调用链
4. `charger_routine_thread()`
5. `tc_charger_control_check()`
6. `tc_charger_set_property()` / `tc_charger_prop_init()`
7. JEITA 电池表：`tc_check_batt_jeita()` → `tc_chg_update_single_batt_jeita()` / `tc_chg_update_dual_batt_jeita()`（见下文「JEITA CV/CC/EOC」）

关键标识：
- 平台驱动/设备名统一为 `charger`
- 统一对外设备常见为 `tc_charger`

## 分析步骤

```text
充电主控排查清单
- [ ] 先确认阶段：probe / 插入 / 充电循环 / 拔出
- [ ] 跟踪 tc_charger_plug_in() / tc_charger_plug_out()
- [ ] 跟踪 charger_routine_thread() 何时被唤醒
- [ ] 跟踪投票链：tc_charger_control_vote() -> tc_charger_control_check()
- [ ] 跟踪策略结果如何下发到 algo / charger device
- [ ] 核对 dtsi `support_alg` 是否在 `tc_charger_parse_dt()` 成功解析，并在 `charger_init_algo()` 中 `get_tchg_alg_by_name()` 全部成功
- [ ] 若涉及“跑了哪套快充算法”，优先看 `tc_basic_charger.c: tc_algo_protocol_process()` 的 `data->running_algo`，不要默认等于 PE5 内 `support_ta`
- [ ] 确认通知链路：tran_dev_notify / uevent
- [ ] 区分“主控策略层问题”与“type detect 已经在前序出错”
```

### 客制化特性快速判定（主控层）

```text
客制化特性排查清单
- [ ] 低功率充电增强：
  - 锚点：`support_enhance_mode`、`set pid target temp 1/0`、`ALG_ADAPTER_CAPACITY`
  - 前提：`alias_type == TC_DCP`
  - 先看 `running_algo` 和 `adapter_capacity`，再看 `TRAN_PROP_ENHANCE_MODE` 是否成功下发
  - 必须区分“未触发（条件不满足）”与“已触发但未生效（目标温度未切换）”
- [ ] 全场景旁路 / 旁路2.0：
  - 锚点：`bypass_charger`、`wait_protocol_work`、`bypass_checkcnt`、`BYPASS_CHG_VOTER`
  - 全场景旁路判据：`vote ichg = 300000`（约 300mA 入电池）
  - 旁路2.0判据：`BYPASS_V20_ENABLE` / `TRAN_PROP_SET_BYPASS_CHG_VOTE`
  - 必须确认 `running_algo == pe5` 时是否触发 `tchg_alg_stop_algo()` 退 PE50
- [ ] 差旅疾充：
  - 锚点：`chgspeed_ctl_store/show`、`TRAN_MULTI_SPEED_TRAVEL`、`speed_owner_old/chg_speed_old`
  - PE5 交互：`ALG_MULTI_CHG_SPEED`/`OWNER` 下发、`project_power` vs `adapter_capacity` 回退
  - 必须区分“命令被接受但回退”与“多档热限流参数已生效”
- [ ] 高温低 CV / 不报百（停充 + 上报）：
  - 专项 skill：`transsion-batt-high-temp-low-cv-eoc`
  - 锚点：`tc_high_temp_lock_uisoc_check`、`is_low_cv_status`（`vbat_cv` vs `smooth_soc_full_vol`）、`is_chg_done`、`CHG_BAT_HT_EOC_STATUS`、`high temp charger full, report uevent`、`VOTER_BATT_HIGH_TEMP_EOC`
  - 与纯 `batt_ht_notify_check` 高温 notify 区分：本路径强调 **低 CV + EOC 满 + UISOC 未达到 100** 的组合
```

## 关键边界

- 本 skill 默认认为“充电类型结果已经产出，或者至少前序 type detect 已有明确证据”。
- 若问题落在以下符号，优先转交 `transsion-bc12-type-detect`：
  - `tc_detect_bc12_work()`
  - `do_bc12_pre_work()`
  - `is_usb_rdy()`
  - `tc_detect_bc12_run()`
- 若问题落在以下符号，优先转交 `transsion-dcp-fastcharge-probe`：
  - `support_alg` / `pe5` / `pd` / `hvdcp20` / `tc30` / `pe20`
  - `tc_algo_protocol_process()` / `tchg_alg_is_algo_ready()` / `data->running_algo`
  - PE5 内层：`tfcp_adapter` / `pd_adapter` / `hvdcp30_adapter` / `support_ta`
  - `PE50_RFC` / `PE50_PPS` / `PE50_QC3`
  - `pe50_is_ta_rdy()`
- 若问题落在 `CC_ALERT` / `ps_change` / `TCP_NOTIFY_*`，优先转交 PD 或 TCPC adapter skill。
- 若客制化入口（增强/旁路/差旅）已命中，但问题表现为协议协商或调压细节异常，本 skill 给出主控层结论后转交对应协议 skill。

## JEITA CV/CC/EOC（`single_batt` / `dual_batt`）

**入口**：`tc_check_batt_jeita()` → `tc_chg_update_single_batt_jeita()` / `tc_chg_update_dual_batt_jeita()`（`tc_charger.c`）。  
**配置**：各机种 `tc_charger.dtsi` 中 `single_batt_*`、`master_batt_*`、`slave_batt_*` 等温度阶梯与 `vbat[]` / `ibat[]` / `eoc` 表。

### 强规则（解析与配置）

- **不允许**把 **CV / CC / EOC 为 0** 当作 JEITA 的**合法解析结果**：`tc_charger.dtsi` 中对应阶梯的 `vbat`、`ibat`、`eoc` 应配置为非 0；单电与双电路径（`tc_chg_update_single_batt_jeita`、`tc_chg_update_dual_batt_jeita`）同属此规则。
- **代码事实**：`data->vbat_cv` / `vbat_cc` / `vbat_eoc`（及 dual 下 master/slave 各组）**仅在**满足「CC 条件且 CV 将变」或「温度/FFC 阶梯切换」的 `if` 分支内**才会被赋值**；若本周期该分支**未进入**，成员可能仍为**结构体初值 0**，但末尾 `tchr_info("[SINGLE_BATT]" / "[DUAL_BATT]")` **仍会打印**。  
  - 日志出现 **`cv:0` / `cc:0` / `eoc:0`** 时，**不得**直接结论为「DTS 解析出 0」，应先区分 **本周期未更新（未写入）** 与 **表中真为 0（配置错误）**。

### 与 `Vbat=... cv:3900000` 的语义区分

- 主线程里 `tchr_err("Vbat=... cv:%d\n", ..., chg_cv)` 中的 **`chg_cv`** 来自 **`charger_dev_get_constant_voltage(chg1_dev, &chg_cv)`**，即 **charger IC 读回的当前 CV**（单位 **µV**，`3900000` = **3.9V**）。
- 若策略侧曾尝试低于 **IC 最小 CV**（例如 **mt6375** 常见 **最低约 3.9V**），下层会**钳位到硬件允许范围**，读回仍为 **3.9V**；这与同周期 JEITA 行若出现 **`cv:0`**（未更新或异常）**不是同一层含义**：前者是 **器件寄存器/驱动读回**，后者是 **主控 `tc_data` 中的 JEITA 目标（可能未刷新）**。

## 输出模板

```markdown
## 分域结论
- 主域：<transsion-charger-orchestrator>
- 次域：<transsion-dcp-fastcharge-probe / transsion-pe5-vi-tuning / none>

## 触发点
- 输入触发：<关键词/日志>
- 首个命中函数：<function>

## 充电路径
- 主调用链：<call chain>
- 投票与结果：<vote state and effect>

## 失败分层
- A 资格门控：<通过/失败 + 证据>
- B 执行路径：<通过/失败 + 证据>
- C 验收路径：<通过/失败 + 证据>

## 边界判断
- 是否在本 skill 范围：<yes/no + 原因>
- 是否需要转交：<目标 skill 或 none>

## 根因与下一步
- 最可能原因：<1-2 行>
- 下一步验证点：<文件/函数/日志>
```

## 约束

- 结论仅限于充电主控编排层，不跨域下结论
- 不把 `BC1.2 未完成` 与 `主控策略异常` 混为一谈
- 若前序 charger type 尚未确定，先转交 `transsion-bc12-type-detect`
- 若问题属于 PD 协商，转交 PD-TypeC skill
- 若问题属于 USB 角色或枚举，转交 extcon 或 mtu3 skill
- 若问题属于 DCP 后算法竞选、PE20/HVDCP/TC30/PE5 运行态切换，转交 `transsion-dcp-fastcharge-probe`
- 若问题属于 PE5 已选型后的热限流表/调压调流参数生效，转交 `transsion-pe5-vi-tuning`
- 若问题属于 **低 CV 满充判定、CHG_BAT_HT_EOC、高温停充 uevent、smooth_soc_full_vol**，转交 `transsion-batt-high-temp-low-cv-eoc`
- 若问题属于 **JEITA 表解析、日志中 cv/cc/eoc 为 0 与 charger 读回 cv 不一致**，在本 skill「JEITA CV/CC/EOC」小节分层说明；配置表错误优先核对 `tc_charger.dtsi` 非 0 与温度/FFC/cycle 档位匹配
- 仅在根因明确（或用户明确确认某根因）时输出“改进措施”
- 若根因不确定，仅输出“可能根因”与证据，不输出改进措施
- 若引用 RFC/PD/HVDCP/TC30/PE 等协议握手失败日志，必须先核对“对端是否支持该协议”；不能把失败日志直接等同为主控层异常
- 对端能力未知时，结论必须写明“能力未知，当前仅能判定协商未成功”
