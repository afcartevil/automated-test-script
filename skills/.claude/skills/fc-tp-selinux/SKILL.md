---
name: fc-tp-selinux
description: Func-check skill for Transsion/MTK TP proc/sysfs SELinux labels and shell read access via adb. Use when func-check needs TP se节点检查、ls -Z proc context、Permission denied on gesture/tp_panel_test/large_area nodes, or unlabeled TP proc before sepolicy port.
funcType: "AI自动化适配"
category: "驱动"
---

# FC: TP SELinux 节点检查

系统化检查 **proc/sysfs 是否存在、SELinux 标签是否正确、adb shell 是否可读**。策略修复走 `tp-adapt-selinux`；本 skill 只做 **现场判定**，不改 sepolicy。

## 前置条件

- `adb devices` 可见设备
- 建议 **userdebug/eng** 或已 `adb root`（部分节点仅 root 可读，见 [nodes.md](nodes.md)）

## 快速检查（推荐）

```powershell
python "$env:USERPROFILE\.cursor\skills\func-check\fc-tp-selinux\scripts\check_tp_selinux.py"
```

脚本输出每节点：`EXISTS` / `MISSING`、`LABEL`（`ls -Z`）、`READ`（`cat` 结果摘要）。见 [../RUN.md](../RUN.md)。

## 手工步骤

本 skill **不查** dmesg/logcat 中的 `avc: denied`；仅以 **`ls -lZ` 标签** 与 **`cat` 是否 Permission denied** 判定。

### 1. 核心 proc 节点：存在 + 标签 + 可读

对 [nodes.md](nodes.md) 中 **必查** 表逐项执行：

```text
adb shell ls -lZ /proc/<node>
adb shell cat /proc/<node>
```

判定：

| 现象 | 结论 |
|------|------|
| `No such file` | **节点未创建** → 驱动/port 问题，非 SELinux |
| `ls -Z` 为 `u:object_r:unlabeled:s0` 或 `default_t` | **未打标** → `tp-adapt-selinux` 补 `genfs_contexts` |
| `cat` 报 `Permission denied` | **SELinux 或 DAC** → `tp-adapt-selinux` |
| 标签含 `proc_gesture_*` / `proc_nvt_selftest` / `proc_tp_*` 等且 shell 可读 | **Pass**（该节点） |

期望 type 与路径对照见 `~/.cursor/skills/adapt/tp-adapt-selinux/REFERENCE.md` §3–§4。

### 2. sysfs（MTK TPD）

```text
adb shell ls -Z /sys/bus/platform/drivers/mtk-tpd/*/
adb shell cat /sys/bus/platform/drivers/mtk-tpd/*/tp_firmware_version
adb shell cat /sys/bus/platform/drivers/mtk-tpd/*/tp_vendor
```

| 现象 | 结论 |
|------|------|
| `Permission denied` | SELinux → `tp-adapt-selinux` |
| 路径不存在 | → `tp-adapt-engineering-sysfs` / 驱动 probe |

### 3. 字符设备（按需）

```text
adb shell ls -lZ /dev/tppolldrv
```

期望 `tppolldrv_device_t`（见 REFERENCE §2）。不存在则跳过（非全项目启用）。

## Pass / Fail

| 级别 | 条件 |
|------|------|
| **Pass** | 必查 proc 节点均存在；标签非 `unlabeled`/`default_t`；`adb shell cat` 无 `Permission denied`（或项目明确仅 HAL 访问的节点在 nodes.md 标为 N/A 且已说明） |
| **Fail** | 任一必查节点 MISSING / 未打标 / shell 读 `Permission denied` 且与功能相关 |

## 输出格式

```
## 功能检查：TP SELinux 节点

**skill**: fc-tp-selinux
**结果**: Pass / Fail

| 节点 | 存在 | SELinux 标签 | shell 读 | 判定 |
|------|------|--------------|----------|------|
| /proc/gesture_function | ... | ... | ... | Pass/Fail/N/A |

### 下一步
```

## Fail 后续

- `tp-adapt-selinux`（打标、`allow`、HAL 域）
- 节点不存在：`tp-adapt-gesture-driver` / `tp-adapt-factory-capacitance` / 对应功能 adapt skill
- 有完整日志且上层报错：`tp-log-gesture` / `tp-log-large-area` 等

## 与其它 skill 分工

| skill | 职责 |
|-------|------|
| **本 skill** | 设备上 **检查** 标签与访问 |
| `tp-adapt-selinux` | 源码侧 **修复** sepolicy |
| `fc-tp-factory` | 工模容值 + 简要 proc 检查；深度 SELinux 用本 skill |

## 附加资源

- 必查节点清单与可选节点：[nodes.md](nodes.md)
