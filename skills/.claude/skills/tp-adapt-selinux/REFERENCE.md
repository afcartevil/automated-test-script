# Transsion TP sepolicy 参考表（可维护）

说明：以下内容自 `vendor/transsion/security/sepolicy/tp` 抽取。新机迁移时请 **以当前仓库为准** 做 diff；`genfs_contexts` 中含大量 **项目相关** 的 sysfs wakeup 路径，新机型需按实际 DTS/输入设备路径增删。

---

## 1. 目录与职责

| 路径 | 作用 |
|------|------|
| `kernel/vendor/file.te` | 声明 TP 相关 `proc_*`、`sysfs_*` 等类型 |
| `kernel/vendor/genfs_contexts` | `proc`/`sysfs` 路径 → `u:object_r:<type>:s0` |
| `kernel/vendor/file_contexts` | 字符设备路径（如 `tppolldrv`）标签 |
| `kernel/vendor/tpaidl.te` | `tran_tp_binder` 对 proc/sysfs 等的 `allow` |
| `kernel/vendor/tppolldrv.te` | `tppolldrv` 设备类型；`tran_tp_binder` 对 `tppolldrv_device_t` |
| `kernel/vendor/system_server.te` | `system_server` 访问 TP proc/设备及 fhpd 设备等 |
| `kernel/vendor/system_app.te` | `system_app` 对各类 TP proc 节点 |
| `kernel/vendor/shell.te` | `shell`（adb）读部分 proc/sysfs |
| `kernel/vendor/platform_app.te` | 部分 gesture 相关 proc |
| `kernel/vendor/untrusted_app.te` | 厂商调试 APK / THP 等受限开放 |
| `kernel/vendor/radio.te` / `meta_tst.te` | 读 MTK TPD sysfs |
| `kernel/vendor/property_contexts` | 触控相关只读属性（示例：`ro.vendor.tran_mistouch_support`） |
| `hal/vendor/trantp_binder.te` | `tran_tp_binder` 域、HAL 注册、`add_service` |
| `hal/vendor/hal_trantp.te` | HAL 客户端与 `tran_tp_binder` 对部分 sysfs/proc |
| `hal/vendor/system_server.te` | `system_server` 与 `tran_tp_binder` Binder |
| `hal/vendor/service_contexts` | `vendor.hardware.trantp.ITrantp/default` → `tran_tp_binder_service` |
| `hal/vendor/hwservice.te` / `vndservice.te` | 服务类型声明 |
| `hal/vendor/device.te` | `fhpd_*`、`thp_demo_device` 等 dev 类型 |
| `hal/vendor/file_contexts` | TranTP 可执行文件、fhpd、Rain 相关 `/dev/*` |
| `hal/vendor/fhpd_daemon.te` | `fhpd_daemon` 权限集 |
| `hal/vendor/dumpstate.te` | `dumpstate` 调用 `tran_tp_binder` |

---

## 2. 字符设备与 HAL 可执行文件（`file_contexts`）

| 路径模式 | SELinux type | 文件 |
|----------|--------------|------|
| `/dev/tppolldrv` | `tppolldrv_device_t` | `kernel/vendor/file_contexts` |
| `/dev/key_shoulder0`、`/dev/key_shoulder1` | `tppolldrv_device_t` | `kernel/vendor/file_contexts` |
| `/(system|vendor)/bin/hw/vendor.hardware.trantp-service`（policy 中为正则） | `tran_tp_binder_exec` | `hal/vendor/file_contexts` |
| `/odm/bin/fhpd` | `fhpd_daemon_exec` | `hal/vendor/file_contexts` |
| `/dev/fhp_input` | `fhpd_input_device` | `hal/vendor/file_contexts` |
| `/dev/fhp_ft` | `fhpd_ft_device` | `hal/vendor/file_contexts` |
| `/dev/sm_thp_raw` | `thp_demo_device` | `hal/vendor/file_contexts` |

---

## 3. `/proc` 节点 → 类型（`genfs_contexts` + `file.te`）

表中 **SELinux type** 与 `genfscon proc /xxx` 对应；部分历史行复用同一 type（以仓库实际 `genfs_contexts` 为准）。

