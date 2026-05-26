---
name: fc-tp-gesture
description: Func-check skill for TP gesture proc node via adb. Use when func-check task needs to verify gesture_function node on connected device.
funcType: "AI自动化适配"
category: "驱动"
---

# FC: TP 手势节点检查

## 前置条件
- 设备已通过 adb 连接

## 检查步骤

```bash
adb shell cat /proc/gesture_function
```

## Pass / Fail

| 结果 | 条件 |
|------|------|
| Pass | 输出手势使能状态，如 `gesture enable: 1` 或手势 ID 列表 |
| Fail | `No such file or directory` / 空输出 |

## Fail 后续

- `tp-adapt-gesture-driver`
- `tp-log-gesture`（有日志时）
