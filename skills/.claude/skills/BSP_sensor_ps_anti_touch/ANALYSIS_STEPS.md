# 详细分析步骤

## 分析流程概览

本SOP用于确认物理距感状态上报异常是否导致口袋防误触模式异常。核心流程如下：

1. 先在 `scp_log` 中搜索 `anti_touch_ultrasound`，排除超声距感项目。
2. 在 `main_log` 中枚举所有上层开始监听防误触的时间点，建立候选监听窗口。
3. 在每个监听窗口内，分析 `scp_log` 中的口袋状态上报是否正常。
4. 对于底层已上报进入口袋模式的窗口，再去 `main_log` 检查上层是否收到状态、是否展示UI。
5. 最终输出表格化证据链，并判断问题属于sensor模块、上层模块还是audio模块。

## 问题分类

需要先根据用户描述明确问题属于哪一类：

1. 应该触发防误触界面，但没有触发
2. 不应该触发防误触界面，但是触发了

两类问题共用同一套日志链路，但判断分支不同。

## 步骤0：有效性确认

### 目标

确认问题是否属于sensor物理距感领域。

### 操作

1. 打开 `mobilelog/APLog_XXXX_XXXX_XXXXXX__X/scp_log_X__XXXX_XXXX_XXXXXX`。
2. 搜索关键字：`anti_touch_ultrasound`。

### 判断条件

| 条件 | 结论 | 下一步 |
|------|------|--------|
| 存在 `anti_touch_ultrasound` | 这是超声距感防误触项目，不属于sensor领域 | 转audio模块 |
| 不存在 `anti_touch_ultrasound` | 这是物理距感防误触问题 | 进入步骤1 |

## 步骤1：枚举候选监听窗口

### 目标

找到所有上层开始监听防误触的时间点。

### 操作

1. 打开 `mobilelog/APLog_XXXX_XXXX_XXXXXX__X/main_log_X__XXXX_XXXX_XXXXXX`。
2. 如果是背部物理距感，搜索 `Sensor name="pdb"`。
3. 如果是正面物理距感，搜索 `Sensor name="anti_touch"`。
4. 记录每一个监听时间戳。
5. 以“某次监听开始到下一次监听开始”为一个候选监听窗口。

### 日志示例

```text
背部物理距感:
05-14 14:52:02.790464 13417 13417 D SensorManager: registerListenerImpl sensor={Sensor name="pdb", vendor="transsion", version=1, type=65634, maxRange=65535.0, resolution=1.0, power=0.001, minDelay=0} pid=13417 uid=1000 pkgname=com.transsion.microintelligence listener=g4.a@10134d6

正面物理距感：
05-14 14:17:20.931538 10237 10237 D SensorManager: registerListenerImpl sensor={Sensor name="anti_touch", vendor="mtk", version=1, type=65624, maxRange=65535.0, resolution=1.0, power=0.001, minDelay=0} pid=10237 uid=1000 pkgname=com.transsion.microintelligence listener=g4.a@6972883
```

### 判断条件

| 条件 | 结论 | 下一步 |
|------|------|--------|
| 不存在相关监听打印 | 上层没有正常监听防误触状态 | 输出结论并转上层 |
| 存在相关监听打印 | 建立一个或多个候选监听窗口 | 进入步骤2 |

## 步骤2：检查每个监听窗口内的SCP口袋状态上报

### 目标

检查底层是否在每个监听窗口内正常上报口袋状态。

### 操作

1. 打开 `mobilelog/APLog_XXXX_XXXX_XXXXXX__X/scp_log_X__XXXX_XXXX_XXXXXX`。
2. 背部物理距感搜索：`timesync|pdb:pre and now state`。
3. 正面物理距感搜索：`timesync|anti_touch: anti pre and now state`。
4. 利用 `timesync` 将SCP时间换算到安卓时间，通常 `main_log` 时间约等于 `scp_log` 时间加8小时。
5. 将每一笔 `0 1` 或 `1 0` 上报归入对应的监听窗口。
6. 对每个监听窗口分别判断是否存在进入口袋模式的 `0 1`。

### 日志示例

```text
背部物理距感：
[1120.434](0)[0] deputy.pdb:pre and now state is 0 1
//14:56:22.372016-(1120.790-1120.434)=14:56:22.016016时刻上报了进入口袋模式（1）的消息
[1120.790](0)[0] principal.timesync scp 1120790165749 host 1130464123450 offset 9676208547 tick 1120790 sched 1130480720463 android 05-14 06:56:22.372016
//此时SCP侧时间为06:56:22.372016，对应main_log里面时间：14:56:22.372016
[1121.387](0)[0] deputy.pdb:pre and now state is 1 0
//14:56:22.372016+(1121.387-1120.790)=14:56:22.969016时刻上报了退出口袋模式（0）的消息

正面物理距感：
[11330.495](0) deputy.anti_touch: anti pre and now state is 1 0
[11331.114](0) deputy.anti_touch: anti pre and now state is 0 1
[11331.180](0) principal.timesync scp 11331180209554 host 11339235964787 offset 8057788079 tick 11331180 sched 2475845551848 android 05-14 06:18:07.131226
```

