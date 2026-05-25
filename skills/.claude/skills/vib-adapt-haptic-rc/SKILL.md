---
name: vib-adapt-haptic-rc
description: Guides debugging and porting of LRA/haptic sysfs and devnode permissions in Transsion tp/init.tp.rc using chmod/chown to system, plus PRODUCT_COPY_FILES in device-vext.mk to ship rc to odm/etc/init. Covers single vibrator_single and dual linear vibrator_l/vibrator_r sysfs trees. Use when adapting马达节点权限 root→system, RichTap/AW8697 permission denied, dual LRA init.tp.rc, device-vext.mk ODM copy line, init.tp.rc merge across projects, or vendor.haptic.calibrate.done flow.
disable-model-invocation: true
---

# Transsion 马达节点权限（init.tp.rc）

## 适用范围

在 Transsion MTK 项目上，通过 **`vendor/transsion/projects/<机型>/tp/init.tp.rc`** 在 init 阶段把触觉马达相关 **字符设备** 与 **LED trigger sysfs**（单马达为 **`vibrator_single`**，双线性马达为 **`vibrator_l` + `vibrator_r`**）从默认 root 归属改为 **`system system`**，必要时对关键节点 **`chmod 0666`**，供 HAL/RichTap 等非 root 进程访问。

仅编辑源码树下的 **`tp/init.tp.rc`** 不会生效：必须通过 **`device-vext.mk`** 将其 **拷贝进 ODM 分区**，镜像里路径为 **`odm/etc/init/init.tp.rc`**（设备上对应 **`/odm/etc/init/init.tp.rc`**），init 才会加载。

参考 **`vendor/transsion/projects/cm8_h973/device-vext.mk`**（约在文件靠前位置）：

```makefile
PRODUCT_COPY_FILES += $(LOCAL_PATH)/tp/init.tp.rc:odm/etc/init/init.tp.rc
```

- **`$(LOCAL_PATH)`**：当前机型目录（含该 `device-vext.mk` 的目录），源文件为同目录下 **`tp/init.tp.rc`**。
- **新机移植**：若参考机型有上述一行而新机型没有，需补上，否则马达 **`chown`/`chmod`** 逻辑根本不会执行。
- **机上核对**：`adb shell ls -l /odm/etc/init/init.tp.rc`，并与源码差异对比（以编译进机的产物为准）。

其它可参考机型：`lj9_h972`、`x6856_h971`、`cm7_h781`、`x6876_h786`、`x6873_h972` 等各自的 **`device-vext.mk`**，写法与上行一致。

## 标准做法

1. **在驱动 / sysfs 已创建之后**再执行 `chown`/`chmod`，否则 init 会报错或静默失败。
2. **`chown system system <path>`**：把属主/属组改为 system（与上层 HAL 进程匹配）。
3. **`chmod 0666 <path>`**：通常用于 **`/dev/aw8697_haptic`**、**`/dev/aac_richtap_5f`**（双马达时可能有多路设备节点，以 **`ls /dev`** 为准），以及部分项目对 **`rtp`** sysfs 放开读写；单马达多为 **`/sys/class/leds/vibrator_single/rtp`**，双线性马达则为 **`vibrator_l/rtp`** 与 **`vibrator_r/rtp`** 各一路。其余 sysfs 条目多以 **`chown` 为主**，是否与参考项目完全一致以现场 SELinux/访问测试为准。
4. 块末尾常见 **`setprop vendor.haptic.calibrate.done 1`**，用于通知校准/业务流程可以继续；移植时若参考有机型带此属性，新机型需对齐业务预期。

## 触发时机（两种主流写法）

| 触发条件 | 含义 | 注意 |
|---------|------|------|
| `on property:vendor.all.modules.ready=1` | 模块就绪较早 | 需确认此时 **`/sys/class/leds/vibrator_single/*`**（或双马达 **`vibrator_l/*`、`vibrator_r/*`**）与对应 **`/dev/...`** 已存在 |
| `on property:sys.boot_completed=1` | 开机完成后 | 偏晚但节点一般已就绪；部分机型配合 **`write /dev/kmsg`** 便于串内核日志确认执行 |

移植新机型时：**优先沿用同平台、同马达方案参考机的触发条件**；若出现「执行时节点不存在」，再考虑改为更晚的 property 或拆分两段（先 dev、后 sysfs）。

## 常见路径清单（AW + RichTap 典型）

下列路径在仓库参考 `init.tp.rc` 中重复出现，移植时按内核实际 **`leds` 名**与 **`misc`/字符设备名**核对：

