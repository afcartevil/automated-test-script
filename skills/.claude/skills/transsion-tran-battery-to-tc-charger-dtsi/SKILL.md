---
name: transsion-tran-battery-to-tc-charger-dtsi
description: >-
  将 kernel-5.10 设备树中 tran_battery（compatible = "tran,chg_fun"）的 PCB/JEITA 参数，
  转换为 kernel_device_modules-6.12 中 &charger（tc,charger）的 min_charger_current、tpcb_*、
  single_batt_level_* 等可合入片段。含老侧 tran_charger.c 公式、单位、与 6.12 模型差异及
  tpcb 阶梯拟合步骤。老侧 `tran_battery_aging`（`tran,chg_aging`）新树不承接、识别到即忽略。
  默认由 mtk-adapt-upgrade-branch-orchestrator（或其它迁移编排类 skill）
  在阶段 3/3B 中 Read 后执行；用户也可单独 @ 本 skill 做即席转换。不依赖先读
  transsion-charger-dtsi-driver-bridge。
disable-model-invocation: true
---

# tran_battery → `&charger`（6.12）独立转换 skill

## 调用规则（必读）

本 skill 已设 **`disable-model-invocation: true`**：模型**不会**仅凭对话上下文自动加载本文件。必须由 **父任务** 显式要求助手 **`Read` 本 `SKILL.md` 全文** 后再按下文规则产出。

### 谁必须 Read、何时 Read

| 调用方 | 何时必须 Read 本 skill |
|--------|-------------------------|
| **`mtk-adapt-upgrade-branch-orchestrator`** | 编排 **分支迁移/升级适配** 且信源或批次涉及 **`tran_battery`（`compatible = "tran,chg_fun"`）**、或同文件 **`jeita_*_chg_cur` / `pcb_*`** 等需并入 **6.12 `&charger`** 时；在写 **`tc_charger.dtsi` 的 `&charger` 合并片段** 或 **阶段 3B「tran_battery / JEITA·PCB」批** 之前 **必须 Read**。不得依赖用户再单独 @ 本 skill。 |
| **`mtk-adapt-upgrade-inventory-checklist`** | 若清单模板将 **`tran_battery`→`&charger`** 列为交付物或检查项，在让执行者「出转换片段」时 **应写明：按 `transsion-tran-battery-to-tc-charger-dtsi` Read 并执行**（与编排器衔接）。 |
| **`mtk-adapt-template-router`** | 当路由结论为 **「5.10 `tran_battery` 策略迁到 6.12 `tc_charger`」** 且非仅器件脚位时，handoff 中 **应指向 Read 本 skill**（可与 `mtk-adapt-template-basic-charging-capability` 并列）。 |
| **用户 / 其它 skill** | 即席「只转这一块 DTS」、无编排器时，由用户 **@ 本 skill 名** 或说明「按 tran_battery 转换 skill」，助手同样 **Read** 后执行。 |

### 与 `transsion-charger-dtsi-driver-bridge` 的分工

- **本 skill**：**可执行** 的字段映射 + **PCB 斜率→`tpcb_ichg` 阶梯**拟合步骤 + **`single_batt_level_*` 19 元布局**；产出 **可直接合入的 `&charger` 片段**。
- **bridge**：更广的 **DTSI↔驱动语义**、OTG、aging、长对照表；**不替代**编排器在 tran_battery 场景下对本 skill 的 **强制 Read**。

### 迁移方向说明

- 本文件正文默认 **老分支（5.10）`tran_battery` → 新分支（6.12）`&charger`**（正变换）。
- 若编排器处理的是 **新→老** 反向落盘：仍应 **Read** 本 skill 以统一语义与单位，再 **逆变换** 写回 `tran_battery`（逆变换步骤可由编排器「阶段 3B」补一句：以本 skill 表格反向查）。

---

## 目标

用户给出 **老 DTS 中 `tran_battery` 一段属性**（及可选：同文件 `&charger` 里 SW JEITA 温度阈值、`jeita_temp_*_cv`、`non_ffc_eoc` 等），本 skill 要求助手 **直接产出**：

