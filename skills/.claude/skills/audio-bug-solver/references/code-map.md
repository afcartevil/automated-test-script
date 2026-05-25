# Audio 代码入口速查

本文件仅列"第一入口"，给出按问题现象找到源码起点的最短路径。所有路径均相对 `branch_root`，统一使用正斜杠。

## 1. `frameworks/base/services/core/java/com/android/server/audio/`

Java 层 AudioService 生态，负责系统服务、音量、路由仲裁、权限协同、设备状态广播。

- `AudioService.java`：`AudioService` 系统服务总入口。搜索点：
  - `setStreamVolume` / `adjustStreamVolume`：音量设置
  - `handleAudioFocusChange` / `AudioFocusStack`：焦点
  - `silenced` / `RECORD_AUDIO` / `noteOp`：权限/静音相关切入点
  - `setCommunicationDevice`：通信设备切换
- `AudioDeviceBroker.java`：设备接入/切出仲裁（蓝牙/耳机/USB）。搜索 `onSetForceUse`、`setBluetoothA2dpOn`、`mDeviceStateLock`。
- `AudioDeviceInventory.java`：设备清单维护。搜索 `onSetWiredDeviceConnectionState`、`makeA2dpDeviceAvailable`。
- `AudioSystemAdapter.java`：Java→Native 适配层，`AudioSystem` 静态方法的实际封装。
- `AudioServiceEvents.java`：事件环形缓冲，`dumpsys audio` 的事件段来自这里。
- `AudioServerPermissionProvider.java`：向 Native 侧供给权限视图。

## 2. `frameworks/av/services/audioflinger/`

Native AudioFlinger，媒体数据通路的执行方（线程/Track/Mix/IO）。

- `AudioFlinger.cpp` / `AudioFlinger.h`：`createTrack` / `createRecord` / `openOutput` / `openInput`。崩溃、track 创建失败的首要定位点。
- `Threads.cpp`（含 Playback/Record/Mix/Direct/Offload Thread 的超类实现）：IO 线程主循环、`setSilenced`、`standby`。
- `Tracks.cpp`：`IAfTrack` / `IAfRecordTrack` / `PlaybackTrack` / `RecordTrack` 的具体实现，`setSilenced`、`start`、`stop` 的行为。
- `datapath/` / `fastpath/`：数据通路、Fast Mixer / Fast Capture（低时延路径）。
- `timing/`：时钟/时间戳相关，CTS latency 类失败可能落在这里。
- `afutils/`：工具类（vibrator/patch/allocator）。

## 3. `frameworks/av/services/audiopolicy/`

Native AudioPolicy，策略仲裁（选 device、选 mixPort、选 strategy）。

- `service/AudioPolicyService.cpp` + `AudioPolicyInterfaceImpl.cpp`：Binder 入口。搜索 `getInputForAttr`、`getOutputForAttr`、`startInput`、`startOutput`。
- `managerdefault/AudioPolicyManager.cpp`：默认策略管理器主体。搜索 `getDeviceForAttributes`、`getDevicesForStrategyInt`、`setForceUse`、`setDeviceConnectionStateInt`。
- `enginedefault/` / `engineconfigurable/`：策略引擎实现（新老两套）。
- `common/managerdefinitions/`：`DeviceDescriptor` / `HwModule` / `IOProfile` 定义，解析 `audio_policy_configuration.xml` 的结果持有于此。
- `config/`：默认 XML 配置，实际产品 XML 通常在 `device/<vendor>/<product>/audio/` 或 vendor 下。
- `custom_extensions/`：厂商扩展钩子（若存在）。

## 4. `vendor/transsion/system_modules/audio/frameworks/av/`

Transsion 对 `frameworks/av` 的客制化。常见 hook 点：

- `servics/`（注意原仓库拼写为 `servics`，非 `services`）：对 AudioPolicyService / AudioFlinger 服务层的扩展。
- `media/`：对 `libaudioclient` / `AudioTrack` / `AudioRecord` 的扩展与工具。
- `utils/`：通用工具、场景/能力开关、日志封装。

诊断时关注点：

- 搜索 `TRAN` / `TranAudio` / `transsion` 前缀，快速找到客制化入口。
- 大多数 GMS 路由/行为差异都来源于此目录对 AOSP 的覆盖。

## 5. `vendor/transsion/system_modules/audio/frameworks/base/`

Transsion 对 `frameworks/base` 的客制化，Java 层。

- `services/`：对 `services.jar` 的扩展；Audio 相关的 hook 常在 `com/android/server/audio/` 子路径内，作为 `AudioService` 等类的补丁或子类。
- `media/`：对 `framework.jar` 中 `android.media.*` 的扩展。

