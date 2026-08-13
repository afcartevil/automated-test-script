# 上行录音问题工作流

**适用范围**：第三方/系统 App 录音上行无声、录音/录像音量异常偏小、偶发录音静音。

**不适用**：通话中下行无声（属播放/路由问题）、录音 crash（走 [audio-crash.md](audio-crash.md)）。

## 一、进入条件

任一满足即可进入本工作流：

- `issue` 描述为"App 录不到声/声音很小"。
- `main_log` 含 `silencing record` / `setSilenced` / `App op ... missing`。
- `AudioRecord: set()` 后看不到 `start(` 或 `start(` 返回非 0。
- 用户明确点名"录音问题"。

## 二、证据收集（并行 Grep）

一次性并行发起，不要串行。`{log_dir}` 下递归搜索，附 `-n` 行号：

- 权限/静音类：`App op|silencing record|setSilenced|RECORD_AUDIO|AppOps|SensorPrivacy|privacy_indicator`
- AudioRecord / AudioFlinger：`AudioRecord: set\(|createRecord_l|startRecording|openRecord_l|RecordThread|AudioFlinger_Threads`
- AudioPolicy：`APM_AudioPolicyManager|getInputForAttr|startInput|releaseInput`
- HAL（MTK）：`AudioALSAStreamIn|AudioALSAStreamManager|AudioALSACaptureHandler|AudioALSACaptureDataProvider|pcm_start|pcm_read|createAudioPatch|routingInputDevice`
- HAL（QCOM，若机型为高通）：`audio_hw_primary|in_read|start_input_stream|select_devices|tinyalsa`
- 增益场景：`AudioMTKGainController|setNormalVolume|mSceneIndex`
- Transsion 客制化：`TRAN|TranAudio|transsion.audio`

> 以 `App op` / `silencing record` / `setSilenced` 作为主锚点；数字 op id（如 27 = `OP_RECORD_AUDIO`）不同 Android 版本会变，仅作辅助不作唯一判据。

## 三、层级裁决（证据 → 结论）

按"由外向内"的证据强度裁决，而不是严格串行。每条命中即可直接下钻；未命中则继续下一层。

### 3.1 App/系统权限层（上层静音）

**证据形态**：

```
02-13 14:49:24 I audioserver: App op 27 missing, silencing record AttributionSourceState{pid:..., uid:..., packageName:com.xxx.yyy, ...}
02-13 14:49:24 D AF::RecordTrack: setSilenced: track with port id: 1327, (silenced)
```

**结论细分（对原 SOP 案例 1 的修正）**：不要直接说"未赋予录音权限"，应区分子场景：

- 用户从未授权（`PermissionChecker` 返回 denied）→ App 自身引导授权问题。
- 用户已授权但被动态 revoke：
  - 隐私指示器 / `SensorPrivacyManager` 全局静音开关打开。
  - App 进入受限后台/被冻结/非前台 `foregroundService` 未声明 `microphone` 类型。
  - `AppOpsManager` 内部策略（厂商 Power/Guard 模块）临时撤销 `OP_RECORD_AUDIO`。
- 包被 `DeviceIdleController` 或厂商省电模块置入白名单外。

**代码锚点**：

- `frameworks/base/services/core/java/com/android/server/audio/AudioService.java` 的权限/静音路径（搜 `silenced`、`RECORD_AUDIO`、`noteOp`）。
- `frameworks/av/services/audioflinger/RecordThread.*` 与 `IAfTrack`/`RecordTrack` 的 `setSilenced`。
- Transsion 侧若有 hook：`vendor/transsion/system_modules/audio/frameworks/base/services/...`、`vendor/transsion/system_modules/audio/frameworks/av/services/...`。

**修复方向**：转 AppOps / AMS / 权限模块负责人；若属系统策略误撤销，需在对应 hook 处补齐"前台录音豁免"逻辑，**不得**按包名写死。

### 3.2 Framework 录音通路层

**证据形态**：

```
D AudioRecord: set(): ... inputSource 0, sampleRate 48000, ...
D AudioRecord: createRecord_l: ...
D AudioRecord: start(204): ...
W AudioRecord: createRecord_l: ... status -22 (BAD_VALUE)
```

**判据**：

