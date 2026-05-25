---
name: bug-scenario-power-standby
description: "Android功耗-待机耗电: 待机/灭屏耗电根因深度分析 | wakelock/AudioMix/suspend/SPM/R12/r13/26M/AlarmManager/待机电流/mA/healthd/电量跳变 | 当用户报告待机耗电快、灭屏电流大、wakelock长持锁、AP无法suspend、频繁唤醒时使用。须在加载本skill后按SOP执行"
---

# 功耗待机问题分析（Power Standby / SOP2）

本 Skill 对应 `功耗待机问题分析SOP2Skill.md`，在 **`bug-analysis` 完成初步判断** 且现象归类为 **功耗待机 / 灭屏高耗电 / suspend-wake / 持锁** 时加载，用于 **第二阶段深挖**。分析原则来自 README：**工作区有 Jira 信息与完整日志**，按时间窗口与证据链做根因推断。

## 与 `bug-analysis` 的关系

- 遵守 **`bug-analysis`** 的硬规则：时间锚点、按序阅读、证据路径+行号/时间戳、结论置信度（**已证实 / 高度疑似 / 待验证**）、 gaps 写局限性。
- 报告仍写入工作区根目录的 **`bug_analysis_report.md`**（简体中文），并在 **`# 使用的 Skill`** 中列出 **`bug-analysis`** 与本 Skill 的 **`name`**：**`bug-scenario-power-standby`**。
- 本 Skill 补充 **功耗域专有步骤与判定阈值**；细节案例与 **R12 表** 见 **`references/`**（见下文「渐进披露」）。

## 反幻觉与数据边界（必须遵守）

以下规则优先级 **高于** 本 Skill 任意「示例/算术/常见」表述：

1. **单一事实来源**：凡 **mA、百分比、包名、UID、锁名、R12/r13 位含义、`timer_out` 换算结果、TOP 排行**，只能来自 **① 当前 defect 工作区内的日志/Jira**，或 **② `功耗待机问题分析SOP2Skill.md` 已写明的文字**，或 **③ 用户/仓库内显式给出的头文件、测试报表**。**不得**根据经验、模型记忆或本 bundle 的案例 **编造、补全、推断「必然如此」的数值**。
2. **示例≠本案**：`SKILL.md` 中的公式演算（如某容量 × 耗电 %）、`references/power-standby-cases.md` 中的 Steam/微博日志，**仅作格式与对照**；除非 **本案文件中存在相同证据行**，否则 **禁止** 把案例里的电流、包名、UID 写进本案结论。
3. **阈值与单位**：§「功耗与提单阈值」、健康标准等 **逐项可追溯至 SOP 或项目基线**；若项目与 SOP 冲突或未见书面定义，结论写 **`待验证`**，并列出需要确认的文档/版本，**禁止**私定阈值。
4. **R12 解码**：`references/r12-table.md` 的 legacy 表 **仅对应某一公开旧内核版本**；对本案 **`r12=`** 的命名解释，以 **当前设备内核源码/符号表** 为准；表中 **掩码算术** 只为说明「多 bit 可按位展开」，**不是** 实采日志。
5. **置信度**：无对应 log 行或无法交叉验证时，**不得**写「已证实」；用 **`高度疑似` + 证据链** 或 **`待验证` + 缺什么日志**。

## 渐进披露（`references/`）

| 文件 | 何时阅读 |
|------|----------|
| [`references/r12-table.md`](references/r12-table.md) | 需把 **`r12=0x…`** 与 **名称/位** 对照时（须核对本项目内核，表仅为参考） |
| [`references/power-standby-cases.md`](references/power-standby-cases.md) | 对照 **SOP 固定案例的原文摘录**（禁止当成本案数据） |
| [`references/grep-cheatsheet.md`](references/grep-cheatsheet.md) | 需要 **按缓冲区/关键字** 检索工作区文件时（命中行才是证据） |

主流程仍以本 `SKILL.md` 为准；**不要为了省 token 跳过主流程跳读案例**。

---

## 报告落点（与 `bug-analysis/reference.md` §2 对齐）

- **不要新增**顶层 `#` 标题破坏模板；功耗专项结论写入：
  - **`# 日志与 trace 关键发现`**：阈值、mA 换算、wake locks 统计、R12 TOP、`26M_off_pct`、CPU/rssi。
  - **`# 根因分析`**：**整体链路**（持锁/唤醒源 → 模块/应用 → 现象），每条附置信度。
  - **`# 解决方案与改动建议`**：应用/驱动/模组分工；需三方日志时写 **建议补采**。
- 证据表格式见 **`bug-analysis/reference.md` §3**；可在附录增加「功耗专用 grep 列表」路径索引。

## 速决分流（先归类再深挖）

