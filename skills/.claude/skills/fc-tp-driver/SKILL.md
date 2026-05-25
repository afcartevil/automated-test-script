---
name: fc-tp-driver
description: Func-check skill for TP driver probe status via adb dmesg. Use when func-check task needs to verify TP IC driver loaded successfully on connected MTK device.
---

# FC: TP 驱动加载检查

## 前置条件
- 设备已通过 adb 连接
- 建议重启后或问题复现后立即执行

## 检查步骤

```bash
adb shell dmesg | grep -iE "fts|gtp|nvt|ili|chsc|tcm|synaptics|atmel" | tail -30
```

## Pass / Fail

| 结果 | 条件 |
|------|------|
| Pass | 含 `probe success` / `probe OK` / `registered` / IC 型号 |
| Fail | `probe failed` / `no such device` / 无匹配输出 |

## Fail 后续

- `tp-log-touch`（有日志时）
- `tp-adapt-dws-pin`（probe fail，查 GPIO/interrupt）