- **字符设备**：`/dev/aw8697_haptic`、`/dev/aac_richtap_5f`（双线性方案若导出多个 haptic/richtap 节点，需逐节点 **`chmod`/`chown`**）
- **tp 轮询（部分项目）**：`/dev/tppolldrv` — `chown system system`（与马达无关但常与同文件一块维护）
- **单线性马达 sysfs**：`/sys/class/leds/vibrator_single/` 下若干属性，例如：`activate`、`activate_mode`、`duration`、`rtp`、`gain`、`state`、`trigger`、`brightness`、`vibr_level`、`cali`、`reg` 等（以驱动导出为准）

若内核 led 名称不是 `vibrator_single`，必须改成实际 **`/sys/class/leds/<name>/...`**。

### 双线性马达（`vibrator_l` / `vibrator_r`）

双线性马达配置时：**不要使用 `vibrator_single`**；sysfs 前缀改为两套并行目录：

- **`/sys/class/leds/vibrator_l/<属性>`**
- **`/sys/class/leds/vibrator_r/<属性>`**

适配步骤：

1. 以单马达参考块为模板，将每一条 **`.../vibrator_single/...`** **复制为两份**，分别替换为 **`vibrator_l`** 与 **`vibrator_r`**（属性名与单马达一致部分逐项对齐）。
2. **`chmod 0666`**：若单马达只对 **`rtp`** 放开，则双马达应对 **`vibrator_l/rtp`**、**`vibrator_r/rtp`** 各执行一次（或与参考 HAL 需求一致）。
3. **字符设备**：左右路若在 **`/dev`** 下对应不同节点名，按实际列出；禁止照搬单马达只有一个 **`aw8697_haptic`** 的假设而不核对。
4. 先用 **`adb shell ls /sys/class/leds/`** 确认仅有 **`vibrator_l`、`vibrator_r`**（而无 **`vibrator_single`**），再写 `init.tp.rc`，避免触发时机到达时路径不存在。

## 适配 / 调试步骤

1. **对齐参考项目**：打开同马达 IC、同内核方案的 **`tp/init.tp.rc`**，复制 `#USD: modify for LRA` 整段，再按差异增删节点。
2. **核对设备名**：在设备上 `adb shell ls -l /dev/aw8697_haptic /dev/aac_richtap_*`、`ls /sys/class/leds/`，确认是 **`vibrator_single`** 还是 **`vibrator_l`/`vibrator_r`**（或混合命名），路径与参考一致后再批量替换。
3. **确认 ODM 拷贝**：机型 **`device-vext.mk`** 中存在 **`PRODUCT_COPY_FILES += $(LOCAL_PATH)/tp/init.tp.rc:odm/etc/init/init.tp.rc`**，否则会误以为改了 **`tp/init.tp.rc`** 却无权限效果。
4. **确认 rc 已加载**：`adb shell ls -l /odm/etc/init/init.tp.rc`、`getprop | grep init`（或按需查编译产物中带 init.tp 的包）。
5. **权限仍未放开**：查 **`main_log`/`kernel_log`** 是否仍有 **Permission denied**；并行抓 **`avc: denied`**（SELinux），可能需要 sepolicy/`file_contexts` 与 init.rc 一起收口，而不是单靠 `chmod`。
6. **过早执行**：若 init 报找不到文件或属性未生效，改用 **`sys.boot_completed`** 或与驱动加载完成的属性对齐。

## 同一文件中的其它权限块

部分机型在 **`init.tp.rc`** 后半段另有肩键、工厂 SAR 等 **`chmod`/`chown`**（示例：`x6876_h786`）；移植时不要覆盖马达块，按需合并或独立 `#USD` 注释块。

## 输出给同事的改动说明模板

```markdown
- 源码：`vendor/transsion/projects/<机型>/tp/init.tp.rc`
- ODM：`device-vext.mk` 增加 `PRODUCT_COPY_FILES += $(LOCAL_PATH)/tp/init.tp.rc:odm/etc/init/init.tp.rc`（参考 `cm8_h973/device-vext.mk`）
- 触发：`on property:...`
- 变更：对 `/dev/...`、`/sys/class/leds/vibrator_single/...`（或双马达 **`vibrator_l`、`vibrator_r`** 两套路径）执行 `chown system system`；对 `rtp`/字符设备按需 `chmod 0666`
- 验证：镜像内存在 `/odm/etc/init/init.tp.rc`；机上跑 `fc-vib-rootperm`（节点 owner 为 `system system`）与 `fc-vib-selinux`；HAL/RichTap 访问成功；`vendor.haptic.calibrate.done` 行为与参考机一致
```

## 延伸阅读

若需 DTS 供电/regulator 与 vibrator 关系，见独立 skill：`dts-regulator-vibrator-tp`。若需从日志链路透拆振动失败，见：`DRV_Vibrator_VibrationFault`。