## 6. `vendor/mediatek/proprietary/hardware/audio/common/V3/aud_drv/`（MTK HAL 主要源码，本分支可读可改）

MTK 平台 `audio.primary.mediatek.so` 的实现源码。tombstone backtrace 出现该 so 时，**首先到这里找符号定位与补丁点**，不要默认"闭源 so 转 MTK"。文件平铺在该目录下（无 `src/` 子目录）。

### 6.1 典型入口类（按子系统归类，搜索文件名即可快速落位）

- **HAL 门面 / 设备管理**：`AudioALSAHardware.cpp`（HIDL/AIDL `IDevice` 入口，`setParameters` / `getParameters` / `createAudioPatch` / `releaseAudioPatch` / `setConnectedState` 归宿）、`AudioALSAStreamManager.cpp`（stream 生命周期、routing）、`AudioALSADeviceConfigManager.cpp`（device / pcm 配置表）。
- **输出流（下行）**：`AudioALSAStreamOut*.cpp`、`AudioALSAPlaybackHandler*.cpp`、`AudioALSAPlaybackDataProvider*.cpp`（DSP / 非 DSP / offload / direct / hifi / deep_buffer / voip_rx 各路径）。
- **输入流（上行，录音问题首选查看处）**：`AudioALSAStreamIn*.cpp`、`AudioALSACaptureHandler*.cpp`、`AudioALSACaptureDataProvider*.cpp`（Normal / Dsp / DspBt / DspHFP / DspRaw / DspUsb / EchoRef / BLE / BTCVSD / BTSCO / FMRadio / TDM / Voice / VoIP / ModemDai 等）、`AudioALSACaptureDataClient*.cpp`（含 `AudioALSACaptureDataClientAurisysNormal.cpp` — Transsion VoIP crash 常命中此路径的上层）。
- **USB 声卡**：`AudioUSBCenter.cpp`（`setUSBOutConnectionState` / `setUSBInConnectionState` / `set_hifi_config` / 采样率格式能力查询；USB 热插拔阻塞类问题首选入口）、`AudioUSBPhoneCallController.cpp`、`AudioUSBPhoneCallControllerDSP.cpp`。
- **音量 / 增益**：`AudioMTKGainController*.cpp`、`AudioVolumeFactory*.cpp`。
- **音效 / 后处理 / DRC**：`AudioCompFltCustParam.cpp`、`AudioMTKFilter*.cpp`、`AudioMTKStreamOutEffect*.cpp`。
- **通话 / Modem**：`AudioMTKPhoneCallController*.cpp`、`SpeechDriverFactory.cpp`、`SpeechDriver*.cpp`、`AudioMessengerIPI*.cpp`（DSP IPC）。
- **Aurisys（MTK 音频算法框架）集成点**：`AudioALSACaptureDataClientAurisysNormal.cpp`、`AurisysLibManager*.cpp`；算法 so（如 `libvpnr.so`、`libaurisys*.so`）本身仍为闭源，但挂载点、入参、bypass 开关在本目录里。

### 6.2 定位速查（"什么现象 → 去 aud_drv 哪个文件"）

- `+setParameters(...)` 后长时间没有 `-setParameters(...)` → 先搜 `AudioALSAHardware::setParameters`，按传入 key (`connect=` / `disconnect=` / `routing=` / `closing=` / `exiting=`) 分发到 `AudioUSBCenter` / `AudioALSAStreamManager` / 各 `PhoneCallController`。
- `createAudioPatch` / `releaseAudioPatch` 悬空 → `AudioALSAHardware::createAudioPatch`、`AudioALSAStreamManager::routingOutputDevice` / `routingInputDevice`。
- 录音无声 / silence buffer → `AudioALSACaptureDataProvider*.cpp` 的 `readDataFromRingBuffer` / `provideCaptureDataToClient`；静音源头也常落在 `AudioMTKGainController` 的上行增益链。
- `Aurisys` / `TranAudioDenoiseVoIPIgoVP` / `TranAudioVoIPCallController` 相关 crash → `AudioALSACaptureDataClientAurisysNormal.cpp` 的 `processThread` + Aurisys scenario 配置。
- `pcm_open` / `pcm_start` / `pcm_read` / `pcm_write` 失败（常见 `-EBUSY` / `-EPIPE` / `-ENODEV`） → 在 `AudioALSACaptureDataProvider*.cpp` / `AudioALSAPlaybackHandler*.cpp` 找 `pcm_*` 调用点。
- USB 耳机 connect/disconnect 卡 audioserver → `AudioUSBCenter::setUSBInConnectionState` / `setUSBOutConnectionState` / `set_hifi_config`；注意 MTK 会在此处同步轮询 `pcm_params_get`，是高发卡点。

