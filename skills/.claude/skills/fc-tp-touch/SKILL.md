---
name: fc-tp-touch
description: Func-check skill for TP touch event reporting via adb getevent. Use when func-check task needs to verify ABS_MT touch coordinates on connected device.
funcType: "AI自动化适配"
category: "驱动"
---

# FC: TP 触摸上报检查

## 前置条件
- 设备已通过 adb 连接，屏幕可交互

## 检查步骤

1. 执行：
   ```bash
   adb shell getevent -l
   ```
2. 在屏幕上滑动手指，观察输出

## Pass / Fail

| 结果 | 条件 |
|------|------|
| Pass | 输出 `ABS_MT_POSITION_X`、`ABS_MT_POSITION_Y`、`EV_SYN` |
| Fail | 无事件输出，或只有 KEY 事件无 ABS_MT |

## Fail 后续

- `fc-tp-driver`（先确认驱动是否加载）
- `tp-log-touch` / `tp-adapt-dws-pin`
