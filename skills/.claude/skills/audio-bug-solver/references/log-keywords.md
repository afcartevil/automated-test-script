# 分层稳定关键字词典

按稳定性优先级列出：**主锚点**为跨版本跨机型都可信的字符串；**辅助锚点**用于缩窄范围。规避使用版本相关的数字（如 `App op 27`）作为唯一判据。

## A. 录音类

**主锚点**：

- `App op` ← 判断是否有 App OP 被动态撤销（后面紧跟 `missing, silencing record`）
- `silencing record` ← audioserver 侧确认了静音行为
- `setSilenced` ← RecordTrack 侧生效点
- `AudioRecord: set(` ← 上层创建 AudioRecord
- `createRecord_l` ← AudioFlinger 创建 record track
- `AudioRecord: start(` ← 开始录音
- `getInputForAttr` / `startInput` ← AudioPolicy 选 input

**辅助锚点**：`RECORD_AUDIO`、`AppOpsManager`、`SensorPrivacy`、`privacy_indicator`、`AttributionSource`、`inputSource`、`RecordThread`、`AudioFlinger_Threads`

## B. 播放 / Track 类

**主锚点**：

- `AudioTrack: set(` / `createTrack_l`
- `createTrack`（AudioFlinger）
- `getOutputForAttr`
- `openOutput`
- `start` / `stop` / `pause` / `flush`（注意结合上下文，单字符易误命中）
- `underrun`

**辅助锚点**：`PlaybackThread`、`MixerThread`、`DirectThread`、`OffloadThread`、`FastMixer`、`FastCapture`

## C. 路由 / 设备状态

**主锚点**：

- `setDeviceConnectionState` / `setDeviceConnectionStateInt`
- `setForceUse`
- `setCommunicationDevice`
- `getDeviceForAttributes` / `getDevicesForAttributes`
- `createAudioPatch` / `releaseAudioPatch`
- `routingOutputDevice` / `routingInputDevice`（MTK HAL）

**辅助锚点**：`BT_SCO`、`A2DP`、`WIRED_HEADSET`、`USB`、`HDMI`、`selected device`

## D. HAL（MTK 专用）

**主锚点**：

- `AudioALSAHardware`
- `AudioALSAStreamIn` / `AudioALSAStreamOut`
- `AudioALSAStreamManager`
- `AudioALSACaptureHandler*` / `AudioALSACaptureDataProvider*` / `AudioALSACaptureDataClientAurisys*`
- `AudioALSAPlaybackHandler*` / `AudioALSAPlaybackDataProvider*`
- `AudioALSADeviceConfigManager`
- `AudioMTKGainController` + `setNormalVolume` + `mSceneIndex`
- `pcm_start` / `pcm_read` / `pcm_write` / `pcm_open`

**辅助锚点**：`Aurisys`、`mAurisysScenario`、`openWavDump`、`TIMEOUT!!`

## E. HAL（QCOM 专用）

**主锚点**：

- `audio_hw_primary`
- `start_input_stream` / `start_output_stream`
- `select_devices`
- `platform_get_snd_device_name` / `platform_send_audio_calibration`
- `compress_` / `compress_write` / `compress_drain`
- `tinyalsa`

**辅助锚点**：`msm_` / `adsp_` / `q6asm_` / `mixer_paths`

## F. Crash / Tombstone

**主锚点**：

- `Fatal signal`（触发）
- `*** *** ***` / `F DEBUG   :`（tombstone 分割线/头）
- `Cmdline:`（定位崩溃进程）
- `pid:` `tid:` `name:`
- `signal 11 (SIGSEGV)` / `signal 6 (SIGABRT)` / `signal 7 (SIGBUS)`
- `Cause:`（如 `null pointer dereference`、`stack pointer is ...`）
- `backtrace:` + `#NN pc`
- `BuildId:`
- `abort_message` / `Abort message:`
- `Scudo ERROR` / `CHECK failed` / `assertion failed`
- `Sending signal 9` / `SIGKILL`

