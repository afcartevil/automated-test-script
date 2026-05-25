# 详细分析步骤

## 分析流程概览

```
[获取日志] → [日志过滤] → [分析kernel日志] → [分析main/sys日志] → [输出根因]
                              │
                              ├── pocket state = 0  → 根因A（上层未写入口袋模式）
                              ├── pocket state = 1
                              │     ├── 无 Large area touch down  → 根因B（驱动或固件未适配大面积特性）
                              │     │       ├── B1：驱动侧未开启/未导入大面积特性
                              │     │       └── B2：固件未上报大面积事件给驱动
                              │     └── 有 Large area touch down + 概率失效 → 根因C（固件效果不佳）
                              └── 概率性场景 → 转 TP_Effect 模块
```

## 步骤1：获取日志

### 目标

获取分析所需的 `kernel_log`、`main_log`（可选 `sys_log`），排除与TP领域无关的日志文件，只保留串口日志、Kernel日志、Android日志等。

### 操作

1. 如果给定的是JIRA号、文件夹等非直接Log文件，先获取日志文件
2. 若存在 `mobilelog` 文件夹，则读取该文件夹下的 `kernel_log` 与 `main_log`
3. 若问题发生在开机阶段，进入 `mobilelog/boot_normal` 子目录读取对应日志

### 判断条件

| 条件 | 结论 | 下一步 |
|------|------|--------|
| 获取日志失败 | 缺失分析必需日志 | 停止分析，反馈日志缺失 |
| 获取日志成功 | 日志可用 | 进入步骤2 |

## 步骤2：日志过滤

### 目标

筛选TP大面积灭屏相关的关键日志，缩小后续分析范围。

### 操作

1. 在 `kernel_log` 中筛选关键字：`touch`、`fts`、`cts`、`gtp`、`nvt`、`chsc`、`ilitek`、`tcm`、`large area`
2. 在 `main_log` / `sys_log` 中筛选关键字：`keycode`（也可补充 `KeyguardGesture`）

> 其中 `large area` 关键字可直接命中驱动上报大面积键值的日志行（如 `Large area touch down`），有助于快速判定驱动侧上报链路是否通畅。

### 判断条件

| 条件 | 结论 | 下一步 |
|------|------|--------|
| 筛选完成 | 关键日志已聚焦 | 进入步骤3 |

## 步骤3：分析kernel日志

### 目标

依次确认三个事实：
1. TP驱动是否正常工作
2. 亮屏时TP驱动的口袋模式节点是否被写为 `1`
3. TP驱动是否有大面积键值上报日志

### 操作

#### 3.1 检查TP驱动加载

搜索：

```
modprobe: [tran_touch-INFO]tran_tp_get_boot_mode 199:bootmode is 0
flod_main_device_init
match_tp_controller
load main controller vendor:xxx ic:xxx success
```

#### 3.2 检查亮屏过程中的口袋模式节点

搜索 `drm notify tp resume start` ~ `drm notify tp resume end` 之间的：

```
tp_state_recovery 233:pocket state = ?
```

#### 3.3 检查大面积键值上报

搜索：

```
Large area touch down
```

> 上报函数名随vendor不同而不同，例如 `fts_pocket_state_report`、`nvt_pocket_state_report`、`tcm_pocket_state_report` 等，统一以日志正文 `Large area touch down` 为准。

### 判断条件

| 条件 | 结论 | 下一步 |
|------|------|--------|
| TP驱动未加载 / 匹配IC失败 | TP驱动异常 | 优先排查驱动加载链路（超出本SOP范围） |
| 亮屏时 `pocket state = 0` | 上层未通知底层进入口袋模式 | 输出 **根因A**，参阅 [COMMON_ISSUES.md 问题1](COMMON_ISSUES.md) |
| 亮屏时 `pocket state = 1` 且无 `Large area touch down` | 驱动或固件未适配大面积防误触特性（B1驱动 / B2固件，二者均可导致） | 输出 **根因B**，按下方"B1/B2 区分思路"双向排查，参阅 [COMMON_ISSUES.md 问题2](COMMON_ISSUES.md) |
| 亮屏时 `pocket state = 1` 且存在 `Large area touch down`，但用户反馈概率失效 | TP驱动链路通畅，效果不佳 | 输出 **根因C**，转TP_Effect模块，参阅 [COMMON_ISSUES.md 问题3](COMMON_ISSUES.md) |
| 亮屏时 `pocket state = 1` 且存在 `Large area touch down`，必现失效 | 驱动侧已正常，问题可能在上层 | 进入步骤4 |

