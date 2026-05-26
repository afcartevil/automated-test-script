---
name: fc-vib-rotor
description: Func-check skill for MTK ERM rotor vibrator (regulator-vibrator): dmesg probe, /sys/class/leds/vibrator activate and duration nodes. Use when func-check needs 转子马达、regulator-vibrator、regulator_vibrator probe、转子无振动、ERM vibrator 功能验证。
funcType: "AI自动化适配"
category: "驱动"
---

# FC: 转子马达（regulator-vibrator）功能检查

## 前置条件

- 设备已通过 adb 连接
- 确认为 **转子 ERM**（非 LRA/RichTap）；若仅有 `vibrator_single`/`vibrator_l`/`vibrator_r`，改走 `fc-vib-driver` / `fc-vib-effect`

## 检查步骤（按序）

### 1. 驱动 probe

```bash
adb shell dmesg | grep -iE "regulator.vibrator|regulator_vibrator|vibr_conf|probe success|probe failed" | tail -30
```

### 2. LED 节点与关键属性

```bash
adb shell ls -l /sys/class/leds/vibrator/
```

确认存在 **`duration`**、**`activate`**（部分机型为 **`active`**，下同优先 `activate`）。

`label` 非 `vibrator` 时，将路径中的 `vibrator` 换为 `ls /sys/class/leds/` 下实际目录名。

### 3. 读取当前值

```bash
adb shell cat /sys/class/leds/vibrator/activate
adb shell cat /sys/class/leds/vibrator/duration
```

无 `activate` 时改为 `active`：

```bash
adb shell cat /sys/class/leds/vibrator/active
```

### 4. 触发振动（duration + activate）

先写时长（ms），再拉高使能：

```bash
adb shell "echo 500 > /sys/class/leds/vibrator/duration"
adb shell "echo 1 > /sys/class/leds/vibrator/activate"
```

无 `activate` 时用 `active`：

```bash
adb shell "echo 1 > /sys/class/leds/vibrator/active"
```

观察约 500ms 振感；结束后关闭：

```bash
adb shell "echo 0 > /sys/class/leds/vibrator/activate"
```

（`active` 节点时把 `activate` 换成 `active`。）

### 5. 回读确认（可选）

```bash
adb shell cat /sys/class/leds/vibrator/activate
adb shell cat /sys/class/leds/vibrator/duration
```

`activate`/`active` 写 1 后应有振感；写 0 后停止。

## Pass / Fail

| 结果 | 条件 |
|------|------|
| Pass | dmesg 含 `probe success` 且 `vibr_conf`；存在 `vibrator` 目录且含 `duration` + `activate`（或 `active`）；步骤 4 写成功且有振感 |
| Fail | `probe failed` / 无 regulator dmesg；无 `vibrator` 或缺 `duration`/`activate`；写节点 Permission denied / Invalid argument；写 1 无振感 |

## Fail 后续

| Fail 点 | 路由 |
|---------|------|
| probe / 无 dmesg | `vib-adapt-rotor-driver`（KO/宏控/DTS） |
| `get regulator` / supply | `vib-adapt-rotor-driver` → `vib-adapt-dts-regulator` |
| 无 duration/activate | `vib-adapt-rotor-driver`（驱动/LED 子系统未导出） |
| 节点在但写失败 | `fc-vib-selinux` / `fc-vib-rootperm` |
| probe OK 写成功不振 | `vib-adapt-rotor-driver`（DWS 电压 / OC） |
| 误走 LRA | `fc-vib-hal` → `vib-adapt-projectconfig` |
| 有完整日志 | `jira/vib-log-fault` |
