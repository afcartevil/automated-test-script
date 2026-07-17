---
name: harness-flash-single-img
description: 通过 harness device flash 选择性刷入单个分区镜像。用户给出一个本地 .img 路径和目标分区，把该镜像 staging 到临时目录并只刷这一个分区，全程走 harness 的 fastboot 后端（复用进 bootloader、OEM 解锁、内置 fastboot、reboot 与风险分区保护）。当用户要"只刷 boot/dtbo/vbmeta/super 等某一个 img 到对应分区""单刷分区""刷单个镜像不刷整包"时使用。
disable-model-invocation: true
---

# Harness 单分区镜像刷入

只刷一个 img 到它对应的分区，其余分区不动。**全程通过 `harness device flash --backend fastboot` 完成，不直接拼 `fastboot` / `adb`**。

原理：harness fastboot 后端在目录里没有 `android-info.txt` / `flash_all.*` 时进入 auto 模式，按文件名 `<partition>.img` 逐分区刷。因此把目标 img 复制成 `<partition>.img` 放进一个**只含这一个文件**的临时目录，再指定该目录刷机，就只会刷这一个分区。

## 何时使用

- 用户给出单个本地镜像路径（如 `D:\imgs\boot.img` 或任意文件名 `xxx.img`）并指明要刷到哪个分区；
- 用户要"单刷/只刷某个分区"，不想刷整包。

## 支持的分区（路线 A）

`boot`、`recovery`、`system`、`system_ext`、`vendor`、`vendor_boot`、`product`、`odm`、`dtbo`、`vbmeta`、`vbmeta_system`、`super`、`persist`、`modem`、`preloader`、`logo`

**不支持**：`userdata`、`cache`（harness fastboot auto 模式默认跳过这两个分区，CLI 无法关闭该跳过）。用户要刷这两个分区时，直接告知不支持，并建议走整包 `harness device flash` 或提 feedback 让产品加单分区 CLI。

## 前置条件

- 设备已 **OEM 解锁**（locked bootloader 下 fastboot flash 会失败）；
- 设备能被识别（`harness device probe` 能看到，或能被拉进 fastboot）。

## 执行策略：自动执行，不等用户确认

信息齐全后**直接跑完整刷机流程，不要停下来征求用户确认**。只有在缺少必要输入或发生异常时才停止，并按下面"异常引导"输出可执行指示。每一步以结构化 JSON 结果为准判断成败。

必要输入：源 img 本地路径、目标分区。SN 可自动探测（见步骤 1）。三者能凑齐就直接开刷。

## 工作流（复制此清单并逐项跟踪）

```
- [ ] 1. 确定 SN（缺省则自动探测）
- [ ] 2. 校验分区在支持列表内
- [ ] 3. staging：临时目录内放 <partition>.img
- [ ] 4. dry-run 自动预检
- [ ] 5. 预检通过即正式刷入（无需用户确认）
- [ ] 6. 清理临时目录
```

**1. 确定 SN**

用户已给 SN 就直接用。未给则自动探测：

```text
harness --json device probe
```

- 恰好一台设备 → 直接用其 SN，继续。
- 零台或多台 → 停止，按"异常引导"输出（列出可选 SN 或提示连接设备）。

**2. 校验分区**

目标分区必须在上面"支持的分区"列表内。是 `userdata`/`cache` 或不在列表 → 停止并按"异常引导"说明；其余情况直接继续。

**3. Staging（关键：只放一个文件，命名为 `<partition>.img`）**

在**源 img 所在盘**建临时目录，避免跨盘复制大文件（`super.img` 可达数 GB）。优先用硬链接（同盘瞬时、不占额外空间），失败再复制：

```powershell
$src = "D:\imgs\my_boot_v2.img"    # 用户给的源 img
$partition = "boot"                  # 目标分区
$stage = Join-Path (Split-Path $src) (".harness_flash_stage_" + $partition)
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory -Path $stage | Out-Null
$dst = Join-Path $stage ($partition + ".img")
try { New-Item -ItemType HardLink -Path $dst -Target $src -ErrorAction Stop | Out-Null }
catch { Copy-Item -LiteralPath $src -Destination $dst -Force }
```

**4. dry-run 自动预检**

```text
harness --json device flash --sn <sn> --rom-path <stage> --backend fastboot --dry-run
```

