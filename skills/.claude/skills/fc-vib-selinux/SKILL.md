---
name: fc-vib-selinux
description: Func-check skill for Transsion/MTK LRA/haptic dev and LED sysfs SELinux labels and shell access via adb. Use when func-check needs 马达 se节点检查、vibrator/richtap/haptic Permission denied、unlabeled haptic nodes on aw8697/aac_richtap or vibrator_single rtp sysfs before sepolicy port.
funcType: "AI自动化适配"
category: "驱动"
---

# FC: 马达 SELinux 节点检查

检查 **字符设备** 与 **`/sys/class/leds/vibrator_*`** 关键属性的 SELinux 标签与 adb shell 访问。**不检查** `/vendor/etc/vibrator/` HE 文件权限（HE 是否存在见 `fc-vib-he`）。策略/init 修复见 Fail 后续。

## 前置条件

- `adb devices` 已连接
- 建议 userdebug/eng 或 `adb root`（部分 `rtp`/`reg` 仅 system 可写，shell 只读检查仍有效）
- 马达驱动已加载（可先执行 `fc-vib-driver`）

## 快速检查（推荐）

```powershell
python "$env:USERPROFILE\.cursor\skills\func-check\fc-vib-selinux\scripts\check_vib_selinux.py"
```

单马达 `vibrator_single` 或双马达 `vibrator_l`/`vibrator_r` 均按 [../fc-vib-rootperm/nodes.md](../fc-vib-rootperm/nodes.md) **全表**扫标签。见 [../RUN.md](../RUN.md)。

## 手工步骤

本 skill **不查** dmesg/logcat 中的 `avc: denied`；仅以 **`ls -lZ` 标签** 与 **`cat` 是否 Permission denied** 判定。

### 1. 跑脚本（推荐）

与 rootperm 使用同一节点表；`vibrator_single` 时覆盖 `init.tp.rc` 全部条目。

### 2. 手工抽查

```text
adb shell ls -lZ /dev/aw8697_haptic
adb shell ls -lZ /sys/class/leds/vibrator_single/rtp
adb shell cat /sys/class/leds/vibrator_single/rtp
```

| 现象 | 结论 |
|------|------|
| `unlabeled` / `default_t` | sepolicy 打标 |
| `rtp` Permission denied 且 owner 已是 system | sepolicy `allow` |
| owner 仍 root | `fc-vib-rootperm` |

完整路径表：[nodes.md](nodes.md) → [../fc-vib-rootperm/nodes.md](../fc-vib-rootperm/nodes.md)。

## Pass / Fail

| 级别 | 条件 |
|------|------|
| **Pass** | 全表已存在节点标签非 unlabeled；`rtp` 试读无 Permission denied |
| **Fail** | 任一已存在节点未打标，或 `rtp` 读拒 |

## 输出格式

```
## 功能检查：马达 SELinux 节点

**skill**: fc-vib-selinux
**结果**: Pass / Fail
**方案**: 单马达 / 双马达

| 节点 | 存在 | SELinux 标签 | shell 读 | 判定 |
|------|------|--------------|----------|------|

### 下一步
```

## Fail 后续

- `vib-adapt-haptic-rc`（`init.tp.rc`、`chown`/`chmod`、ODM 拷贝、`vendor.haptic.calibrate.done`）
- sepolicy：在 `vendor/**/sepolicy` 补 `file_contexts` / `genfs_contexts` / `allow`（修复流程可参考 `tp-adapt-selinux`）
- `fc-vib-driver` / `fc-vib-hal`（节点不存在或 HAL）
- `fc-vib-he`（仅 HE 文件缺失，与 SELinux 无关）
- `vib-log-fault`（有完整日志）

## 与其它 skill 分工

| skill | 职责 |
|-------|------|
| **本 skill** | 马达节点 **SELinux 检查** |
| `fc-vib-rootperm` | owner 是否为 **system system** |
| `vib-adapt-haptic-rc` | init 阶段 **修复** DAC |
| `fc-vib-effect` | 能否振起来（功能） |
| `fc-vib-he` | HE 文件是否存在（不查 SELinux） |
| `fc-tp-selinux` | TP 域 proc/sysfs（勿混用） |

## 附加资源

- 必查路径与标签特征：[nodes.md](nodes.md)
