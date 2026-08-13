# Audio Crash 工作流

**适用范围**：`audioserver` 崩溃、`android.hardware.audio.service*` 等 HAL 进程 Native Crash、`system_server` 中 Audio 相关线程崩溃、Audio 模块引发的 Watchdog SIGKILL。

**不适用**：Java 层应用在 `AudioRecord.start()` 抛 `IllegalStateException` 但进程未死（走业务线排查）；仅通话质量问题（走专项）。

## 一、进入条件

- `tombstones/` 或 `crash_log/` 中存在 `Fatal signal` 且 `Cmdline` 指向 `audioserver` / `android.hardware.audio.service*` / `system_server`（且 backtrace 含 `libaudio*` / `audio.primary.*.so`）。
- `main_log` 出现 `F libc`、`F DEBUG`、`FATAL EXCEPTION` + 进程被重启的节奏。
- Watchdog 相关：`system_server` 打印 `WATCHDOG KILLING: ... audio` 并对 `audioserver` 发 `SIGKILL`。

## 二、证据收集（并行）

同时发起以下 Grep（`-n` 带行号，范围 `{log_dir}`）：

- Tombstone/Signal：`Fatal signal|tombstone|backtrace|FATAL EXCEPTION|Cmdline:|>>> |DEBUG   :|abort_message|Scudo ERROR|CHECK failed|Assertion`
- Audio Framework：`AudioFlinger|AudioPolicyService|AudioPolicyManager|APM_|RecordThread|PlaybackThread|MixerThread|audioserver|createRecord|createTrack`
- Audio HAL：`AudioALSA|android.hardware.audio|audio.primary|pcm_open|pcm_read|pcm_write|compress_|Aurisys`
- Transsion 定制：`TRAN|TranAudio|transsion`
- Watchdog：`Watchdog|WATCHDOG|Sending signal|SIGKILL|slow operation|blocked in|HangDetector`

## 三、分析框架（证据驱动，五问）

不要把顺序当成流水线，按最先收敛的一问下钻。

### 问题 1：崩溃的是谁？

从 tombstone header 读 `Cmdline`、`pid/tid/name`、`signal/code/Cause`：

```
Cmdline: /vendor/bin/hw/android.hardware.audio.service-aidl.mediatek
pid: 1237, tid: 22370, name: processThread_1
signal 11 (SIGSEGV), code 1 (SEGV_MAPERR), fault addr 0x0
Cause: null pointer dereference
```

**分流**：

- `Cmdline` 含 `audioserver` → 去问题 2。
- `Cmdline` 含 `android.hardware.audio.service*` 或 backtrace 主导 `.so` 为 `audio.primary.*.so` / `libvpnr.so` / `libaurisys*.so` → 去问题 3。
- `Cmdline = system_server` 但 backtrace 含 `AudioService.java` / `AudioDeviceBroker.java` / `libaudiosystem*` → 视为 Framework 层，用问题 2 的思路配合 Java 栈处理。
- 均不符 → 记录观察到的线索后回到 SKILL 顶层再分诊。

### 问题 2：audioserver 自身 crash 还是被 HAL 拖死？

**Signal 语义**（记住就够，不要混）：

- `SIGSEGV (11)`：非法访问。`code 1 SEGV_MAPERR` 常为空指针；`code 2 SEGV_ACCERR` 常为权限或 UAF。
- `SIGABRT (6)`：主动 abort，常伴 `abort_message:` 行（`CHECK failed`、`assertion failed`、`Scudo ERROR: double free`）。
- `SIGBUS (7)`：对齐/共享内存错，多见 DSP 共享 buffer 异常。
- `SIGKILL (9)` 且 tombstone 常**没有** backtrace（或只是进程退出记录）→ 几乎必是被外部 kill：优先查 Watchdog。

**判据（对原 SOP 步骤 2 的修正）**：audioserver 被 `SIGKILL` 并非一定"HAL 拖死"，需区分：

- (a) HAL 真正 hang：`main_log` 中 HAL 侧出现某个 `+openXxx` / `+writeXxx` / `+standby` 打印，**在崩溃前 3–10 秒内没有对应的 `-openXxx` 收尾**；同时 audioserver 线程栈（若有 `ANR` dump 或 `debuggerd -b <pid>` 抓到的栈）卡在 IPC 等待 HAL 返回 → 根因在 HAL/Kernel。
- (b) audioserver 自身锁序问题：HAL 侧 `+/- ` 正常成对，audioserver 多线程互相等锁（典型 `AudioFlinger::mLock` 与 `AudioPolicyService::mLock` 交叉）→ 根因在 Framework。
- (c) audioserver 单线程自陷在某个长耗时操作（大循环、大 map 遍历、日志过量）→ 根因在 Framework。

