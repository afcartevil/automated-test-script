# 详细分析步骤

## 分析流程概览

```
[获取日志] -> [日志过滤] -> [分析 sys_log] -> [分析 main_log] -> [输出结论]
                                  |
                  +---------------+---------------+
                  |                               |
            JIRA: 无振动                     JIRA: 无波形返回
                  |                               |
        确认 HAL RichTapVibrator             确认是否走 TranVibrator
        Service 是否正常                      ManagerInternal
                  |                               |
        正常 -> 查 main_log 是否              未走 Tran HE 下发 -> 已可判定安卓原生振动链路
        有 HE 文件                            -> main_log 抓取 LED trigger /
                                              SystemVibratorManager 等佐证（可选）
```

## 步骤1：获取日志

### 目标
拿到与马达振动分析直接相关的有效日志。

### 操作
1. 如果给定的是 JIRA 号、文件夹等非直接 log 文件，先获取日志文件
2. 排除与马达驱动无关的日志文件，只保留串口日志、`kernel_log`、Android 日志等
3. 若存在 `mobilelog` 文件夹，获取该文件夹下的 `kernel_log`、`main_log` 和 `sys_log`
4. 若存在 `mobilelog` 文件夹，开机阶段相关日志存放在子文件夹 `booot_normal` 中

### 判断条件

| 条件 | 结论 | 下一步 |
|---|---|---|
| 获取日志失败 | 无可用日志 | 停止分析 |
| 获取日志成功 | 进入下一步骤 | 进入步骤2 |

## 步骤2：日志过滤

### 目标
筛选马达振动分析的关键日志。

### 操作
1. 在 `kernel_log` 中筛选关键字：`haptic`、`vib`
2. 在 `main_log`、`sys_log` 中筛选关键字：`vib`、`haptic`、`richtap`

### 判断条件

| 条件 | 结论 | 下一步 |
|---|---|---|
| 筛选成功，得到有效片段 | 关键日志已准备 | 进入步骤3 |
| 筛选无任何相关日志 | 日志不包含马达活动 | 反馈日志缺失或问题不可复现 |

## 步骤3：分析 sys_log 日志

### 目标
确认 framework 层是否正确下发 HE 文件、HAL 层是否正常。

### 分支 A：JIRA 标题说的是"无振动"

**操作**：
1. 根据 JIRA 信息找出有问题的下发的 HE 文件名和应用
   - 关键日志：`TranVibratorManagerInternal: vibrate: <文件名>.he, pkg = <pkg>, usage = <usage>`
2. 确认 HAL 层的 `RichTapVibratorService` 服务是否正常
   - 异常关键日志：`RichTapVibratorService: aac richtap doVibratorStop fail.`

**判断条件**：

| 条件 | 结论 | 下一步 |
|---|---|---|
| 出现 `RichTapVibratorService: aac richtap doVibratorStop fail.` | HAL 层马达服务异常 | 输出结论："HAL 层服务异常，需检查马达算法库" |
| 未出现 HAL 异常关键句 | HAL 层正常 | 进入步骤4 分支 A |

### 分支 B：JIRA 标题说的是"无波形返回"

**操作**：
1. 根据 JIRA 信息找出有问题的下发的 HE 文件名和应用
2. 分析应用的本次 HE 下发是否走 `TranVibratorManagerInternal` 调用 HE 文件
   - 走 HE：能搜索到 `TranVibratorManagerInternal: vibrate: <文件名>.he, pkg = <pkg>`
   - 未走 HE：sys_log 中找不到 `TranVibratorManagerInternal: vibrate: *.he`，只能看到 `VibratorManager: [SystemVibratorManager vibrate] going to service.vibrate for pkg: <pkg>`

**判断条件**：

