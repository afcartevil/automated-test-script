---
name: "DRV_TP_LargeArea"
description: "针对MTK平台锁屏界面TP大面积灭屏（口袋模式防误触）功能失效问题（包含大面积灭屏失效、大面积不灭屏、铜柱测试概率不灭屏等场景），通过分析kernel_log中TP驱动加载、口袋模式节点写入、大面积键值上报，以及main_log/sys_log中framework接收上层按键处理，定位问题根因并输出分析结论。当用户提供包含touch/fts/cts/gtp/nvt/chsc/ilitek/tcm/large area/KeyguardGesture/keycode等关键字的日志，且JIRA问题模块为(Drv) TP并涉及锁屏大面积灭屏失效时使用。"
funcType: "AI故障分析"
category: "驱动"
---

# MTK锁屏界面TP大面积灭屏失效问题分析

## 适用范围

- **问题类型**：锁屏界面TP大面积灭屏（口袋模式防误触）功能失效
- **适用场景**：
  - 锁屏界面手掌拍到屏幕上无法触发大面积灭屏
  - 大面积不灭屏 / 大面积灭屏概率性失效
  - 铜柱测试概率不灭屏
- **适用芯片平台**：MTK
- **问题有效性确认方法**：MTK平台、有相关log、JIRA问题模块为(Drv) TP

## 前置条件

分析前需确认以下日志文件可用：

| 日志文件 | 必需性 | 用途 |
|----------|--------|------|
| kernel_log | 必需 | 检查TP驱动是否正常工作、确定亮屏时是否支持锁屏界面的大面积灭屏、确定大面积键值上报是否正常 |
| main_log | 必需 | 检查上报的键值是否被上层接收处理 |
| sys_log | 可选 | 辅助检查上层按键处理流程 |

> 若给定的是JIRA单号、文件夹等非直接Log文件，先获取日志文件。若存在 `mobilelog` 文件夹，则获取该文件夹下的 `kernel_log` 与 `main_log`；开机阶段相关日志存放在子文件夹 `boot_normal` 中。

## 分析工作流

按以下步骤依次执行分析：

### 步骤1：获取日志
- **目标**：获取分析所需的kernel_log、main_log（可选sys_log），排除与TP领域无关的日志文件
- **操作**：
  - 若输入为JIRA号/文件夹，定位 `mobilelog` 下的 `kernel_log` 与 `main_log`
  - 若开机阶段相关，关注 `boot_normal` 子目录
- **判断**：
  - 获取日志失败 → 停止分析，提示日志缺失
  - 获取日志成功 → 进入步骤2

### 步骤2：日志过滤
- **目标**：筛选TP大面积灭屏相关关键日志
- **操作**：
  - 在 `kernel_log` 中筛选关键字：`touch|fts|cts|gtp|nvt|chsc|ilitek|tcm|large area`
  - 在 `main_log` / `sys_log` 中筛选关键字：`keycode`（以及 `KeyguardGesture`）
- **判断**：筛选成功 → 进入步骤3

### 步骤3：分析kernel日志
- **目标**：判断TP驱动是否正常工作、口袋模式节点是否被写入、大面积键值是否被上报
- **操作**：
  1. 检查TP驱动加载是否成功（`load main controller vendor:xxx ic:xxx success`）
  2. 检查亮屏过程中口袋模式节点是否被写为1：搜索 `tp_state_recovery` 中的 `pocket state` 值
  3. 检查驱动是否上报大面积键值：搜索 `Large area touch down` 等日志输出
- **判断**：
  - 亮屏时 `pocket state = 0` → **根因A：上层未写入口袋模式节点**，进入【常见问题1】
  - 亮屏时 `pocket state = 1` 且无 `Large area touch down` → **根因B：驱动或固件未适配大面积防误触特性**（驱动侧未开启宏控/未导入特性 **或** 固件未上报大面积事件），需进一步在驱动代码/宏控配置与固件版本两个方向排查，进入【常见问题2】
  - 亮屏时 `pocket state = 1` 且存在 `Large area touch down` → 进入步骤4
  - 概率性出现，TP驱动链路通畅 → **根因C：TP固件效果不佳**，转TP_Effect模块，进入【常见问题3】