只有 (a) 才能把结论写成"HAL 导致 audioserver 超时"，(b)(c) 属 audioserver 自身缺陷。

**代码锚点**：

- `frameworks/av/services/audioflinger/AudioFlinger.cpp`、`PlaybackTrack.cpp`、`RecordTrack.cpp`、`Threads.cpp`。
- `frameworks/av/services/audiopolicy/managerdefault/AudioPolicyManager.cpp`、`service/AudioPolicyService.cpp`、`service/AudioPolicyInterfaceImpl.cpp`。
- `frameworks/base/services/core/java/com/android/server/audio/AudioService.java`、`AudioDeviceBroker.java`、`AudioDeviceInventory.java`。
- Transsion 定制：`vendor/transsion/system_modules/audio/frameworks/av/{media,servics,utils}/`、`.../frameworks/base/{services,media}/`。
- **MTK HAL 源码（本分支可读可改）**：`vendor/mediatek/proprietary/hardware/audio/common/V3/aud_drv/`（`AudioALSAHardware.cpp`、`AudioALSAStream{Manager,In,Out}.cpp`、`AudioUSBCenter.cpp`、`AudioALSACaptureDataProvider*.cpp`、`AudioALSACaptureDataClientAurisysNormal.cpp`、`AudioMTKPhoneCallController.cpp` 等，按 [../references/code-map.md §6](../references/code-map.md) 落位）。判据 (a)"HAL 真正 hang" 或 backtrace 含 `audio.primary.mediatek.so` 时，**先到此目录按符号名定位具体函数**，不再先走"转 MTK"流程。
- **MTK 参数 XML 解析链路**：`vendor/mediatek/proprietary/external/AudioParamParser/`（`AudioParamParser.c`、`AudioType.c`、`XmlWrapper.c`）。若日志/栈出现 `AudioParamParser-vnd`、`appHandleThreadLoop`、`audioTypeSaveAudioParamXml`、`loadXmlOps/unloadXmlOps`、`libxml2`，优先检查此目录的解析/热更新/回调路径，再联动 HAL `setParameters` 触发源。

### 问题 3：Audio HAL 崩溃在哪一段？

读 backtrace（从 #00 往上看，`#00` 是最深处），典型条目：

```
#00 pc 0xe01088  /vendor/lib64/libvpnr.so
#01 pc 0x46e938  /vendor/lib64/hw/audio.primary.mediatek.so (android::TranAudioDenoiseVoIPIgoVP::process(...)+88)
#02 pc 0x465dc0  /vendor/lib64/hw/audio.primary.mediatek.so (android::TranAudioVoIPCallController::TranAudio_UlProcess(...)+384)
#03 pc 0x21360c  /vendor/lib64/hw/audio.primary.mediatek.so (android::AudioALSACaptureDataClientAurisysNormal::processThread(...)+3308)
```

**判据**：

- `#00` 落在第三方算法库（`libvpnr.so`、`libaurisys*.so`、`libspeex*.so`、`libwebrtc*.so`）→ 第三方库缺陷或上层传入非法 buffer/参数。
- `#00` 落在 `audio.primary.*.so` 且函数名含 `Tran*`（如 `TranAudioDenoiseVoIPIgoVP::process`）→ **Transsion 定制的 HAL 扩展**。本仓虽不含 HAL so 源码，但定制逻辑常在 `vendor/transsion/system_modules/audio/frameworks/av/` 有上层调用/配置，需核对 hook 入参。
- `#00` 落在 `libc.so` 且 `abort_message` 指向 `Scudo ERROR: invalid chunk state` / `double free` / `heap buffer overflow` → 内存破坏，往上找首个业务栈。
- `#00` 在 `libbinder` 且上层是 AudioFlinger/AudioPolicy → 多为 IPC 死对象访问，配合 main_log 看 client 端是否已 `died`。

### 问题 4：Tombstone 符号化（如何把 `pc` 变成源码行号）