**辅助锚点**：`tombstone`、`libc`、`FATAL EXCEPTION`、`AndroidRuntime`

## G. Watchdog / ANR

**主锚点**：

- `Watchdog` / `WATCHDOG KILLING`
- `HangDetector`
- `Blocked in handler on` / `blocked in monitor`
- `slow operation`
- `ANR in`
- `Subject:` + `Process:`

**辅助锚点**：`mediaserver`、`audioserver`、`binder:*`

## H. GMS 测试

**主锚点**：

- `TestRunner: failed:`
- `AssertionError`
- `expected:` / `but was:`
- `Test failed`
- `Process crashed`
- `junit`
- `CtsMediaAudioTestCases`
- `VtsHalAudio`
- `GtsMediaTestCases`
- `CtsVerifier`

**辅助锚点**：`android.media.audio.cts`、`com.google.android.media.gts`、`android.hardware.audio`

`test_result.xml` 中主锚点：`result="fail"` + `Module name="..."` + `TestCase name="..."` + `Test name="..."` + `failure message=`。

## I. Transsion 定制

**主锚点**：

- `TRAN`（前缀）
- `TranAudio`
- `transsion`

**辅助锚点**：`TranAudioDenoise*`、`TranAudioVoIP*`、`TranAudio_UlProcess`、`TranAudio_DlProcess`

## M. 音频效果 / 音质异常（杂音、卡顿、响度异常）

**主锚点**：

- 数据流拥堵：`underflow`、`underrun`、`overrun`、`XRUN`、`write blocked`、`delayed writes`
- 路由突变：`setOutputDevice`、`routing`、`select_devices`、`audio_route`、`Apply path`、`enable_audio_route`
- 焦点/状态机：`AudioFocus`、`pause`、`flush`、`standby`、`active`、`duck`、`AUDIOFOCUS_LOSS`
- 音量/参数：`setVolume`、`setStreamVolume`、`VolumeShaper`、`SmartPA`、`calibration`、`AudioParam`、`NVRAM`

**辅助锚点**：`distortion`、`clip`、`limiter`、`tfa98xx`、`GetAudioCustomParamFromNvram`、`mixer_paths`

**快速归因提示**：

- `write blocked` + `underrun` + 同窗 `cpufreq/thermal/sched` 异常 -> 优先看性能调度与功耗策略。
- `setOutputDevice` / `Apply path` 切到 `earpiece/voice-call` -> 优先看路由策略与并发状态机。
- `SmartPA calibration failed` / `AudioParam ... fail/default/bypass` -> 优先看参数链路与功放初始化。

## J. 易误用/失效的关键字

- `App op 27`：`27` 是 `OP_RECORD_AUDIO` 常见取值，但跨版本可能变化；**以字符串 `App op` 为主锚**，数字仅作辅助。
- 单字母/极短串如 `start`、`open`、`read`：必须配合上下文（类名/tag）使用。
- `audio`：范围过大，绝不作为一级检索关键字。
- tombstone 中第一帧 `#00` 在 libc 时不要当成根因；它只是崩溃的即时位置，需要看业务栈。

## L. Kernel log（仅供 audio-crash.md §问题 6 触发时查阅）

本组是一个**只在 [workflows/audio-crash.md](../workflows/audio-crash.md) 问题 6 触发条件成立时**才需要的词典。日常 crash / 录音 / GMS 问题无需读 kernel_log，不用拉这里的锚点。

### L1. USB 音频（snd-usb-audio / xhci / dwc3）

- `usb \d+-\d+: USB disconnect`、`usb \d+-\d+: new (low|full|high|super)-speed USB device` — 拔插 / 重新枚举
- `idVendor=[0-9a-f]{4}, idProduct=[0-9a-f]{4}` — 识别具体耳机/声卡
- `usb_set_interface failed` — UAC alt-setting 切换失败（常见 `-110 ETIMEDOUT` / `-32 EPIPE`）
- `cannot submit urb` / `urb \S+ submitted while active` — URB 提交失败/重入
- `reset (low|full|high|super)-speed USB device` — 设备被内核重置
- 辅助：`xhci_hcd`、`dwc3`、`uac_`、`snd_usb_`

