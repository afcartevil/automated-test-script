---
name: sensor-als-autobrightness
description: "MTK-Sensor光感-自动背光: 分析光感运行期间自动背光异常，按候选观察窗口验证光感值与背光值对应关系 | AutomaticBrightnessController/lux/g_data/brightness_val/光感/自动亮度/忽明忽暗/偏亮偏暗 | 当用户报告MTK设备自动亮度忽明忽暗、偏亮偏暗、反应迟钝、不响应环境光时使用。首笔上报异常走sensor-als-first-report"
funcType: "AI故障分析"
category: "驱动"
---

# Sensor光感运行期间自动背光问题分析

## 适用范围

- **问题类型**：Sensor光感运行期间自动背光问题
- **适用场景**：
  - 亮度忽明忽暗、频繁跳变
  - 屏幕明显偏亮或偏暗
  - 自动亮度反应迟钝
  - 完全不响应环境光变化
  - 遮挡光感情况下，亮度无法降低
- **适用芯片平台**：MTK

## 前置条件

分析前需确认以下日志文件可用：

| 日志文件 | 必需性 | 用途 |
|----------|--------|------|
| `mobilelog/APLog_XXXX_XXXX_XXXXXX__X/main_log_X__XXXX_XXXX_XXXXXX` | 必需 | 查看上层下发注册sensor的时间，以及底层SCP侧sensor数据到达HAL层的打印时间 |
| `mobilelog/APLog_XXXX_XXXX_XXXXXX__X/scp_log_X__XXXX_XXXX_XXXXXX` | 必需 | 查看sensor开始enable时间，以及sensor吐数据和上报数据的时间和情况 |
| `mobilelog/APLog_XXXX_XXXX_XXXXXX__X/sys_log_X__XXXX_XXXX_XXXXXX` | 可选 | 查看sensor数据被上层应用比如自动背光、屏幕旋转等接收到sensor数据的时间点 |

## 问题有效性确认

在开始分析前，先确认问题有效性：

拨号 `*#801#` 进入开机工模查看sensor是否校准，如果已经进行校准，证明为手机软件问题。

## 分析原则

- 如果用户能提供问题发生时间，优先分析该时间点附近的一次enable窗口。
- 如果用户不能提供问题发生时间，不能只抓一处 `lux`、`g_data` 或 `brightness_val` 就下结论，必须先枚举所有候选观察窗口。
- 一个观察窗口定义为“本次 `enable: 5` 到下一次 `enable: 5` 之间”的完整运行区间。
- 只允许在同一观察窗口内比较光感值和背光值，禁止跨窗口拼接日志。

## 分析工作流

按以下步骤依次执行分析。用户未提供时间戳时，默认进入“候选观察窗口遍历模式”。

### 步骤1：枚举候选注册事件
- **目标**：找到所有可能与问题相关的自动背光注册事件
- **操作**：在 `main_log` 中搜索关键字 `AutomaticBrightnessController|registerListenerImpl|OriginChannel`，把每一次自动背光注册都记为一个候选起点
- **判断**：
  - 没有光感注册相关打印 -> 问题出在上层，转单给上层
  - 有多次光感注册相关打印 -> 为每次注册记录时间戳、sensor type、下发频率，逐条进入步骤2

### 步骤2：为每个候选注册匹配观察窗口
- **目标**：检查上层注册光感后，底层SCP侧是否正常enable光感，并确定观察窗口
- **操作**：在 `scp_log` 中搜索关键字 `timesync|principal.transceiver enable: 5`，为每个候选注册匹配时间上最近且晚于注册时间的一次 `enable: 5`，再找到下一次 `enable: 5` 作为窗口终点
- **判断**：
  - 某个候选注册没有匹配到enable -> 该候选窗口为通信链路异常候选
  - 某个候选注册匹配到enable -> 记录“本次enable到下次enable”的窗口范围，进入步骤3