- `createRecord_l` 返回非 0（`NO_INIT = -19`、`BAD_VALUE = -22`、`INVALID_OPERATION = -38`）→ 入参非法 或 `AudioPolicyService::getInputForAttr` 失败（如没有可用 input profile）。
- `AudioRecord: set` 有但无 `start(` → App 侧未调用 `startRecording`（Framework 正常）。
- `AudioRecord: start` 后没有任何 HAL `AudioALSAStreamIn:` 打印（MTK）→ AudioPolicy 未真正 open input，常因设备不可用或策略冲突。

**代码锚点**：

- `frameworks/av/services/audioflinger/AudioFlinger.cpp` 中 `createRecord` 与 `IAfRecordTrack`。
- `frameworks/av/services/audiopolicy/service/AudioPolicyInterfaceImpl.cpp` 的 `getInputForAttr` / `startInput`。
- `frameworks/av/services/audiopolicy/managerdefault/AudioPolicyManager.cpp` 的 `getInputForAttr` 选 profile 逻辑。
- 客制化覆盖：`vendor/transsion/system_modules/audio/frameworks/av/servics/`（注意该目录拼写为 `servics`）、`.../media/`。

**修复方向**：

- 入参非法 → App 侧修参数。
- profile 选不中 → 排查 `audio_policy_configuration.xml` 是否声明了对应 `inputSource`/`sampleRate`/`channelMask` 的 `mixPort`。
- Transsion 客制化逻辑误拦截 → 补齐 hook 条件分支。

### 3.3 HAL 通路建立层（MTK）

**证据形态**：

```
D AudioALSAStreamManager: openInputStream(), devices =0x80000080, ...
D AudioALSAHardware: +createAudioPatch() ...
D AudioALSAStreamManager: +routingInputDevice(), input_device: 0x80000080 => 0x80000080
```

**判据**：

- `openInputStream` 缺失或返回非 0 → HAL 拒绝创建输入流，检查 `audio_device.xml` / DSP 配置。
- `createAudioPatch` 缺失 → AudioPolicy 没下发 patch，回到 3.2。
- `routingInputDevice` 选到了 `AUDIO_DEVICE_NONE (0x0)` 或非预期 device mask → 路由策略/耳机插拔竞态。

**代码锚点**：

- MTK 平台：**HAL 源码在本分支内开放**，主要路径 `vendor/mediatek/proprietary/hardware/audio/common/V3/aud_drv/`（入口类详见 [../references/code-map.md §6](../references/code-map.md)）。上行录音相关优先看 `AudioALSAHardware.cpp`、`AudioALSAStreamIn*.cpp`、`AudioALSACaptureHandler*.cpp`、`AudioALSACaptureDataProvider*.cpp`、`AudioALSACaptureDataClientAurisysNormal.cpp`、`AudioMTKGainController*.cpp`；可直接改代码并给出补丁。只有当 backtrace/现象指向第三方算法 so（`libvpnr.so`、`libaurisys*.so` 等）或 DSP/SCP 固件时，才按"闭源"处理、转厂商。
- 若机型为 QCOM：对应关键字替换为 `audio_hw_primary.c`、`start_input_stream`、`select_devices`，并将 `AudioALSA*` 视为不适用。

### 3.4 HAL 数据读取层

**证据形态**：

```
D AudioALSACaptureDataProviderNormal: +readThread(), pid:..., tid:..., kReadBufferSize=0x1e00, ...
D AudioALSACaptureDataProviderBase: pcm_start
W AudioALSACaptureDataProviderNormal: readThread, latency_in_s,...TIMEOUT!!
```

**判据**：

- 无 `+readThread` / `pcm_start` → HAL 未开始采集，回查 3.3。
- 频繁 `TIMEOUT` → Kernel/DSP 侧供给数据不足，去 `kernel_log` 查对应驱动报错（`mt_soc_pcm*`、`snd_pcm`、`dsp`）。
- 有 `pcm_start` 但 dump PCM 全 0 → 麦克风硬件/前端模拟通路问题或 Aurisys 算法库吃掉了声音；可在 HAL 配置中临时 bypass 音效算法（`mAurisysScenario`）二分定位。

### 3.5 音量/增益场景错配（音量偏小）

**证据形态**：

```
D AudioMTKGainController: setNormalVolume(), mSceneIndex = N, stream 5, devices 0x2, index 6, mode 0x0, gainDevice 0x2
```

**判据**：`mSceneIndex` 与当前场景不匹配（例如录音场景却选了 `Speaker Playback` 索引）→ PGA 增益加载错误。

