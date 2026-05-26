---
name: transsion-pe5-vi-tuning
description: "Transsion-PE5调压调流: PE5协议选型完成后的通用V/I调节骨架，从tc_pe50.dtsi读取参数、TA认证、软启动 | pe5/VTA/ITA/tc_pe50.dtsi/RFC/PPS/QC3 | 当用户报告PE5快充无法进入、V/I调节异常、DTS参数问题时使用。快充选型走transsion-dcp-fastcharge-probe"
funcType: "AI故障分析"
category: "驱动"
---

# PE5 通用：DTS 参数与调压调流骨架

## 适用范围

- 聚焦 **`drivers/power/supply/transsion/tc_pe5.c`** 及 **`tc_pe5_*_intf.c`**（`rfc` / `pps` / `qc3`）在 **TA 已认证、`algo_num` 已选定** 之后的 **电压/电流初值与闭环调节**。
- **不包含**：`tc_chg_type_det` BC1.2、`pd_adapter` ready 判定、TCPM/PDO 协商细节（见 `transsion-dcp-fastcharge-probe` 与 PD-TypeC skill）。

## DTS 在哪里（按项目变化，必须先定位）

- **典型路径**（仅作模式参考，**每个机种不同**）：
  - `arch/arm64/boot/dts/mediatek/charge/<机种目录>/tc_pe50.dtsi`
  - 由板级 `*.dts` / `*.dtsi` **`#include`** 进来，节点通过 **`&pe5 { ... }`** 或等价 overlay 展开到 **`compatible = "tc_pe5"`** 的 platform 设备。
- **本仓库案例（仅供参考）**：  
  `kernel/kernel_device_modules-6.12/arch/arm64/boot/dts/mediatek/charge/lk6_h582/tc_pe50.dtsi`  
  分析其它项目时 **禁止默认套用该文件数值**，必须以 **当前机种的 `tc_pe50.dtsi`（或最终合并进内核的 pe5 节点）** 为准。

### 若当前环境拿不到 DTS

以下任一情况应 **停止猜参数**，请使用者提供：

- 工作区无对应机种目录、或 `tc_pe50.dtsi` / `tc_charger.dtsi` 未包含 `pe5` 节点；
- 无法确认 **`support_ta` / `support_spec` / `vta_cap_*` / `step_ffc_level_*`** 等关键数组与项目一致性。

**请使用者提供**：目标机种 **`tc_pe50.dtsi` 全文**，或 **`pe5 { ... }` 节点**（含 `support_spec`、`pe50_vta_init`、`pe50_ita_init`、热限流表、`step_ffc_level*` 等）。

## 参数如何进内核（代码入口）

- **解析函数**：`tc_pe5.c` 的 **`pe50_parse_dt()`**（约 `tc_pe5.c:4005` 起）。
- **机制**：
  - 布尔 / 单值 u32 / s32：通过 **`pe50_dtprops_bool` / `pe50_dtprops_u32` / `pe50_dtprops_s32`** 表批量 `of_property_read_*` 到 **`struct pe50_algo_desc`**（见 `tc_pe5.c` 约 `3684~3735` 行附近表项）。
  - 数组： **`pe50_dtprops_u32_array` / `pe50_dtprops_s32_array`**（如 `support_spec`、`vta_cap_min/max`、`ita_cap_min`、`tta_level_def`+`tta_curlmt` 等）。
  - **FFC 分档**：`step_ffc_level`、`step_ffc_level_<n>` 等由 **`pe50_parse_dt()` 内专用逻辑** 读入（含 `batt_id` 索引的 `step_ffc_level` 选择，见约 `3913` 行附近）。
  - **双电 FFC**：`pe50_parse_dual_batt_ffc_dt()` 读取 `step_master_ffc_level_*` / `step_slave_ffc_level_*`（若使能双电）。
- **默认值**：`struct pe50_algo_desc` 的 **`default_info`**（`tc_pe5.c` 顶部）在 DTS **未写某属性** 时保留默认；但 **`pe50_vta_init` / `pe50_ita_init`** 等在 `tc_pe5.h` 有 **`PE50_VTA_INIT` / `PE50_ITA_INIT`** 默认（例如 5300mV / 3000mA），DTS 可覆盖。