### L2. ALSA / 通用声卡框架

- `snd_pcm_` / `snd_compress_` / `snd_soc_` — PCM / compress offload / ASoC 报错
- `xrun` / `underrun` / `overrun`（kernel 侧）
- `dai .* op fail` / `dai \S+ startup`
- 辅助：`machine driver`、`codec`、`i2s`、`tdm`、`pcm-dma`

### L3. 高通 ADSP / q6（QCOM）

- `adsp` / `adsp_loader` / `adsp_ssr` / `subsystem_restart` / `ssr` / `crashdump`
- `q6afe` / `q6asm` / `q6core` / `q6routing`
- `rproc` + `remote processor`、`mdt_loader` / `load_firmware fail`
- 辅助：`apr_`、`smem_`、`glink_`

### L4. MTK SCP / DSP / Tinysys

- `scp` / `scp_ipi` / `scp_recovery`
- `audio_dsp` / `adsp_mt` / `adsp_ipi`
- `tinysys` / `TINYSYS`
- `mtk_sof` / `sof-audio`（若启用 SOF）

### L5. 同步阻塞 / 看门狗

- `binder[_:].*hung`（典型：`binder hung from audioserver : binder:\d+_\w to ... code 0x...`）
- `rcu: INFO: rcu_sched` / `rcu: INFO: rcu_preempt`
- `blocked for more than \d+ seconds`（hung task detector）
- `watchdog: BUG: soft lockup` / `watchdog: BUG: hard lockup`

### L6. 内核 Panic

- `Unable to handle kernel (NULL pointer|paging request)`
- `Internal error: Oops:`、`Kernel panic - not syncing`
- `BUG: KASAN:`、`BUG: KFENCE:`
- `WARNING: CPU: \d+ PID: \d+ at` — WARN_ON 触发点

### L7. errno ↔ 驱动含义速查（HAL 日志中看到这些 errno 时，可去 kernel_log 核对一次）

- `-110` ETIMEDOUT — USB NAK 超时 / DSP IPC 超时 / I2S DMA 长时间无中断
- `-32` EPIPE — PCM underrun/overrun / USB stall
- `-19` ENODEV — 设备消失（热拔出 / remoteproc 掉线 / 声卡卸载）
- `-77` EBADFD — PCM 状态机顺序错（未 prepare 即 start）
- `-5` EIO — 通用 IO 错，需回 kernel_log 找具体子系统原因

### L8. 易混点

- `kernel_log` / `sys_kernel_log` / `dmesg.txt` / `kern.log` 都是 kernel 环形缓冲区 dump，时间戳为相对启动 `[sec.usec]`；需与 main_log 做偏移标定后再外推。
- `logcat -b kernel` 输出时间戳为**绝对时间**，不需要换算。

## K. 一次性并行检索模板

当问题归属尚不明确时，可一次发起如下并行检索以快速分诊：

- `Fatal signal|tombstone|>>> |F DEBUG`
- `App op|silencing record|setSilenced|AudioRecord: set\(|createRecord_l`
- `AudioFlinger|AudioPolicyService|APM_AudioPolicyManager|createTrack|createAudioPatch|getDeviceForAttributes`
- `AudioALSA|audio_hw_primary|pcm_(open|read|write|start)|compress_write`
- `underflow|underrun|XRUN|write blocked|setOutputDevice|Apply path|AudioFocus|flush|standby|setVolume|SmartPA|AudioParam`
- `TestRunner: failed|AssertionError|CtsMediaAudioTestCases|VtsHalAudio|GtsMediaTestCases`
- `Watchdog|WATCHDOG|Sending signal|SIGKILL|blocked in|HangDetector`
- `TRAN|TranAudio`