本分支内可符号化的源码范围：AOSP 开源部分（`libaudioflinger.so`、`libaudiopolicymanager*.so`、`libaudioutils.so` 等）**以及 MTK HAL**（`audio.primary.mediatek.so`，源码在 `vendor/mediatek/proprietary/hardware/audio/common/V3/aud_drv/`，构建产物 unstripped so 通常在 `out/target/product/<device>/symbols/vendor/lib64/hw/audio.primary.mediatek.so`）。真正闭源的是第三方算法 so（`libvpnr.so`、`libaurisys*.so`、`libspeex*.so`、`libwebrtc*.so` 等），它们无源码。

**操作指引**（给开发者，不替用户执行）：

1. 取 tombstone 中 `BuildId: <id>`。
2. 在对应构建产物目录（一般为 `out/target/product/<device>/symbols/system/lib64/...` 或 `.../vendor/lib64/hw/...`）找同名 so，用 `readelf -n` 或 `file` 核对 BuildId 一致。
3. 使用：
   - `llvm-symbolizer --obj=<unstripped.so> <pc_hex>`，或
   - `aarch64-linux-android-addr2line -C -f -e <unstripped.so> <pc_hex>`。
4. 若 BuildId 对不上，说明符号与崩溃镜像不匹配，结论不可信，需要拉取对应版本的符号。

对真正闭源的第三方算法 so 只记录现象与调用契约，交回厂商；而 MTK HAL（`audio.primary.mediatek.so`）符号化后应继续追到 `vendor/mediatek/proprietary/hardware/audio/common/V3/aud_drv/` 里的具体源码行给出修复。

### 问题 5：崩溃前 5 秒发生了什么？

在 `main_log` 中取 tombstone 时间戳往前 5 秒窗口，重点扫：

- 路由切换：`setDeviceConnectionState`、`routingOutputDevice`、蓝牙 `BT_SCO_ON`、耳机插拔 `WIRED_HEADSET`。若切换过程中 crash → 资源并发释放/生命周期问题。
- Track 生命周期：`createAudioPatch`、`releaseAudioPatch`、`createTrack` / `createRecord` / `destroyTrack`。频繁创建销毁 + crash → 计数/智能指针泄漏或 race。
- 音效/VoIP：`setParameters ... input_source=`、`Aurisys`、`AEC`、`NS`、`TranAudio*`。VoIP 通话切换场景是 Transsion 定制逻辑的高发区。
- 内存/低内存：`lowmemorykiller`、`Out of memory`。

若窗口内出现某个 `+opXxx` 无对应 `-opXxx`，直接锁定 HAL hang（回到问题 2 判据 a）。

### 问题 6：是否需要下钻到 kernel_log？（按需触发，不是默认步骤）

**原则**：kernel_log（`dmesg` / `sys_kernel_log` / `logcat -b kernel`）信息密度大、信噪比低，不作为默认读取对象。**只在证据链已经延伸到 HAL 以下、且仅凭 main_log / tombstone 无法闭环**时才读，避免无谓噪声。其他 crash 场景（空指针、锁序死锁、第三方算法库越界等）根本不需要 kernel_log 就能收敛。

#### 6.1 触发判据（命中任一再考虑读 kernel_log）

- **HAL hang 已成立且方向明确**：问题 2 判据 (a) 成立（`+opXxx` 无对应 `-opXxx`、audioserver 栈卡在 IPC 等 HAL），想进一步区分"HAL 自身无退避 / 驱动卡死 / 硬件无响应"三者之一。
- **`Abort message` 直接点名 HAL 阻塞**：如 `TimeCheck timeout for IAudioFlinger::...` / `IAudioPolicyService::setDeviceConnectionState`、`binder ... hung`、`analysis [Blocked directly due to HAL call: ...]`。
- **崩溃窗口内发生 USB 音频设备动作**：`main_log` 出现 `UsbAlsaManager: USB Audio Device Added/Removed`、`AudioService: onUsbDeviceAdded`、`APM_AudioPolicyManager: setDeviceConnectionStateInt(..., 0x4000000, ...)` / `0x82000000`，且现象与该动作有时间相关性。
- **`SIGBUS` 或 Scudo 报错指向共享内存 / DMA buffer**：tombstone 的 `Cause` / `abort_message` 含 `SIGBUS`、`alignment`、`ion`、`dmabuf`、或栈帧里有 `compress_*` / `pcm_mmap` / `snd_pcm_*`。
- **连锁系统性卡死**：`system_server` ANR 同时伴随 `audioserver` 被 watchdog kill，现有 5 步无法区分"锁序死锁 / binder 饿死 / 底层设备卡死"时。

