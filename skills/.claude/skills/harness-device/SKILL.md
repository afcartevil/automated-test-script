---
name: harness-device
description: harness 本地设备操作子 skill。覆盖 device flash（本地 ROM 刷机，支持 device_update / fastboot 双后端）、device smoke（WCN 冒烟测试）、device probe（adb/fastboot 设备探测）、device remount（受控 root/remount/disable-verity，MTK 支持传音 OEM 解锁）和 apk sign（公司在线签名接口，默认归一签名）。不要让 Agent 直接拼 adb / fastboot / SP Flash Tool / 原始 shell。
version: 2.1.17
---

# Harness Device 子 skill

刷机、设备探测、remount、冒烟、APK 签名是 CLI 可直接解决的问题：优先运行 `harness device ...` / `harness apk sign ...`，不要先 `knowledge route/search`。APK 签名默认走公司在线签名接口和归一签名，不要要求用户提供本地 keystore。只有后端识别失败、用户询问刷机规则/分层布局、或 CLI 返回需要解释的错误时才读 references 或查知识库。

## 何时进入

- 用户要刷本地 ROM、冒烟测试、查 adb / fastboot 设备状态；
- 要 `adb root` / `adb remount` / `adb disable-verity`；
- 要给 APK 重新签名。

## 命令速查

```text
# 设备探测（adb + fastboot）
harness --json device probe
harness --json device probe --sn <sn>

# 本地刷机（dry-run 先看 plan）
harness --json device flash --sn <sn> --rom-path <rom> --dry-run
harness --json device flash --sn <sn> --rom-path <rom>

# WCN 冒烟
harness --json device smoke --sn <sn> --wifi-ssid QR123 --wifi-password 12345678

# Remount（先 dry-run）
harness device remount --sn <sn> --dry-run
harness --json device remount --sn <sn> --dry-run
harness --json device remount --sn <sn> --disable-verity --reboot
harness --json device remount --sn <sn> --tran-oem-unlock --disable-verity --reboot --dry-run

# APK 签名
harness --json apk sign --input app.apk
harness --json apk sign --input app.apk --key-type lineage --key-name plt_tecno_a16release
harness --json apk sign --backend local --input app.apk --keystore release.jks --alias release --ks-pass pass:<password>
```

参数完整契约用 `harness commands describe device flash` 等查询。

## 拉 ROM 到本地（关键：先问用户路径）

`harness device flash --rom-path` 需要的是**本地路径**。当 ROM 来自上海 / 重庆版本服务器（UNC `\\10.150.98.24\...` 或 `\\10.205.4.40\...`），Agent 在 `Copy-Item` 之前**必须先与用户确认本地落点目录**，原因：

- ROM zip 常 ≥ 5 GB，整机镜像目录可达 20 GB。
- 用户的 C: 盘经常紧张（系统 + AppData + IDE 缓存），默认 `%TEMP%` 或 `%USERPROFILE%` 都在 C:，**不能默默拉到 C:**。
- 不同同事偏好不同盘符，没法靠默认值兜底。

Agent 操作顺序：

1. 用 `Get-PSDrive -PSProvider FileSystem` 查所有本地盘的 Used / Free，过滤出剩余空间 ≥ ROM 大小 × 1.5 的盘，向用户报告候选；C: 永远不作为默认首选。
2. 用 AskUserQuestion / 等价机制让用户选目录或自填（例：`D:\roms\<project>\<version>`、`E:\flash\X6878-TEST-...`）。给一个明确的"默认建议"是允许的，但默认值**必须基于剩余空间最大的非 C 盘**，不能是 `%TEMP%`。
3. 用户确认后再 `Copy-Item -Force <unc> <local-dir>`；多文件时 `robocopy` 更稳并显示进度。
4. 复制完成后用 `harness --json device flash --rom-path <local-dir>` 接刷机。

复制/拉取 ROM 只是把版本服务器产物 staging 到用户确认的本地目录，**不要自动解压 ROM zip 或镜像包**。`device flash` 支持 zip 文件或已解包目录，并会按布局识别 `device_update` / `fastboot` 后端；默认解压会额外占用数十 GB、污染用户目录，还可能破坏原始包结构。只有用户明确要求“解压/检查包内容/提取镜像”时，才先说明目标目录和空间风险，再执行对应动作。

如果 ROM 来源来自 `harness version-server find-latest` / `+latest` 的 JSON，复制源优先用 `preferred_download_path`。这个字段由 CLI 的 SMB RTT 探测在上海/重庆路径之间选择；不是固定重庆优先，上海同事 RTT 更近时会选上海。没有该字段时再向用户确认使用 `source_path/version_path` 还是 `release_path/chongqing_path`，不要自行默认选 `version_path` 拉 40GB+ ROM。`source_path` 仍主要用于 `.pipe/pack.json` / rdtool 配置发现。

不能省的反例：

- ❌ Agent 直接选 `%TEMP%\<rom-name>` 然后开始 `Copy-Item`，复制中途 C: 满 → 系统不稳定。
- ❌ Agent 选 `%USERPROFILE%\Downloads`：还是 C:。
- ❌ Agent 选 `D:\` 但没问用户，覆盖了用户在 `D:\` 的其他文件。
- ❌ Agent 复制 ROM 后主动 `Expand-Archive` / `tar -xf` / `unzip`，把 5 GB+ zip 展开成数十 GB 目录。

如果用户已经在 env 配置了 `HARNESS_ROM_STAGE_DIR`（约定大于配置），可以直接用并向用户报告这个路径，不必每次问。

## 刷机后端识别

`--backend` 取值：
- `auto`（默认）：根据 ROM 布局识别
  - scatter XML 存在 → `device_update`
  - 含 `android-info.txt` / `flash_all.bat` 或 `boot.img`/`super.img` 等 → `fastboot`
  - 未知布局直接报错，不会胡乱试
- `device_update`：强制 MTK scatter 刷机
- `fastboot`：强制标准 fastboot 刷机

`user` variant 刷机后需要手工完成 OOBE 并重新开启 USB 调试，否则后续 adb 自动化无法继续。

## 边界

- 真实 remount 会改变设备状态。MTK 设备遇到 bootloader 锁导致 remount 失败时，先用 `harness --json device remount --sn <sn> --tran-oem-unlock --disable-verity --reboot --dry-run` 给用户确认；非 dry-run 必须加 `--confirm-data-wipe`。不要手拼 adb / fastboot；该流程包含 `fastboot erase userdata`，会清除用户数据。
- APK 签名默认使用公司在线接口：上海 `10.150.98.147:8081`，重庆/深圳 `10.205.0.34:8081`；默认参数是归一签名 `key_type=a16-release`、`key_name=platform`。只有用户明确要求本地离线签名时才用 `--backend local` 和 keystore 参数，密码不要在回答中明文回显。
- ROM 同时有顶层 scatter + 市场 overlay 时，优先用 `--rom-path <rom>/<market>` 或 `--stage <market>`，不要轻易传 `--acknowledge-base-layout`。
- 不要绕过 harness 直接调 `adb` / `fastboot` / SP Flash Tool / `apksigner`。

参数来源、后端识别规则、内置工具路径、分层市场布局和返回结构见 `references/local-flash.md`。

## 反馈

```text
harness --json feedback create --scenario device-smoke --problem-type bad-result \
  --tool "harness device flash" --detail "..."
```
