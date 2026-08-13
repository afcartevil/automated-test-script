---
name: fc-tp-sysfs
description: Func-check skill for TP firmware version and vendor sysfs nodes via adb. Use when func-check task needs to verify tp_firmware_version and tp_vendor on connected device.
funcType: "AI自动化适配"
category: "驱动"
---

# FC: TP sysfs 信息检查

## 前置条件
- 设备已通过 adb 连接

## 检查步骤

```bash
adb shell cat /sys/bus/platform/drivers/mtk-tpd/*/tp_firmware_version
adb shell cat /sys/bus/platform/drivers/mtk-tpd/*/tp_vendor
```

## Pass / Fail

| 检查项 | Pass | Fail |
|--------|------|------|
| tp_firmware_version | 输出版本号，如 `0x01` / `FW_VER: 0x12` | 空 / `UNKNOWN` / 节点不存在 |
| tp_vendor | 输出厂商名，如 `FocalTech` / `Goodix` | 空 / `UNKNOWN` / 节点不存在 |

## Fail 后续

- `fc-tp-factory-info`（工模信息页需核对 IC/模组/BV 格式与 BOM）
- `tp-adapt-engineering-sysfs`
- `tp-adapt-selinux`（Permission denied 时）