> **重要提示**：日志中不存在 `Large area touch down` 输出，**不能直接断定为驱动未适配**。固件如果未上报对应事件给驱动，驱动中断里就收不到大面积事件，自然也不会输出该日志。需结合驱动代码/项目宏控配置与固件版本同时排查，必要时联系TP vendor确认固件是否使能了大面积上报能力。

### 步骤4：分析main、sys日志
- **目标**：检查上层是否成功接收到大面积灭屏的键值并执行灭屏
- **操作**：搜索 `interceptKeyBeforeQueueing keyCode = 358` 与 `TranPhoneWindowManagerImpl: interceptKeyTq keycode=358`
- **判断**：
  - 上层未收到 358 键值 → 驱动上报链路异常，需结合步骤3进一步分析
  - 上层收到 358 键值但未灭屏 → 上层处理逻辑异常，需结合framework策略分析

详细的分析操作说明和日志示例，参阅 [ANALYSIS_STEPS.md](ANALYSIS_STEPS.md)。

## 关键字速查

完整的关键字列表和日志示例，参阅 [KEYWORDS.md](KEYWORDS.md)。

- kernel_log 核心关键字：`touch|fts|cts|gtp|nvt|chsc|ilitek|tcm|large area`
- main_log/sys_log 核心关键字：`KeyguardGesture|keycode`

## 输出格式

按以下模板输出分析结论：

### MTK锁屏界面TP大面积灭屏失效问题 日志分析报告

#### 基本信息
- **分析时间**：{当前时间}
- **日志来源**：{用户提供的日志文件列表}
- **问题描述**：{用户描述的问题现象}
- **芯片平台**：MTK
- **JIRA模块**：(Drv) TP

#### 分析过程

**步骤1：获取日志**
- 搜索目标：定位 kernel_log / main_log
- 搜索结果：{找到 / 未找到}
- 步骤结论：{日志可用 / 日志缺失}

**步骤2：日志过滤**
- 搜索目标：在kernel_log中筛选 `touch|fts|cts|gtp|nvt|chsc|ilitek|tcm|large area`，在main_log中筛选 `keycode`
- 搜索结果：{命中条数}
- 步骤结论：{筛选完成}

**步骤3：分析kernel日志**
- 搜索目标：TP驱动加载状态、`pocket state` 值、`Large area touch down`
- 搜索结果：
  ```
  {匹配到的关键日志行}
  ```
- 步骤结论：{TP驱动加载成功/失败；口袋模式节点为0/1；驱动是否上报大面积键值}

**步骤4：分析main、sys日志**
- 搜索目标：`interceptKeyBeforeQueueing keyCode = 358` / `interceptKeyTq keycode=358`
- 搜索结果：
  ```
  {匹配到的关键日志行}
  ```
- 步骤结论：{上层收到/未收到大面积键值；上层是否触发灭屏}

#### 分析结论
- **问题根因**：{选择 A/B/C 之一或自定义根因}
  - A：上层未通知底层进入口袋模式，导致驱动中断无法上报大面积键值
  - B：驱动或固件未适配大面积防误触特性（需进一步确认是 **B1-驱动侧未开启/未导入** 还是 **B2-固件未上报大面积事件**）
  - C：TP固件效果不佳，无法准确识别大面积场景（概率性问题）
- **证据摘要**：{支持结论的关键日志行列表}
- **置信度**：{高/中/低，基于证据充分程度}
- **建议措施**：
  - 根因A → 反馈display/policy上层模块，确认亮屏流程中口袋模式节点写入逻辑
  - 根因B → 双向排查：
    - B1：检查TP驱动归一化框架与vendor驱动是否实现并使能大面积防误触特性、对应宏控/feature开关是否打开
    - B2：联系TP vendor确认当前固件版本是否使能大面积上报能力，必要时切换/升级固件版本复测
  - 根因C → 转TP_Effect模块，由影像同事进行固件效果优化

#### 参考信息
- 常见问题对照：参阅 [COMMON_ISSUES.md](COMMON_ISSUES.md)
- 典型案例参考：参阅 [CASES.md](CASES.md)
- 关键字与日志示例：参阅 [KEYWORDS.md](KEYWORDS.md)
- 详细分析步骤：参阅 [ANALYSIS_STEPS.md](ANALYSIS_STEPS.md)
