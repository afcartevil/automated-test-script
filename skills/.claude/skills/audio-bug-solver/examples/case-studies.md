# 典型案例端到端推导

三个案例分别对应三类问题。每例展示"log 行 → 代码/配置 → 修改方案 → 验证"的完整链路，作为模型输出的参照。

## 案例 1：抖音录音无声（上行录音）

### 现象
- 抖音（`com.ss.android.ugc.aweme`）不在通话界面时无法录音；其他 App 正常。
- `mobile_log/main_log` 中出现：
  ```
  Line 27572: 02-13 14:49:24.920039 1803 6053 I audioserver: App op 27 missing, silencing record AttributionSourceState{pid: 13931, uid: 10330, deviceId: 0, packageName: com.ss.android.ugc.aweme, ...}
  Line 27582: 02-13 14:49:24.939258 1803 2019 D AF::RecordTrack: setSilenced: track with port id: 1327, (silenced)
  ```

### 推导
1. 分诊：主锚点 `App op` + `silencing record` 命中录音类。进入 [workflows/uplink-recording.md](../workflows/uplink-recording.md) §3.1。
2. 层级：静音行为由 audioserver 根据 `AppOps` 视图触发，根因在上层（App 权限/系统策略），不是 HAL。
3. 子场景判定（对原 SOP 案例 1 的修正）：需进一步区分"用户从未授权"与"动态 revoke"。交叉检索 `AppOpsManager` / `SensorPrivacy` / 厂商 Power/Guard 日志：
   - 若 `AppOpsManager: op=RECORD_AUDIO mode=MODE_IGNORED` 由 `setUidMode` 触发且调用方为厂商 Guard 服务 → 动态 revoke。
   - 若无 revoke 记录，仅 `PermissionChecker` denied → 用户从未授权，由 App 引导授权。
4. 代码锚点：`frameworks/base/services/core/java/com/android/server/audio/AudioService.java`（搜索 `silenced` / `noteOp`）与 `frameworks/av/services/audioflinger/Tracks.cpp`（搜索 `setSilenced`）。

### 修改方案
- 若定性为动态 revoke：
  - 定位厂商 Guard/Power 模块（本仓在 `vendor/transsion/system_modules/audio/frameworks/base/services/` 下可能存在 hook），校正"前台活跃录音的 App 不应被撤权"的规则；
  - **不得**按 `packageName == "com.ss.android.ugc.aweme"` 写白名单，改为按"前台 `foregroundServiceType` 含 `microphone`"或"正在持有 AudioRecord"等通用条件。
- 若定性为未授权：App 侧修引导流程；系统侧无需修改。

### 验证
- 复现原场景，观察 `App op ... missing, silencing record` 是否不再出现；
- `adb shell dumpsys appops | grep -i record_audio` 查看模式变化；
- `adb shell dumpsys media.audio_flinger | grep -A2 silenced` 确认 track 不被静音。

## 案例 2：android.hardware.audio.service 在 VoIP 降噪处空指针（Audio Crash）

### 现象
- `tombstones/` 中：
  ```
  Cmdline: /vendor/bin/hw/android.hardware.audio.service-aidl.mediatek
  pid: 1237, tid: 22370, name: processThread_1
  signal 11 (SIGSEGV), code 1 (SEGV_MAPERR), fault addr 0x0
  Cause: null pointer dereference
  backtrace:
      #00 pc 0x0e01088  /vendor/lib64/libvpnr.so
      #01 pc 0x046e938  /vendor/lib64/hw/audio.primary.mediatek.so (android::TranAudioDenoiseVoIPIgoVP::process(void*, void*, unsigned int)+88)
      #02 pc 0x0465dc0  /vendor/lib64/hw/audio.primary.mediatek.so (android::TranAudioVoIPCallController::TranAudio_UlProcess(audio_pool_buf_t*, bool, audio_pool_buf_t*)+384)
      #03 pc 0x021360c  /vendor/lib64/hw/audio.primary.mediatek.so (android::AudioALSACaptureDataClientAurisysNormal::processThread(void*)+3308)
  ```

### 推导
1. 分诊：命中 Crash 锚点。进入 [workflows/audio-crash.md](../workflows/audio-crash.md) 问题 3（HAL 崩溃）。
2. `#00` 在第三方库 `libvpnr.so`；`#01/#02` 归属 `audio.primary.mediatek.so` 中的 `TranAudio*` 符号 → **Transsion 定制的 VoIP 降噪 hook**。
3. 空指针推断：最常见情形是 `libvpnr.so` 的实例未初始化或在切换 VoIP 场景时被销毁后仍被 `process(buf, buf, size)` 调用 → UAF。
4. 交叉验证：在 `main_log` 取崩溃前 5 秒窗口，并行 Grep `TranAudio|Aurisys|input_source|setParameters`，若发现 `+TranAudio_UlProcess` 密集创建/销毁或 mode 切换 → 证实场景。
5. 符号化：若要把 `#01/#02` 的 `pc` 对到具体行号，需拿对应版本 unstripped `audio.primary.mediatek.so`，对比 `BuildId: 3cc1a7e3c23a1c892708ef2e21dc349d` 一致后用 `llvm-symbolizer` 或 `addr2line`。

