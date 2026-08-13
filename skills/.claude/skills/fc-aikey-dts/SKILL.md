---
name: fc-aikey-dts
description: Func-check skill for AI key DTS node, IRQ and gpio-keys device via adb. Use when func-check task needs to verify linux,code 605 and gpio-keys registration.
funcType: "AI自动化适配"
category: "驱动"
---

# FC: AI Key DTS/设备节点检查

## 前置条件
- 设备已通过 adb 连接

## 检查步骤

```bash
adb shell cat /proc/device-tree/gpio-keys/ai-key/linux,code | xxd
adb shell cat /proc/interrupts | grep -iE "gpio|ai.key|605"
adb shell cat /proc/bus/input/devices | grep -A5 "gpio-keys"
```

## Pass / Fail

| 检查项 | Pass | Fail |
|--------|------|------|
| linux,code | 十六进制 `00000259`（605） | 节点不存在 / 值错误 |
| IRQ | 存在对应中断行 | 无中断行 |
| gpio-keys | 设备已注册 | 无 gpio-keys 设备 |

## Fail 后续

- `aikey-adapt-dts`
