# TP SELinux 功能检查节点清单

期望 **SELinux type** 以仓库 `vendor/transsion/security/sepolicy/tp` 为准；下表与 `adapt/tp-adapt-selinux/REFERENCE.md` §3 对齐，供 `fc-tp-selinux` 判定标签是否「像 TP policy」。

## 必查 proc（双屏项目主屏用 `main_*` 替代）

| proc 路径 | 期望 type（客体） | shell 读说明 |
|-----------|-------------------|--------------|
| `/proc/gesture_function` | `proc_gesture_function` | 应能 `cat` 出手势开关信息 |
| `/proc/gesture_state` | `proc_gesture_state` | 应能 `cat` |
| `/proc/gesture_flag` | `proc_gesture_flag` | 应能 `cat` 或写测试（只读检查用 `cat`） |
| `/proc/tp_panel_test` | `proc_nvt_selftest` | 工模/容值；可能需工模触发后才有内容 |
| `/proc/fingerprint_status` | `proc_fingerprint_status` | FOD 项目必查 |
| `/proc/tp_large_area_mistouch_switch` | `proc_tp_large_area_mistouch_switch` | 大面积灭屏项目必查 |
| `/proc/tp_scene` | `proc_tp_scene` | 存在则查 |

主副屏别名：`main_gesture_function` → `proc_main_gesture_function`，`main_gesture_flag` → `proc_main_gesture_flag` 等。

## 可选 proc（按项目裁剪）

| proc 路径 | 期望 type |
|-----------|-----------|
| `/proc/game_mode` | `proc_game_mode` |
| `/proc/tp_report_rate_switch` | `proc_tp_report_rate_switch` |
| `/proc/border_suppression` | `proc_border_suppression` |
| `/proc/custom_mistouch` | `proc_gesture_flag` 或 `proc_custom_mistouch`（以 genfs 为准） |
| `/proc/tran_edge_level` | `proc_gesture_flag` |
| `/proc/shutdown_flag` | `proc_shutdown_flag` |

节点不存在 → 标 **N/A**，不单独判 Fail。

## sysfs

| 路径模式 | 期望 type（片段） |
|----------|-------------------|
| `/sys/bus/platform/drivers/mtk-tpd/*/tp_firmware_version` | `sysfs_mtk_tpd` / `kernel_lc_sysfs_mtk_tpd` 等 |
| `/sys/bus/platform/drivers/mtk-tpd/*/tp_vendor` | 同上 |

## 设备节点

| 路径 | 期望 type |
|------|-----------|
| `/dev/tppolldrv` | `tppolldrv_device_t` |

## 标签 Fail 特征

- `u:object_r:unlabeled:s0`
- `u:object_r:default_t:s0`
- 与上表 **完全无关** 的 proc 通用类型，或 `cat` 返回 `Permission denied`