| proc 相对路径 | SELinux type（客体） |
|---------------|----------------------|
| `/gesture_function` | `proc_gesture_function` |
| `/gesture_state` | `proc_gesture_state` |
| `/ag_state` | `proc_ag_state` |
| `/gtp_leather_mode` | `proc_gtp_leather_mode` |
| `/pen_switch_state` | `proc_pen_switch_state` |
| `/ftxxxx-debug` | `proc_ftxxxx-debug` |
| `/NVTflash` | `proc_NVTflash` |
| `/NVTSPI` | `proc_NVTSPI` |
| `/report_rate_switch` | `proc_report_rate_switch` |
| `/custom_mistouch` | `proc_gesture_flag`（注：独立类型 `proc_custom_mistouch` 在 `file.te`，以 genfs 为准） |
| `/nvt_selftest`、`/tp_panel_test` | `proc_nvt_selftest` |
| `/main_selftest` | `proc_main_selftest` |
| `/border_suppression` | `proc_border_suppression` |
| `/main_border_suppression` | `proc_main_border_suppression` |
| `/fingerprint_status` | `proc_fingerprint_status` |
| `/main_gesture_function` | `proc_main_gesture_function` |
| `/main_gesture_state` | `proc_main_gesture_state` |
| `/gesture_flag` | `proc_gesture_flag` |
| `/main_gesture_flag` | `proc_main_gesture_flag` |
| `/game_state` | `proc_gesture_flag` |
| `/main_game_state` | `proc_main_gesture_flag` |
| `/tran_edge_level` | `proc_gesture_flag` |
| `/tran_vib_vendor` | `proc_gesture_flag` |
| `/game_mode` | `proc_game_mode` |
| `/tp_report_rate_switch` | `proc_tp_report_rate_switch` |
| `/tp_transient_report_rate_switch` | `proc_tp_transient_report_rate_switch` |
| `/tp_micro_control_accuracy` | `proc_game_mode` |
| `/shutdown_flag` | `proc_shutdown_flag` |
| `/sm_thp_cmd`、`/thp_data_enable` | `proc_thp_data_enable` |
| `/tp_scene` | `proc_tp_scene` |
| `/tp_large_area_mistouch_switch` | `proc_tp_large_area_mistouch_switch` |

---

## 4. 典型 sysfs → 类型

| sysfs 路径（片段或模式） | SELinux type |
|--------------------------|--------------|
| …/spi2.0/`special_area`（参考：`11012000.spi2` 下） | `sysfs_tran_touch_file` |
| `sysfs_mtk_tpd_file`、`kernel_lc_sysfs_mtk_tpd_file` | MTK TPD 调试/信息类 sysfs（具体路径由平台 policy 与驱动约定） |

`genfs_contexts` 内 **GMS wakeup** 相关长路径（多机型 `.../input.../wakeupNNN`）标签为 `sysfs_wakeup`，新机复制时需对照 **实际 input 编号与总线** 改写。

---

## 5. 域 ↔ 常见权限落点（排查 `allow` 时快查）

| Domain | 主要相关文件 | 典型客体 |
|--------|----------------|----------|
| `tran_tp_binder` | `kernel/vendor/tpaidl.te`、`hal/vendor/trantp_binder.te`、`hal/vendor/hal_trantp.te` | 多数 TP proc、部分 sysfs、`tppolldrv_device_t` |
| `system_server` | `kernel/vendor/system_server.te`、`hal/vendor/system_server.te` | TP proc、fhpd 设备、`binder` 调 HAL |
| `system_app` | `kernel/vendor/system_app.te` | 与框架/设置协同的 proc |
| `shell` | `kernel/vendor/shell.te`、`hal/vendor/system_server.te`（binder 至 HAL） | adb 调试可读节点 |
| `untrusted_app*` | `kernel/vendor/untrusted_app.te` | 限厂商调试/THP 等 |
| `fhpd_daemon` | `hal/vendor/fhpd_daemon.te` | `tppolldrv_device_t`、`proc_*`、`fhpd_*` 设备、网络等 |

---

## 6. 服务与 Binder

| 名称 | 类型 / 注册 | 文件 |
|------|-------------|------|
| `vendor.hardware.trantp.ITrantp/default` | `tran_tp_binder_service` | `hal/vendor/service_contexts`、`hal/vendor/hwservice.te` |
| fhpd vndservice | `fhpd_daemon_service` | `hal/vendor/vndservice.te`、`fhpd_daemon.te` |

---

## 7. 新机迁移 checklist

- [ ] 驱动新增节点是否已有 `genfscon` / `file_contexts`。
- [ ] `tcontext` 是否已定义为 `file.te` 中的 `type` 且属性完整。
- [ ] **访问域** 是否在正确 `.te` 中 `allow`（优先通过 HAL/system 收敛权限）。
- [ ] `sysfs_wakeup` 长路径是否需随 input 实例更新。
- [ ] 更新本 REF 表对应行，避免下一项目从零查找。
