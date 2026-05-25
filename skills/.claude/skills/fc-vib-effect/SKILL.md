---
name: fc-vib-effect
description: Func-check skill for vibrator effect trigger via adb cmd vibrator. Use when func-check task needs to verify device can vibrate on connected device.
---

# FC: 马达振动触发检查

## 前置条件
- 设备已通过 adb 连接，可感知振动

## 检查步骤

```bash
adb shell cmd vibrator vibrate 500
```

观察设备是否产生约 500ms 振动。

## Pass / Fail

| 结果 | 条件 |
|------|------|
| Pass | 设备明显振动 |
| Fail | 无振动 / `cmd: error` |

## Fail 后续

- `fc-vib-driver` → `fc-vib-hal` → `fc-vib-he`（逐项排查）
- `fc-vib-rootperm`（节点仍 root:root、init.tp.rc 问题）
- `fc-vib-selinux`（Permission denied 或节点 unlabeled）
- `vib-log-fault`（有日志时）
