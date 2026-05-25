# 关键字与日志示例参考

## 关键词列表

用于日志搜索的关键词（竖线分隔，可直接用于 grep）：

### kernel_log 关键词
```
haptic|vib
```

### main_log / sys_log 关键词
```
vib|haptic|richtap
```

### 高价值定位关键句
```
RichTapVibratorService: aac richtap doVibratorStop fail.
TranVibratorManagerInternal: vibrate:
TranVibratorManagerInternal: can not find patternList.
TranFileUtil: java.io.FileNotFoundException: /tr_product/etc/asset/vibrates/
Vibrator: Vibrator using LED trigger
VibratorManagerService: vibratorservice play he
VibratorManagerService: RichtapCallback  onCallback result:
```

## 关键日志示例与解读

### 1. 马达驱动工作

#### 1.1 艾为（awinic）马达驱动

**日志示例**：
```
//艾为马达驱动接收到上层下发的ioctrl命令
[haptic_hv][1579]richtap_file_unlocked_ioctl: enter stream mode

[haptic_hv][1452]richtap_rtp_work: richtap_rtp_work end richtap play
```

**解读**：艾为马达驱动 (`haptic_hv`) 接收到上层 ioctl 命令并完成 richtap RTP 播放。代表 kernel 层驱动正常工作。

**关注字段**：
- `richtap_file_unlocked_ioctl`：上层下发 ioctl 入口
- `enter stream mode`：进入 stream 模式
- `richtap_rtp_work end richtap play`：RTP 播放结束

#### 1.2 瑞声（AAC）马达驱动

**日志示例**：
```
//接收到上层下发的命令
[104126.794207] [ics_haptic]richtap_file_unlocked_ioctl: richtap ioctl cmd=0x5205, arg=0x64
[104126.794795] [ics_haptic]richtap_file_unlocked_ioctl: richtap ioctl cmd=0x5205, arg=0x64
[104126.795092] [ics_haptic]richtap_file_unlocked_ioctl: richtap ioctl cmd=0x520a, arg=0x0

[104126.796107] [ics_haptic]stream len = 108, retry = 28, fifo_size = 1024

[104126.816696] [ics_haptic]ics_haptic_irq_handler: irq state = 0x08
```

**解读**：瑞声马达驱动 (`ics_haptic`) 接收到 ioctl，进入 stream 流式播放，并产生 IRQ。代表 kernel 层驱动正常工作。

**关注字段**：
- `cmd=0x5205`、`cmd=0x520a`：ioctl 命令字
- `stream len`、`fifo_size`：流式播放的数据长度与 FIFO 大小
- `irq state`：IRQ 状态

### 2. framework 下发振动 HE 流程

#### 2.1 瑞声马达算法

**日志示例**：
```
//下发的he文件名和调用下发he的应用pack
TranVibratorManagerInternal: vibrate: Gesture_back.he, pkg = com.android.systemui, usage = 0
.....
//瑞声算法库接管
RichTapVibrationEffect: RichTapVibrationEffect read token: 503!
//返回到马达managerservice服务
VibratorManagerService: enter  vibrator opPkg = com.android.systemui
//优先级判断是否要忽略
TranVibratorManagerServiceInternal: shouldIgnoreByScale com.android.systemui false

//是不是白名单里面的应用
VibratorManagerService: is 4d vibrator SupportedApp  NO!
VibratorManagerService: is 4d vibrator SupportedApp  NO!
VibratorManagerService: Starting vibrate for vibration 46
VibratorManagerService: Check AppOp mode VIBRATE for uid 10141 and package com.android.systemui returned audio=allow, op=allow
VibratorManagerService: is 4d vibrator SupportedApp  NO!
VibratorManagerService: is 4d vibrator SupportedApp  NO!
VibratorManagerService: before startVibrationLocked
VibratorManagerService: isSupportApp(UID check) yes!

//下发he文件到驱动成功
VibratorManagerService: vibratorservice play he
VibratorManagerService: isSupportApp(UID check) yes!

//下发的振动强度amplitude信息
Vibrator: looper:1,interval:0,amplitude:201,freq:0

//瑞声算法库打印的此次振动信息
AacRichTapConvert: effect_id:12293,strength:100
.......
TranVibratorManagerServiceInternal: onStopTranVibrate com.android.systemui
VibrationPatternListPlayer: mLoopCount = 0
//此次振动的下发结果
VibratorManagerService:  RichtapCallback  onCallback result:1
```

**解读**：瑞声方案下，应用通过 `TranVibratorManagerInternal: vibrate` 下发 HE 文件，经过 `RichTapVibrationEffect`、`VibratorManagerService` 处理，最终 `vibratorservice play he` 下发到驱动，由 `RichtapCallback onCallback result:1` 返回结果。

**关注字段**：
- `vibrate: <文件名>.he, pkg = <pkg>, usage = <usage>`：HE 文件名 / 调用应用 / 用途
- `shouldIgnoreByScale ... false/true`：是否因优先级被忽略
- `is 4d vibrator SupportedApp NO!/yes!`：是否在白名单
- `vibratorservice play he`：实际下发 HE 文件到驱动
- `RichtapCallback onCallback result:1`：下发结果

#### 2.2 艾为马达算法库

