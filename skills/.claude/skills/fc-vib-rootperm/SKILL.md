---
name: fc-vib-rootperm
description: Func-check skill for Transsion/MTK LRA haptic init.tp.rc node owner via adb ls -l. Verifies chown system system on tppolldrv, aw8697_haptic, aac_richtap_5f, and full vibrator_single sysfs list. Use when func-check needs 马达节点 owner、线性马达 chown、init.tp.rc 权限未生效, or vibrator_single nodes still root:root.
---

# FC: 马达节点 owner 检查（system system）

核对触觉马达相关节点的 **属主/属组是否为 `system system`**（`init.tp.rc` 中 `chown system system` 是否生效）。**本 skill 以 owner 为准**；权限位（如 0666）仅作参考，不单独判 Fail。

## 前置条件

- `adb devices` 已连接
- 开机完成后再查（`chown` 多在 `vendor.all.modules.ready` 或 `sys.boot_completed` 之后）
- 建议先 `fc-vib-driver` 确认节点已创建

## 快速检查（推荐）

```powershell
python "$env:USERPROFILE\.cursor\skills\func-check\fc-vib-rootperm\scripts\check_vib_rootperm.py"
```

见 [../RUN.md](../RUN.md)。

## 手工步骤

### 1. 确认方案

```text
adb shell ls /sys/class/leds/
```

- **`vibrator_single`**：单马达，全表检查 `vibrator_single/*`。
- **`vibrator_l` / `vibrator_r`**：双马达，属性名与单马达相同，对 **存在的每一路** 各跑全表（见 [nodes.md](nodes.md)）。

### 2. 判定

对每个**已存在**节点 `adb shell ls -l <path>`，第 3、4 列须为 **`system`** **`system`**。

| owner:group | 判定 |
|-------------|------|
| `system system` | Pass |
| 其它 | **Fail** |

`chmod 0666` 三处（两 dev + `rtp`）mode 异常仅 **WARN**。

### 3. 辅助：init.tp.rc（可选）

```text
adb shell ls -l /odm/etc/init/init.tp.rc
```

节点仍为 `root root` 且 rc 缺失 → 优先 `vib-adapt-haptic-rc`。

### 4. 与 SELinux 区分

属主已是 `system system` 仍 `Permission denied` → `fc-vib-selinux`（只看标签与 shell 读，不查 avc 日志）。

## Pass / Fail

| 结果 | 条件 |
|------|------|
| **Pass** | 当前方案（single 或 dual）下，已存在的 [nodes.md](nodes.md) 全表节点均为 **system system** |
| **Fail** | 任一已存在节点 owner/group 不是 **system system** |

## 输出格式

```
## 功能检查：马达节点 owner

**skill**: fc-vib-rootperm
**结果**: Pass / Fail

| 路径 | owner:group | 判定 |
|------|-------------|------|

### 下一步
```

## Fail 后续

- `vib-adapt-haptic-rc`（`chown system system`、路径、`init.tp.rc` 拷贝与触发时机）
- `fc-vib-selinux`（owner 已是 system 仍拒访）
- `fc-vib-driver`（节点不存在）

## 与其它 skill 分工

| skill | 职责 |
|-------|------|
| **本 skill** | **owner/group 是否为 system system** |
| `fc-vib-selinux` | SELinux 标签（同节点表） |
| `vib-adapt-haptic-rc` | 源码侧补 `chown` |

## 附加资源

- 必查路径：[nodes.md](nodes.md)
