---
funcType: "AI自动化适配"
category: "驱动"
---
﻿---
name: tp-adapt-selinux
description: >-
  Debugs and extends Transsion/MTK TP-related SELinux for proc/sysfs/device
  nodes, TranTP HAL (tran_tp_binder), fhpd, and tppolldrv. Use when AVC denied
  logs mention touch proc nodes, sysfs_mtk_tpd_file, kernel_lc_sysfs_mtk_tpd_file,
  sysfs_tran_touch_file, tran_tp_binder, hal_trantp, fhpd_daemon, tppolldrv,
  vendor.hardware.trantp, or when porting TP sepolicy between projects.
disable-model-invocation: true
---

# Transsion TP 驱动 SELinux 节点调试

## 何时使用

- `avc: denied` 与 `/proc/*` 触控节点、`/sys/*` 触控路径、`/dev/tppolldrv` 或 TranTP / fhpd 设备相关。
- 新 proc/sysfs/字符设备节点在驱动里已创建，但 `adb shell` / `system_server` / APK / `vendor.hardware.trantp` 访问报权限错。
- 从参考项目迁移 TP sepolicy 到新机型（需对照 [REFERENCE.md](REFERENCE.md) 补 `genfs_contexts`、`file_contexts`、类型与 `allow`）。

## 源码树位置（维护 REF 时以仓库为准）

| 分区 | 典型路径（相对 `vendor/transsion/security/sepolicy/tp`） |
|------|----------------------------------------------------------|
| Kernel / proc+sysfs 标签与被调用域 | `kernel/vendor/` |
| HAL / Binder / 设备节点可执行文件标签 | `hal/vendor/` |

合并进整机编译时，这些目录通常由 vendor sepolicy 的 `BOARD_SEPOLICY_DIRS`（或等价变量）引入；若整机未收录，先确认 `Android.bp`/`Android.mk` 是否把该路径加入策略集。

## 调试流程

1. **从日志拿到三元组**
   - `scontext=`（哪个域在访问）、`tcontext=`（目标客体标签）、`tclass=`（file/dir/chr_file 等）、缺失的 `permission=`。
   - 若是 `u:r:untrusted_app:s0` 之类，注意未 `allow` 的域是否需要走 HAL / system_server，或给 `mlstrustedobject` 类型需单独评估风险。

2. **在 REF 里反查**
   - 打开 [REFERENCE.md](REFERENCE.md)，按 **proc/sysfs 路径 → SELinux type** 或 **type → 已 allow 的 domain** 查找是否已有条目。
   - 若 `tcontext` 是 `u:object_r:unlabeled:s0` 或通用类型，说明 **缺 `genfscon` / `file_contexts` 或节点尚未打标**，先补标签再补 `allow`。

3. **按客体类别改文件（Transsion TP 树内惯例）**
   - **proc/sysfs 新类型**：在 `kernel/vendor/file.te` 声明 `type`（带 `fs_type`、`sysfs_type` 或 `proc_type` 等属性，与同文件现有 proc/sysfs 类型一致）。
   - **proc/sysfs 路径打标**：在 `kernel/vendor/genfs_contexts` 增加 `genfscon proc /node_name ...` 或 `genfscon sysfs /path/under/sys ...`。
   - **块/字符设备或固定路径**：在对应 `hal/vendor/file_contexts` 或 `kernel/vendor/file_contexts` 增加 `u:object_r:...`。
   - **谁的访问**：在 `kernel/vendor/system_server.te`、`system_app.te`、`shell.te`、`untrusted_app*.te`、`hal/vendor/*.te` 等与 **当前 scontext 域** 对应的片段中增加 `allow`（保持与同类型现有权限粒度一致）。

4. **HAL / 服务**
   - TranTP：`tran_tp_binder` 对 proc/sysfs 的权限多在 `kernel/vendor/tpaidl.te` 与 `hal/vendor/hal_trantp.te`；Binder 与 `system_server` 在 `hal/vendor/system_server.te`。
   - Rain/THP 等：`fhpd_daemon` 在 `hal/vendor/fhpd_daemon.te`，设备类型在 `hal/vendor/device.te`，exec/设备路径在 `hal/vendor/file_contexts`。

5. **验证**
   - 全编或单编 sepolicy 后刷机；复现场景下确认 `avc` 消失。可临时 `setenforce 0` 仅作对比，**不能**作为发布修复。

6. **维护 REF**
   - 新增或修改节点时，同步更新 [REFERENCE.md](REFERENCE.md) 中的表格条目（路径、type、主要 domain、源文件），便于下一项目复用。

## 输出给用户的结论格式

用简短条目列出：**拒绝日志摘要**、**根因（未打标 / 缺 allow / 域不匹配）**、**建议修改的文件与规则要点**、**安全注意点**（扩大 `untrusted_app` 或 `shell` 写权限需确认）。

## 延伸阅读

- 完整路径 ↔ 类型 ↔ 域 ↔ 源文件明细：[REFERENCE.md](REFERENCE.md)