**日志示例**：
```
//下发的he文件名和调用下发he的应用pack
TranVibratorManagerInternal: vibrate: Press_dial.he, pkg = com.sh.smart.caller, usage = 18
....
//优先级判断是否要忽略
TranVibratorManagerServiceInternal: shouldIgnoreByScale com.sh.smart.caller false

//是不是白名单里面的应用
VibratorManagerService: is 4d vibrator SupportedApp  yes!  com.sh.smart.caller
RichTapVibratorService: none richtap effect, do nothing!!
VibratorManagerService: Starting vibrate for vibration 38
VibratorManagerService: Check AppOp mode VIBRATE for uid 10133 and package com.sh.smart.caller returned audio=allow, op=allow
VibratorManagerService: is 4d vibrator SupportedApp  yes!  com.sh.smart.caller
VibratorManagerService: is 4d vibrator SupportedApp  yes!  com.sh.smart.caller

//艾为算法库部分
RichTapVibratorService: aac richtap doVibratorStop
RichTapVibratorService: richtap service stop!!
RichTap Compatible: aac_vibra_loop_stopPerformHe enter!
TikTap Compatible: [tiktap_stop][3473]:enter!
TikTap Compatible: [dynamic_effect_stop_callback][3455]:stop now
TikTap Compatible: [dynamic_effect_stop_callback][3467]:stop finished
VibratorManagerService: before startVibrationLocked
VibratorManagerService: is 4d vibrator SupportedApp  yes!  com.sh.smart.caller
.....
//下发振动he文件
VibratorManagerService: vibratorservice play he
VibratorManagerService: is 4d vibrator SupportedApp  yes!  com.sh.smart.caller
Vibrator: looper:1,interval:0,amplitude:201,freq:0

//艾为算法库部分
RichTap Compatible: aac_vibra_loop_post enter!
RichTap Compatible: tiktap support HE_V1.0
TikTap Compatible: [tiktap_start][3252]:loop = 1,
TikTap Compatible: [tiktap_start][3263]:close BEA algo
TikTap Compatible: [tiktap_parse_richtap_data][2656]:tiktap support HE_V1.0
TikTap Compatible: [tiktap_start][3296]:parse finish, size = 2
TikTap Compatible: [tiktap_start][3350]:right motor not ok!
TikTap Compatible: [dynamic_effect_play_callback][1976]:time_interval = 0, t_stamp = 0

//此次振动的下发结果,该次he下发的流程结束
VibratorManagerService:  RichtapCallback  onCallback result:1
```

**解读**：艾为方案下，可观察到 `RichTap Compatible` 与 `TikTap Compatible` 标签的算法库日志（如 `aac_vibra_loop_post`、`tiktap_start`、`tiktap_parse_richtap_data`），完成 HE 解析并下发到驱动。

**关注字段**：
- `RichTap Compatible: aac_vibra_loop_post enter!`：艾为算法接管 HE 处理
- `tiktap support HE_V1.0`：HE 版本协议
- `tiktap_start ... parse finish, size = N`：解析完成的子段数量
- `right motor not ok!`：右马达不可用（需关注是否是物理限制）

### 3. 安卓原生振动（无波形返回）

**日志示例**：
```
//没有如下的日志，不会调用TranVibratorManagerInternal 下发he
#TranVibratorManagerInternal: vibrate: Press_dial.he, pkg = com.sh.smart.caller, usage = 18
.....

//下发的振动的应用
VibratorManager: [SystemVibratorManager vibrate] going to service.vibrate for pkg: com.gallery20
.....
//关闭马达振动
Vibrator: Vibrator off
.....
//使用led trigger振动
Vibrator: Vibrator using LED trigger

//振动完成信息
VibratorManagerService: Finish AppOp mode VIBRATE for uid 10144 and package com.gallery20
```

**解读**：在问题场景对应的应用与时间窗口内，**检索不到** `TranVibratorManagerInternal: vibrate: *.he`，即可判定**未走 Tran HE 下发**，振动走的是安卓原生类通路（不会有 HE 波形返回）。日志中出现的 `SystemVibratorManager vibrate`、`LED trigger` 等为**常见佐证**，有则更确信驱动走的是原生触发链路；**无这两条仍可单凭「无 Tran HE 下发」下结论**，但需在分析报告中注明佐证不足。

**关注字段**：
- **判定核心**：问题窗口内无 `TranVibratorManagerInternal: vibrate: *.he`（且 pkg 与场景对齐）
- `SystemVibratorManager vibrate ... pkg`：原生通路发起的佐证（可选）
- `Vibrator: Vibrator using LED trigger`：LED trigger 驱动的佐证（可选，非唯一依据）

### 4. framework 提示找不到 HE 文件

**日志示例**：
```
//syslog上层下发he
TranVibratorManagerInternal: vibrate: Calculator_keyboard.he, pkg = com.transsion.calculator, usage = 0
....
//mainlog中未找到he文件
TranFileUtil: java.io.FileNotFoundException: /tr_product/etc/asset/vibrates/Calculator_keyboard.he: open failed: ENOENT (No such file or directory)
....
//syslog未找到对应he，下发振动失败
TranVibratorManagerInternal: can not find patternList.
```

**解读**：sys_log 中应用下发 HE 文件成功，但 main_log 中 `TranFileUtil` 抛出 `FileNotFoundException`，HE 文件实际不存在于 `/tr_product/etc/asset/vibrates/` 下，导致 `can not find patternList`，下发失败。

**关注字段**：
- `vibrate: <文件名>.he`：下发的 HE 文件名
- `FileNotFoundException: /tr_product/etc/asset/vibrates/<文件名>.he`：缺失路径
- `can not find patternList.`：下发失败标志

### 5. HAL 层算法库出现问题

**日志示例**：
```
//HAL层算法库异常
RichTapVibratorService: aac richtap doVibratorStop fail.
```

**解读**：HAL 层瑞声算法库异常，无法正常调用 `doVibratorStop`，可能导致全场景无振动。

**关注字段**：
- `RichTapVibratorService: aac richtap doVibratorStop fail.`：HAL 异常的唯一判定特征
