# 音频效果类问题工作流（杂音 / 卡顿 / 响度异常）

**适用范围**：播放/录音过程中的卡顿断续（stutter）、Pop/Click/底噪等杂音、响度异常（过大破音/过小/忽大忽小）、音效异常（无低频、发闷、声场异常）。

**不适用**：进程 crash（走 [audio-crash.md](audio-crash.md)）、xTS 认证失败（走 [gms-test-failure.md](gms-test-failure.md)）、纯上行录音无声（走 [uplink-recording.md](uplink-recording.md)）。

## 一、进入条件

任一满足即可进入本工作流：

- `issue` 明确描述"杂音/卡顿/爆音/声音异常/音质变差"。
- `main_log` 命中 `underflow|underrun|XRUN|write blocked|delayed writes|pop|click|distortion|clipping`。
- 路由/参数关键字命中：`setOutputDevice|routing|Apply path|audio_route|setVolume|SmartPA|AudioParam`。
- 用户无法归类但听感属于"断续、突变、响度不稳定、音效失真"。

## 二、必备输入与时间锚定

### 2.1 必备日志

- `mobile_log/main_log`（必需）：Framework + AudioFlinger + HAL 主证据。
- `kernel_log`（必需）：性能/调度/底层驱动证据。  
  若暂缺，可先给**初判**，但【根因层级】只能写"待 kernel 证据补强"，不得直接定性为性能问题。

### 2.2 时间锚定（先做）

目标：把听感异常转成可检索窗口。

1. 从提单或复现描述拿到精确到秒的案发时刻 `T0`。
2. 先取 `T0 ± 5s` 作为首窗；若未命中关键证据，再扩至 `±15s`。
3. 没有精确时间时，先以"播放开始/切歌/插拔耳机/来通知"等事件做锚点反推；仍无法对齐时，要求补充时间点。

## 三、证据收集（并行 Grep）

一次并行发起，不要串行。范围 `{log_dir}` 递归，附 `-n`：

- 数据流/性能：`underflow|underrun|overrun|XRUN|write blocked|delayed writes|FastMixer|OffloadThread|pcm_write|compress_write|ux_exact_audiomixer`
- 路由/通路：`setOutputDevice|routing|select_devices|setDeviceConnectionState|audio_route|Apply path|enable_audio_route|createAudioPatch|releaseAudioPatch`
- 焦点/状态机：`AudioFocus|focus|pause|flush|standby|active|duck|unduck|AUDIOFOCUS_LOSS`
- 音量/参数：`setVolume|setStreamVolume|VolumeShaper|SmartPA|calibration|AudioParam|NVRAM|bypass|limiter|clip`
- HAL（MTK）：`AudioALSAPlaybackHandler|AudioALSAStreamOut|AudioMTKGainController|Aurisys|mixer_paths|setParameters`
- kernel 侧并行：`sched|cpu freq|cpufreq|thermal|xrun|snd_pcm|dma|i2s|adsp|scp|tinysys|usb_set_interface failed`

> 若平台不是 MTK，保留通用锚点，同时替换为平台对应 HAL 关键字（如 QCOM 的 `audio_hw_primary` / `select_devices` / `platform_send_audio_calibration`）。

## 四、层级裁决（按现象分支）

按最先收敛的证据下钻，不要求线性走完全部分支。

### 4.1 卡顿 / 断续（Stutter / Underrun）

**证据形态**：

```
W AudioFlinger: write blocked for 150 msecs, 10 delayed writes ...
W AudioALSAHardware: underrun, frames = 0
```

**判据**：

- 同窗口出现 `write blocked` + `underrun/underflow/XRUN`，且 kernel 同时有降频/高负载/调度抖动 → 性能调度导致数据供给不足。
- 仅 HAL 报 `underrun`，kernel 无明显负载异常 → 优先查 HAL buffer 配置、period 设置、线程优先级、锁持有时间。
- 仅单次 `underrun` 且切歌/seek 场景瞬时出现 → 可能为可接受抖动，需结合听感频率判断是否缺陷。

**修复方向**：

- 提升关键音频线程调度保障（避免灭屏后被降权/降频）；检查音频通路唤醒锁与 UX 调度策略。
- 优化 HAL 缓冲区参数与写入节奏，避免长时间持锁调用阻塞音频线程。
- 对 offload/compress 场景补超时退避，防止长阻塞累积成爆音/断续。

### 4.2 路由突变 / 通路错误（音量骤变、音质突变）

**证据形态**：

```
I AudioPolicyManager: setOutputDevice() selected device 2 (earpiece)
I audio_route: Apply path 'earpiece'
```

