---
name: android-kernel-stability-analysis
description: Android 内核稳定性问题分析总入口：按平台（MTK/展锐）与现象路由到 KE、Hang、HWT、不开机、KernelAPI dump 等子 skill；按需从 GitLab 拉取解压工具（MTK：db/tne；展锐：仅 tne，无 db）。用户提到内核稳定性、重启、死机、panic、watchdog、KE、hang、HWT、不开机、展锐/Unisoc 内核 dump 且未指明具体子类时使用。
---

# Android 内核稳定性问题分析（总入口）

本 skill 为 **`AI故障分析/内核`** 目录的**统一入口**：只做平台判定、问题分型、子 skill 路由与解压工具准备，**不替代**各子 skill 的深度分析。

编写规范：[Skills 编写标准](https://transsioner.feishu.cn/wiki/AT0wwM6bKi94JNkpK3cc7EkdnmK)

## 目录内 skill 分层

| 类型 | skill | 说明 |
|------|-------|------|
| **总入口** | `android-kernel-stability-analysis`（本文件） | 路由与工具准备 |
| **MTK 分析子类** | `android-ke-log-analysis` | KE / ATF / 综合内核异常重启 |
| | `android-hang-log-analysis` | Hang detect、线程阻塞 |
| | `android-hwr-hwt-log-analysis` | HWT / HWR、WDT 硬复位 |
| | `android-bootup-issue-log-analysis` | 不开机 / 卡 Logo / 循环重启 |
| | `android-kernel-api-dump-log-analysis` | Kernel API dump / EMI MPU Violation |
| **展锐分析子类** | `android-unisoc-kernel-crash-log-analysis` | 展锐平台整机重启 dump（**有 `.tne`，无 `.dbg`**） |
| **解压工具**（非分析 skill） | `android-kerneldb-extract` | `.dbg` → `aee_extract` + KSST64（**仅 MTK**） |
| | `android-kerneltne-extract` | `.tne` → `decompress` + KSST64（**MTK / 展锐**） |
| **共享脚本** | `android-analysis-shared` | 各分析子类提取脚本的公共框架 |

详细路由表见 [references/skill-routing-index.md](references/skill-routing-index.md)。

---

## 执行顺序（强制）

1. **平台判定** → MTK 或展锐（不明则停止反问）
2. **问题分型** → 选定 1 个主分析子 skill
3. **工具准备**（日志含 `.dbg` / `.tne` 时）→ 按平台从 GitLab 拉取对应解压工具（见步骤3）
4. **进入子 skill** → 打开同级目录下对应 `SKILL.md` 并完整执行其流程
5. **输出** → 沿用子 skill 规定的 Jira / 分析报告模板

**请勿评论 Jira**（各子 skill 通用约定）。

---

## 步骤1：平台判定

按以下顺序执行；**展锐与 MTK 不得混用解压与分析路径**。

### 1.1 直判为展锐（Unisoc）

命中任一即可：

- 用户明确：展锐 / Unisoc / SPRD / Spreadtrum
- Jira / 版本信息为展锐平台
- 日志特征：`dump_report.txt`、`extend_last_kmsg`、`extend_ylog_buf`、`exception_reboot_reason`（展锐 dump 结构）
- 日志含 **`.tne`**（展锐内核异常包），**不含** MTK 典型 `*.dbg` / `db.fatal.*.dbg`

→ 进入 **`android-unisoc-kernel-crash-log-analysis`**。  
→ **跳过** `android-kerneldb-extract`（展锐**无 `.dbg`**）。  
→ 若 `log_root` 含 **`*.tne`**：按步骤3 安装 `android-kerneltne-extract` 并解压后再分析。

### 1.2 直判为 MTK（默认）

命中任一即可：

- 用户明确：MTK / MediaTek / 联发科
- 日志含 `*.dbg`、`0xffffff0c|0d|04|15_*.tne`、`__exp_main.txt`、`SYS_KERNEL_LOG`、`db.fatal.*.dbg.DEC`
- 子 skill 描述中的 MTK AEE / DEC 结构

→ 继续 **步骤2**（MTK 问题分型）。

### 1.3 无法判定

停止并反问：

> 当前信息不足以区分 MTK 与展锐平台。请确认芯片平台，或提供含平台特征的日志文件名/路径片段。

在用户确认前，**不得**进入任一分析子 skill。

---

## 步骤2：MTK 问题分型与子 skill 选择

在 `log_root`（或即将下载的日志目录）上结合用户描述，选定 **唯一主 skill**：

| 优先匹配的现象 / 关键词 | 子 skill |
|-------------------------|----------|
| 不开机、卡 Logo、循环重启、黑屏无振动、`BOOTPROF`、`dm-verity`、`fs_mgr_mount_all` | `android-bootup-issue-log-analysis` |
| Hang detect、关机/重启卡死、system_server 无响应、D 状态线程、阻塞 | `android-hang-log-analysis` |
| HWT、HWR、`hw reboot`、`lastpc`、`systracker`、WDT 硬复位 | `android-hwr-hwt-log-analysis` |
| Kernel API dump、EMI MPU、`Plat_Parser`、violation address | `android-kernel-api-dump-log-analysis` |
| KE、Kernel panic、Oops、ATF crash、OCP reboot、通用重启根因（以上均不明显时） | `android-ke-log-analysis` |

若现象跨类：以**用户主诉**与**最强日志证据**定主 skill；次类现象写入报告「关联线索」，不并行执行多个完整分析流程。

---

## 步骤3：解压工具准备（按平台）

`android-kerneldb-extract` 与 `android-kerneltne-extract` 为**工具类 skill**（体积大、含二进制），**不随本仓库日常分发**；按日志内容与平台**按需**从 GitLab 安装到 `.cursor/skills/`。

**源仓库**：<http://gitlab.transsion.com/lq/skills.git>

### 3.0 平台与日志格式（强制）

| 平台 | `.dbg` | `.tne` | 可用解压工具 |
|------|--------|--------|--------------|
| **MTK** | 有 | 有 | `android-kerneldb-extract` + `android-kerneltne-extract`（按扫描结果择一或两者） |
| **展锐** | **无** | **有** | **仅** `android-kerneltne-extract`（**禁止**安装/调用 `android-kerneldb-extract`） |

### 3.1 判定需要哪个工具

在 `log_root` 下递归扫描：

| 日志特征 | 平台 | 需安装的工具 | 仓库内路径 |
|----------|------|--------------|------------|
| 存在 `*.dbg` | MTK | `android-kerneldb-extract` | `skills/AI故障分析/内核/android-kerneldb-extract` |
| 存在 `*.tne` | MTK / 展锐 | `android-kerneltne-extract` | `skills/AI故障分析/内核/android-kerneltne-extract` |
| 同时含 `.dbg` 与 `.tne` | MTK | **两个都安装** | 上表两行 |
| 仅含 `.tne` | 展锐 | **仅** `android-kerneltne-extract` | 上表第二行 |

子 skill 与工具的对应关系（摘要）：

- **MTK**（ke / hang / hwt / bootup / kernel-api-dump）：通常需 `kerneldb-extract`；含 `.tne` 时还需 `kerneltne-extract`
- **展锐**：日志为 **`.tne` 格式、无 `.dbg`**；仅需 `kerneltne-extract`（含 `.tne` 时），**不得**使用 `kerneldb-extract`

分析子类自带的 `*_extract.py` 依赖 **`android-analysis-shared`**；若本地缺失，一并从仓库安装：

- 路径：`skills/AI故障分析/内核/android-analysis-shared`
- 目标：`.cursor/skills/android-analysis-shared`

### 3.2 安装到 `.cursor/skills/`（推荐）

工作目录为仓库根；目标为 **扁平 skill 名**（与各子 skill 内命令一致）。

**Linux / macOS / 容器**：

```bash
GITLAB_REPO="http://gitlab.transsion.com/lq/skills.git"
WORK="/tmp/lq-skills-$$"
DEST=".cursor/skills"

git clone --depth 1 --filter=blob:none --sparse "$GITLAB_REPO" "$WORK"
cd "$WORK"
git sparse-checkout set \
  "skills/AI故障分析/内核/android-kerneldb-extract" \
  "skills/AI故障分析/内核/android-kerneltne-extract" \
  "skills/AI故障分析/内核/android-analysis-shared"

mkdir -p "$DEST"
for name in android-kerneldb-extract android-kerneltne-extract android-analysis-shared; do
  cp -a "skills/AI故障分析/内核/$name" "$DEST/"
done
cd - && rm -rf "$WORK"
```

仅缺其中一个工具时，可只 sparse-checkout 对应路径。

**Windows（PowerShell）**：

```powershell
$repo = "http://gitlab.transsion.com/lq/skills.git"
$work = Join-Path $env:TEMP "lq-skills-$(Get-Random)"
$dest = ".cursor\skills"
git clone --depth 1 $repo $work
$names = @("android-kerneldb-extract","android-kerneltne-extract","android-analysis-shared")
foreach ($n in $names) {
  $src = Join-Path $work "skills\AI故障分析\内核\$n"
  if (Test-Path $src) { Copy-Item -Recurse -Force $src (Join-Path $dest $n) }
}
Remove-Item -Recurse -Force $work
```

### 3.3 安装后校验

```bash
test -x .cursor/skills/android-kerneldb-extract/tools/aee_extract/aee_extract && echo "kerneldb-extract OK"
test -x .cursor/skills/android-kerneltne-extract/tools/decompress/linux/decompress && echo "kerneltne-extract OK"
test -f .cursor/skills/android-analysis-shared/scripts/dec_extract_common.py && echo "analysis-shared OK"
```

任一失败：报告缺失项，**不得**假装解压已完成。

---

## 步骤4：进入子 skill

在**本目录同级**打开已选子 skill 的 `SKILL.md`，例如：

```
AI故障分析/内核/android-ke-log-analysis/SKILL.md
```

子 skill 内若引用 `.cursor/skills/android-kerneldb-extract/...` 或 `android-kerneltne-extract/...`，须先完成步骤3。  
**展锐**：仅允许 `kerneltne-extract`（含 `.tne` 时），**禁止**调用 `kerneldb-extract`。

---

## 路径约定（全目录通用）

- **工作目录**：仓库根；临时文件写入 `temp/`
- **分析子 skill 路径**（本仓库）：`skills/AI故障分析/内核/<skill-name>/`
- **解压工具路径**（执行脚本）：`.cursor/skills/<tool-skill-name>/`
- **Windows cmd**：`set PYTHONIOENCODING=utf-8 &&`；路径可用反斜杠

---

## 输出要求

以**子 skill**模板为准；总入口额外在报告开头注明：

1. **平台**：MTK / 展锐  
2. **路由 skill**：最终采用的子 skill 名称  
3. **工具**：已安装并执行的解压工具（展锐：仅 tne / 无 dbg；MTK：按实际）