### 判断条件

#### 分支A：不应该触发防误触界面，但是触发了

| 条件 | 结论 | 下一步 |
|------|------|--------|
| 监听窗口内存在 `0 1` | 底层识别到靠近状态，优先怀疑未校准、结构问题或底噪高 | 输出sensor侧结论 |
| 监听窗口内不存在 `0 1` | 底层未上报进入口袋模式状态 | 输出结论并转上层口袋防误触模块 |

#### 分支B：应该触发防误触界面，但没有触发

| 条件 | 结论 | 下一步 |
|------|------|--------|
| 监听窗口内不存在 `0 1` | 底层未识别到靠近，优先怀疑未校准、测试手法或硬件问题 | 输出sensor侧结论 |
| 监听窗口内存在 `0 1` | 底层已正常上报靠近状态 | 进入步骤3 |

## 步骤3：检查上层接收状态与UI展示

### 目标

逐笔检查底层上报的进入口袋模式事件，是否被上层接收并显示防误触界面。

### 操作

1. 回到 `mobilelog/APLog_XXXX_XXXX_XXXXXX__X/main_log_X__XXXX_XXXX_XXXXXX`。
2. 搜索关键字：`onSensorChanged distance|SHOW_INADVERTENTVIEW`。
3. 对于每一笔 `pdb:pre and now state is 0 1` 或 `anti pre and now state is 0 1`：
   - 查找对应时间点附近的 `KeyguardGestureManager: onSensorChanged distance:1.0`
   - 再查找后续是否存在 `KeyguardGestureManager: SHOW_INADVERTENTVIEW, VISIBLE`
4. 为每一笔底层上报建立完整证据链。

### 日志示例

```text
在scp_log中
[1120.434](0)[0] deputy.pdb:pre and now state is 0 1
//14:56:22.372016-(1120.790-1120.434)=14:56:22.016016时刻底层上报了进入口袋模式（1）的消息

在main_log中
05-14 14:56:22.035678 14104 14104 I KeyguardGestureManager: onSensorChanged distance:1.0  ,mProximityThreshold: 0.0  ,isTpTouch: true ,mNeedCreate: true
//main_log中在14:56:22.035678时刻收到了底层上报的状态1

05-14 14:56:22.313170 14104 14104 I KeyguardGestureManager: SHOW_INADVERTENTVIEW, VISIBLE
//main_log中在14:56:22.313170时刻开始显示防误触页面
```

### 判断条件

| 条件 | 结论 | 下一步 |
|------|------|--------|
| 上层没有收到上报的口袋状态 | 底层上报失败或链路传输异常 | 输出sensor链路结论 |
| 上层收到了口袋状态，但没有 `SHOW_INADVERTENTVIEW, VISIBLE` | 上层口袋模式逻辑异常 | 输出结论并转上层 |
| 上层收到了状态，且有 `SHOW_INADVERTENTVIEW, VISIBLE` | 功能正常 | 输出结论并建议规范测试 |

## 步骤4：输出结论与证据表

### 目标

用表格汇总所有关键证据并输出最终结论。

### 操作

1. 汇总每个监听窗口中的所有关键事件：
   - 监听开始时间
   - SCP状态内容
   - SCP换算后的安卓时间
   - main_log接收状态日志与时间
   - UI显示日志与时间
2. 输出表格，覆盖所有关键状态上报。
3. 如果属于sensor模块问题，补充输出最可能的3个原因、解决方案和自查方案。
4. 如果不属于sensor模块，明确说明应转到audio模块或上层模块。

### 证据表最少应包含的列

| 监听窗口 | SCP状态内容 | SCP时间 | main_log接收状态 | 接收时间 | UI状态 | UI时间 | 结论 |
|----------|-------------|---------|------------------|----------|--------|--------|------|
| 窗口1 | 0 1 | 14:56:22.016016 | onSensorChanged distance:1.0 | 14:56:22.035678 | SHOW_INADVERTENTVIEW, VISIBLE | 14:56:22.313170 | 功能正常 |

## 结论输出要点

- 所有结论必须给出证据链说明。
- 必须输出一个表格，包含所有SCP上报状态、防误触状态内容、时间戳，以及一一对应的 `main_log` 接收日志和UI日志。
- 如果是sensor模块问题，必须输出最可能的3个原因，并给出解决方案和自查方案。
- 如果不是sensor模块问题，必须说明需要转到对应模块进行分析。
