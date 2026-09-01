# 射频校准 MetaCLI（EasyAdapter 集成）

Console **公共能力 → 校准数据** 通过 BFF 在本机调用 Modem Meta `MetaCLI.exe`，实现与 UI「Update Parameter / Read Write Cal Data」等价的备份与恢复。

**操作 SOP（推荐同事按此执行）**：[SOP.md](./SOP.md)

## 前置条件

- Windows 本机已安装 **Modem Meta**（含 `bin\MetaCLI.exe`）
- 已在 EasyAdapter **配置 → 一键配置表单 → Modem 工具** 填写 **Modem Meta** 安装目录并保存

## 进 META（与 Modem Meta GUI 相同）

| 步骤 | GUI | EasyAdapter |
|------|-----|-------------|
| 1 | 点「连接」 | 点「开始备份/恢复」 |
| 2 | 手机关机 | 手机关机 |
| 3 | 插入 USB | 插入 USB |

MetaCLI init 对齐 GUI 配置（`configs/User_Latest_Settings.txt`）：

```ini
[Connection]
PlatformType = Smart Phone
ComPortType = USB
ComPort = Auto Connection
EnableSwitchModemMode = 1
EnableADBService = 0
```

| 方式 | 说明 |
|------|------|
| **Modem Meta 连接方式（推荐）** | 先启动 MetaCLI 再等插 USB，与 GUI 一致 |
| **已在 META** | 设备已在 META 时，填写 `MediaTek USB Port` 对应 COM 口 |
| **adb reboot meta** | 仅部分工程版有效 |

## 环境变量 / 一键配置

| 来源 | 说明 |
|------|------|
| **一键配置表单 → Modem 工具 → Modem Meta** | **权威配置**（`modem_meta_root`，落盘 `.tahp/unified-config.json`） |
| `MODEM_META_ROOT` | 仅用于打开表单时预填；保存表单后以统一配置为准。未保存时执行备份/恢复会提示去配置 |

射频校准页不再单独填写安装目录；未配置时会提示并引导到「配置 → 一键配置表单」。

默认应填 **META.exe 所在目录**，例如：

```
D:\Tool\MTK\ModemMeta_v10.2412.0.02_transsion_20240428\ModemMeta_v10.2412.0.02_transsion_20240428
```

（该目录下可见 `META.exe`，以及 `bin`、`configs`、`plugins` 等；不要填到某个 `.exe` 文件本身。）

## IMEI 保护（默认排除）

传音等机型有 **IMEI 保护**，META 下不能可靠备份/还原 IMEI。EasyAdapter 默认：

| 模式 | 行为 |
|------|------|
| 备份 | MetaCLI 仍可能日志里出现 `IMEI Failed`（可忽略）；写出后从 ini **剥离 IMEI**；仅 IMEI 失败时任务仍判成功 |
| 恢复 | 使用去掉 IMEI 的临时校准文件再 Download，避免写回 IMEI |

RF（GSM/WCDMA/LTE 等）校准数据不受影响。

## MetaCLI init 键（Modem1Action1）

段名必须是 **`[Modem1Action1]`**（`Modem{MD}Action{槽位}`）。`[ModemAction]` / `[Modem1Action]` 会被忽略。

| 模式 | 键 | 含义 |
|------|-----|------|
| 备份 | `OutputCalibrationDataFilePath` | 从设备上传并保存校准数据 |
| 恢复 | `CalibrationFilePath` | 将校准文件下载到设备 |
| 共用 | `DB = Load from target` | 连接后从目标加载 DB |

Connection 段使用 `PlatformType = Smart Phone`、`ComPort = Auto Connection`（可在页面指定 COM 口）。

## 手工验证

在 Modem Meta 根目录下（PATH 含 `bin` 与 `systems\*\CRT`）：

```bat
MetaCLI.exe -i path\to\generated.ini
```

init 文件由 Console 自动生成于 `.tahp-config/rf-calib-meta/inits/<runId>.ini`。

## 示例 items ini

见 [items.ini.example](./items.ini.example)。**须替换为项目真实 ini**，占位文件无法用于生产。