| 条件 | 结论 | 下一步 |
|---|---|---|
| 未调用 `TranVibratorManagerInternal: vibrate: *.he`（问题场景时间窗口内无对应 pkg 的 HE 下发） | 走的是安卓原生振动链路（无 HE 波形） | 进入步骤4 分支 B 抓取佐证日志 |
| 调用了 `TranVibratorManagerInternal: vibrate: *.he` 且出现 `can not find patternList.` | HE 文件下发失败 | 进入步骤4 分支 A 确认 HE 是否缺失 |

### 日志示例

**正常瑞声方案下发**：
```
TranVibratorManagerInternal: vibrate: Gesture_back.he, pkg = com.android.systemui, usage = 0
RichTapVibrationEffect: RichTapVibrationEffect read token: 503!
VibratorManagerService: vibratorservice play he
VibratorManagerService:  RichtapCallback  onCallback result:1
```

**HAL 异常**：
```
RichTapVibratorService: aac richtap doVibratorStop fail.
```

**未走 HE，走原生**：
```
VibratorManager: [SystemVibratorManager vibrate] going to service.vibrate for pkg: com.gallery20
```
（无 `TranVibratorManagerInternal: vibrate: *.he` 日志）

## 步骤4：分析 main_log 日志

### 目标
确认 HE 文件是否存在；对「无波形返回」分支，在已判定未走 Tran HE 下发的前提下，抓取安卓原生链路的佐证日志。

### 分支 A：JIRA 标题说的是"无振动"

**操作**：
1. 检查是否有找不到应用下发 HE 文件的情况
   - 关键日志：`TranFileUtil: java.io.FileNotFoundException: /tr_product/etc/asset/vibrates/<文件名>.he: open failed: ENOENT (No such file or directory)`

**判断条件**：

| 条件 | 结论 | 下一步 |
|---|---|---|
| 出现 `FileNotFoundException: .../vibrates/*.he` | HE 文件缺失 | 输出结论："振动效果 HE 文件缺失，需要在 SCM 平台配置该 HE 文件" |
| 无 FileNotFoundException 且 HAL 正常 | HE 文件存在但仍无振动 | 提示进一步排查驱动 / 算法库 |

### 分支 B：JIRA 标题说的是"无波形返回"

**操作**：
1. 步骤3 若已确认问题场景内无 `TranVibratorManagerInternal: vibrate: *.he`，**结论上已属安卓原生振动链路（无 HE 波形）**，本步主要是补强证据链。
2. 在 `main_log` / `sys_log` 中检索佐证日志（任一条命中均可提高置信度，均缺失亦可仅凭步骤3下结论并在报告中注明）：
   - `VibratorManager: [SystemVibratorManager vibrate] going to service.vibrate for pkg: <pkg>`
   - `Vibrator: Vibrator using LED trigger`

**判断条件**：

| 条件 | 结论 | 下一步 |
|---|---|---|
| 步骤3 已判定无 `TranVibratorManagerInternal: vibrate: *.he`（时间与 pkg 对齐问题场景） | 应用未走 HE 下发，属安卓原生振动通路 | 输出结论："应用场景未适配 / 未通过 Tran 下发 HE"；结合佐证日志标注置信度 |
| 同上，且出现 `SystemVibratorManager vibrate` 或 `Vibrator: Vibrator using LED trigger` | 佐证原生链路 | 在报告中引用对应日志行 |
| 有 `TranVibratorManagerInternal: vibrate: *.he` 且无 `LED trigger` 等原生佐证 | 走 HE 通路但无波形或波形异常 | 检查算法库返回 / `RichtapCallback onCallback result`、HE 是否真正 play 到驱动 |

### 日志示例

**HE 文件缺失**：
```
TranFileUtil: java.io.FileNotFoundException: /tr_product/etc/asset/vibrates/Calculator_keyboard.he: open failed: ENOENT (No such file or directory)
TranVibratorManagerInternal: can not find patternList.
```

**走 LED trigger**：
```
Vibrator: Vibrator off
Vibrator: Vibrator using LED trigger
```