## 初始 VTA / ITA 如何确定（三路径共性）

在各自 **`pe50_init_*_algo_data()`**（如 `tc_pe5_rfc_intf.c`、`tc_pe5_pps_intf.c`、`tc_pe5_qc3_intf.c`）中，**初值由「DTS 期望」与「TA 认证能力」共同钳位**：

- **`pe50_vta_init = max(desc->pe50_vta_init, auth_data->vta_min)`**
- **`pe50_ita_init = min(desc->pe50_ita_init, auth_data->ita_max)`**
- 随后 **`vta_setting` / `ita_setting`** 一般从上述初值起步（再进入使能 TA 输出等流程）。

**含义**：DTS 的 `pe50_vta_init` / `pe50_ita_init` 是**意图起点**；**`auth_data`（来自 `authenticate_ta` / TA 能力）给出允许区间**，二者取 **交** 后才落地。

**案例文件中的示例字段**（lk6_h582，**勿外推到其它项目**）：

```text
pe50_vta_init = <5300>;
pe50_ita_init = <3000>;
```

## DTS 中与「调压调流」强相关的参数分组（阅读顺序建议）

以下分组对应 **`lk6_h582/tc_pe50.dtsi`** 中的结构，用于建立心智模型；**具体数组长度与取值以目标项目为准**。

1. **入口与周期**
   - `polling_interval`、`chg_time_max`、`ta_blanking` 等：主循环/超时/TA 指令间隔相关。

2. **TA 能力窗口（与认证 spec 绑定）**
   - `support_spec`、**`vta_cap_min` / `vta_cap_max` / `ita_cap_min` / `vbus_max_ovp`**：多档 spec（如 6:2、4:1 等）下的电压/电流能力与 OVP 上限，与 **`running_spec`**、**`conversion_ratio`**（在 `pe50_init_*_algo_data` 里按 spec 设置）联动。

3. **初始与软启动（DVCHG/IBUS 侧）**
   - **`idvchg_ss_init`、`idvchg_ss_step`、`idvchg_ss_step1`、`idvchg_ss_step2`、`idvchg_ss_step1_vbat`、`idvchg_ss_step2_vbat`**：分段步进；**`idvchg_term` / `idvchg_pps_term`**：截止条件（示例里注释有 ibus 比例说明，以项目 DTS 为准）。
   - **`ita_level` + `rcable_level`**：线阻/电流档位，与 **`pe50_init_vol_diff`**（`vol_diff_level` / `cable_capability_level`）等一起影响允许压差与功率判断。

4. **热与系统功率限流**
   - `tta_*`、`tbat_*`、`tpcb_*`、`tpa_*`、`tdvchg_*`、`sys_power_*`：温度/功率档位与 **curlmt** 表，运行中根据采样温度 **选档限流**（`supprot_multi_level_charging` 时还有 **按 chg_speed 选 `t*_level_def_*` 多套表**）。

5. **电池侧 CV / FFC 分段**
   - `vbat_cv`、`step_ffc_level`、`step_ffc_level_*`、`pe5_ffc_gap`：随 **温度带、cycle 区间** 选择 **FFC 曲线** 与 **DVCHG 终止电流** 等；进入 **CC/CV** 后电压电流目标随 **vbat 分段** 更新（见 `tc_pe5.c` 中 **`pe50_select_*ffc` / step 索引** 一类逻辑）。

6. **工程与保护**
   - `project_power`、`project_pwr_ratio`、`min_ita_gap`、`ita_stable_cnt`、`vol_diff_gap`、`ifod_threshold`、`rsw_min`、`ircmp_rbat`、`ircmp_vclamp` 等：稳定性判定、线补、异常保护阈值。

## 后续「调节」逻辑（代码层面应看哪里）

