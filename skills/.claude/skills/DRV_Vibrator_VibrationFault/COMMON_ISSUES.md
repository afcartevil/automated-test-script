# 常见问题与原因对照表

| 序号 | 问题现象 | 日志特征 | 根因说明 |
|---|---|---|---|
| 1 | 全场景无振动 / XXX 场景无振动，有波形文件返回 | sys_log 应用下发 HE 文件，但出现 `RichTapVibratorService: aac richtap doVibratorStop fail.` | HAL 层马达服务异常 |
| 2 | XXX 场景无振动但有波形文件返回 | sys_log 调用 `TranVibratorManagerInternal: vibrate: *.he`，main_log 出现 `FileNotFoundException: .../vibrates/*.he`，sys_log 出现 `can not find patternList.` | 振动效果 HE 文件缺失，framework 下发振动失败 |
| 3 | XXX 有振动但无波形文件返回 / 波形返回错误 | 问题场景复现时间窗口内，`sys_log`/`main_log` 均无对应应用的 `TranVibratorManagerInternal: vibrate: *.he`（未走 HE 下发）；可选佐证：`VibratorManager: [SystemVibratorManager vibrate]`、`Vibrator: Vibrator using LED trigger` | 应用场景未适配或未通过 Tran 下发 HE，走的是安卓原生振动（无 HE 波形）；佐证日志有则提高置信度 |

## 详细说明

### 问题1：马达 HAL 层服务异常，无振动，有波形文件返回

**问题描述**：
- XXX 场景无振动
- XXX 无振动，无波形文件返回（或全场景无振动）

**日志特征**：
sys_log 中检测到 JIRA 单提到的应用下发 HE 文件，但是 HAL 层服务异常，导致无法下发到驱动中。

```
//应用下发he文件
TranVibratorManagerInternal: vibrate: SmartButton_longpress.he, pkg = smart button, usage = 18
//HAL层服务异常
RichTapVibratorService: aac richtap doVibratorStop fail.
```

**根因分析**：
HAL 层服务异常。只要出现 `RichTapVibratorService: aac richtap doVibratorStop fail.` 即可判定为 HAL 层马达服务异常，需要检查马达算法库。

**相关 JIRA 参考**：
- LK7OS163-1016
- CM8OS16-262
- CM7OS16-618
- CM7OS16-251

**排查建议**：
- 检查 HAL 层瑞声 / 艾为算法库版本与对应平台是否匹配
- 检查算法库初始化日志是否正常
- 必要时拉算法库同事一起分析

---

### 问题2：马达 HAL 层服务正常、无振动，有波形文件返回

**问题描述**：
- XXX 无振动但有波形文件返回

**日志特征**：
sys_log 中应用下发的单次振动，没有调用 `TranVibratorManagerInternal`（或调用了但抛 `can not find patternList`），mainlog 中本次振动通过的是 `FileNotFoundException`。

```
//没有如下的日志，不会调用TranVibratorManagerInternal 下发he
#TranVibratorManagerInternal: vibrate: Press_dial.he, pkg = com.sh.smart.caller, usage = 18
.....

//下发的振动的应用
VibratorManager: [SystemVibratorManager vibrate] going to service.vibrate for pkg: com.gallery20
mainlog中 该次振动走的

//未找到he文件
TranFileUtil: java.io.FileNotFoundException: /tr_product/etc/asset/vibrates/Calculator_keyboard.he: open failed: ENOENT (No such file or directory)
```

如果没有找到 HE 文件则需要在 SCM 平台上进行配置。

**根因分析**：
振动效果 HE 文件缺失，framework 下发振动失败。

**相关 JIRA 参考**：
- X6855OS16-864
- X6855OS16-868
- X6855OS16-847
- CM8OS16-185

**排查建议**：
- 确认 `/tr_product/etc/asset/vibrates/` 目录下是否存在该 HE 文件
- 在 SCM 平台上配置缺失的 HE 文件
- 提交完成后让对应模块同事回归验证

---

### 问题3：马达 HAL 层服务正常、有振动，无波形文件返回

**问题描述**：
- XXX 有振动但无波形文件返回
- XXX 有振动，但波形文件返回错误

**日志特征**：
在 JIRA 所述场景、对应应用与时间窗口内检索：**未出现** `TranVibratorManagerInternal: vibrate: <*.he>, pkg = <问题应用>`，即可判定**未走 Tran HE 下发**，属于安卓原生振动链路范畴（无 HE 波形返回）。

以下为**可选佐证**（任一条存在可增强结论置信度，不要求同时具备）：

```
VibratorManager: [SystemVibratorManager vibrate] going to service.vibrate for pkg: com.gallery20
```

```
Vibrator: Vibrator using LED trigger
```

**根因分析**：
应用场景未适配或未通过 `TranVibratorManagerInternal` 下发 HE；振动仍可能由 `SystemVibratorManager` 等原生通路触发，故无 HE 波形数据。

**排查建议**：
- 将问题交给对应应用的同事分析
- 应用同事需要在该场景下接入 `TranVibratorManagerInternal.vibrate(...)` 下发 HE
- HE 文件名需与 SCM 平台配置的一致

**说明**：若同一次振动中曾尝试 Tran 下发但因 HE 缺失失败（见问题2：`can not find patternList`、`FileNotFoundException`），则应优先按 **HE 文件缺失** 归类，而非本条「仅原生通路」。
