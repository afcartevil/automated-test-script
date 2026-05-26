---
name: fc-vib-he
description: Func-check skill for vibrator HE waveform files via adb. Use when func-check task needs to verify .he files exist under /vendor/etc/vibrator/.
funcType: "AI自动化适配"
category: "驱动"
---

# FC: 马达 HE 文件检查

## 前置条件
- 设备已通过 adb 连接

## 检查步骤

```bash
adb shell ls /vendor/etc/vibrator/
```

## Pass / Fail

| 结果 | 条件 |
|------|------|
| Pass | 列出 `.he` 文件，如 `click.he` / `tick.he` |
| Fail | 目录不存在 / 空列表 |

## Fail 后续

- `vib-adapt-projectconfig`（HE 未打包）
- `vib-log-fault`（应用层 HE 路径问题）
