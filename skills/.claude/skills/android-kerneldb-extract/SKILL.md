---
name: android-kerneldb-extract
description: "Android-KernelDB提取: 从Jira日志目录提取.dbg内核异常包，使用aee_extract解压+KSST64离线分析 | aee_extract/.dbg/.dbg.DEC/KSST64/SpOfflineDebugSuite | 当用户要求解压.dbg、生成.dbg.DEC、跑KSST64离线分析时使用"
funcType: "AI故障分析"
category: "内核"
---

# Android Kernel DB（.dbg）解压与 KSST64 提取

## 工具依赖与路径

本 skill 目录下已携带工具副本（与源目录同步更新时从源复制覆盖即可）：

| 工具 | skill 内路径 | 源目录（本机维护） |
|------|----------------|---------------------|
| `aee_extract` | `tools/aee_extract/` |
| `SpOfflineDebugSuite` | `tools/SpOfflineDebugSuite/` |

- Linux 分析机：使用 `tools/aee_extract/aee_extract` 与 `tools/SpOfflineDebugSuite/linux/KSST64`。

## 何时应用

用户给出 **Jira 单号** 或已下载的 **日志根目录**，需要：

1. 在日志目录（含子目录）中查找所有 **`*.dbg`**；
2. **`aee_extract <文件.dbg>`** 解压；
3. 在 **`.dbg` 所在目录** 对解压得到的 **`*.dbg.DEC/`** 目录执行 **`printf '\nq\n' | ./SpOfflineDebugSuite/linux/KSST64 ./<name>.dbg.DEC/`**（非交互进入子 shell 后输入 `q` 退出）。

## 工作流程

### 1. 取得日志目录

- 若仅 Jira 单号：先按项目惯例下载附件/日志（例如调用 **`jira_login_download`** 技能中的脚本）到本地，得到**日志根目录** `LOG_ROOT`。
- 若用户已提供路径：直接使用该路径作为 `LOG_ROOT`。

### 2. 发现 `.dbg` 文件

在 `LOG_ROOT` 下递归查找后缀为 **`.dbg`** 的文件（忽略大小写按项目约定，默认小写 `.dbg`）。

记录每个文件的**所在目录** `DBG_DIR` 与**文件名** `DBG_NAME`（如 `db.fatal.00.KE.dbg`）。

### 3. 解压：`aee_extract **.dbg`

先判断 `.dbg` 在含该文件的目录是否有写权限，若无写权限，先将 `.dbg` 下载到本地，再执行以下步骤，若有写权限可以直接执行以下步骤
对每个 `.dbg` 在含该文件的目录中执行（将 `aee_extract` 换成本 skill `tools` 下实际路径或已加入 `PATH` 的同名命令）：

```bash
cd "$DBG_DIR"
aee_extract "$DBG_NAME"
```

解压成功后，同目录下通常会出现与包名对应的 **`*.dbg.DEC/`** 目录（目录名与 `aee_extract` 输出一致即可）。

### 4. 运行 KSST64（自动 `q` 退出）

仍在 **`$DBG_DIR`**（即 `.dbg` 文件所在目录）下执行；`KSST64` 使用本 skill 内 Linux 副本的相对路径（请按实际 skill 根目录 `SKILL_ROOT` 调整）：

```bash
cd "$DBG_DIR"
printf '\nq\n' | "$SKILL_ROOT/tools/SpOfflineDebugSuite/linux/KSST64" "./${DEC_DIR_NAME}/"
```

其中 `DEC_DIR_NAME` 为该 `.dbg` 对应的 **`*.dbg.DEC`** 目录名（若同一目录多个 DEC，按步骤 3 的产物逐个执行）。

说明：

- 第一行 `\n`：对应提示中的「回车进入命令行」。
- 第二行 `q\n`：进入后输入 `q` 退出子 shell。
- **不使用 `expect`**，仅用管道喂 stdin。

若目标程序从 **`/dev/tty`** 读键而非 stdin，管道可能无效，需改用 **`script`** 等伪终端方案（见 `scripts/README.md`）。

### 5. 输出与后续分析

- KSST64 运行结束后，`*.dbg.DEC/` 内应包含已导出的 kernel log、符号解析结果等，供 **`kernel-panic-crash-analysis`**、**`android-ke-log-analysis`** 等技能继续分析。
- 向用户汇总：每个 `.dbg` 的路径、`aee_extract` 是否成功、`KSST64` 是否完成及产物目录路径。

## 一键脚本（Linux）

在日志根目录已就绪且本 skill 已同步到分析机时，将下面路径换成本仓库中本 skill 的绝对路径后执行：

```bash
bash /path/to/repo/.cursor/skills/android-kerneldb-extract/scripts/kerneldb_extract_all.sh /path/to/LOG_ROOT
```

`kerneldb_extract_all.sh` 会根据脚本位置自动解析 `SKILL_ROOT`，从 `tools/` 调用 `aee_extract` 与 `KSST64`。若管道无法驱动交互，见 [scripts/README.md](scripts/README.md)。

## 检查清单

- [ ] 已确认 `LOG_ROOT` 或已从 Jira 拉取日志。
- [ ] 已枚举所有 `*.dbg` 并逐个 `aee_extract`。
- [ ] 在每个 `.dbg` 同级目录对对应 `*.dbg.DEC/` 执行 `printf '\nq\n' | .../KSST64 ./.../`。
- [ ] 已记录产物路径并视需要触发下游内核/KE 分析技能。
