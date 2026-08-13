---
name: fc-vib-driver
description: Func-check skill for vibrator/haptic driver probe via adb dmesg. Use when func-check task needs to verify haptic driver loaded on connected device.
funcType: "AI自动化适配"
category: "驱动"
---

# FC: 马达驱动加载检查

## 前置条件
- 设备已通过 adb 连接

## 检查步骤

```bash
adb shell dmesg | grep -iE "haptic|richtap|cs40l|awinic|aw869" | tail -20
```

## Pass / Fail

| 结果 | 条件 |
|------|------|
| Pass | 含 `probe success` / `initialized` / IC 型号 |
| Fail | `probe failed` / 无输出 |

## Fail 后续

- `vib-adapt-dts-regulator`（供电问题）
- `vib-adapt-projectconfig`（宏控未开）
