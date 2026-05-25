---
name: fc-aikey-event
description: Func-check skill for AI key event reporting via adb getevent. Use when func-check task needs to verify KEY_F26/605 key events on connected device.
---

# FC: AI Key 按键上报检查

## 前置条件
- 设备已通过 adb 连接

## 检查步骤

1. 执行：
   ```bash
   adb shell getevent -l
   ```
2. 按下 AI key，观察输出

## Pass / Fail

| 结果 | 条件 |
|------|------|
| Pass | 输出 `KEY_F26` 或 `KEY (0x259)` 的 DOWN/UP（605 = 0x259） |
| Fail | 无任何键值输出 |

## Fail 后续

- `fc-aikey-dts`（先查 DTS/IRQ）
- `aikey-adapt-dts`
