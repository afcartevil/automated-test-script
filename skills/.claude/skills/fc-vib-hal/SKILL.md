---
name: fc-vib-hal
description: Func-check skill for RichTap vibrator HAL service process via adb. Use when func-check task needs to verify RichTapVibratorService is running.
funcType: "AI自动化适配"
category: "驱动"
---

# FC: 马达 HAL 服务检查

## 前置条件
- 设备已通过 adb 连接

## 检查步骤

```bash
adb shell ps -A | grep -iE "RichTap|richtap|vibrator"
```

## Pass / Fail

| 结果 | 条件 |
|------|------|
| Pass | 输出含 `RichTapVibratorService` 或相关 vibrator 服务进程 |
| Fail | 无相关进程 |

## Fail 后续

- `vib-adapt-haptic-rc`（服务未启动）
- `fc-vib-selinux`（HAL 访问 haptic/richtap 节点 Permission denied）
- `vib-log-fault`（有 sys_log 时）
