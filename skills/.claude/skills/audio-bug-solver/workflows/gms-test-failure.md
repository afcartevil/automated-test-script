# Audio GMS 测试失败工作流

**适用范围**：CTS（`CtsMediaAudioTestCases` 等）、VTS（`VtsHalAudio*`）、GTS（`GtsMediaTestCases` 等）、CtsVerifier 音频手动项（Routing / Latency / Pro Audio）失败。

**不适用**：非 Audio 模块 Fail（如 `CtsMediaPlayerTestCases` 中的纯视频用例）。

## 一、进入条件

- `test_result.xml` 中 `Module` 含 `audio` 且存在 `result="fail"` 的 `TestCase`。
- Device `main_log` 出现 `TestRunner: failed:` + 音频包名（`android.media.audio.cts` / `android.media.audio.cts.*` / `com.google.android.media.gts.*` / `android.hardware.audio.*`）。
- Host 侧 `*.log` / `inv_*.log` 出现 `AssertionError` 且断言代码归属 Audio 用例。

## 二、证据收集

### 2.1 先读报告（必做第一步）

从 `test_result.xml` 中筛失败项：

- 抓取字段：`Module name`、`TestCase name`、`Test name`、`failure message`、`stack trace`。
- 区分来源：
  - `CtsMediaAudioTestCases` / `CtsMediaCodecTestCases` 等 → **CTS**（AOSP 行为合规）。
  - `VtsHalAudio*` / `VtsHalAudioEffect*` → **VTS**（HAL AIDL/HIDL 接口合规）。
  - `GtsMediaTestCases` / `com.google.android.media.gts.*` → **GTS**（GMS 专有，含 DRM/Widevine、CDD 要求）。
  - CtsVerifier 手测：看 `CtsVerifier` 的 `verifierReports` 输出。

### 2.2 再读 device log

并行 Grep：

- 测试框架：`TestRunner: failed|AssertionError|expected:|but was:|Test failed|Process crashed|junit`
- Framework：`AudioService|AudioSystem|AudioPolicyService|APM_AudioPolicyManager|AudioFlinger|AudioTrack|AudioRecord|setDeviceConnectionState|setSpeakerphoneOn|setCommunicationDevice|getDevicesForAttributes`
- HAL：`AudioALSAHardware|openInputStream|openOutputStream|createAudioPatch|setParameters|BAD_VALUE|INVALID_OPERATION|compress_|offload|Secure|underrun`
- 定制：`TRAN|TranAudio|transsion`

## 三、分析框架（按失败类别分支）

不要走线性，按失败类别直接跳到对应分支。

### 3.1 路由类（Routing）

**现象**：`AssertionError: expected:<DEVICE_OUT_SPEAKER> but was:<DEVICE_OUT_EARPIECE>` 或 `getDevicesForAttributes` 返回不符。

**下钻锚点**：

- `frameworks/av/services/audiopolicy/managerdefault/AudioPolicyManager.cpp` 的 `getOutputForAttr` / `getDeviceForAttributes` / `getDevicesForStrategyInt`。
- `frameworks/av/services/audiopolicy/enginedefault/` 或 `engineconfigurable/` 的策略实现。
- `frameworks/base/services/core/java/com/android/server/audio/AudioDeviceBroker.java` 的 `setCommunicationDevice`、通信路由。
- Transsion 定制路由：`vendor/transsion/system_modules/audio/frameworks/av/servics/`、`.../utils/`。

**常见根因**：

- 厂商定制策略覆盖默认选择（例如强制把媒体流切到 receiver）。
- `audio_policy_configuration.xml` 缺少对应 `devicePort` 的声明。
- 通话/VoIP 场景下 `mode` 切换不一致导致策略误选。

### 3.2 Offload / 压缩音频写入失败

**现象**：`testMP3AudioTrackOffload ... Unable to write all read data, wrote 65536 bytes`、`compress_write` 阻塞、`DSP timeout`。

**下钻锚点**：

- `audio_policy_configuration.xml` 中 `AUDIO_OUTPUT_FLAG_COMPRESS_OFFLOAD` profile 的声明。
- HAL `compress_*` 接口（vendor blob）。
- `kernel_log` 中 `snd_compress` / `adsp` / `dsp timeout`。