**说明**：若老 **`mediatek,charger` 的 `&charger`** 上另有 **`temp_t4_thres`…`、ffc_*、`dv2_ffc_gera_*`** 等需并入 **`single_batt_level*`** 的字段，**DROP/忽略/摘 `pid_chg`** 等 **闸门** 以 **`transsion-charger-dtsi-driver-bridge`** **「老 `&charger`（mediatek,charger）」** 为准；本 skill 负责 **可执行的 `single_batt` 布局与 tran_battery 数值迁移**，**不**重复列 DROP 表。

1. **文字转换表**（旧属性名 → 新属性名 / 是否拟合 / `[REVIEW]` 点）；
2. **`/plugin/` 下 `&charger { ... }` 片段**（带 `/* SOURCE: OLD tran_battery ... */`、`/* CONVERT: ... */` 注释），便于合入 `charge/<project>/tc_charger.dtsi`。

**不要求**助手在本任务中再打开或引用 **`transsion-charger-dtsi-driver-bridge`**；本文件已包含迁移所需规则与边界。

---

## 老侧证据链（固定路径）

- **解析与限流**：`kernel-5.10/drivers/power/supply/tran_chg/tran_charger.c`
  - PCB：`change_current_by_pcb_temp()` → `g_max_temp_delta`；`change_current_by_temp()` → `ichg = g_ibat_temp_cur - g_max_temp_delta`。
  - JEITA 充电流：`select_jeita_charging_current()` 把 `jeita_*_chg_cur` 写入 `pdata->charging_current_limit`。
- **DTS 默认值宏**：同目录 `tran_charger.h`（如 `TRAN_PCB_DROP_*`、`JEITA_*` 默认）。
- **重要**：老侧 **`pcb_cur_step_*` 路径没有按 charge pump 数量 ×2**；双路 DCS 仅把已算好的总电流按比例拆到两路，不翻倍 `pcb_cur`。

---

## 新侧落点（固定路径）

- **`tc_charger.c`**：`tc_parse_single_batt_jeita()` 读 `single_batt_level`、`single_batt_level_*`；`tc_check_tpcb_level()` 用 `tpcb_temp[]` / `tpcb_temp_gap` 得到 `tpcb_level`。
- **`tc_basic_charger.c`**：`charging_current = min(..., max_charging_current_limit - tpcb_ichg[tpcb_level], ...)`（µA；**阶梯减额**，作用在 **`max_charging_current_limit`** 上）。
- **`single_batt`**：`tc_chg_update_single_batt_jeita()` 用选中行的 `ibat[]` 更新 `vbat_cc`（与 `tpcb_ichg` 等 **叠加 min**）。

**勿混淆**：`mtk_pe5.c` 里双充时对 **ITA** 使用的 **`2 * tpcb_curlmt[]`** 属于 **PE5 协议栈**，与 **`tran_battery` 的 `pcb_cur_step_*`** 不是同一套配置、单位也不同；本 skill **不**用 PE5 表去反推 `tran_battery` 的 `pcb_cur`。

---

## 属性级转换规则

### 0) `tran_battery_aging`（`compatible = "tran,chg_aging"`）— 新分支不承接

老分支若存在如下形态节点（含 `battery_aging_module0..3` 等），**新分支（如 6.12 KDM）不要**、也**不写等价 DTS 节点**：

```dts
tran_battery_aging: tran_battery_aging {
	compatible = "tran,chg_aging";
	status = "okay";
	battery_aging_module0 = <0>;
	/* ... module1..3 ... */
};
```

**执行规则（与 `mtk-adapt-upgrade-branch-orchestrator` / inventory 对齐）**

- **`mtk-adapt-upgrade-branch-orchestrator`**、**`mtk-adapt-upgrade-inventory-checklist`**：在老 DTS 中 **识别到** 该节点即可，**直接忽略**——**不**生成 `&charger` / 其它迁移片段，**不**把 `battery_aging_module*` 映射到新树属性，**不**纳入 3B「待确认字段」列表；适配简报中可 **一行注明**「老侧 `tran,chg_aging` 已按项目策略跳过」。
- **`transsion-tran-battery-to-tc-charger-dtsi`** 全文产出范围 **不包含** 本节点；若用户只贴 aging 块而无 `tran_battery`，**不**套用本 skill 的 JEITA/PCB 表。
- 驱动层背景（旧 `tran_battery_aging.c`、新侧 gauge / `tc_charger` aging 等）若需长文对照，仍见 **`transsion-charger-dtsi-driver-bridge`** 表中 **`tran_battery_aging`** 行。

### 1) 节点级

| 老侧 | 新侧 |
|------|------|
| 整节点 `tran_battery` / `compatible = "tran,chg_fun"` | **删除**；策略写入 **`&charger`（`tc,charger`）** |

### 2) `pcb_min_chg_cur`

| 老属性 | 新属性 | 数值 |
|--------|--------|------|
| `pcb_min_chg_cur` | `min_charger_current` | **µA 原样拷贝** |

### 3) `enable_pcb_tml` + `pcb_temp_step_*` + `pcb_cur_step_*` → `tpcb_temp` / `tpcb_ichg` / `tpcb_temp_gap`

#### 老模型（必须按公式理解）

- `pcb_temp_step_one`、`pcb_temp_step_two` 与 `thermal_get_ap_ntc_temp()` **同单位**，头文件默认量级为 **毫摄氏度（m°C）**（例：`43000` = 43℃）。
- **`pcb_cur_step_one` / `pcb_cur_step_two` 不是「固定减 µA」**，而是 **斜率**（µA 温升量纲 = **µA / m°C**）：

在 `PCB_temperature > pcb_temp_step_one` 时：

- 若 `pcb_temp_step_one < PCB ≤ pcb_temp_step_two`：

  `delta_uA = (PCB_temperature - pcb_temp_step_one) * pcb_cur_step_one`

- 若 `PCB > pcb_temp_step_two`：

  `delta_uA = (pcb_temp_step_two - pcb_temp_step_one) * pcb_cur_step_one + (PCB_temperature - pcb_temp_step_two) * pcb_cur_step_two`

随后 `ichg = g_ibat_temp_cur - clamp累积后的 g_max_temp_delta`（细节以老 `change_current_by_temp` 为准）。

#### 新模型

- `tpcb_temp[]`：**℃**（整数，可为负）。
- `tpcb_ichg[]`：与 `tpcb_temp` **等长**；在 `tc_basic_charger` 里为 **`max_charging_current_limit - tpcb_ichg[level]`** 的 **阶梯减额（µA）**。
- 新树 **无** `enable_pcb_tml`：若老侧为 **false**，则不在本迁移中写 PCB 降额（或全 0）；若为 **true**，必须写 **非全 0** 的 `tpcb_ichg`（或与产品原有曲线合并）。

#### 拟合到 `tpcb_ichg[]`（助手必做的一步）

1. **取得目标档位表**：优先使用 **目标项目现网 `tc_charger.dtsi` 里已有** `tpcb_temp` / `tpcb_ichg` 长度与温度结点（常见 **12 档**）；**不要**无故改列长，除非用户要求整表替换。
2. 将老 `pcb_temp_step_*` 换为 **℃**：`T1_C = pcb_temp_step_one / 1000`，`T2_C = pcb_temp_step_two / 1000`（若项目证明老树用 0.1℃ 等标尺，以实机/注释为准并标 `[REVIEW]`）。
3. 对每个新档位温度 `Ti`（取该档代表温度，例如 **≥ 上一档且 ≤ 本档上沿** 或取 **档内中点**），用上面 **老公式** 算 `delta_uA(Ti)`（仅当 `Ti` 换算回 m°C 后 > `pcb_temp_step_one` 才非 0）。
4. 令 **`tpcb_ichg[i]` ≈ `delta_uA(Ti)`**（或 **≥** 该值以保证新侧不比老侧更松），并满足单调/产品习惯；与现网 `tpcb_ichg` **逐档 merge** 时取 **更保守（更小充电电流）** 的一侧，除非用户明确以老 tran_battery 为准覆盖。
5. 在注释中标 **`[REVIEW]`**：老模型是 **连续斜率**，新模型是 **阶梯**；且老侧扣在 **`g_ibat_temp_cur`**、新侧扣在 **`max_charging_current_limit`**，极端协议/温区下 **允许 ichg 不完全一致**。

### 4) `jeita_*_chg_cur` → `single_batt_level` + `single_batt_level_*`

#### 行数

- 老 DTS 常见 **6 路**（`below_neg10`、`below_t0`、`t0_to_t1`、无 `t1_to_t2` 时与 `t0_to_t1` **合并**、`t2_to_t3`、`t3_to_t4`、`above_t4`）→ **`single_batt_level = <6>`** 与 `single_batt_level_0..5`。
- 若老侧有 **独立 `jeita_t1_to_t2_chg_cur`** 或项目现网为 **7 段**，则 **`single_batt_level = <7>`**，不得硬压成 6；与用户现网 **diff 合并**。

#### 温度边界来源

- **默认**：从 **同文件老 `&charger`** 读取 `temp_neg_t1`、`temp_t0`、`temp_t1`、`temp_t2`、`temp_t3`、`temp_t4`、`min_charge_temp` 等，构造与 **`tc_chg_update_single_batt_jeita`** 一致的区间：**`tbat > temp_lo && tbat <= temp_hi`**。
- **含边界 -10℃**：左端常用 **`temp_lo = -11`**（因严格大于 `temp_lo`）。
- 若用户未贴 `&charger`，则 **列出假设边界** 并标 **`[REVIEW]`**。

#### `single_batt_level_N` 数组布局（`struct batt_desc` 按顺序展开）

下列 **19 个 s32** 与 `tc_charger.c` 中 `__of_property_read_s32_array(np, "single_batt_level_i", (u32 *)&desc->single_batt[i], length)` 一致：

| 顺序 | 字段 | 含义 |
|------|------|------|
| 1–2 | `temp[0]`, `temp[1]` | 温区 **(lo, hi]**：`tbat > lo && tbat <= hi`（℃） |
| 3 | `ffc_status` | 无 FFC 区分：**`-1`** |
| 4–9 | `vbat[0..5]` | µV；通常从同文件 **`jeita_temp_*_cv` / `battery_cv`** 抄 **6 段 CV**；缺省用现网 `single_batt` |
| 10–15 | `ibat[0..5]` | µA；**该温区下各 CV 段的充电电流**：无分段时 **6 个相同**，值为对应 **`jeita_*_chg_cur`** |
| 16 | `eoc` | µA；常从 **`non_ffc_eoc`** 或现网抄 |
| 17–18 | `cycle_cnt[0]`, `cycle_cnt[1]` | 无循环限制：**`0`, `-1`** |
| 19 | `rechg_gap` | µV；无则 **`0`** 或现网 |

**老 `jeita_*_chg_cur` 无 ×2**：按 **µA 原样**写入 `ibat` 列（与 `tran_charger.c` 一致）。

### 5) `jeita_*_input_cur`

| 老属性 | 新侧 |
|--------|------|
| `jeita_*_input_cur` | **通常不写**同名温区表；在输出里用 **注释** 提示与 `dcp_input_current`、`max_input_current_limit`、PD 栈核对 |

### 6) `bootmode = <&chosen>`（仅挂在 `tran_battery`）

- 删除空壳节点后：**由 `tc_misc`（或产品已有节点）承接 `bootmode = <&chosen>`**；**勿重复**。

---

## 输出模板（助手应直接粘贴给用户）

```dts
/dts-v1/;
/plugin/

