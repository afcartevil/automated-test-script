---
name: spd-memory-feature-check
description: SPD「内存」维度功能检查：接受已连接 adb 设备，自动执行融合/压缩版本识别、内存压缩2.0、Quantus、kswapd、shrink_slab、look around、水位/lmkd、内存分配等脚本，输出 PASS/FAIL/BLOCKED 与巡检报告。用户提到 SPD 内存、内存压缩2.0、memcgcprsv2、Quantus 或表格 T8AOsejtthiNfHtQjaBcmNj9n9b 时使用。
---

# SPD-内存 Feature 功能检查

**输入**：已通过 USB 调试连接的一台测试机（`adb devices` 可见）  
**输出**：SPD 内存维度巡检报告（每项 PASS/FAIL/BLOCKED + 关键证据）  
**闭环**：本 Skill 内部通过脚本完成检查；内存压缩按「单版本原则」只执行本机应检路径。

编写规范：[Skills 编写标准](https://transsioner.feishu.cn/wiki/AT0wwM6bKi94JNkpK3cc7EkdnmK)

## 路径约定

- 工作目录：仓库根
- Windows cmd：`set PYTHONIOENCODING=utf-8 &&`
- 退出码：**0=PASS，1=FAIL，2=BLOCKED**
- TOS 版本检测共用：`.cursor/skills/spd-shared/scripts/tos_detect.py`

---

### 步骤1：确认 adb 与设备环境

```bash
adb devices
adb shell uname -r
adb shell sh -c 'getprop | grep version'
```

---

### 步骤2：版本识别（推荐优先）

```bash
PYTHONIOENCODING=utf-8 python .cursor/skills/spd-memory-feature-check/scripts/detect_memfusion_compress_version.py --json
```

返回：`memfusion_version`、`memcompress_version` 及 reason，写入报告「环境」段。

---

### 步骤3：内存压缩单路径检查

```bash
PYTHONIOENCODING=utf-8 python .cursor/skills/spd-memory-feature-check/scripts/check_mem_compress_status.py
```

按本机应检版本**只执行一种**压缩实现路径，报告正文仅写「内存压缩」单项结论。

---

### 步骤4：一键执行全量内存检查（可选）

```bash
PYTHONIOENCODING=utf-8 python .cursor/skills/spd-memory-feature-check/scripts/run_all_spd_memory_checks.py
```

汇总各项 PASS/FAIL/BLOCKED；**内存压缩以步骤3为准**，避免与步骤4重复堆砌。

**SKILL_FAILED 判定：**
- 仅脚本输出 `SKILL_FAILED:` 时触发
- 单项 FAIL/BLOCKED **不得**触发 SKILL_FAILED，须完成巡检报告

---

### 步骤5：AI 汇总巡检报告

对照下方飞书表格与脚本说明填写；表格与脚本冲突时**以表格为准**。

---

## 权威来源（必读）

每个内存 feature 的**检查方式、检查步骤、命令与判定**以以下飞书表格为准，分析或执行检查时必须先对照表格对应行的「参考文档 / 检查方法」列（以及表格中后续列），勿凭通用知识替代表格约定。

- [SPD - 内存（memory）表格](https://transsioner.feishu.cn/sheets/T8AOsejtthiNfHtQjaBcmNj9n9b)

若表格与口头描述不一致，**以表格为准**。

## 内存 feature 项范围（用户给定清单）

内存 feature 项主要包含在 [上述表格](https://transsioner.feishu.cn/sheets/T8AOsejtthiNfHtQjaBcmNj9n9b) 文档中：**内存融合2.2/2.3、内存融合/压缩版本识别、内存压缩、内存压缩2.0（新内存融合）、kswapd绑中小核、shrink_slab、look around、kswapd回收效率log、TOP10 page fault、内存管理Quantus框架、内存配置参数(kswapd水位)、内存配置参数(lmkd 参数)、内存分配**。

执行检查时按表格中的 SPD 编号与行顺序逐项核对；上列为业务侧归纳范围，**具体命令与文档链接仅在表格中维护**。

## 检查工作流

1. **打开表格**：定位 sheet「memory」（或当前版本使用的子表），确认检查项列与「参考文档 / 检查方法」列无折叠或隐藏列。
2. **逐 feature**：对每一行读取「检查项」→ 展开链接与单元格内嵌步骤（含 adb/shell/prop/criterion）→ 按表格描述的版本分支（如不同内核、`tos16` 前后）选择对应方法；**tos16 / TOS 主次版本**可优先用 `adb shell sh -c 'getprop | grep version'` 从机内截取，并与脚本解析结果交叉核对。
3. **记录证据**：保存命令输出片段、关键字段匹配结果或截图路径；注明机型、软件版本、内核分支。
4. **结论**：每项给出 Pass / Fail / Blocked（无法访问设备或表格链接失效）及简述依据。
5. **缺口处理**：若表格某行仅有文档链接而无内嵌命令，按链接文档执行并在结论中注明「依据文档：xxx」。
6. **版本先行（推荐）**：对依赖「融合 / 压缩实现代际」的检查项，先运行下方 **版本识别脚本**，在报告「环境」中写明 `memfusion_version` 与 `memcompress_version`，再选用表格或脚本中对应分支。
7. **内存压缩单版本原则（SPD）**：每台设备在交付上**只需满足一种**内存压缩实现（新融合 2.0 **或** 表路径 1.1 等），**不得**对同一台机在报告中并列罗列多套互不隶属的全量检查。**必须先判定「本机应检版本」**，再**只执行该版本**对应的自动化检查；**SPD 报告正文仅写「内存压缩」单项的结论**（PASS/FAIL/BLOCKED 与依据），勿堆砌与本机应检版本无关的另一套压缩脚本输出。入口脚本详见下文 **`check_mem_compress_status.py`**。

## 内存融合 / 内存压缩 版本识别

依据内部说明《如何判断内存融合、压缩的版本》，在设备上读取 `/proc/memfusion` 与 cgroup / 属性，输出融合版本与压缩版本，供后续检查适配（例如选择 `aegean#wbs` vs `compact_v2`、是否校验 `memcg_compress_v2` 等）。

### 判定摘要（与说明图一致）

**公共前提**：`cat /proc/memfusion/dump_info` 中含 `Swap_Write_Enable:Kernel[On], Frameworks[On]`（脚本对空格大小写略有容错）。

| 维度 | 版本 | 关键条件 |
|------|------|----------|
| 融合 | **2.2** | `swap_write_enable` 为 **1** |
| 融合 | **3.0** | `swap_write_enable` 为 **3**，且 `aggr_enable` 含 **`aggr ab: on`** |
| 压缩 | **1.0** | 上述前提 + `swap_write_enable==3` + `compress_enable` 为 **`compress: on`** |
| 压缩 | **1.1** | 前提 + `swap==3` + `memcg_compress` 为 **`memcg-compress: on`** + `uid_1000/<pid>/cgroup.controllers` 含 **`memory`** + `persist.tr_perf.aegean.mem_compact.support` 为 **2** + `persist.odm.tr_memfusion.memcgcprav2.support` 为 **false 或不存在** |
| 压缩 | **2.0（旧 cgroup）** | 在 1.1 同类基础上 + `memcg_compress_v2` 为 **`memcg-compress-v2: on`** + **`memcgcprav2.support` 为 true**（相对融合代际的 cgroup 侧升级；压缩链路仍可按 1.1 理解） |
| 压缩 | **2.0（新融合）** | 公共前提（`Swap_Write_Enable:Kernel[On], Frameworks[On]`）+ **`persist.odm.tr_memfusion.memcgcprsv2.support` = true** + `dump_info` 同时含 **zram0 + partition** 与 **swapfile + file** + **`/proc/memfusion/zram_bd_list` 含 `/dev/block/dm-*`**；**不要求** `swap_write_enable == 3` |

**说明**：`uid_1000` 下取**第一个数字子目录**作为采样 pid 读取 `cgroup.controllers`；若目录不存在或不可读，**旧 cgroup 压缩**分支可能判为 `unknown`。融合与压缩版本可分别输出；除 **压缩 2.0（新融合）** 外，**1.0 / 1.1 / 2.0（旧 cgroup）** 均要求 `swap_write_enable == 3`，否则 `memcompress_version` 记为 **`none`**。

### 脚本用法

```bash
python .cursor/skills/spd-memory-feature-check/scripts/detect_memfusion_compress_version.py
```

- `--json`：输出结构化 JSON（含 `memfusion_version`、`memcompress_version` 与简要 reason），便于其它工具消费。
- `--export`：额外打印 `MEMFUSION_VERSION=...` 与 `MEMCOMPRESS_VERSION=...`，便于 shell 中 `eval` / 后续脚本分支。

**取值约定**：`memfusion_version` ∈ `2.2` | `3.0` | `unknown`；`memcompress_version` ∈ `none` | `1.0` | `1.1` | `2.0` | `unknown`。

若说明图与飞书表格冲突，**以飞书表格为准**；本段用于自动化识别与报告字段统一。

## 自动检查功能：内存融合2.2/2.3

以飞书表格为准；榫卯架构下 **kernel-5.15 / 6.1 / 6.6 / 6.12** 均为专项支持。检查方法与期望如下：

- 检查命令：
  - `getprop | grep memfusion`
  - `getprop | grep swapfile`
- 期望关键项（`memfusion`）：
  - `[ro.odm.tr_memfusion.support]: [1]`
  - `[ro.odm.tr_memfusion.version21.support]: [true]`
  - `[ro.odm.tr_memfusion.version22.support]: [true]`
- 期望关键项（`swapfile`，表格内 `persist.odm.tr_memfusion.*`）：
  - `[persist.odm.tr_memfusion.swapfile.support]: [true]`
  - `[persist.odm.tr_memfusion.swapfile_size_mb]`：为所选扩展容量对应数值；**任意非零**即视为正常（示例：`6144`）。

为减少人工比对，优先使用本 Skill 脚本：

```bash
python .cursor/skills/spd-memory-feature-check/scripts/check_memfusion_22_23.py
```

判定规则：

- 先识别设备内核版本（`adb shell uname -r`），解析 `major.minor`
- 支持内核：`5.15`、`6.1`、`6.6`、`6.12`
- 上述 `ro.odm` / `persist.odm.tr_memfusion.swapfile.support` 键值与表格一致；`swapfile_size_mb` 为可解析整数且 **> 0** => `PASS`
- 任一必需键缺失、布尔项不为 `true`、或 `swapfile_size_mb` 缺失/非正 => `FAIL`
- `adb` 不可用、设备未连接、命令执行失败、内核版本不支持/无法解析 => `BLOCKED`

将脚本输出中的 `uname -r`、`memfusion/swapfile` 原始行与 `CHECK RESULT` 一并纳入最终检查报告。

## 自动检查功能：内存压缩

### 单版本判定 → 单路径检查 → 报告只含本 feature

1. **判定本机「应检」内存压缩版本（唯一）**，优先级如下（与 `check_mem_compress_status.py` 一致）：
   - **内存压缩 2.0（新内存融合）**：`persist.odm.tr_memfusion.memcgcprsv2.support=true`，**或**（**TOS≥16.3** ∧ **kernel≥6.1**，前者从列举的 `ota`/tran `*.version` 等属性中检索 **`16.3.`** 或解析 **`x.y.z`≥16.3）。
   - **否则**，若 kernel 为脚本矩阵中的 **6.1 / 6.12**：应检 **内存压缩 1.1（飞书表路径）**。
   - **否则**：自动化视为 **BLOCKED / 无矩阵**，应检版本以飞书表格人工为准。
2. **仅执行对应一条检查路径**：2.0 → `evaluate_mem_compress_2_0`（与说明图三项）；1.1 → `evaluate_mem_compress_v11`。**不对同一设备同时跑 2.0 与 1.1 全量脚本并把两套结果都写入 SPD 正文**。
3. **SPD 报告正文**：只保留 **「内存压缩」** 的 **应检版本说明、执行检查名、PASS/FAIL/BLOCKED、失败或阻断要点**。`detect_memfusion_compress_version.py` 的输出为**运行时画像**，与「应检版本」可能不一致；默认 **不写进 SPD 正文**，调试时用 **`check_mem_compress_status.py --verbose`**。

```bash
python .cursor/skills/spd-memory-feature-check/scripts/check_mem_compress_status.py
python .cursor/skills/spd-memory-feature-check/scripts/check_mem_compress_status.py --verbose
python .cursor/skills/spd-memory-feature-check/scripts/check_mem_compress_status.py --json
```

- **`--json`**：单行 JSON，字段含 `feature`、`expected_version`、`expected_label`、`check_executed`、`result`、`details`，便于流水线汇总。
- 退出码：**0** PASS，**1** FAIL，**2** BLOCKED。

**专项脚本（复现 / 已人工确认版本时使用）**：勿替代上文入口做多版本并列报告——仅在已明确需单独验证 **`check_mem_compress_2_0.py`** 或 **`check_mem_compress.py`** 时使用。

基于你提供的表格截图，`内存压缩`（1.0 / 1.1）的检查方式与期望结果如下：

- 检查方式（截图可读内容）：
  - `1.0`：
    - `adb shell dumpsys activity aegean#wbs`
    - `cat /proc/memfusion/compress_enable`
  - `1.1`：
    - `adb shell dumpsys activity aegean#compact_v2 wbs`
    - `cat /proc/memfusion/memcg_compress`
- 期望结果关键字：
  - `wbs pass=true`（上层能力）
  - `compress:on`（底层能力）

为减少人工比对，优先使用本 Skill 脚本：

```bash
python .cursor/skills/spd-memory-feature-check/scripts/check_mem_compress.py
```

判定规则：

- 先识别设备内核版本（`adb shell uname -r`），解析 `major.minor`
- 当前按截图识别的内核支持信息：
  - `kernel-6.1`：专项支持（执行 `1.1` 流程）
  - `kernel-6.12`：专项支持（执行 `1.1` 流程）
  - `kernel-5.15`：专项不支持（`BLOCKED`）
  - `kernel-6.6`：截图中状态未清晰标注（默认 `BLOCKED`，需人工确认）
- `1.1` 流程下同时命中 `wbs pass=true` 且 `memcg_compress` 为 `on` => `PASS`
- 任一关键期望不满足 => `FAIL`
- `adb` 不可用、设备未连接、命令执行失败、内核不支持/状态不明确 => `BLOCKED`

将脚本输出中的 `uname -r`、两条检查命令原始输出与 `CHECK RESULT` 一并纳入最终检查报告。

## 自动检查功能：内存压缩 2.0（新内存融合）

**定位**：内存压缩 **2.0** 为**内存融合**能力迭代；命名 2.0，底层压缩链路仍可按 **1.1** 理解，差异主要在 **ROM / 融合侧框架与 backing 形态**。说明图注明：开启后 `aggr_enable` 等仍可能显示 **on**，但**聚合回写不再作为有效能力**，**不必**再做聚合回写专项测试。

**与机型样例的关系**：说明图中**具体机型/样例标识不作为**本 Skill 的判定依据；**功能检查**仅以下列**技术条件**为准（产线 MTK 对 **tOS ≥ 16.3 且 kernel ≥ 6.1** 项目的**交付要求**见飞书/项目清单，脚本**不**按项目代号自动门控）。

### 条件 1：属性（`getprop` 中含 `memfusion` 的键）

- **必须**：`[persist.odm.tr_memfusion.memcgcprsv2.support]: [true]`（**内存压缩 2.0 / 新内存融合**开关标识）。
- **须与融合侧一致**（与「内存融合 2.2/2.3」脚本对齐）：`ro.odm.tr_memfusion.support`、`version21/22`、`swapfile.support`、`swapfile_size_mb`（**> 0**）等。
- **忽略**：`persist.odm.tr_memfusion.uxcompaction.support`（说明图明确**不必**考虑）。

等价现场命令示例：`adb shell sh -c 'getprop | grep memfusion'`（脚本内解析全量 `getprop` 后筛选）。

### 条件 2：`dump_info`

- `adb shell cat /proc/memfusion/dump_info` 可读。
- 内容须同时体现：**zram0** 且类型为 **partition**；**swapfile** 且类型为 **file**。
- 须含 **`Swap_Write_Enable:Kernel[On], Frameworks[On]`**（新融合激活）。

### 条件 3：`zram_bd_list`（backing 设备形态）

- `adb shell cat /proc/memfusion/zram_bd_list`
- **期望**：出现 **`/dev/block/dm-<n>`**（**device mapper**，新路径）。
- **旧路径**：若仅 **`/dev/block/loop`** 等而无 **`dm-*`**，按说明图视为**旧 backing**，检查结论 **FAIL**。

自动化脚本：

```bash
python .cursor/skills/spd-memory-feature-check/scripts/check_mem_compress_2_0.py
```

判定规则：

- 上述 **三项全部满足** => **PASS**；任一项不满足 => **FAIL**
- `adb` 不可用、设备未连接、关键节点不可读 => **BLOCKED**

**版本识别**：`detect_memfusion_compress_version.py` 在 **`memcgcprsv2=true` + dump 形态 + `zram_bd_list` 含 `dm-*`** 时，会将 `memcompress_version` 标为 **`2.0`**（与旧 cgroup 路径识别的 2.0 共用枚举值，理由串不同，可对照输出）。

## 自动检查功能：kswapd绑中小核

基于你提供的表格截图，`kswapd绑中小核` 的检查方式与期望结果如下：

- 检查命令：
  - `getprop | grep kswapd0`
- 期望关键项：
  - `persist.odm.tr_powerhal.kswapd0_bind.feature.support` 值为 `1` 或 `-1`
  - 备注：截图提示此值用于表示当前开关/策略状态

为减少人工比对，优先使用本 Skill 脚本：

```bash
python .cursor/skills/spd-memory-feature-check/scripts/check_kswapd_bind.py
```

判定规则：

- 先识别设备内核版本（`adb shell uname -r`），解析 `major.minor`
- 当前按截图识别的内核支持信息：
  - `kernel-5.15`：专项不支持（`BLOCKED`）
  - `kernel-6.1`：专项支持
  - `kernel-6.6`：专项支持
  - `kernel-6.12`：专项支持
- 支持内核下，若 `persist.odm.tr_powerhal.kswapd0_bind.feature.support`（或兼容历史键）值为 `1/-1` => `PASS`
- 键缺失或值不在期望集合 => `FAIL`
- `adb` 不可用、设备未连接、命令执行失败、内核不支持/未知 => `BLOCKED`

将脚本输出中的 `uname -r`、`getprop | grep kswapd0` 原始行与 `CHECK RESULT` 一并纳入最终检查报告。

## 自动检查功能：shrink_slab

基于你提供的表格截图，`shrink_slab` 的检查方式与期望结果如下：

- 检查命令：
  - `ps -ef | grep shrink_slab`
- 期望关键输出：
  - 包含 `[kshrink_slabd]`

为减少人工比对，优先使用本 Skill 脚本：

```bash
python .cursor/skills/spd-memory-feature-check/scripts/check_shrink_slab.py
```

判定规则：

- 先识别设备内核版本（`adb shell uname -r`），解析 `major.minor`
- 当前按截图识别的内核支持信息：
  - `kernel-5.15`：专项支持
  - `kernel-6.1`：专项支持
  - `kernel-6.6`：专项支持
  - `kernel-6.12`：专项不支持（`BLOCKED`）
- 支持内核下，`ps -ef | grep shrink_slab` 输出包含 `kshrink_slabd` => `PASS`
- 支持内核下，未命中该关键输出 => `FAIL`
- `adb` 不可用、设备未连接、命令执行失败、内核不支持/未知 => `BLOCKED`

将脚本输出中的 `uname -r`、`ps -ef | grep shrink_slab` 原始行与 `CHECK RESULT` 一并纳入最终检查报告。

## 自动检查功能：look around

`look around` 按**内核主次版本**分两条检查路径（脚本自动选择）：

### 分支 A：**kernel 6.1** — 内核原生 LRU_GEN

6.1 使用内核原生 look around（**LRU_GEN**），**不**检查 `/sys/module/look_around/`。

- 检查命令：`adb shell cat /sys/kernel/mm/lru_gen/enabled`
- 期望：`enabled` 节点可读，且取值**非 0**（如 `0x0003` 表示已使能）

### 分支 B：**kernel 5.15 / 6.6** — Tran `look_around.ko` 模块

沿用模块 sysfs 检查：

- 检查命令：`adb shell ls /sys/module/look_around/`
- 期望目录项：`coresize`、`holders`、`initsize`、`initstate`、`notes`、`refcnt`、`sections`、`taint`、`uevent`

为减少人工比对，优先使用本 Skill 脚本：

```bash
python .cursor/skills/spd-memory-feature-check/scripts/check_look_around.py
```

判定规则：

- 先识别设备内核版本（`adb shell uname -r`），解析 `major.minor`
- 内核支持矩阵：
  - `kernel-5.15`：专项支持 → **分支 B**（模块目录）
  - `kernel-6.1`：内核派生支持 → **分支 A**（`lru_gen/enabled` 非 0）
  - `kernel-6.6`：专项支持 → **分支 B**（模块目录）
  - `kernel-6.12`：专项不支持（`BLOCKED`）
- **6.1**：`lru_gen/enabled` 可读且非 0 => `PASS`；节点缺失或值为 0 => `FAIL`
- **5.15 / 6.6**：`ls /sys/module/look_around/` 命中所有期望目录项 => `PASS`；缺少任一项 => `FAIL`
- `adb` 不可用、设备未连接、内核不支持/未知 => `BLOCKED`

将脚本输出中的 `uname -r`、对应分支的命令原始输出与 `CHECK RESULT` 一并纳入最终检查报告。

## 自动检查功能：kswapd回收效率log

基于你提供的表格截图，`kswapd回收效率log` 的检查方式与期望结果如下：

- 检查命令：
  - `adb shell logcat | grep TranMemoryInfo`
  - 或 `adb shell dmesg | grep TranMemoryInfo`
- 期望结果：
  - 有相关日志输出（截图备注：若未立即显示，可等待并触发相关场景后再检查）

为减少人工比对，优先使用本 Skill 脚本：

```bash
python .cursor/skills/spd-memory-feature-check/scripts/check_kswapd_reclaim_log.py
```

判定规则：

- 先识别设备内核版本（`adb shell uname -r`），解析 `major.minor`
- 当前按截图识别的内核支持信息：
  - `kernel-5.15`：专项支持
  - `kernel-6.1`：专项支持
  - `kernel-6.6`：专项支持
  - `kernel-6.12`：专项支持
- 支持内核下，`logcat` 或 `dmesg` 任一命中 `TranMemoryInfo` 相关日志 => `PASS`
- 支持内核下，两者都无命中 => `FAIL`（建议等待并触发业务场景后复测）
- `adb` 不可用、设备未连接、命令执行失败、内核支持状态未知 => `BLOCKED`

将脚本输出中的 `uname -r`、`logcat/dmesg` 原始匹配行与 `CHECK RESULT` 一并纳入最终检查报告。

## 自动检查功能：TOP10 page fault

基于你提供的表格截图，`TOP10 page fault` 的检查方式与期望结果如下：

- 检查命令：
  - `adb shell dmesg | grep TranMemoryInfo`
  - `cat /proc/tran_mm_collect/page_fault_sampling`
- 期望结果：
  - `dmesg` 有 page fault 相关信息输出

为减少人工比对，优先使用本 Skill 脚本：

```bash
python .cursor/skills/spd-memory-feature-check/scripts/check_top10_page_fault.py
```

判定规则：

- 先识别设备内核版本（`adb shell uname -r`），解析 `major.minor`
- 当前按截图识别的内核支持信息：
  - `kernel-5.15`：专项支持
  - `kernel-6.1`：专项支持
  - `kernel-6.6`：专项支持
  - `kernel-6.12`：专项支持
- 支持内核下，`dmesg` 命中 `TranMemoryInfo/page fault` 且 `page_fault_sampling` 节点可读 => `PASS`
- 支持内核下，任一关键证据缺失 => `FAIL`
- `adb` 不可用、设备未连接、命令执行失败、内核支持状态未知 => `BLOCKED`

将脚本输出中的 `uname -r`、`dmesg` 匹配行、`page_fault_sampling` 原始输出与 `CHECK RESULT` 一并纳入最终检查报告。

## 自动检查功能：内存管理Quantus框架

**共同前提**：设备 **TOS 主次版本 ≥ 16.3**（脚本使用 `SPD_TOS_VERSION` → 专用 TOS 属性 → `adb shell sh -c 'getprop | grep version'`，与 `tos_detect` 一致）。不满足时结论 **BLOCKED**（不区分内核分支）。

检查命令（两条均在设备上执行）：

1. `adb shell cat /proc/pages_prefiltered/page_filter_state`
2. `adb shell sh -c 'getprop | grep quantus'`（或 adb shell 内 `getprop | grep quantus`）

### 分支 A：**TOS ≥ 16.3 且 kernel6 及以上**（`uname -r` 解析为 **(major, minor) ≥ (6, 0)**，且非下表专项不支持内核）

- **期望**：
  - `page_filter_state` 为使能：**值为 `1`**，或 **`1:*`** 类格式且可按表将前段 **`1`** 视为使能；
  - `getprop` 中存在 **quantus** 相关属性（值**不**强制全为 1，与早期截图一致）。
- **专项不支持（脚本 BLOCKED）**：`kernel-6.6`、`kernel-6.12`（与历史飞书截图「专项不支持」一致；若表格已放开，需改脚本常量 `UNSUPPORTED_KERNEL_MM`）。

### 分支 B：**TOS ≥ 16.3 且 kernel 小于 kernel6**（如 **5.15**，即 **(major, minor) < (6, 0)**）— 补充路径

- **期望（更严）**：
  - `page_filter_state` **取值须为 `1`**（严格等于 **1**；不接受仅靠 `1:2` 等多段格式判 Pass，除非整段抽取值即为 **`1`**）；
  - **所有** 名称含 `quantus` 的 `getprop` 项，**值均为 `1`**（与「grep quantus 结果为 1」一致：逐键校验）。

为减少人工比对，优先使用本 Skill 脚本：

```bash
python .cursor/skills/spd-memory-feature-check/scripts/check_quantus_framework.py
```

判定规则（脚本自动选分支）：

- 无法解析 **TOS** 或 **TOS < 16.3** => **BLOCKED**
- **kernel 6.6 / 6.12**（在 kernel≥6 类设备上）=> **BLOCKED**（表内专项不支持）
- **kernel ≥ 6**（且非 6.6/6.12）：分支 A —— `page_filter_state` 使能 + 存在 quantus 属性 => **PASS**；否则 **FAIL**
- **kernel < 6** 且 **TOS ≥ 16.3**：分支 B —— `page_filter_state` **严格为 1** + 全部 quantus 属性值为 **1** => **PASS**；否则 **FAIL**
- `adb` 不可用、命令失败等 => **BLOCKED**

将脚本输出中的 **TOS 解析**、`uname -r`、分支名、`page_filter_state` 原始值、`getprop | grep quantus` 与 `CHECK RESULT` 一并纳入最终检查报告。

## 自动检查功能：内存分配

**前置支持条件（业务 / SPD 约定：仅 TOS16.3 及以上，且 kernel6 及以上）**：

- **TOS**：须为 **TOS16.3 及以上**，即解析出的主次版本 **≥ 16.3**（**16.3、16.4、17.x** 等；**16.2 及以下** 不满足，脚本结论 **BLOCKED**）。解析顺序与 CPU SPD 共用 **`.cursor/skills/spd-shared/scripts/tos_detect.py`**：`SPD_TOS_VERSION` → 专用 TOS 属性 → 设备 **`adb shell sh -c 'getprop | grep version'`** 输出中截取 `主.次`（优先键名含 `tos`/`tranos` 或主版本 **≥16** 的候选）。读不到有效主次版本时 **BLOCKED**。
- **Linux 内核（kernel6 及以上）**：解析 `uname -r` 的 **(major, minor) ≥ (6, 0)**（含 **6.0、6.1、6.6、6.12** 等；**5.15** 等 **< 6.0** **BLOCKED**）。若飞书将「kernel6」定义为仅 **6.1+**（不含 6.0），需将脚本常量 `KERNEL_MIN_INCLUSIVE_MM` 改为 `(6, 1)` 并与表格对齐。

不满足上述任一门槛时，自动化结论为 **BLOCKED**（不继续判 PASS/FAIL）。

基于你提供的表格截图，`内存分配` 的检查方式与期望结果如下：

- 前提（从截图可读；且须已满足上文 TOS / 内核门槛）：
  - 先确认 umf 功能是否正常开启
  - 非 trms 项目与支持 trms 项目使用不同属性/命令分支
- 检查命令：
  1. 属性检查（按项目分支）
     - 非 trms：`adb shell getprop | findstr aegean`
     - trms：`adb shell getprop persist.tr_perf.rms.memvip.support`
  2. WBS 检查（按项目分支）
     - 非 trms：`adb shell dumpsys activity aegean#umf wbs`
     - trms：`adb shell dumpsys activity service TranRmsService rms#memvip config_mem_vip`
  3. 分配功能状态检查：
     - `adb shell cat /proc/priority_allocate/vip_page_pool_state`
  4. 分配功能内存池检查：
     - `adb shell cat /proc/priority_allocate/vip_page_pool`
- 期望结果（按截图可读）：
  - 非 trms 属性包含 `persist.tr_perf.aegean.support:[1]` 或 `persist.tr_perf.aegean.umf.support:[1]`
  - trms 属性包含 `persist.tr_perf.rms.memvip.support:[1]`
  - 非 trms 的 WBS 输出包含 `check enable:true`、`check init:true`、`check kernel:1`、`check pool:true`
  - trms 的 WBS 输出包含 `isUmfEnabletrue`（或等价格式）
  - `vip_page_pool_state` 中 `vip_page_pool_setup: 1`、`vip_page_fillthread_setup: 1`
  - `vip_page_pool` 中 `total_used`、`pcp_used` 等统计为有效非零值

为减少人工比对，优先使用本 Skill 脚本：

```bash
python .cursor/skills/spd-memory-feature-check/scripts/check_memory_allocate.py
```

可选（与 `spd-cpu-feature-check` 一致）：在运行前导出 **`SPD_TOS_VERSION`**，用于在未刷出 TOS 属性时强制版本门控。

```bash
# PowerShell 示例
$env:SPD_TOS_VERSION="16.3.0"
python .cursor/skills/spd-memory-feature-check/scripts/check_memory_allocate.py
```

判定规则：

- 先识别 **Linux 内核** `uname -r`：**(major, minor) ≥ (6, 0)**（kernel6 及以上）才继续，否则 **BLOCKED**。
- 再识别 **TOS** 主次版本：**≥ 16.3**（TOS16.3 及以上）才继续，否则 **BLOCKED**（`SPD_TOS_VERSION`、专用 TOS 属性、`getprop | grep version` 均无法解析出满足条件的版本时 **BLOCKED**）。
- 门控通过后：属性分支匹配 + WBS 检查通过 + `vip_page_pool_state` 通过 + `vip_page_pool` 计数有效 => `PASS`
- 门控通过后：任一关键证据缺失 => `FAIL`
- `adb` 不可用、设备未连接、命令执行失败 => `BLOCKED`

将脚本输出中的 **TOS 解析行**、`uname -r`、属性检查输出、WBS 输出、`vip_page_pool_state` 与 `vip_page_pool` 原始内容及 `CHECK RESULT` 一并纳入最终检查报告。

## 输出模板（结论汇总）

```markdown
# SPD-内存 Feature 检查结论

## 环境
- 机型/项目：
- 版本/build：
- TOS（内存分配门控：须 **≥16.3**，如 16.3.0）：
- 内核/平台：（如已知）

## 逐项结果

| 检查项 | 结果 | 依据摘要 |
|--------|------|----------|
| ... | Pass/Fail/Blocked | 命令/日志要点 |

## 待跟进
- （表格或文档链接无法打开、命令与当前版本不匹配等）
```

## 注意事项

- 不同平台（MTK / Qualcomm / Unisoc 等）同一 feature 的检查分支可能写在表格同一单元格内，需完整阅读再执行。
- 「检查结果」若存在于表格独立列，应与现场证据交叉核对后再填写汇总表。
- 勿将本 Skill 中的归纳列表当作完整检查步骤；**步骤细节永远在飞书表格及表格内链文档中**。