**修复方向（对原 SOP 案例 3 的修正）**：

- **不要**无条件建议"从 XML 移除 MP3 offload profile"——这会隐藏产品实际声明的能力。正确做法：
  1. 先确认产品 spec 是否声明支持 MP3 offload；若**不**声明，才可以从 XML 中移除 profile（并同步移除 framework 上层声明）。
  2. 若声明支持，则必须修 DSP/驱动/HAL，使 `compress_write` 在合法数据下正常返回；可以临时通过 system property 禁用 offload 走软解作为兜底，但最终必须修底层。

### 3.3 Secure / DRM 类（GTS 专属为主）

**现象**：`Cannot create secure track for non-secure output`、`createTrack_l ... status: -22`、`AUDIO_OUTPUT_FLAG_SECURE` 匹配失败。

**下钻锚点**：

- `audio_policy_configuration.xml` 中 `mixPort` 的 `flags` 是否包含 `AUDIO_OUTPUT_FLAG_SECURE`。
- `frameworks/av/services/audioflinger/Threads.cpp` / `AudioFlinger.cpp` 的 `createTrack` 安全路径。
- 底层 DSP 是否支持 Widevine L1 的加密音频 buffer。

**修复方向**：在 `primary` 或独立 module 的 output 中新增带 `AUDIO_OUTPUT_FLAG_SECURE` 的 `mixPort`，确保 HAL 能处理加密 buffer；DSP 不支持的产品不应声明 L1，避免 GTS 误命中。

### 3.4 VTS 接口合规类

**现象**：`VtsHalAudioV*TargetTest ... expected INVALID_ARGUMENTS but was OK`、`openInputStream` 对非法参数不返回错误码。

**下钻锚点**：

- HAL AIDL/HIDL 实现（`hardware/interfaces/audio/` 上游 + vendor 实现）。
- `openInputStream` / `openOutputStream` 入参校验（采样率/声道/格式）。

**修复方向**：在 HAL 入参校验处补合法性判断，对 VTS 给出的非法组合返回 `BAD_VALUE` / `INVALID_OPERATION`，不得静默接受。

### 3.5 Latency / Performance 类

**现象**：`testOutputLatencyMs` 等断言超出阈值；CtsVerifier 的 Latency Test 显示超标。

**下钻锚点**：

- HAL `period_size` × `period_count` × 采样率 → 理论延迟。
- `audio_policy_configuration.xml` 中 `AUDIO_OUTPUT_FLAG_FAST` / `AUDIO_OUTPUT_FLAG_RAW` profile 是否存在且被路由选中。
- `frameworks/av/services/audioflinger/fastpath/` 的 FastMixer / FastCapture 线程路径。

**修复方向**：调低 HAL buffer 尺寸、启用 fast/raw profile、确保测试 App 拿到 fast track。

### 3.6 Profile / 格式支持类

**现象**：某采样率/声道不被支持但测试期望支持，或相反。

**下钻锚点**：`audio_policy_configuration.xml` 中的 `profile` 声明与 HAL 实际能力是否一致。

**修复方向**：以 HAL 实际能力为准同步 XML；不在 XML 中虚假声明。

### 3.7 录音静音类（与 uplink 工作流交叉）

**现象**：跑测工具录到 0。若看到 `App op ... missing silencing record`，直接按 [uplink-recording.md](uplink-recording.md) 的权限层处理。

**注意**：CTS/GTS 测试 runner 属于系统 App，正常情况不应被 `silencing record`；若出现，一般是厂商权限/隐私策略误伤测试 runner。修复**不得**按包名豁免测试包，改为保证"已授权且在前台的录音请求不会被动态撤权"。

## 四、红线（GMS 合规）

> 以下条款覆盖原 SOP 案例 2 的建议——如 `if (isCtsCaller(uid)) { // 不执行 Fade-out }`——**禁止使用**，理由：Google 将"依据调用方身份切换系统行为"视为 test-aware behavior，违反 GMS 认证要求。

替代方案：