| 优先信号 | 倾向路径 | 下一步 |
|----------|----------|--------|
| `Estimated power use` 中 **wakelock/audio/某 UID** 极长；或 partial wake **>0.5h** | **未睡 / 长持锁** | 步骤 2.1 → 包名/锁名 |
| 密集 **`suspend wake up by`**，R12 可分类 | **睡了但被叫醒** | 步骤 2.2 → R12 TOP + 是否数传 |
| **`26M_off_pct`≈0** 且 **LPM blocked by xxx** | **深度休眠时钟/子系统未闭** | 步骤 2.3 + connsys/modem/MD 统计行 |
| **R12_CONN2AP / R12_AP2AP_PEER** 为主 | **数据业务唤醒** | 步骤 3 + netlog |

---

## 适用芯片与问题范围

- **典型平台**：文档以 **MTK** SPM/R12 字段为例；若日志为其他平台，保留 **同类语义**（suspend 入口、唤醒原因、子系统 block、26M/时钟等），在报告中注明平台差异 **`待验证`**。
- **问题有效性**：先确认是 **设备侧问题**（非充电器、环境温湿度、测试方法错误等）；缺信息则列 **`待验证`** 与 **建议补采**。

---

## 所需日志与用途

| 日志 | 必需性 | 用途概要 |
|------|--------|----------|
| **APLog**（含 kernel/main 等） | 必需 | 唤醒源、持锁链路、`PM: suspend entry/exit`、`suspend wake up by`、**R12**、`26M_off_pct`、`Cpus Usage`、`healthd`、rssi 等 |
| **bugreport**（大包可先解压） | 必需 | `Estimated power use`、`All kernel wake locks`、`All partial wake locks`；过大时 **分段读取（如每段 ~200k）** 做统计 |
| **netlog / .cap** | 可选 | 数据业务路径、与 R12_CONN2AP / modem peer 唤醒联动时用 **Wireshark** 看数传应用 |

---

## 功耗与提单阈值（复杂待机）

以下阈值与分级 **转写自** `功耗待机问题分析SOP2Skill.md` §2.2；**仅当** Jira/测试记录/描述中 **已有** 可对标的待机电流（或可由 **工作区材料中的容量、耗电%、时长** 合法换算）时写入报告对照，**禁止虚构**「约 XX mA」而无算式与数据来源。

用于 **等级判定** 与 **是否 Critical / block**，结论写入 **`# 现象与影响范围`** / **`# 日志与 trace 关键发现`** 中与等级相关的表述。

- **复杂待机（实网一晚，WiFi+数据场景）**  
  - WiFi：**< 25 mA** 为达标级参考；**25–35 mA** 可考虑 **Critical**；**> 35 mA** 倾向 **提单 block（标 MP block）**。  
  - SIM：**≤ 30 mA** 为参考；**30–40 mA** 可考虑 **Critical**；**> 40 mA** 倾向 **提单 block**。  
- **待机电流估算**：使用 SOP 给定公式；**仅当** Jira/报表/描述中已提供 **电池容量、耗电百分比、待机时长** 时才能在报告中代入数字。**算术演示（非本案数据）**：SOP 原文已给出「5000mAh、12h、12%」等一笔，用于说明如何换算成 mA — **禁止**将演示数字当作当前 defect 的测量值，除非工作区中有同一组数据。

说明：具体项目以 **项目基线/书面规范** 为准；任何未在材料中出现的数字 **不得** 捏造。

---

## 应用健康行为（灭屏；摘要）

分析应用侧时对照（细节以项目白皮书为准）：

- **Partial wakelock**：灭屏累计持锁不宜过长（SOP 示例 **≤ 5 min** 量级，需结合项目定义）。
- **CPU**：灭屏 **10 min 内平均负载** 不宜持续超 **10%**（按进程统计）。
- **数据收发**：如网络流量、包频阈值（IM/其他类型包/小时）；异常则与 **数传工具 / netlog** 交叉验证。
- **Alarm / JobScheduler / GPS / BT 扫描 / WiFi Scan**：按 SOP 表中间隔与次数阈值做 **高度疑似** 或 **待验证** 标注。

---

## 关键检索线索（关键词）

在锚定时间窗内搜索（区分大小写视日志而定）：

- **电池 / 功耗**：`battery_level`、`Estimated power use`、`healthd`
- **休眠与锁**：`PM: suspend entry`、`suspend exit`、`Pending Wakeup Sources`、`aborting suspend`、`active wakeup source`
- **唤醒**：`suspend wake up by`（或平台变体 `[SPM] wake up by`）、**R12** 寄存器含义、`debug_flag`、`r13`
- **26M**：`26M_off_pct`、`blocked by`、`unexpected unclosed pll`、`suspend warning`（audio/耳机相关）
- **CPU / 网络**：`Cpus Usage` / `Usage`、`rssi`