**不触发的典型反例**（即使是 crash，也别去拉 kernel_log）：

- backtrace 明确指向 `libvpnr.so` 等第三方闭源算法 so 崩溃 → 直接按问题 3 给"转厂商 + 在 `aud_drv/AudioALSACaptureDataClientAurisysNormal.cpp` 等上层挂载点加入参校验 / bypass 开关"。
- backtrace 指向 MTK HAL 本仓符号（`audio.primary.mediatek.so` 中 `android::AudioALSA*` / `android::AudioUSBCenter*` / `android::AudioMTKPhoneCallController*` 等） → 直接去 `vendor/mediatek/proprietary/hardware/audio/common/V3/aud_drv/` 对应 `.cpp` 改代码，不走"转厂商"。
- `CHECK failed` / `assertion failed` 条件清晰 → 按问题 2 (b)(c) 解决。
- 锁序死锁证据充分（两把锁、两个线程、反向加锁） → Framework 层修复，kernel 无关。

#### 6.2 操作步骤（触发后才执行）

1. **定位并读取 kernel_log**：按常见命名优先级搜：`kernel_log` / `sys_kernel_log` / `mobile_log/kernel_log*` / `dmesg.txt`。若均不存在，AskQuestion 向用户索取（`adb shell dmesg -T` 或工厂工具抓取的 `sys_kernel_log`）；在 kernel_log 拿到前，不要硬下"底层有问题 / 底层没问题"的结论。

2. **时间基线对齐**：kernel 时间戳是相对启动秒（`[sec.usec]`），与 main_log 墙钟不同。通用做法：在两份日志里找同一事件做标定，常见三种：
   - USB 音频事件：main_log `UsbAlsaManager: USB Audio Device Added/Removed` ↔ kernel `usb \d+-\d+: new ...-speed USB device` / `USB disconnect`。
   - 声卡注册/卸载：main_log `AudioService: onAudioServerDied` 或 `sound_trigger` 启停 ↔ kernel `sound: card\d+` / `snd_*` 加载。
   - 蓝牙连接：main_log `BluetoothEventManager` ↔ kernel `Bluetooth: HCI Event` / `btusb`。
   用标定事件算出偏移量 `Δ = T_abs − T_kernel`，再外推整个异常窗口。

3. **按子系统并行 Grep**（范围 `kernel_log`，完整锚点见 [../references/log-keywords.md](../references/log-keywords.md) L 组；下面只给最常用的一组）：
   - USB：`usb \d+-\d+: (USB disconnect|new .* USB device|.*usb_set_interface failed|reset .* USB device)`、`idVendor=.* idProduct=`
   - ALSA / 声卡：`snd_pcm_|snd_compress_|snd_soc_|xrun|cannot submit urb`
   - DSP / 协处理器：`adsp|subsystem_restart|ssr|q6afe|q6asm|rproc|load_firmware fail|scp|tinysys`
   - 同步阻塞：`binder[_:].*hung|rcu: INFO|blocked for more than \d+ seconds|watchdog: BUG: (soft|hard) lockup`
   - 内核 Panic：`Unable to handle kernel|Internal error: Oops|Kernel panic|BUG: KASAN`

4. **构建三层时间线**：把同一窗口内 `main_log`（用户空间）→ HAL log（AudioALSA 等）→ kernel_log 三层日志按时间对齐，作为【证据链】的一部分。示例：
   ```
   main_log   04:05:41.192  APM_AudioPolicyManager: setDeviceConnectionStateInt(...USB, state=1)
   main_log   04:05:41.193  AudioALSAHardware: +setParameters(card=1;connect=...;device=0)
   kernel     [44894.413149] usb 2-1: 1:1: usb_set_interface failed (-110)     ← 同步调用被卡在此
   kernel     [44899.533626] usb 2-1: 1:1: usb_set_interface failed (-110)     ← 5.12s 后的重试仍失败
   kernel     [44904.655321] usb 2-1: 1:1: usb_set_interface failed (-110)     ← 第三次 -110
   tombstone  04:05:58.193  SIGABRT: TimeCheck timeout ... elapsed 17000ms
   ```
   三层时间戳闭合 = HAL 在 17s 内被 kernel 的三次 ETIMEDOUT 阻塞，根因在 HAL 没做超时退避，而不是 kernel USB 异常。