### B1/B2 区分思路（无 `Large area touch down` 时进一步定位）

> 日志中没有 `Large area touch down` 输出，不一定是驱动未适配，也可能是固件未适配。需结合代码 + 固件两个方向排查。

| 排查方向 | 检查内容 | 判定 |
|----------|----------|------|
| **B1 驱动侧** | 1. 项目宏控/feature开关：归一化框架与vendor驱动中 `LARGE_AREA` / `POCKET_MODE` 相关宏是否使能<br>2. vendor驱动中是否实现 `*_pocket_state_report` / `Large area touch down` 输出路径<br>3. dts/dws中口袋模式相关属性是否齐全 | 若代码侧未实现/宏未开 → **B1：驱动侧未适配** |
| **B2 固件侧** | 1. 联系TP vendor确认当前固件版本是否支持大面积上报<br>2. 切换/升级固件版本复测<br>3. 必要时让vendor开启TP调试模式抓取TP内部寄存器，确认固件是否产生大面积事件 | 若驱动代码完备但固件版本不支持/未使能 → **B2：固件侧未适配** |

> **结论建议**：在日志只能体现"驱动没收到大面积事件"的事实时，先按 B1 排查驱动代码与宏控（结论快、自查成本低），若驱动侧确认完备再按 B2 联系TP vendor确认固件能力。

### 日志示例

**正常情况（链路通畅）**：

```
[tran_touch-INFO]nvt_disp_notifier_callback 103:[main]: drm notify tp resume start
[tran_touch-INFO]tp_state_recovery 233:pocket state = 1
[tran_touch-INFO]dsp_event_callback 276:[main] drm notify tp resume end
......
[FTS_TS/I]fts_pocket_state_report:Large area touch down
```

**异常情况A（上层未写入口袋模式）**：

```
[tran_touch-INFO]nvt_disp_notifier_callback 103:[main]: drm notify tp resume start
[tran_touch-INFO]tp_state_recovery 233:pocket state = 0
[tran_touch-INFO]dsp_event_callback 276:[main] drm notify tp resume end
```

**异常情况B（驱动未开启大面积特性）**：

```
[tran_touch-INFO]nvt_disp_notifier_callback 103:[main]: drm notify tp resume start
[tran_touch-INFO]tp_state_recovery 233:pocket state = 1
[tran_touch-INFO]dsp_event_callback 276:[main] drm notify tp resume end
......
（kernel log中未发现 "Large area touch down" 输出）
```

## 步骤4：分析main、sys日志

### 目标

检查上层是否成功接收到大面积灭屏的键值并执行灭屏动作。

### 操作

1. 搜索 framework 接收键值：

   ```
   WindowManager: interceptKeyBeforeQueueing keyCode = 358
   ```

2. 搜索上层策略处理：

   ```
   TranPhoneWindowManagerImpl: interceptKeyTq keycode=358
   ```

### 判断条件

| 条件 | 结论 | 下一步 |
|------|------|--------|
| 上层未收到 `keyCode = 358` | 驱动上报链路异常（或键值映射错误） | 回到步骤3复查 |
| 上层收到 `keyCode = 358` 但未灭屏 | 上层策略处理异常 | 反馈framework/policy侧分析 |
| 上层收到 `keyCode = 358` 且灭屏 | 链路完整、功能正常 | 检查问题复现条件 |

### 日志示例

**正常情况**：

```
WindowManager: interceptKeyBeforeQueueing keyCode = 358, down = true, policyFlags = 570425344, isWakeKey = false, isKeyGestureTriggered = false
TranPhoneWindowManagerImpl: interceptKeyTq keycode=358 down = true
```