**判据**：

- 媒体播放中被切到 `earpiece` / `voice-call` / 非预期 device path → 音频策略或并发状态机触发了错误路由。
- 插拔耳机/蓝牙切换时 `createAudioPatch` 与 `Apply path` 频繁抖动 → 设备状态去抖或竞态处理不足。

**修复方向**：

- 核对 `AudioPolicyManager` 设备选择逻辑与 `audio_policy_configuration.xml` 声明一致性。
- 修复并发场景（通知音、后台录音、通话模式切换）对媒体路由的误影响。
- 仅做最小路径修复，避免通过删 profile 掩盖真实能力问题。

### 4.3 焦点抢占 / 状态机切换（Pause/Flush 后 Pop）

**证据形态**：

```
I AudioFocus: request/release ...
I AudioTrack: pause/flush/standby ...
```

**判据**：

- 异常点前后出现 `AudioFocus` 抢占 + `pause/flush/standby` 连锁，恢复时伴随 pop/click → 焦点策略或状态机切换时序问题。
- `flush` 后立刻做 PA 下电，缺少静音尾帧/斜坡（ramp）处理 → 电平突变导致爆音。

**修复方向**：

- 优化焦点切换下的播放状态机：保证 pause/flush/standby 时序稳定。
- 在功放上下电路径补零阶/渐变处理，避免残余电平直接切断。
- 对通知音/短音效叠加场景加去抖，减少频繁启停硬件。

### 4.4 参数/功放异常（响度小、无低频、破音）

**证据形态**：

```
E tfa98xx: SmartPA calibration failed, fallback to bypass mode
W AudioALSA: GetAudioCustomParamFromNvram fail, use default param
```

**判据**：

- `SmartPA calibration failed`、`AudioParam ... fail/default/bypass` 命中 → 参数加载或校准失败。
- `setVolume` 映射到异常低增益（dB）或限制器长期工作 → 音量曲线/增益表配置错误。

**修复方向**：

- 修复 SmartPA 固件、参数文件、NVRAM 读取链路，确保初始化成功。
- 核对增益表、场景索引、设备类型映射（speaker/earpiece/headset）的一致性。
- 若进入 bypass 仅可作临时兜底，最终需恢复正确调音参数。

## 五、结论输出（强制结构）

最终报告必须按 [../references/report-template.md](../references/report-template.md) 四节输出，并满足以下约束：

- 【证据链】：给出触发异常的原始 log 行（如 `underrun`、`Apply path`、`SmartPA fail`）及对应时间对齐关系；涉及性能定性时必须同时给出 kernel 证据。
- 【根因层级】：限定为"性能调度/功耗策略、路由策略逻辑、焦点状态机、参数配置/功放链路"之一或多因排序。
- 【修改方案】：必须是可落地动作（线程调度策略、路由规则修正、PA 时序修正、参数/固件修复），禁止空泛建议。
- 【验证方法】：最小复测路径 + 需补抓日志（`adb logcat -b all`、`dumpsys media.audio_flinger`、`dumpsys audio`、必要时 `dmesg -T`）。

## 六、SOP 失效时的跳出（结果导向）

触发任一即跳出固定分支，改用专家推断：

- `T0 ± 15s` 内关键锚点几乎无命中，或命中彼此矛盾。
- 听感异常明显但日志级别不足（缺 AudioFlinger/HAL tag）导致证据断层。
- 现象可能属于未覆盖机制：时钟漂移、SRC 失配、effect 链挂载错误、蓝牙编解码协商异常（SBC/AAC/LC3）、AAudio MMAP 路径。

跳出后建议视角：

- 线程模型（Mixer/FastMixer/Offload）与实时性保障是否匹配当前产品功耗策略。
- `audio_patch` 生命周期与路由切换竞态。
- effect 链（AEC/NS/EQ/DRC/Virtualizer）挂载时机与流类型是否匹配。
- 蓝牙/USB 外设链路是否存在重协商或时钟域不一致。

跳出后仍需输出完整四节报告，并在【证据链】标注"因 X 原因跳出 workflow，改用 Y 机制推断"。

## 七、常见陷阱

- 只看到一次 `underrun` 就直接定性性能问题，忽略切歌/seek 的瞬态行为。
- 仅凭 `Apply path` 字样下结论，不核对当时 `mode`、设备状态与焦点上下文。
- 把 SmartPA 失败当作唯一根因，未排除上游音量曲线/路由错配。
- 只看 main_log 不看 kernel_log 就下"CPU 降频导致卡顿"定论。
- 为了消除测试现象而禁用音效/删 profile，掩盖真实能力缺陷。