### 6.3 修改注意事项

- 源码开放≠可随意改：该目录属 vendor 代码，改动仍需走厂商对齐（avoid breaking DSP IPC 协议、Aurisys scenario 表、声卡 card/device id 映射、与 kernel 侧 `mixer_paths*.xml` / `audio_device.xml` 的一致性）。
- 红线同样适用：不允许 test-aware 判定；不允许为了规避 TimeCheck 抬高 HAL 超时阈值；任何 `sleep/usleep/poll` 式阻塞都应限制总上界 ≤ 1s，避免击穿 `mediautils::TimeCheck` 看门狗。
- 厂商基线合并：若修改与 MTK 下一次基线合并冲突，优先保留功能补丁并在 commit message 中标注 Jira / 现象，便于后续 rebase。

## 7. `vendor/mediatek/proprietary/external/AudioParamParser/`（参数 XML 解析与热更新）

这个目录不是单一“工具库”，而是 MTK 音频参数的核心解析/缓存/回写模块。后续任何问题里，只要涉及“参数 XML 被读写、热更新、回调通知、libxml2 调用”，都要优先进入这里。

### 7.1 关键文件与职责（按排查优先级）

- `AudioParamParser.c` / `AudioParamParser.h` / `AudioParamParserPriv.h`：`AppHandle` 生命周期、`appHandleParseXml` 初始化、`appHandleThreadLoop`（inotify 监控）、`appHandleReloadAudioType`（热重载）、回调注册与通知。
- `AudioType.c`：`AudioType` 数据结构和参数树写回，重点看 `audioTypeSaveAudioParamXml` / `audioTypeSetFieldData` / `audioTypeSetParamData`。
- `XmlWrapper.c` / `XmlWrapper.h`：`libxml2.so` 的 `dlopen/dlsym/dlclose` 封装，`loadXmlOps` / `unloadXmlOps` 与所有 `appXml*` 调用路径。
- `AudioParam.c` / `AudioParamFieldInfo.c` / `AudioParamUnit.c` / `AudioCategory.c` / `AudioParamTreeView.c`：参数树/字段/分类模型及校验。
- `AudioUtils.c`：公共工具（目录创建、字符串/数组转换、XML 节点辅助等），典型入口 `utilMkdir`。

### 7.2 典型日志锚点（通用）

- `AudioParamParser-vnd`
- `appHandleParseXml`, `appHandleThreadLoop`, `appHandleReloadAudioType`
- `audioTypeSaveAudioParamXml`
- `loadXmlOps`, `unloadXmlOps`
- `inotify_init`, `inotify_add_watch`, `inotify read`

### 7.3 通用问题模型与首查点

- **XML 初始化失败/加载不全**：先看 `appHandleParseXml`、`appHandleLoadDirFeatureOptionsInfo`、`appHandleLoadDirAudioTypeInfo` 的返回路径。
- **cust XML 改完不生效或重复重载**：看 `appHandleThreadLoop` 里 `IN_CLOSE_WRITE` 过滤、`allowReload` 置位与清零、`appHandleReloadAudioType` 是否短路。
- **参数写回失败/文件权限异常**：看 `audioTypeSaveAudioParamXml` + `utilMkdir`；重点核查 `saveDir`、目标文件路径和权限处理。
- **回调链放大（反复通知/反复 setParameters）**：看 `appHandleNotifyAllCallbacks` 与上游 `service/*/Device.cpp` 的联动节流是否缺失。
- **libxml2 相关 crash 或异常栈**：看 `XmlWrapper.c` 的 `loadXmlOps/unloadXmlOps` 生命周期是否与并发调用时序冲突。

### 7.4 解决方案模板（基于本目录代码，可跨问题复用）

- 给“变更触发路径”加去重/节流：对相同 `audioType` 的连续 reload 做时间窗压缩，避免 inotify 风暴触发频繁 parse。
- 把 `libxml2` 生命周期与事件批处理对齐：减少高频 `dlopen/dlclose` 抖动，确保 `loadXmlOps` 与 `unloadXmlOps` 成对且在同一控制域。
- 收敛回调重入：`appHandleNotifyAllCallbacks` 前后增加重入保护或异步队列，避免 callback 反向触发 parser 再入。
- 固化写盘路径与权限校验：在 `audioTypeSaveAudioParamXml` 写盘前后打印完整路径、统一 `mkdir/chmod` 失败处理，防止 silent fail。
- 核对写盘后权限调用参数：`audioTypeSaveAudioParamXml` 里 `chmod` 必须使用真实文件路径（`filePath`），避免对空串或错误路径调用导致“保存成功但权限未落地”。
- 统一锁顺序：遵守 `AppHandle lock -> AudioType lock` 的固定顺序，避免 reload/save 并发互锁。

