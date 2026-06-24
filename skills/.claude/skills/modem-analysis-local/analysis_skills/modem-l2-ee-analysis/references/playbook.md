# L2 ModemEE 分析 Playbook

## 概述

ModemEE（Modem Exception）是 Modem 子系统发生异常时的统称，包括但不限于：
- Modem EE（Modem Exception）
- PhoneCrash
- Assert 失败
- Watchdog 超时
- Subsystem Reset

## 分析流程

### 1. 确认异常类型

从日志中识别 ModemEE 的具体类型：

```
Modem EE:
- "Modem EE" / "Modem Exception"
- err_code 字段
- exception source 字段

PhoneCrash:
- "PhoneCrash"
- 通常伴随 modem 状态变化

Assert:
- "assert" / "ASSERT"
- 断言失败位置和条件

Watchdog:
- "watchdog" / "WDK"
- 超时原因

Subsystem Reset:
- "subsystem reset"
- 复位原因
```

### 2. 提取关键信息

#### 2.1 异常代码（err_code）
```
示例：err_code = 0x00000001
```
异常代码是定位问题的重要线索，不同代码对应不同问题类型。

#### 2.2 异常源（exception source）
```
示例：exception source = MD_WDT
```
异常源指示异常发生的模块或位置。

#### 2.3 时间戳
记录异常发生的精确时间，用于：
- 关联其他日志
- 重建问题时间线
- 分析触发条件

### 3. 数据库查询

使用提取的关键信息查询 ModemEE 数据库：

#### 查询参数
- `ee_type`: 异常类型
- `err_code`: 异常代码
- `exception_source`: 异常源

#### 查询结果处理
- **命中（hit）**: 返回已知解决方案和根因
- **未命中（miss）**: 写入新记录，标记为待分析

### 4. 证据收集

#### 4.1 时间线重建
```
[时间] 异常前事件 A
[时间] 异常前事件 B
[时间] ModemEE 发生
[时间] 异常后恢复事件
```

#### 4.2 关联日志
- radio_log: Modem 侧日志
- main_log: Android 侧日志
- ps.txt / system.txt: 协议栈日志

### 5. 候选根因分析

根据异常类型和证据，分析可能的根因：

#### Modem EE
- 内存访问异常
- 协议栈错误
- 硬件故障

#### PhoneCrash
- Modem 固件崩溃
- 驱动异常
- 电源问题

#### Assert
- 代码逻辑错误
- 状态不一致
- 资源竞争

#### Watchdog
- 死锁
- 长时间阻塞
- 资源耗尽

### 6. 输出结论

将分析结果整理为结构化输出：
- 时间线
- 关键证据
- 候选根因
- 数据库查询结果
- 建议下一步

## 常见问题处理

### Q1: 找不到 err_code
- 检查日志完整性
- 尝试从其他日志文件中查找
- 使用异常类型作为备选查询参数

### Q2: 数据库查询失败
- 检查网络连接
- 验证 API Token
- 记录错误信息，继续本地分析

### Q3: 多个异常同时出现
- 按时间顺序排序
- 确定主要异常和次要异常
- 分别查询数据库

## 参考资料

- MTK ModemEE 分析指南
- 内部 ModemEE 数据库文档
- 历史案例分析报告