5. **底层状态归类**（结论限定，择一写入报告）：
   - **kernel / driver bug**：驱动自身 `Oops`、`KASAN`、DMA 越界、ring buffer 被踩。修改方向在驱动/BSP。
   - **硬件/外设异常被 kernel 正确报告**：如热插拔导致 `-110 ETIMEDOUT`、`-19 ENODEV`、`USB disconnect`+快速重新枚举。修改方向在 HAL / Framework 加入防御（超时退避、热插拔去抖、降级路径）；kernel 无需改。
   - **kernel 仅是被动报告**：异常由 HAL 错误的 ioctl 序列、非法入参、非对齐 buffer 触发。修改方向在 HAL / Framework 自身。
   区分错了，修复方向就错了——所以必须明确归一类。

#### 6.3 errno 速查（HAL 侧常见，看到就往 kernel_log 核对一次）

| errno | 含义 | 典型 kernel 侧触发点 |
|------|------|---------------------|
| `-110` ETIMEDOUT | 下行硬件/总线超时 | USB NAK 超时、DSP IPC 超时、I2S DMA 长时无中断 |
| `-32` EPIPE | 管道破裂 | PCM underrun/overrun、USB stall |
| `-19` ENODEV | 设备消失 | 热拔出、remoteproc 掉线、声卡卸载 |
| `-77` EBADFD | PCM 状态机错 | 未 `prepare` 即 `start`、`drain` 期间再 `start` |
| `-5` EIO | 通用 IO 错 | 子系统层面，需回 kernel_log 找具体原因 |

#### 6.4 证据强度契约

- 触发 6.1 且读了 kernel_log 的报告，【证据链】节必须同时给出 main_log 与 kernel_log 片段，两层对齐；只给一侧视为证据不足，对应结论在 §2 根因层级写"待 kernel 证据补强"而不是定论。
- 未触发 6.1 的报告无需此节，不要为了完备性硬塞 kernel_log 片段。

## 四、输出（按根因模式给修改方案）

严格按 [../references/report-template.md](../references/report-template.md) 四节输出。对应典型修复方向：

- **空指针/UAF (SIGSEGV)**：
  - 给出调用栈指向函数的判空/生命周期缺陷点；
  - 多线程处用智能指针 (`sp<>` / `wp<>`) 配合 `Mutex::Autolock`；
  - 明确哪个对象"已被释放却仍被访问"，补 `promote()` 成功性判断。
- **断言失败 (SIGABRT)**：
  - 从 `abort_message` 反推前置条件违反点；
  - 若是 `CHECK(...)` 真值条件不成立，追溯调用链上游的非法入参来源并在入口处拒绝。
- **内存越界/共享内存 (SIGBUS / heap-*)**：
  - 尺寸/对齐核对；DSP 共享内存尾部守卫；
  - Aurisys buffer size 与 `period_size * period_count * frame_bytes` 是否一致。
- **死锁/Watchdog (SIGKILL)**：
  - 梳理 `AudioFlinger::mLock`、`AudioPolicyService::mLock`、`AudioDeviceBroker.mDeviceStateLock` 的加锁顺序；
  - 所有可能反向加锁的路径改为单向拓扑；
  - 长耗时动作（HAL IPC、文件 IO）不要持锁调用。
- **MTK HAL（`audio.primary.mediatek.so`）崩溃或卡顿**：
  - **本分支源码已开放**：在 `vendor/mediatek/proprietary/hardware/audio/common/V3/aud_drv/` 按 backtrace 符号名直接定位到 `.cpp` 文件与函数，给出真实代码改动（空指针保护、生命周期、超时退避、锁序修正等），而不是先推"转 MTK"。
  - 典型高发点：`AudioUSBCenter::setUSB{In,Out}ConnectionState`（USB 热插拔阻塞）、`AudioALSAStreamManager::routing{Input,Output}Device`（路由并发）、`AudioALSACaptureDataProvider*::readDataFromRingBuffer`（录音通路）、`AudioALSACaptureDataClientAurisysNormal::processThread`（Aurisys 算法链上层）、`AudioMTKPhoneCallController`（通话切换）。
  - 若修改涉及与 DSP/SCP 固件 IPC 协议（`AudioMessengerIPI*`）或改变 card/device id、mixer_paths 契约，仍需对齐厂商基线。