## 8. 闭源 so 映射（读不到源码，但要认识）

这些 so 出现在 tombstone backtrace 里时，注意"可做什么、不可做什么"：

- `/vendor/lib64/hw/audio.primary.mediatek.so`（MTK）：音频 HAL 实现。**本分支源码已开放**（见 §6），优先在 `vendor/mediatek/proprietary/hardware/audio/common/V3/aud_drv/` 直接定位与修复；只有当 backtrace 落在该 so 但符号无法在 §6 源码中找到时，才视为真正"闭源部分"并转 MTK。
- `/vendor/lib64/hw/audio.primary.<soc>.so`（QCOM 或其它 SoC）：在本仓内可能是闭源，按传统方式仅从 vendor/transsion 侧影响其入参。
- `/vendor/lib64/libaurisys*.so`、`/vendor/lib64/libvpnr.so`、`/vendor/lib64/libspeex*.so`、`/vendor/lib64/libwebrtc*.so`：音效/降噪/回声消除算法库。crash 落这里时，通常是上层 buffer/状态错或算法库自身缺陷；可在 §6 的 `AudioALSACaptureDataClientAurisysNormal.cpp` 等挂载点做入参校验 / bypass。
- `/vendor/lib64/hw/android.hardware.audio@*-impl.so` / `/vendor/bin/hw/android.hardware.audio.service-aidl.*`：HAL 服务宿主。

## 9. 配置文件（也算"代码"）

- `audio_policy_configuration.xml`：mixPort / devicePort / flags / profile / routes。实际生效文件在 `device/<vendor>/<product>/audio/` 或 `vendor/<vendor>/proprietary/.../`，项目通常用 include 拼装 `audio_policy_configuration_7_0.xml` 之类。
- `audio_policy_engine_configuration.xml` / `audio_policy_engine_product_strategies.xml`：可配置策略引擎的规则表。
- `audio_effects.xml` / `audio_effects.conf`：音效挂载。
- `mixer_paths*.xml`（QCOM 常见）/ `audio_device.xml`（MTK 常见）：底层通路描述。

## 10. "这个现象去看哪里"速查

- 某 App 录不到声且日志有 `App op ... missing` → `AudioService.java`（权限）→ `RecordThread`/`RecordTrack` 的 `setSilenced`。
- `createTrack / createRecord` 返回非 0 → `AudioFlinger.cpp` + `AudioPolicyManager.cpp` 的 `getXxxForAttr`。
- 路由选错设备 → `AudioPolicyManager::getDeviceForAttributes` + `enginedefault/` + Transsion 客制化覆盖。
- GMS Latency Fail → HAL buffer 尺寸 + `audio_policy_configuration.xml` 的 fast/raw profile + `fastpath/`。
- Secure 音频失败 → `audio_policy_configuration.xml` 的 `AUDIO_OUTPUT_FLAG_SECURE` + `AudioFlinger::createTrack`。
- 蓝牙/耳机插拔后 crash → `AudioDeviceBroker.java` + `AudioDeviceInventory.java` + `AudioPolicyManager::setDeviceConnectionStateInt`。
- backtrace 含 `Tran*` → Transsion 定制 hook 点，优先去 `vendor/transsion/system_modules/audio/` 查。
- backtrace 含 `audio.primary.mediatek.so` 且符号形如 `android::AudioALSA*` / `android::AudioUSBCenter*` / `android::Aurisys*` → **MTK HAL 本仓源码**，直接去 `vendor/mediatek/proprietary/hardware/audio/common/V3/aud_drv/` 按文件名落位（见 §6）。
- 日志含 `AudioParamParser-vnd` / `appHandleThreadLoop` / `audioTypeSaveAudioParamXml` / `loadXmlOps` / `unloadXmlOps` → 先查 `vendor/mediatek/proprietary/external/AudioParamParser/`（见 §7），再联动 HAL `setParameters` 入口定位触发源。
- USB 耳机插拔引发 audioserver TimeCheck / ANR / 崩溃 → `vendor/mediatek/proprietary/hardware/audio/common/V3/aud_drv/AudioUSBCenter.cpp` 的 `setUSB{In,Out}ConnectionState` / `set_hifi_config` 是首个检查点；kernel 侧配合看 `usb_set_interface failed (-110)`。