**修复方向**：在 HAL 增益表加载与 `AudioMTKGainController::setNormalVolume` 的调用路径上核对 scene map；Transsion 定制的场景加载可能在 `vendor/transsion/system_modules/audio/frameworks/av/media/` 或 `.../utils/`。

## 四、数据落位与交叉验证

- PCM dump：通过 `AudioALSACaptureDataProviderBase: openWavDump()` 开启的 dump 节点，按提示拉 `hal_capturedataprovider_Normal.flag*` 与 `hal_streamin_flag*` 两段 PCM，比对有无声。若 provider 端有声但 streamin 端无声 → 算法库问题；若 provider 端就没声 → 前端/驱动问题。
- 同时对齐时间戳取 `dumpsys media.audio_flinger` 与 `dumpsys audio` 的快照，看 `AudioRecord` 的 track 状态、`input` 数量、`silenced` 标记。

## 五、输出（按根源给修改方案）

严格按 [../references/report-template.md](../references/report-template.md) 四节输出。典型修复方向：

- App 权限/策略：修 `AppOps` 或厂商省电/Guard 模块，**不得按测试包 UID 分支**。
- Framework：修 AudioPolicy profile 选择或 Transsion hook 的过滤条件；若属 Upstream bug，记录并上报。
- HAL（vendor blob）：输出现象与调用栈，转对应芯片厂商修；提供临时规避（bypass 音效、限制采样率）但标注"非最终方案"。
- XML 配置：最小增量添加 `mixPort` / `profile`，不改动不相关条目。
- 硬件：若判定为前端/麦克风硬件问题，给出测点与实验方法（换机/换麦/工厂模式测试），转硬件同事。

## 六、SOP 失效时的跳出（结果导向）

当以下任一触发时，立即停止按 §三 串线推演，回到 Android 音频栈的一般性机制做专家推断：

- 所有锚点 Grep 均未命中，但用户确认现象真实存在（日志可能被裁剪/日志级别过低/使用了非默认 logtag）。
- 命中层级与现象严重不符（例如 HAL 层一切正常，但 App 端 PCM 全 0），说明问题落在本 workflow 未列的通路：如 `AudioEffect`（预处理效果挂载）、`SoundTrigger`（被独占麦）、`AudioManager.setMicrophoneMute`、`AudioSource` 非法组合被策略回退、DRM/ConcurrentCapturePolicy 限制、并发录音独占（`ConcurrentCapturePolicy`）等。
- 机型非 MTK/QCOM 的常见组合（如展锐、紫光、Broadcom），关键字词典不适配。

跳出时可考虑的一般性视角：

- **录音 source 与 capture preset**：`AudioSource` 枚举（`MIC`/`VOICE_RECOGNITION`/`VOICE_COMMUNICATION`/`UNPROCESSED`/`VOICE_PERFORMANCE`）决定 HAL 选用的 preset 与音效链；App 选错 source 会得到"通路正常但声音被算法处理成近乎 0"的现象。
- **独占策略**：同一麦克风被 `SoundTrigger` 或 VoIP 通话独占，普通 App 的 `AudioRecord` 会被 `ConcurrentCapturePolicy` 限制或迟迟拿不到 buffer。
- **`AudioManager.setMicrophoneMute`**：全局 mute 可由 `TelephonyManager`、`HeadsetService` 等设置，日志里可能只留一条 `setMicrophoneMute true`。
- **AAudio / MMAP 路径**：低时延录音走的是 `libaaudio_internal`，并非 `AudioRecord: set()` 路径，关键字换 `AAudio`、`AAudioServiceEndpointMMAP`、`MmapStream`。

跳出后仍需输出完整四节报告，并在【证据链】显式写明"因 X 原因跳出 SOP，改用 Y 视角分析"。

## 七、常见陷阱

- 把 `App op 27` 的数字写死在正则里：跨版本失效，应以 `App op` + `silencing record` 为锚。
- 只看 `AudioRecord` 层 OK 就下结论"系统侧没问题"：HAL 层 `TIMEOUT` 与 Aurisys bypass 情况下，framework 看起来完全正常。
- MTK 与 QCOM 关键字混用：`AudioALSA*` 与 `AudioMTKGainController` 仅适用 MTK，高通平台需切到 `audio_hw_primary` / `msm_*`。
- 拿 `App op missing` 直接定性"用户没授权"：可能是隐私指示器或厂商策略动态撤权，需交叉核对 `AppOps` / `SensorPrivacy` 日志。
