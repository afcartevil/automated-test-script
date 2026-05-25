# 线性马达 init.tp.rc 节点清单

**Pass**：已存在节点的 `ls -l` 为 **`system system`**。

## 字符设备（单/双马达共用）

| 路径 | init.tp.rc |
|------|------------|
| `/dev/tppolldrv` | chown |
| `/dev/aw8697_haptic` | chmod 0666 + chown |
| `/dev/aac_richtap_5f` | chmod 0666 + chown |

## sysfs 属性（三种 led 名共用同一套属性名）

| led 目录 | 场景 |
|----------|------|
| `vibrator_single` | 单线性马达 |
| `vibrator_l` | 双线性马达左路 |
| `vibrator_r` | 双线性马达右路 |

每个 led 下均 chown 下列属性；**`rtp`** 另有 chmod 0666：

`activate`, `activate_mode`, `awrw`, `brightness`, `bullet_nr`, `cali`, `cont`, `cont_brk_time`, `cont_drv_lvl`, `cont_drv_time`, `cont_wait_num`, `duration`, `f0`, `f0_save`, `gain`, `gun_type`, `haptic_audio`, `haptic_audio_time`, `index`, `loop`, `lra_resistance`, `max_brightness`, `osc_cali`, `osc_save`, `prctmode`, `ram_num`, `ram_update`, `ram_vbat_comp`, `reg`, **`rtp`**, `seq`, `state`, `trig`, `trigger`, `uevent`, `vbat_monitor`, `vibr_level`

示例路径：`/sys/class/leds/vibrator_l/activate` 与 `/sys/class/leds/vibrator_single/activate` 仅目录名不同。

## 脚本如何选方案

| `ls /sys/class/leds/` | 检查范围 |
|------------------------|----------|
| 有 `vibrator_l` 和/或 `vibrator_r` | **双马达**：对每个存在的 `l`/`r` 跑**全表**属性 |
| 仅有 `vibrator_single` | **单马达**：`vibrator_single` 全表 |
| 都没有 | Fail |

## 说明

- 节点不存在 → `MISSING`，不判 owner Fail。
- 数据文件：`scripts/lra_nodes.py`；检查：`scripts/check_vib_rootperm.py`。
