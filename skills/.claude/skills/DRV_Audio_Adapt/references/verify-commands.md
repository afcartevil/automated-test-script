# Bringup 验收建议命令

本表给阶段 6 交付时建议开发者在 **首次起机后** 跑的一组最小自检命令，用于快速判断本次 bringup 的整体走通情况。**SKILL 不替开发者执行这些命令**，只产出清单。

## 1. 通用快照（任何项目都建议先跑）

```bash
adb root
adb shell dumpsys audio        > dumpsys_audio.txt
adb shell dumpsys media.audio_flinger > dumpsys_audioflinger.txt
adb shell dumpsys media.audio_policy  > dumpsys_audiopolicy.txt
adb shell cat /proc/asound/cards
adb shell cat /proc/asound/devices
adb shell logcat -b all -d > full_logcat.txt
```

观察点：

- `dumpsys media.audio_flinger` 中应能看到 `mixer` / `record` 线程，且无大量 `XRUN` / `underrun`。
- `dumpsys audio` 应能列出 SPK / MIC / TypeC 相关 device 状态。
- `/proc/asound/cards` 中需出现 MTK 的声卡条目；多声卡缺失常是 DTS / kernel module 未起。

## 2. ProjectConfig.mk / 编译期校验

```bash
# 编译时验证（不在设备上跑）
# 在 base_code_sunmao 根目录
source build/envsetup.sh
lunch <full_lunch_name>
m -j ProjectConfig.mk 2>&1 | tee project_config_build.log
```

观察点：

- 编译期间若有"audio macro not defined"类警告 → 回阶段 1 复查。
- 4 个 PA `*_SUPPORT` 宏控的互斥是否在编译期触发 `error` / `warning`。

## 3. PA / Aurisys 自检

```bash
adb shell ls -l /odm/etc/vconfig/audio/        # 看升级后参数是否打包进 ODM
adb shell ls -l /vendor/lib64/soundfx/ /vendor/lib64/ | grep -E 'aurisys|aw87|fsm|oca'
adb shell ls -l /odm/etc/aurisys_config*.xml /vendor/etc/aurisys_config*.xml
adb logcat -b all -d | grep -iE 'aurisys|smartpa|aw87|fsm|fs1599|fs1589|oca72'
```

观察点：

- `/odm/etc/vconfig/audio/` 下参数目录是否存在（如 `audio_param/`、`pa_param/` 等，取决于 aurisys xml 内 `param_path`；§6 已将 `/vendor/etc/` 统一改到 odm）。
- `grep -R '"/vendor/etc/'` 在设备侧或源码 `aurisys_config*.xml` 中应为空。
- aurisys 算法初始化日志（`AurisysLibManager` / `Aurisys scenario`）应无 `load fail` / `param missing`。

## 4. DTS / kernel 模块

```bash
adb shell dmesg -T | grep -iE 'tran_audio_controller|aw87xxx|oca72xxx|fs15xx|hl1280|sliptswitch|dio1520'
adb shell find /sys/devices/platform -iname '*audio*' -maxdepth 6
adb shell find /sys/devices/platform -iname '*sliptswitch*' -maxdepth 6
```

观察点：

- `tran_audio_controller probe` 应成功。
- typec switch（HL1280 / DIO1520）driver probe 不应报 `-ENODEV` / `-EPROBE_DEFER`。

## 5. 录音 / 播放冒烟

```bash
# 录音 5s
adb shell tinycap /sdcard/cap.wav -D 0 -d 0 -c 2 -r 48000 -t 5
adb pull /sdcard/cap.wav
# 播放
adb shell tinyplay /sdcard/cap.wav -D 0 -d 0
```

> 设备号 `-D 0 -d 0` 仅示例；以 `/proc/asound/cards` 列出的真实编号为准。
>
> SKILL 在阶段 6 应提示开发者：录音 wav 用 audacity / sox 看波形，是否完全 0、是否有明显单声道缺失、是否削顶。

## 6. 工模

- 进工模（`*#*#3646633#*#*` 或厂内通道），按 [factory-ini-rules.md](factory-ini-rules.md) 注释的 5 个 MenuItem 应不可见。
- `Audio.Mic.Sets` 与 `Audio.Input.TypecHeadset` 的生效以工模实际可见项为准。

## 7. 不在本 SKILL 范围的进一步验证

下列项目跑通仍属于"bringup 之后的功能验证"，不在本 SKILL 责任范围内，但建议开发者跟进：

- VoIP / 电话上下行音质（涉及 modem / DSP，超出 ProjectConfig + DTS + DWS 配置范围）。
- 蓝牙 A2DP / HFP（涉及 BT 栈 / `audio_policy_configuration.xml` profile）。
- USB 耳机热插拔与多采样率（涉及 `AudioUSBCenter`，bringup 完成后由专门的 bug 诊断流程跟进）。
- CTS / VTS / GTS Audio 模块。