- **状态机主链**：`tc_pe5.c` 中 **`PE50_ALGO_*`** 状态（如软启动 DVCHG、CC/CV、TA 能力跟踪），以及 **`pe50_rfc_algo_*` / `pe50_pps_algo_*` / `pe50_qc3_algo_*`** 内对 **`vta_setting` / `ita_setting` / `idvchg_cc`** 的更新。
- **向 TA 下发能力**：**`pe50_hal_set_ta_cap` / `pe50_enable_ta_charging`**（各 intf 在启动与调节阶段调用）。
- **IBUS/ITA 稳定与升压**：与 **`min_ita_gap`、`ita_stable_cnt`、`ta_cv_ss_repeat_tmin`** 及 **`pe50_check_ta_cap`** 一类函数相关（具体以当前分支 `tc_pe5.c` 为准）。

### RFC：在 I2C 调压调流之前的 `i2c_trans`（占位，与器件强相关）

RFC/TFCP 侧对 TA 的 **I2C 读写**（最终会走到 **`tc_tfcp_ta.c`** 里对 **`TFCP_REG_SETVC`** 等的写入，即「调压调流」）并不是裸发 I2C：在 **`tfcp_ta_read_device` / `tfcp_ta_write_device`** 中，每次与 TA 通信前后会调用 **`charger_dev_i2c_trans(get_charger_by_name("primary_dvchg"), true/false)`**，用于在 **DVCHG/充电 IC** 与 **TFCP TA** 之间做总线或通道上的协调（具体是 **I2C mux 切换、电平、互斥时序** 等，**因平台与芯片而异**）。

- **代码锚点（本仓库）**：`kernel/kernel_device_modules-6.12/drivers/power/supply/transsion/tc_tfcp_ta.c`（`charger_dev_i2c_trans` 包裹 `i2c_master_send` / `i2c_master_recv`）。
- **本 skill 状态**：此处 **仅作记录**；**`i2c_trans` 的电气含义、何时必须 true、与 PE5 状态机的先后关系** 需结合 **具体 charger/DVCHG 数据手册与原理图** 单独补齐，**勿默认与其它项目一致**。

## 与「RFC / PPS / QC3 差异」的边界

- **共性**：上述 **DTS 骨架 + `auth_data` 钳位初值 + 热/FFC/线阻限流** 为三路共享。
- **差异**：下一层应分别打开 **`tc_pe5_rfc_intf.c` / `tc_pe5_pps_intf.c` / `tc_pe5_qc3_intf.c`**，对照 **TA 交互原语**（如 RFC 与 PPS APDO 请求、QC3 pulse）与 **不同的终止/重试策略**。
- **RFC 特有条目**：除上述共性外，RFC 在到达 **TCPM/PD** 之前走 **TFCP I2C**；**`i2c_trans`** 属于 **板级 I2C 仲裁/切换**，见上一小节占位说明。

## 输出模板（排查 PE5 调压异常时）

```markdown
## DTS 来源
- 机种：<name>
- 文件：<path/to/tc_pe50.dtsi 或合并后的 pe5 节点来源>
- 若缺失：已向使用者索取 / 待补充

## 初值
- desc->pe50_vta_init / pe50_ita_init（DTS）：
- auth_data->vta_min / ita_max（认证后）：
- 落地 pe50_vta_init / pe50_ita_init（clamp 后）：

## 当前 spec
- running_spec / support_spec 向量：
- conversion_ratio：

## 调节阶段
- 状态：PE50_ALGO_*
- 最近更新的 vta_setting / ita_setting / idvchg_cc：
- 触发的限流：温度档 / sys_power / cable / FFC 分段
```

## 转交条件

- 若问题仍在 **TA 认证前**（`authenticate_ta`、adapter 顺序、`pd_adapter` ready）：`transsion-dcp-fastcharge-probe`
- 若问题在 **MTK TCPM/PDO**：`mediatek-pd-typec-protocol-6-12`
- 若问题在 **tc_charger 主线程/vote**：`transsion-charger-orchestrator`

## 约束

- **不得**在未见到目标机种 `pe50` 节点时，用其它机种 DTS **数值** 下结论。
- 所有电压电流单位以 **代码与 DTS 注释** 为准（常见为 **mV / mA**，部分寄存器或接口可能为 µA，需跟 `pe50_hal` 换算）。
- 若分析中引用 RFC/PPS/QC3/PD 等握手失败日志，必须先核对充电器是否声明支持该协议；握手失败本身不能单独推导为通路异常
- 若对端能力未知，必须显式标注“能力未知，当前仅能判定协商未成功”