更多按文件类型拆分的搜索词见 **[`references/grep-cheatsheet.md`](references/grep-cheatsheet.md)**。

**事件侧 `battery_level`（若有）**：若出现与 **`功耗待机问题分析SOP2Skill.md` §3.2** 类似的三元组示例，字段语义 **以本项目日志定义为准**；须在报告中标明依据（摘录原文或厂商说明），**禁止**在未读本案 event 的情况下照抄示例数值当证据。

---

## 大批量日志与 Token 策略

- bugreport/APLog **先定窗再搜**；`Estimated power use` / `wake locks` 段可 **分段读取**（如 ~200k chunk）只抽需要的节。  
- kernel 优先 **`suspend` / `SPM` / `Wake`** 关键字缩小范围，避免整文件粘贴。

---

## 分析主流程（必须按序；每步给出可落地结论）

总分类：**问题有效性** → **大类**（**AP 无法进入 suspend** vs **能休眠但被频繁唤醒**）→ **应用数传** vs **子系统模块**（Modem、sensor、WLAN、BT 等）。**禁止**模糊收尾，每段要有 **证据 + 结论**。

### 步骤 1 — 基础信息与等级

**1.1 功耗等级**

- 在 **events / main** 等中查 **`battery_level`**；在 **bugreport** 查 **`Estimated power use`**。  
- 若 SOP 所述 **「单段平均电流 > ~60 mA 则优先持锁路径」** 中的电流 **来自你的统计或报表**，再据此分流；**若无** 可用的电流统计，不得凭感觉套用 60 mA，应 **`待验证`** 并先补算或补日志。  
- 对 **`Estimated power use`**：关注 **Capacity**、**wakelock** 行时长、**分模块耗电排行**（cpu、mobile_radio、audio、UID 等）。

**1.2 电池曲线合理性**

- **kernel** 中搜 **`healthd`**：  
  - 相邻 **`battery l`** 若 **电量变化 > 1%** → **电量跳变可疑**。  
  - **`v`** 相邻两次变化超过 **SOP 阈值 0.2**（单位随日志缩放/项目口径而定；无法确认则标 **`待验证`**）→ **电压跳变可疑**。  
  - 与 **纯待机电流偏高** 区分：**跳变** 偏 fuel gauge/计量；**高电流** 偏负载与唤醒。

### 步骤 2 — 休眠与唤醒

**2.1 无法 suspend（持锁路径）**

- **kernel**：`PM: suspend entry` 是否频繁失败/缺失；`Pending Wakeup Sources`、`aborting suspend`、`active wakeup source` 看谁占用。  
- **bugreport**：  
  - **`All kernel wake locks`**：统计 **累计 > 0.5 h** 量级的锁（及次数）。  
  - **`All partial wake locks`**：同上。  
- 结论指向：**系统未睡** 时，归因为 **内核锁 / 应用锁** 的具体 **UID/包名/锁名**（证据引用）。

**2.2 suspend 后被唤醒（R12 / wakeup reasons）**

- **R12 名称与 bit 索引**：SOP 列出的若干源 + legacy **`wakesrc_str[32]`** 全表见 **[`references/r12-table.md`](references/r12-table.md)**；**多 bit 并存、`r12_ext`** 见同文件 **§5**。  
- 在 **kernel** 搜 **`suspend wake up by`**（或平台等价串）。  
- **suspend 时长解读（MTK 常见）**：`timer_out` 为 **32k** 计数时，**秒级时长 ≈ timer_out / 32768**；与行末 **`Suspended for X.XXX seconds`** 互参。  
- **AP suspend 常见 R12 语义（示例，MTK）**：  
  - **R12_EINT_EVENT_B**：外设/PMIC 等中断（可结合 `/proc/interrupts`、`alarm`、**AlarmManager** 行）。  
  - **R12_CONN2AP_SPM_WAKEUP_B**：connsys（WiFi 等）；结合 **应用联网**、必要时 **netlog**。  
  - **R12_SCP2SPM_WAKEUP_B**：SCP/sensor/VOW 等。  
  - **R12_CCIF0_EVENT_B**：modem CCCI。  
  - **R12_AP2AP_PEER_EVENT_B**（或旧名 **R12_CLDMA_EVENT_B**）：modem 数据；配合 **netlog**。  
