---
name: fc-tp-factory
description: Func-check skill for TP factory panel test and SELinux node access via adb. Use when func-check task needs to verify /proc/tp_panel_test and proc node permissions.
funcType: "AI自动化适配"
category: "驱动"
---

# FC: TP 工模/容值检查

## 前置条件
- 设备已通过 adb 连接

## 检查步骤

```bash
adb shell cat /proc/tp_panel_test
adb shell ls -Z /proc/gesture_function
adb shell ls -Z /proc/tp_panel_test
```

## Pass / Fail

| 检查项 | Pass | Fail |
|--------|------|------|
| tp_panel_test | 含 `PASS` / 容值数据 / 测试结果 | 节点不存在 / `FAIL` / 空 |
| SELinux 节点 | 节点存在，context 含 tpd 相关标签 | `Permission denied` / 节点不存在 |

## Fail 后续

- `tp-adapt-factory-capacitance`（容值项缺失）
- `fc-tp-selinux`（SELinux 标签/读权限专项排查）
- `tp-adapt-selinux`（sepolicy 修复）