- **第三方闭源算法库（`libvpnr.so` / `libaurisys*.so` / `libspeex*.so` / `libwebrtc*.so`）崩溃**：
  - 输出现象 + 调用契约 + 入参快照，明确"非系统侧可直接修复"，转厂商；
  - 系统侧规避：在上述 MTK HAL 的挂载点（如 `AudioALSACaptureDataClientAurisysNormal`）加入参校验，或在 `vendor/transsion/system_modules/audio/frameworks/av/` 增加功能开关默认关闭。

## 五、SOP 失效时的跳出（结果导向）

触发跳出的情形：

- tombstone 头/backtrace 残缺（只有 `Sending signal 9` 但没有 `Fatal signal` 头；或 backtrace 中 `#00` 无符号且 so 名残缺）。
- 崩溃栈里完全没有音频相关符号，但 `Cmdline` 指向 audioserver/audio HAL（说明真正的祸根被内联/被优化掉或走异步队列）。
- 多进程连锁崩溃（如 `system_server` 先 ANR、`audioserver` 随后被连带 kill），现有 5 步流程无法描述。
- SIGABRT 的 `abort_message` 指向未覆盖的子系统（如 `fastcapture/fastmixer underrun` 触发 `LOG_ALWAYS_FATAL`、`media.metrics` 自杀、`libnbaio` `MonoPipe` 状态非法）。
- Watchdog kill 但 `dumpsys` 栈显示所有锁都被释放，证明是 IPC/Binder thread pool 饿死而非互斥锁死锁。

跳出时可调用的一般性视角：

- **线程模型**：`FastMixer`/`FastCapture` 非抢占，一旦 `LOG_ALWAYS_FATAL` 直接拉崩 audioserver；`OffloadThread` 依赖 HAL `drain` 回调，回调丢失会导致超时。
- **锁序与 IPC**：`AudioFlinger::mLock` 与 `AudioPolicyService::mLock`、`AudioDeviceBroker.mDeviceStateLock` 的任意二者反序加锁都可能死锁；Binder `oneway` 饥饿会让 HAL 事件卡队列，表现像"HAL hang"。
- **共享内存/对齐**：`SharedBuffer`、`Audio MMAP`、DSP 共享环形 buffer 的读写指针越界常引发 SIGBUS。
- **新旧 HAL 兼容**：AIDL HAL（`android.hardware.audio.service-aidl.*`）与 HIDL HAL（`android.hardware.audio@*-impl`）的生命周期不同，混用或半升级状态下易出空指针。
- **内存破坏链路**：Scudo 报错是即时位置，真正越界点在更早的调用；必须反向构造假设并交叉验证分配/释放点。

跳出后仍需输出完整四节报告，并在【证据链】注明依据（如"依 AOSP `FastMixer::threadLoop` 退路设计推断"）。

## 六、常见陷阱

- 只看 `#00` 就下结论：`#00` 若为 libc，必须往上找首个业务栈；`#00` 为第三方库时，上层定制入参常是真凶。
- 把 `SIGKILL` 一律归因 HAL：必须用"HAL `+/-` 是否成对"判据区分 Framework 自身死锁。
- 用错版本符号符号化：`BuildId` 不一致时的 `addr2line` 结果是**误导**，不要采信。
- 在**真正闭源**的第三方算法 so（`libvpnr.so`、`libaurisys*.so` 等）上"猜代码改动"：只能基于公开符号 + 调用契约写建议，不要凭空写补丁。反过来 MTK HAL（`audio.primary.mediatek.so`）源码在 `vendor/mediatek/proprietary/hardware/audio/common/V3/aud_drv/` 是开放的，应当直接读源码再写补丁，避免把它也误判成"闭源不能改"。
- 忽略 vendor 定制：backtrace 里出现 `Tran*` 符号时，查 `vendor/transsion/system_modules/audio/` 的 hook 点往往比追 AOSP 更快命中。
- kernel_log 的过度 / 不足使用：一方面，每个 crash 都去拉 kernel_log 做 Grep 会淹没主线证据；另一方面，在问题 6.1 触发条件成立时（HAL hang 方向明确、USB 动作相关、SIGBUS 指向共享内存、`TimeCheck timeout` 显式点名）不下钻 kernel_log，会把"HAL 缺超时退避"或"热插拔去抖缺失"误判成"kernel/驱动 bug"。按 6.1 判据开关即可。
