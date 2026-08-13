# 输出报告模板（强制四节）

最终回答必须按本模板输出。**严禁**以下反模式：只列关键字、只讲 Android 音频背景、只复述日志、只给一句"转某某模块"。任何结论必须可追溯到证据链。

## 模板

```markdown
# Audio 问题分析报告：<一句话标题>

## 1. 【证据链】

### 1.1 问题分类
- 分类：<上行录音 | Audio Crash | GMS 测试失败 | 跨类/超纲>
- 子场景：<权限静音 / 路由 / HAL 通路 / Tombstone SIGSEGV / CTS 路由 Fail / ...>
- 推理模式：<严格按 workflow | 跳出 SOP 后专家推断>
  - 若"跳出 SOP"，简述触发条件（例如："锚点全部未命中"、"失败项不在 §三 分类"、"tombstone 残缺"）及所依据的一般性机制（例如："依 AudioFlinger 锁序约束"、"依 CDD 5.x 条款"）。

### 1.2 日志证据
- 文件：`<相对或绝对路径>`
- 关键片段（附行号）：
  ```
  <Line 27572>: 02-13 14:49:24.920039 1803 6053 I audioserver: App op 27 missing, silencing record ...
  <Line 27582>: 02-13 14:49:24.939258 1803 2019 D AF::RecordTrack: setSilenced: track with port id: 1327, (silenced)
  ```
- （仅当 Audio Crash 且命中 [../workflows/audio-crash.md](../workflows/audio-crash.md) §问题 6 触发条件时）追加 kernel_log 对齐片段：
  ```
  <Kernel [44894.413149]>: usb 2-1: 1:1: usb_set_interface failed (-110)
  <对齐到 main_log 04:05:41.193 AudioALSAHardware: +setParameters(...;connect=...)>
  ```
  不触发该条件的报告直接省略本小节，不用硬塞。

### 1.3 代码证据（如适用）
- 文件与范围：`frameworks/av/services/audioflinger/Tracks.cpp:L<start>-L<end>`
- 关键片段（引用真实代码时用代码引用块）：
  ```<start>:<end>:<relative_path_under_branch_root>
  <真实代码>
  ```

### 1.4 配置证据（如适用）
- `audio_policy_configuration.xml` 中相关 `mixPort` / `devicePort` / `profile` 声明。

## 2. 【根因层级】

主根因层级（择一为主，并发问题可标注次要）：
- [ ] App 层（权限/调用错误）
- [ ] Framework 层（AudioService / AudioFlinger / AudioPolicy 逻辑或锁序）
- [ ] HAL 层（vendor 闭源 so 缺陷或定制实现）
- [ ] Kernel/DSP（驱动、压缩解码）
- [ ] 配置层（XML profile / flag 声明与能力不符）
- [ ] 硬件（麦克风/前端/功放）
- [ ] 第三方算法库（libvpnr、Aurisys、Speex、WebRTC 等）
- [ ] Transsion 定制（`vendor/transsion/system_modules/audio/`）

简述：<用 2-4 句说明为什么是这个层级，引用 1.2/1.3 的证据>。

## 3. 【修改方案】

按以下结构给出。不允许"建议修复"这种不落地的话。

### 3.1 改动点 1
- 文件：`<相对路径>`
- 位置：`<函数/类/XML 节点>`
- 改动思路：<1-2 句说明意图>
- 补丁草案：
  ```<start>:<end>:<relative_path_under_branch_root>
  <现状代码>
  ```
  建议改为（伪代码/最小增量）：
  ```diff
  - <old>
  + <new>
  ```

### 3.2 改动点 N
（同上）

### 3.3 不能直接改的部分
仅在根因落在**真正闭源**的 so（第三方算法库 `libvpnr.so` / `libaurisys*.so` / `libspeex*.so` / `libwebrtc*.so`，或本分支内无源码的 `audio.primary.<非 mediatek>.so`）或 DSP/SCP 固件时填写。
注意：MTK HAL（`audio.primary.mediatek.so`）在本分支内**源码开放**（`vendor/mediatek/proprietary/hardware/audio/common/V3/aud_drv/`），属于可直接改动的范畴，应在 3.1/3.2 给出真实补丁，不要放到本节。
- 现象：<>
- 推断的调用契约/入参问题：<>
- 需芯片/算法厂商处理的范围：<>
- 系统侧可做的规避（可选）：<最小入参校验 / 功能开关默认关 / bypass 第三方库 / 在 `aud_drv/` 上层挂载点做防御>

### 3.4 禁止项（自检）
- [ ] 未加入 `if (isCtsCaller(uid))` 或任何按包名/UID 判断是否测试进程的分支。
- [ ] 未在未确认产品能力声明的前提下删除 `AUDIO_OUTPUT_FLAG_SECURE` / `offload` 等 profile。
- [ ] 未在不匹配的 `BuildId` 下做 `addr2line` 并当作定论。
- [ ] 未以"先 A 再 B"硬串代替"证据驱动"下的判断。
- [ ] 若已跳出 SOP：方案仍满足红线（不引入 test-aware 分支、不盲删 profile、不破坏 AIDL/Binder 兼容）、并明确给出"依据 X 做出此推断"的一句话说明。

## 4. 【验证方法】

### 4.1 必做复测
- 操作步骤：<最小复测步骤>
- 预期结果：<通过 / 日志中不再出现 X / Y 指标在 Z 范围>

### 4.2 需补抓的日志（若当前证据不足）
- `adb logcat -b all -v threadtime > main_log.txt`
- `adb shell dumpsys media.audio_flinger > af_dump.txt`
- `adb shell dumpsys audio > audioservice_dump.txt`
- GMS 单项重跑：
  - `atest <Module>:<pkg.Class>#<method>`，或
  - `run cts -m <Module> -t <pkg.Class#method>`

### 4.3 回归范围
- 正向：<必须仍然通过的场景，例如蓝牙切换、通话、VoIP>
- GMS：<需要一起跑的 CTS/VTS/GTS 模块>
- 功能：<通话上行/下行、录音、播放>
```

## 使用要点

- 证据链必须给 log **行号**与代码**文件:行号**；只写"日志显示..."会失去可追溯性。
- 若某节因为证据不足暂时无法完成，**保留节标题并明确写出"证据不足，需要用户补充 X"**，不要整节省略。
- 引用本仓代码时使用代码引用块格式（`startLine:endLine:filepath`）。
- 引用不在本仓的外部代码（vendor 闭源 so 的公开符号、Android 上游代码）时使用普通代码块，不伪造行号。
- 允许在证据不足时"跳出 SOP 基于专家知识推断"，但必须在 1.1 标记"推理模式=跳出 SOP"并说明所依据的一般性机制；跳出不是放弃举证，而是把依据换成机制/规范层面的事实。