自动检查 `status` 与 plan 是否只涉及目标分区。`status != ok` → 停止，按"异常引导"处理；通过则**立即进入步骤 5，不询问用户**。

**5. 正式刷入（预检通过后自动执行）**

```text
harness --json device flash --sn <sn> --rom-path <stage> --backend fastboot
```

- bootloader 已锁又需要自动解锁时，加 `--require-oem-unlock`（注意：解锁会清 userdata）。

**6. 清理**

无论刷机成败都执行：

```powershell
Remove-Item $stage -Recurse -Force
```

## 异常引导（遇到问题不静默，输出可执行指示）

任一步返回非 `ok`/`success` 时，停止后续步骤，先清理 staging 目录，再根据 `artifacts.error_code` 或 `output` 输出具体指示：

| 现象 / error_code | 含义 | 给出的指示 |
|---|---|---|
| probe 零设备 | 设备未连接/未识别 | 提示插好 USB、开 USB 调试或进 fastboot，重试 |
| probe 多设备 | SN 不明确 | 列出所有 SN，请用户指定 `--sn` |
| 分区不支持 / userdata / cache | 路线 A 不覆盖 | 说明不支持，建议整包刷或提 feedback |
| `ROM_PATH_NOT_FOUND` | staging 目录/路径错误 | 检查源 img 路径与 staging 是否生成成功 |
| `FASTBOOT_TOOL_NOT_FOUND` / `FLASH_TOOLKIT_NOT_AVAILABLE` | harness 刷机后端缺失 | 运行 `harness doctor`，必要时重装 harness CLI |
| `DEVICE_OFFLINE` / `FASTBOOT_DEVICE_NOT_FOUND` | 进不了 fastboot | 手动 `reboot bootloader` 或检查驱动，重试 |
| `BOOTLOADER_LOCKED` / `BOOTLOADER_UNLOCK_FAIL` | 未解锁 | 加 `--require-oem-unlock`（会清 userdata），或先手动解锁 |
| `PARTITION_FAIL` / `PARTITION_STALLED` | 分区刷入失败 | 回显 fastboot 原始输出，提示 img 与分区/机型是否匹配 |
| 其他 `EXCEPTION` | 未预期错误 | 原样回显 `output`，附 staging 路径与命令供排查 |

## 安全与边界

- 本 skill 默认**全自动、不等确认**。`modem`、`persist`、`preloader` 属高风险分区，刷错可能变砖——自动刷入前在回复里明确标注是高风险分区（告知即可，不阻塞流程）。
- 一个 staging 目录只放一个 `<partition>.img`；不要把多个 img 放进同一目录，否则会一次刷多个分区。
- 不要绕过 harness 直接调 `fastboot` / `adb` / SP Flash Tool。
- 本 skill 只处理 **fastboot 可刷的分区镜像**；MTK scatter 整包刷机仍走 `harness-device` 的 device_update 后端。

## 依赖

- **harness CLI**：命令 `harness` 可用，且 `device flash` / `device probe` 存在（`harness --json commands list` 可核对）。这是唯一的功能性依赖。
- **harness 内置刷机后端**：CLI wheel 自带 `flash_toolkit` 与 `fastboot.exe` / `device_update.exe`。缺失时命令会报 `FLASH_TOOLKIT_NOT_AVAILABLE` / `FASTBOOT_TOOL_NOT_FOUND`，用 `harness doctor` 检查、必要时重装 CLI。**不需要**用户单独装 platform-tools / adb / fastboot。
- **运行环境**：Windows + PowerShell（用于 staging 的 `New-Item -ItemType HardLink` / `Copy-Item`）。硬链接要求源 img 与 staging 目录在**同一 NTFS 盘**；跨盘或非 NTFS 时自动回落到复制。
- **设备侧**：设备已连接且可被 adb/fastboot 识别、已 OEM 解锁（或允许用 `--require-oem-unlock` 自动解锁）。
- 本 skill 自身**无脚本、无 Python 包、无网络依赖**，只有一个 `SKILL.md`；所有实际能力来自 harness CLI。

## 反馈

需要"任意分区名 / 任意文件名 / userdata 单刷"等本 skill 覆盖不了的能力时，提交反馈请产品在 CLI 落地单分区命令：

```text
harness --json feedback submit --scenario device-flash --problem-type missing-guidance --title "需要单分区刷入 CLI" --detail "device flash 缺少 --partition/--image 单分区刷入能力"
```
