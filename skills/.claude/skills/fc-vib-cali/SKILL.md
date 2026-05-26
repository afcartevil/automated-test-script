---
name: fc-vib-cali
description: Func-check skill for LRA factory calibration properties via adb getprop. Use when func-check task needs to verify ro.vendor.tran.midtest.lra.cali.min/max on connected device.
funcType: "AI自动化适配"
category: "驱动"
---

# FC: 马达工模校准属性检查

## 前置条件
- 设备已通过 adb 连接

## 检查步骤

```bash
adb shell getprop ro.vendor.tran.midtest.lra.cali.min
adb shell getprop ro.vendor.tran.midtest.lra.cali.max
```

## Pass / Fail

| 结果 | 条件 |
|------|------|
| Pass | 均输出数值，如 `170` / `230` |
| Fail | 任一为空 |

## Fail 后续

- `vib-adapt-factory-cali`