/* TRAN_BATTERY→&charger: SOURCE=kernel-5.10 tran_battery + 同文件&charger阈值；见 skill transsion-tran-battery-to-tc-charger-dtsi */

&charger {
	/* SOURCE: OLD tran_battery pcb_min_chg_cur */
	min_charger_current = <...>;

	/* SOURCE: OLD tran_battery PCB 斜率 → 拟合到现网 tpcb_temp 各档；[REVIEW] 连续模型 vs 阶梯 */
	tpcb_temp = <...>;   /* 尽量与目标项目原表等长 */
	tpcb_ichg = <...>;
	tpcb_temp_gap = <...>;

	single_batt_level = <...>;

	single_batt_level_0 = <...>; /* 19 个整数，见上表 */
	/* ... single_batt_level_1 .. */
};
```

---

## 自检清单（助手输出前核对）

- [ ] `single_batt_level_*` 每行 **19 个** cell，`ffc_status = -1`，`cycle_cnt = 0, -1` 除非用户另有表。
- [ ] 温区与 **`tbat > lo && tbat <= hi`** 一致；跨 0℃、-10℃ 边界已核对。
- [ ] `tpcb_ichg` 与 `tpcb_temp` **长度一致**；PCB 拟合已说明代表温度点。
- [ ] 已提醒：**`tbat_ichg` / 其它减额** 可能与 `single_batt` **叠扣**，合入现网时避免重复限同一温区。
- [ ] 已区分 **tran_battery PCB** 与 **PE5 `tpcb_curlmt`**，未混用单位。
- [ ] 若输入中含 **`tran_battery_aging`（`tran,chg_aging`）**，已按 **§0** 声明忽略、未生成该节点字段映射。

---

## 与 bridge skill 的关系（可选）

需要 **驱动长文对照、tran_otg**、或 **`tran_battery_aging` 背景说明** 时，仍可读 **`transsion-charger-dtsi-driver-bridge`**。  
**仅做「tran_battery → &charger」数值与片段生成** 时，**以本 skill 为充分条件**；**`tran_battery_aging` 见 §0，不在此产出。**