### 修改方案
- 处理分三块，优先级从高到低：
  1. **MTK HAL 层直接修复（本分支源码开放）**：`TranAudioDenoiseVoIPIgoVP::process` / `TranAudioVoIPCallController::TranAudio_UlProcess` / `AudioALSACaptureDataClientAurisysNormal::processThread` 均属 `audio.primary.mediatek.so`，源码在 `vendor/mediatek/proprietary/hardware/audio/common/V3/aud_drv/`（重点看 `AudioALSACaptureDataClientAurisysNormal.cpp` 及 `TranAudio*` 的同目录实现）。在这里对 `libvpnr` 降噪实例的生命周期加保护：销毁与 `process` 之间加互斥锁；销毁后置空并在 `process` 入口 `if (!instance) return OK;`；切场景时先停 Aurisys `processThread` 再析构。
  2. **功能开关兜底**：提供 `ro.vendor.audio.voip.denoise.igovp` 之类系统属性，默认开启；出问题机型可临时关闭，走无此降噪的兜底通路（仍落在 `aud_drv/` 的 Aurisys scenario 选择分支）。
  3. **转算法厂商**：`libvpnr.so` 本身为闭源第三方算法库，把 `BuildId`、崩溃 pc、入参快照提交给算法厂商修正其内部健壮性（空指针、状态校验）。
- **禁止**用 `if (package==testRunner) ...` 绕过；也**禁止**简单"把 IgoVP 降噪从 audio_effects.xml 移除"作为最终方案（会降级通话体验）。

### 验证
- 触发 VoIP 场景反复切换（微信通话 / Google Duo / 录音转 VoIP），观察 tombstone 是否复现；
- `adb logcat | grep -E "TranAudio|IgoVP"` 验证生命周期打印成对；
- 回归：普通录音、蓝牙通话、AEC/NS 效果。

## 案例 3：GtsMediaTestCases 安全音频播放失败（GMS 测试）

### 现象
- `test_result.xml` 中：
  ```
  <Module name="GtsMediaTestCases" abi="arm64-v8a">
    <TestCase name="com.google.android.media.gts.WidevineSecureAudioTest">
      <Test name="testSecureAudioPlayback" result="fail">
        <Failure message="Failed to initialize AudioTrack for secure content" />
      </Test>
    </TestCase>
  </Module>
  ```
- Device `main_log`：
  ```
  E AudioFlinger: createTrack_l() Cannot create secure track for non-secure output
  W AudioTrack: createTrack_l(0): AudioFlinger could not create track, status: -22
  ```

### 推导
1. 分诊：主锚点 `GtsMediaTestCases` + `createTrack_l ... Cannot create secure track`。进入 [workflows/gms-test-failure.md](../workflows/gms-test-failure.md) §3.3。
2. 根因层级：**配置层**。`AudioPolicyManager::getOutputForAttr` 匹配带 `AUDIO_OUTPUT_FLAG_SECURE` 的 profile 失败，`AudioFlinger::createTrack` 直接拒。
3. 检查 `audio_policy_configuration.xml` 中 `primary` 或独立 module 的 `mixPort`：
   - 若所有 `mixPort` 的 `flags` 均无 `AUDIO_OUTPUT_FLAG_SECURE` → 配置缺失。
   - 若声明了但 HAL 对加密 buffer 不支持 → 配置与能力不符。

### 修改方案
- **配置补齐**（示例，具体放在产品实际的 XML）：
  ```xml
  <mixPort name="primary output secure" role="source"
           flags="AUDIO_OUTPUT_FLAG_DIRECT|AUDIO_OUTPUT_FLAG_SECURE">
    <profile name="" format="AUDIO_FORMAT_PCM_16_BIT"
             samplingRates="48000" channelMasks="AUDIO_CHANNEL_OUT_STEREO"/>
  </mixPort>
  ```
  同步在 `routes` 节点把该 `mixPort` 路由到 `Speaker`/`Headphones` 等合法 sink。
- **确认 HAL 能力**：若 DSP 不支持加密通路，不应声明 Widevine L1；在 `com.google.android.feature.WIDEVINE_L1` 等相关声明中保持一致。若声明 L1，则 HAL 必须能处理 `AUDIO_OUTPUT_FLAG_SECURE` 的输出（对接 DSP 的受保护通路）。
- 不允许用"识别 GTS 测试包后放行"的逻辑规避。

### 验证
- 单项重跑：
  ```
  run cts -m GtsMediaTestCases -t com.google.android.media.gts.WidevineSecureAudioTest#testSecureAudioPlayback
  ```
- 同时回归：
  - `CtsMediaAudioTestCases` 的 track 创建相关用例；
  - 正常音乐/视频播放不受影响；
  - Widevine 样片解码正常。

## 从案例中提炼的通用要点

- 三类问题的主锚点不同，但**证据驱动 → 层级裁决 → 最小增量修改 → 覆盖验证**的结构相同。
- 当根因落在 MTK HAL（`audio.primary.mediatek.so`）时，**本分支源码开放**（`vendor/mediatek/proprietary/hardware/audio/common/V3/aud_drv/`），应直接改代码给补丁；只有在真正闭源的第三方算法库或固件层面，系统侧才限于"生命周期防御 / 入参校验 / 功能开关"。
- 配置文件修改必须最小增量，先核对产品能力声明与 HAL 能力两端。
- 红线：任何按测试调用方 UID/包名切换行为的方案都不是合规修复方案。