1. **对齐语义**：让定制行为在语义上与 AOSP 一致。例如 VolumeShaper `pause/stop/flush` 的**语义要求立即 mute**；产品若要"渐隐"，放到 UI 层/应用层触发，不在系统服务中劫持。
2. **产品化开关**：通过系统属性（`ro.vendor.audio.*`）或产品 overlay 控制定制特性，**默认与 AOSP 一致**；仅在明确不跑 GMS 的产品上打开定制。
3. **严禁**：按包名/UID/`ActivityThread.currentPackageName()` 判断是否为测试进程再切分支。

## 五、输出

按 [../references/report-template.md](../references/report-template.md) 四节输出。特别要求：

- 【证据链】必须包含：失败的 `Module/Class/Method` 全名、`expected/actual` 断言数据、断言对应的 device log 行号。
- 【根因层级】要标注属"定制逻辑冲突 / 框架合规 / HAL 合规 / XML 配置 / DSP/驱动 / 硬件能力缺失"之一。
- 【修改方案】禁用 test-aware 分支；涉及 XML 改动要标明"此 XML 位于产品 `device/<vendor>/<product>/audio/` 或 `vendor/.../audio_policy_configuration.xml`"，并给出最小改动 patch。
- 【验证方法】给出单项重跑命令模板：
  ```
  atest CtsMediaAudioTestCases:<Class>#<method>
  # 或
  run cts -m CtsMediaAudioTestCases -t <pkg.Class#method>
  ```

## 六、SOP 失效时的跳出（结果导向）

触发跳出的情形：

- 失败项不在 §三 的六大子类里（例如 `CtsMediaMetricsTestCases`、`CtsMicrophoneSoundTriggerTests`、`MediaProviderTests` 的音频剪辑类、`CtsAudioHostTestCases` 的 Host-side 测试、`CtsVerifier` 的非常规人工项）。
- 断言报错信息被 obfuscate 或 stack trace 定位到 `ITS`/`ApkInfo` 这类与音频语义无关的类，真因被一层工具链掩盖。
- `test_result.xml` 与 device log 时间戳错位（通常是跨设备跑测或分片重跑），导致找不到对应的断言点。
- 相同用例在 AOSP 参考机上通过，在本机上失败，但 device log 完全无异常打印（通常是测试框架/ITestDevice 侧 flakiness，不是音频 bug）。
- 定制代码与上游 Android 版本存在接口/语义断层（例如上游 Android 升级了 `AudioAttributes` 的 `CAPTURE_PRESET`，厂商 hook 没跟上）。

跳出时可调用的一般性视角：

- **CDD / xTS 契约**：测试在考的是 Android CDD 条款（例如 5.x 音频章节）与 AIDL 接口语义，不是某条特定日志。定位不到日志时，对照 CDD 条款与 `AudioAttributes` / `AudioDeviceInfo` 契约反推系统应有行为。
- **xTS runner 本身的异常**：测试 App 装载失败、tradefed 超时、`run cts` 的 shard 分裂、`test_result.xml` 被重复 merge，都会伪装成"音频失败"。
- **安装包版本漂移**：GTS 包版本与 GMS Core 版本、GSI 镜像版本不匹配时，部分用例会"预期行为"本身就变化。
- **策略引擎差异**：`engineconfigurable` vs `enginedefault` 的产品，路由决策路径完全不同；原 SOP 若只讲 `enginedefault`，切 `engineconfigurable` 产品时要重写推理路径。

跳出后仍需输出完整四节报告，并在【证据链】明确"因 X 原因跳出 SOP，改依据 Y 进行推断"。红线（禁止 test-aware 分支、禁止盲删 XML profile）永远生效。

## 七、常见陷阱

- 拿失败项名就盲改：必须先看 `failure message` / `stack trace` 锁定到具体断言点，再定位代码。
- 误把 CTS 和 GTS 的预期搞混：CTS 考 AOSP 合规，GTS 考 GMS 专有（DRM/Widevine 等）；修复策略不同。
- 在 `AudioService` 里加 `isCtsCaller(uid)` 分支或等价行为切换 → **违反 GMS**。
- 直接删 XML 中某 profile 了事：必须先确认产品能力声明。
- 忽略定制串扰：Transsion 定制（`TRAN*` 关键字）在测试场景下的行为差异是失败高发区，优先排查。
