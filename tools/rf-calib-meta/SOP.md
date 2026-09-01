# 校准数据备份 / 恢复 SOP

适用页面：EasyAdapter **公共能力 → 校准数据**  
能力说明：本机调用 Modem Meta `MetaCLI.exe`，等价 GUI「Update Parameter / Read Write Cal Data」。

---

## 1. 前置准备（首次必做）

1. 本机 Windows 已安装 **Modem Meta**（目录下可见 `META.exe`，以及 `bin`、`configs`、`plugins` 等）。
2. 打开 **配置 → 一键配置表单 → Modem 工具**，填写 **Modem Meta**：
   - 填 **META.exe 所在目录**，例如：
     `D:\Tool\MTK\ModemMeta_v10.2412.0.02_transsion_20240428\ModemMeta_v10.2412.0.02_transsion_20240428`
   - **不要**填到某个 `.exe` 文件本身。
3. 保存一键配置表单。
4. 回到 **公共能力 → 校准数据**，确认顶部显示「Modem Meta 已配置」。

未配置时页面会提示，并提供「前往一键配置表单」入口。

---

## 2. 备份校准数据

| 步骤 | 操作 |
|------|------|
| 1 | 模式选 **备份（Upload → Save）** |
| 2 | 进 META 方式选 **Modem Meta 连接方式（推荐）** |
| 3 | COM 口保持 `Auto Connection`（一般无需改） |
| 4 | 输出文件可留空（系统自动落盘）；或填 `.ini` 完整路径 |
| 5 | 点 **开始备份**（等同 GUI 点「连接」） |
| 6 | **手机关机** → **插入 USB** |
| 7 | 日志出现 `Connect status: Boot ...` 为正常等待；连上后变为 success 并开始读写 |
| 8 | 等待任务状态 **已完成**，并看到日志末尾 `========== 备份完成 ==========` |

备份文件默认在：`{工程根}/reports/rf-calib-meta/<runId>/calibration_data.ini`  
（勿用 `.tahp-config` 下路径作 MetaCLI 输出——该工具对含点号隐藏目录常写失败。）

---

## 3. 恢复校准数据

| 步骤 | 操作 |
|------|------|
| 1 | 模式选 **恢复（Load → Download）** |
| 2 | 填写 **校准数据文件** 路径（待写入手机的 `.ini`） |
| 3 | 进 META 方式选 **Modem Meta 连接方式（推荐）** |
| 4 | 点 **开始恢复** |
| 5 | **手机关机** → **插入 USB** |
| 6 | 等待任务状态 **已完成**，并看到日志末尾 `========== 恢复完成 ==========` |

### 校准文件来源（参数已丢失时）

- **同配置机备份**：将其它**同配置机器**导出的校准数据写入本机恢复。
- **制造资料共享盘**：按项目/配置从下列路径获取对应校准数据再恢复：

```
\\sh-nas\Dcc\03.项目文件\01.项目文件\01.PCBA项目\制造资料\射频校准文件
```

---

## 4. 如何判断成功 / 可忽略项

**成功（以任务状态为准）：**

- 任务状态为 **已完成 / completed**
- 日志末尾有 **备份完成** 或 **恢复完成**
- 备份：有输出 `.ini`；恢复：日志含 `Write calibration file done` 与各项 `Write Category … Done`

**可忽略（不要当成失败）：**

- 日志中的 `IMEI Failed`、`Backup flow failed`、`Upload and save … failed`（机型 IMEI 保护）
- 行尾若标注「可忽略」，以页面任务状态与「备份/恢复完成」为准

**真正失败：**

- 任务状态为 **失败**，且末尾为 `========== 备份/恢复失败 ==========`
- 仅有 `Connect target success` 后立刻断开、未出现 Upload/Write 过程

---

## 5. 注意事项

1. **勿**同时按住 Vol+ 与 Vol-（会进 Recovery，不是校准 META）。
2. 默认 **不备份 / 不还原 IMEI**（机型保护）；RF（GSM/WCDMA/LTE 等）校准数据正常处理。
3. 无需再打开 Modem Meta GUI；本页已覆盖连接与读写流程。
4. 其它进 META 方式：
   - **已在 META**：设备已在 META 时，可选手动/自动 COM
   - **adb reboot meta**：仅部分工程版有效，非首选

---

## 6. 常见问题

| 现象 | 处理 |
|------|------|
| 提示未配置 Modem Meta | 按第 1 节填写并保存一键配置 |
| 一直停在 `Connect status: Boot ...` | 确认已关机再插 USB；检查线材与驱动 |
| 写成功但任务显示 failed | 重启 BFF 使用最新判定逻辑；看是否有「恢复完成」收尾日志 |
| 想清空历史任务 | 删除 `{工程根}/.tahp-config/rf-calib-meta/` 后刷新页面 |
