# 常见问题与原因对照表

| 序号 | 问题现象 | 日志特征 | 根因说明 |
|------|----------|----------|----------|
| 1 | 大面积灭屏失效、大面积不灭屏 | 亮屏过程中 `tp_state_recovery 233:pocket state = 0` | 亮屏时上层未写口袋模式节点，TP驱动中断无法上报大面积键值 |
| 2 | 大面积灭屏失效、大面积不灭屏 | 亮屏过程中 `pocket state = 1`，但kernel log中无 `Large area touch down` | 驱动或固件未适配大面积防误触特性：<br>· **B1 驱动侧**：归一化框架/vendor驱动未开启或未导入大面积上报路径<br>· **B2 固件侧**：TP固件未上报大面积事件给驱动，驱动中断收不到对应事件 |
| 3 | 铜柱测试概率不灭屏、大面积灭屏概率性失效 | TP驱动正常加载，`pocket state = 1`，存在 `Large area touch down` 上报 | TP固件效果不佳，无法准确识别大面积场景 |

## 详细说明

### 问题1：上层未通知底层进入口袋模式，锁屏界面大面积灭屏失效

**问题描述**：大面积灭屏失效、大面积不灭屏

**日志特征**：

```
[tran_touch-INFO]nvt_disp_notifier_callback 103:[main]: drm notify tp resume start
.....
// 亮屏过程中，上层未将口袋模式节点置1
[tran_touch-INFO]tp_state_recovery 233:pocket state = 0
........
[tran_touch-INFO]dsp_event_callback 276:[main] drm notify tp resume end
```

**根因分析**：亮屏时上层未写口袋模式节点，导致未进入口袋模式，TP驱动中断无法上报大面积键值。

**排查建议**：
- 反馈display/policy上层模块，核查亮屏流程中口袋模式节点写入逻辑
- 检查锁屏判定逻辑是否正确触发口袋模式

**关联JIRA**：
- X6873OS162-15
- X6876OS16-30

### 问题2：上层通知底层进入口袋模式，TP驱动无法上报大面积键值

**问题描述**：上层口袋模式节点已置1，但kernel log中观察不到任何一次 `Large area touch down` 上报。

> **重要提示**：**仅凭日志中没有 `Large area touch down` 输出，不能直接断定为驱动未适配**。驱动未适配（B1）与固件未适配（B2）都会表现为相同的日志缺失现象，需要双向排查。

**日志特征**：

```
[tran_touch-INFO]nvt_disp_notifier_callback 103:[main]: drm notify tp resume start
.....
// 亮屏过程中，上层将口袋模式节点置1
[tran_touch-INFO]tp_state_recovery 233:pocket state = 1
........
[tran_touch-INFO]dsp_event_callback 276:[main] drm notify tp resume end
.......
kernel log中未发现 "Large area touch down" 等日志输出
```

**根因分析**（两种可能并存，需逐一排除）：

#### B1：驱动侧未适配
TP的归一化框架或vendor驱动未开启大面积防误触特性，驱动中断处理函数缺少对应键值上报路径。常见形态：
- 归一化框架/项目配置中 `LARGE_AREA`、`POCKET_MODE` 等宏未使能
- vendor驱动未实现 `*_pocket_state_report` / Large area 上报分支
- 部分项目可能存在 dts/dws 中口袋模式属性缺失

#### B2：固件侧未适配
TP固件未上报大面积事件给驱动，因此驱动中断里收不到对应事件，自然就没有 `Large area touch down` 输出。常见形态：
- 当前TP固件版本未使能大面积识别特性
- TP固件能力与驱动期望不匹配（驱动等待某种事件，但固件未发出）

**排查建议**：

1. **先查驱动侧（成本低、可自查）**：
   - 检查归一化框架中大面积防误触特性的宏控开关是否打开
   - 检查vendor驱动是否实现并使能 `pocket_state_report` 相关分支
   - 检查项目对应 dts/dws 的口袋模式相关属性
2. **驱动侧确认无问题后查固件侧**：
   - 联系TP vendor确认当前固件版本是否支持大面积上报
   - 切换/升级到已知支持大面积特性的固件版本复测
   - 必要时让vendor开启TP调试模式，抓取TP内部寄存器/固件side log，确认固件是否产生大面积事件

**关联JIRA**：
- X6895BOS16-563
- X6895OS162-531
- X6840OS16-1549
- X6840OS16-178
- KN4OS16-718

### 问题3：固件问题，导致大面积灭屏概率失效

**问题描述**：铜柱测试概率不灭屏、大面积灭屏概率性失效。

**日志特征**：

```
[tran_touch-INFO]nvt_disp_notifier_callback 103:[main]: drm notify tp resume start
.....
// 亮屏过程中，上层将口袋模式节点置1
[tran_touch-INFO]tp_state_recovery 233:pocket state = 1
........
[tran_touch-INFO]dsp_event_callback 276:[main] drm notify tp resume end

kernel log中发现了 "Large area touch down" 等日志输出
```

> 到这一步TP的驱动分析已经完成了，驱动侧的上报链路是通的，只是效果不佳，无法准确识别大面积，这个就需要TP固件进行优化了。

**根因分析**：TP固件效果不佳，导致手掌按到屏幕上时无法准确识别到大面积场景。

**排查建议**：
- 若从JIRA单信息中确认问题为概率性出现，大概率是固件效果问题
- 转给 **TP_Effect 模块**，由影像同事介入分析固件效果