### 步骤3：逐个观察窗口检查光感值与屏幕背光对应关系
- **目标**：检查每个观察窗口内，光感值与屏幕背光是否连续和对应
- **操作**：在窗口内的 `scp_log` 中搜索 `lux|g_data` 找光感值，在窗口对应时间范围的 `main_log` 中搜索 `brightness_val` 找背光值
- **判断**：
  - 屏幕背光值随着光感值变大变小同步变化 -> 该观察窗口基本正常，需要确认测试环境是否有问题
  - 屏幕背光不变而光感值变动较大，或屏幕背光变动较大而光感值不变 -> 该观察窗口需要转单给上层自动背光同事确认

### 步骤4：对所有观察窗口排序并输出
- **目标**：避免抓错场景或把不同时间段日志串成一个错误结论
- **操作**：汇总所有观察窗口中的 `lux/g_data/brightness/brightness_val` 变化趋势、防抖表现和异常点，按异常程度排序
- **判断**：
  - 只有一个窗口证据最完整且异常最明显 -> 输出该窗口为主结论
  - 存在多个可疑窗口 -> 输出前3个候选窗口并标注置信度

详细的分析操作说明和日志示例，参阅 [ANALYSIS_STEPS.md](ANALYSIS_STEPS.md)。

## 关键字速查

完整的关键字列表和日志示例，参阅 [KEYWORDS.md](KEYWORDS.md)。

核心关键字：`AutomaticBrightnessController|registerListenerImpl|OriginChannel|timesync|principal.transceiver enable: 5|lux|g_data|brightness_val`

## 输出格式

按以下模板输出分析结论：

### Sensor光感运行期间自动背光问题日志分析报告

#### 基本信息
- **分析时间**：{当前时间}
- **日志来源**：{用户提供的日志文件列表}
- **问题描述**：{用户提供的问题现象}
- **芯片平台**：MTK/待确认

#### 分析过程

**步骤1：枚举候选注册事件**
- 搜索目标：在 `main_log` 中搜索 `AutomaticBrightnessController|registerListenerImpl|OriginChannel`
- 搜索结果：{找到N个候选注册事件/未找到匹配}
- 关键日志：
  ```
  {匹配到的关键日志行}
  ```
- 步骤结论：{候选注册事件数量、各候选的注册时间、sensor type、采样频率}

**步骤2：为每个候选注册匹配观察窗口**
- 搜索目标：在 `scp_log` 中搜索 `timesync|principal.transceiver enable: 5`
- 搜索结果：{已匹配M个观察窗口/未找到匹配}
- 关键日志：
  ```
  {匹配到的关键日志行}
  ```
- 步骤结论：{每个候选注册对应的enable时间、窗口起止时间、是否存在无enable异常}

**步骤3：逐个观察窗口检查光感值与屏幕背光对应关系**
- 搜索目标：在 `scp_log` 中搜索 `lux|g_data`，在 `main_log` 中搜索 `brightness_val`
- 搜索结果：{已完成K个观察窗口分析/未找到匹配}
- 关键日志：
  ```
  {匹配到的关键日志行}
  ```
- 步骤结论：{各观察窗口中光感值与背光值是否一一对应、是否存在防抖导致的合理延迟}

**步骤4：对所有观察窗口排序并输出**
- 搜索目标：汇总所有观察窗口的异常点
- 搜索结果：{输出1个主窗口/输出前3个候选窗口}
- 关键日志：
  ```
  {排序后的窗口摘要}
  ```
- 步骤结论：{主结论对应的窗口、异常点、是否存在多候选并列}

#### 分析结论
- **问题根因**：{校准问题/底层光感上报过慢/自动背光上层逻辑问题/并非光感导致}
- **候选时间窗口**：{主结论对应窗口；如有多个候选则列前3条}
- **证据摘要**：{注册、enable、光感值、背光值的关键日志}
- **置信度**：{高/中/低}
- **建议措施**：{检查校准/优化驱动lux算法/排查上层自动背光策略/确认测试环境}

#### 参考信息
- 常见问题对照：参阅 [COMMON_ISSUES.md](COMMON_ISSUES.md)
- 典型案例参考：参阅 [CASES.md](CASES.md)