- **`debug_flag`**：若末字节/约定位置 **不是 `ff`** 等「全闲」形态，提示 **唤醒前子系统仍活跃**；配合 **`System LPM is blocked by <子系统>`** 看 **conn/md/…**。  
- **`r13`**：保存各输入 SPM 的时钟请求类状态；**按位** 对照 **`${platform}_pcm_def.h`**（缺文件则 **`待验证`，禁止臆造位含义）。  
- **深度案例辅助量**：`md_slp_duration`、`mtk_wcn_consys_sleep_info_read_all_ctrl`（各子系统休眠计数）、`scp_sleep_cnt_*`，用于对比 **AP 睡但 modem/BT/SCP 谁未睡**。

**2.3 能 suspend 但 `26M_off_pct` 异常低或为 0**

- **`26M_off_pct` 越高** 通常越省电；**=0** 示 AP 休眠期间仍常开 26M。  
- 搜 **`blocked by`**（如 md、gce）、**`unexpected unclosed pll`**；**audio** 插数字耳机场景注意 **`suspend warning`** / **`pcm_flag`** 等。

### 步骤 3 — 应用数据传输

- 若唤醒源指向 **R12_CONN2AP_SPM_WAKEUP_B**、**R12_AP2AP_PEER_EVENT_B** 等 **数据路径**：  
  - 用 **netlog + Wireshark** 统计测试时段 **TOP 应用/进程**；  

### 步骤 4 — 子系统与应用 CPU / 网络

**4.1 CPU**

- **`Cpus Usage` / `Usage`**：灭屏后 **>10%** 占用的进程列为 **高度疑似** 耗电源（结合 UID/包名）。

**4.2 网络与射频**

- **`rssi`**：**-60 dBm 以上** 偏强；**-75 dBm 以下** 偏弱网（弱网可导致 modem 行为变化）；结论写清是否 **弱网相关**。

---

## 常见问题与日志指纹（写入报告用对照）

| 类型 | 指纹 |
|------|------|
| 应用长 Audio 持锁 | AudioMix 等超长 partial wake + `Estimated power use` audio/wakelock |
| 应用数传 / alarm 唤醒 | `R12_EINT` + alarmtimer/AlarmManager + 可选 `blocked by conn` |
| connsys / modem | `mtk_wmt_resume`、`mtk_wcn_consys_sleep_info_read_all`、`md_slp_duration`、`26M_off_pct=0` 等 |

**完整原始摘录、SOP 逐行解读与微博长 kernel 块**：见 **[`references/power-standby-cases.md`](references/power-standby-cases.md)**。

---

## 报告中必须写清的结论块（建议小节标题）

1. **问题等级与阈值对照**（mA / 百分比换算展示一行公式）。  
2. **大类判定**：未睡 vs 睡醒；**主要唤醒源 TOP** 或 **主要持锁 TOP**。  
3. **责任分层**：应用 / Framework / 驱动或模组 / 未知；与 **`bug-analysis` 分层规则** 一致。  
4. **证据索引**：每条主结论至少一处 `Evidence: path + Lxxx-Lyyy 或时间戳`。  
5. **局限与补采**：缺 netlog、缺完整 bugreport、缺复现时注释说明。

---

## 收束前自检清单（写 `# 根因分析` 前过一遍）

- [ ] **时间窗**已在 `# 现象与影响范围` 或 `# 日志与 trace 关键发现` 写明（含时区/容差）。  
- [ ] **平均电流**或 **官方测试报表** 与 **25/30/35/40 mA 线** 对照结论已写。  
- [ ] **`Estimated power use`** 与 **kernel 休眠唤醒** 无矛盾；长 **wakelock** 与 **partial/kernel lock** 有 **UID/锁名** 证据。  
- [ ] **多原因唤醒**：`r12` 多 bit 已展开（见 **`references/r12-table.md` §5**），未只解释单一位。  
- [ ] **`26M_off_pct` 低/0** 时是否已查 **blocked / pll / pcm_flag**。  
- [ ] **`# 使用的 Skill`** 含 **`bug-analysis`** 与 **`bug-scenario-power-standby`**。

---

## 反模式（避免）

- **编造数据**：报告出现 **本案 log/Jira 中不存在** 的包名、UID、mA、R12 解读、或「典型值」占位。**无则缺省，勿用模板案例填空。**  
- 无时间窗、全树 grep 后猜根因。  
- 仅看 bugreport 不看 kernel 的 suspend/wake **时序**。  
- 把 **现象** 当 **根因**（如只说“耗电高”）。  
- 忽略 **`26M_off_pct` / block** 与 modem/connsys **子系统统计** 的交叉验证。  
- 把 **`references/r12-table.md`** 的 legacy 名 **强行** 安到 **未核对** 的内核版本上。

---

## 仅内部引用

- 飞书 **sheet/白板** 若不可访问：以本 Skill + **`references/r12-table.md`**、**`references/power-standby-cases.md`**、**`references/grep-cheatsheet.md`** 为执行基线。  
- 恢复外链后可在 **`# 附录`** 补充正式文档链接。
