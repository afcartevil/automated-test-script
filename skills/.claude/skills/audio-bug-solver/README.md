# Audio Bug Solver SKILL 使用与维护指导手册

> 适用对象：Audio 模块开发者、系统集成工程师、SKILL 维护者。
> 配套文件：同目录下 [`SKILL.md`](SKILL.md) 及 `workflows/` `references/` `examples/`。

---

## 目录

- [1. SKILL 简介](#1-skill-简介)
- [2. 使用方法与注意事项](#2-使用方法与注意事项)
- [3. 后续音频问题拓展指南](#3-后续音频问题拓展指南)
- [4. 效果调优与反馈机制](#4-效果调优与反馈机制)
- [附录 A：FAQ](#附录-afaq)
- [附录 B：变更日志规范](#附录-b变更日志规范)

---

## 1. SKILL 简介

### 1.1 定位

`audio-bug-solver` 是一个面向 Android Audio 问题分析的 Cursor 项目级 SKILL，负责协助开发者**定位根因并给出可落地修复方案**，目前覆盖三类高频问题：

| 分类 | 典型现象 | 工作流 |
|------|----------|--------|
| 上行录音 | 第三方/系统 App 录音无声、音量偏小、被静音 | [`workflows/uplink-recording.md`](workflows/uplink-recording.md) |
| Audio Crash | `audioserver` / `android.hardware.audio.service*` / `audio.primary.*.so` native crash、Watchdog SIGKILL | [`workflows/audio-crash.md`](workflows/audio-crash.md) |
| GMS 测试失败 | CtsMediaAudioTestCases / VtsHalAudio* / GtsMediaTestCases / CtsVerifier 音频用例失败 | [`workflows/gms-test-failure.md`](workflows/gms-test-failure.md) |

### 1.2 设计哲学

遵循"策略哲学 + 最小完备工具集 + 必要事实说明"，具体见 [`SKILL.md`](SKILL.md) 的《设计哲学》节。关键取向：

- **证据驱动**：每条结论可追溯到 log 行号或代码文件:行号，不臆造。
- **并行收集**：同层次证据（log 锚点、代码入口、配置文件）一次并行检索，再做层级裁决。
- **结果导向**：SOP 只是脚手架；当严格执行失败时，模型被**授权跳出**，改用 Android 音频栈专家知识具体问题具体分析，前提是守住红线。
- **红线不可越**：禁止 test-aware 分支、禁止盲删 XML profile、禁止在闭源 so 上臆造源码改动。

### 1.3 目录结构

```
.cursor/skills/audio-bug-solver/
├── SKILL.md                          # 顶层入口：触发描述、输入契约、分诊图、输出契约、红线
├── README.md                         # 本文件：使用与维护手册
├── workflows/                        # 按问题类别拆分的工作流
│   ├── uplink-recording.md
│   ├── audio-crash.md
│   └── gms-test-failure.md
├── references/                       # 跨问题共享的事实资料
│   ├── code-map.md                   # 五大代码目录入口速查
│   ├── log-keywords.md               # 分层稳定关键字词典
│   └── report-template.md            # 四节报告强制模板
└── examples/
    └── case-studies.md               # 三类端到端案例
```

设计约束：

- 顶层 `SKILL.md` ≤ 200 行（当前约 107 行），保持薄路由。
- 每个 `workflows/*.md` < 250 行，单一职责。
- `references/` 为稳定事实；`examples/` 为示范，不作规则。

---

## 2. 使用方法与注意事项

### 2.1 触发方式

SKILL 的 `description` 已写入大量命中词，以下场景会被 Cursor 自动推荐或由模型主动加载：

- 用户消息含：`录音无声` / `上行静音` / `App op missing` / `silencing record` / `audioserver 崩溃` / `tombstone` / `SIGSEGV audio` / `CtsMediaAudioTestCases fail` / `Vts HalAudio` / `GtsMediaTestCases` 等。
- 用户粘贴 `mobile_log` / `main_log` / `crash_log` / `tombstones` / `test_result.xml` 片段并且语义指向 audio。

若模型未自动用本 SKILL，可显式指示：
> 请使用 audio-bug-solver SKILL 分析以下问题。

### 2.2 标准输入契约

调用 SKILL 时，顶层三项 `branch_root` / `log_dir` / `issue` 必须都提供。其中 `issue` 内部字段按"必填 / 建议 / 可选"三档分级，不强求面面俱到。

1. `branch_root`（**必填**）：分支代码的**绝对路径**。该路径下需能相对解析到：
   - `frameworks/base/services/core/java/com/android/server/audio/`
   - `frameworks/av/services/audioflinger/`
   - `frameworks/av/services/audiopolicy/`
   - `vendor/transsion/system_modules/audio/frameworks/av/`
   - `vendor/transsion/system_modules/audio/frameworks/base/`
2. `log_dir`（**必填**）：日志目录的**绝对路径**。建议包含：
   - `mobile_log/`（内含 `main_log`、`events_log`、`kernel_log`）
   - `crash_log/` 或 `tombstones/`
   - `test_result.xml`（如为 GMS 问题）
   - 产品 `audio_policy_configuration.xml`（如为路由/Secure/Offload 问题）

   关于 `kernel_log`：SKILL **不默认**读取 kernel 日志。只有在 Audio Crash 且命中 [`workflows/audio-crash.md`](workflows/audio-crash.md) §问题 6 的触发条件时（HAL hang 已成立、`TimeCheck timeout` 点名、USB 音频动作相关、`SIGBUS` 指向共享内存等），模型才会拉取并与 main_log 做时间对齐；若此时 `log_dir` 下无 kernel 日志，SKILL 会主动请你补抓（`adb shell dmesg -T` / EngineerMode `sys_kernel_log`）。录音类、GMS 测试类问题无需提供 kernel_log。
3. `issue`（**必填**整体，但内部字段分级）：
   - **必填**：现象描述（"谁"在"什么场景下"发生"什么异常"）。
   - **建议提供**：问题发生时间戳（用于在 `main_log` 中对齐窗口，可以是大致的时间范围；不提供时模型需要自己从日志里圈定异常段，可能增加分析耗时或引入不确定性）。
   - **可选**：复现步骤、复现概率、机型、芯片平台（MTK/QCOM/Unisoc）、Android 版本、ROM 版本。

对于可选字段：若模型判断分析结果**依赖**某项（例如 MTK/QCOM 的关键字词典不同、Android 版本影响 AppOps 行为），它会主动用 AskQuestion 追问；你提供后继续分析，避免基于空气假设。
对于可选字段：若模型判断分析结果**不依赖**某项（例如现象已经足够清晰、证据链自洽），则可直接给出结论，不需要强行索取。

### 2.3 推荐使用流程

1. **准备日志**：把手机上的 `mobile_log` / `crash_log` / `tombstones` 拖到一个固定目录；GMS 问题另外拉 `test_result.xml`。
2. **撰写一段紧凑 prompt**：最简形式只需顶层三项 + `issue` 中的现象描述即可。
   最小例：
   ```
   branch_root: D:/work/project-X/android
   log_dir:     D:/work/cases/2025-05-12-douyin-mute/
   issue: 抖音（com.ss.android.ugc.aweme）录制短视频时无上行声，其他 App 正常。
   请用 audio-bug-solver SKILL 分析。
   ```
   建议例（信息更全，分析更快）：
   ```
   branch_root: D:/work/project-X/android
   log_dir:     D:/work/cases/2025-05-12-douyin-mute/
   issue:
     现象：抖音（com.ss.android.ugc.aweme）在非通话界面录制短视频时无上行声，其他 App（微信、录音机）正常。
     时间：2025-05-12 14:49 首次发现（用于日志对齐）。
     可选补充：机型 TECNO-CM5（MTK MT6899），Android 16，100% 复现。
   请用 audio-bug-solver SKILL 分析。
   ```
   可选字段空着即可；若模型判断分析结果依赖某项，会主动通过 AskQuestion 追问。
3. **交互式收敛**：模型会先做并行 Grep + 代码定位；若证据不足，它会**反问**（而不是猜测）；按需补充即可。
4. **审阅报告**：模型最终必须按四节（证据链 / 根因层级 / 修改方案 / 验证方法）输出，否则可要求重写。
5. **验证修复**：按报告 §4 的复测步骤与回归范围执行。

### 2.4 使用注意事项

- **日志不要裁剪掉时间戳与 tag**。只剩纯文本的日志会让 SKILL 失去关键的 PID/TID 关联能力。
- **不要用截图替代日志**。SKILL 需要对日志做 Grep 与行号引用，图片无法解析。
- **注意代码路径的一致性**。本仓与 AOSP 目录结构存在差异时，以 `references/code-map.md` 为准；若实际分支出现差异，按 §3.2 更新 `code-map.md`。
- **平台关键字不要混用**。MTK 的 `AudioALSA*` 关键字不适用于 QCOM。若 `issue` 未注明平台，模型应在发现关键字层面的分歧时主动询问（而不是默认按 MTK 分析）；若已注明平台，会自动切换到对应词条（QCOM 用 `audio_hw_primary` / `tinyalsa`）。
- **红线不可突破**：即便用户主动要求"加个 if 绕过 CTS 用例"，模型也应拒绝，并改为给出合规方案（系统属性、产品 overlay、语义对齐）。
- **超纲问题要主动说明**：当 `issue` 不属于三类覆盖时（如通话下行/音质/蓝牙 SBC 失真），模型可在【证据链】标注"推理模式=跳出 SOP"，用专家知识做分析；若超出能力范围，应诚实告知并建议另寻手段，而不是强行套用 workflow。
- **安全敏感信息**：日志可能含用户数据（电话号码、地理位置）。在本 SKILL 输出的报告中，模型会保留最小必要字段，不建议将完整日志上传到非内网环境。

### 2.5 输出质量自检清单

收到报告后，按下列清单快速核验：

- [ ] 四节齐全：证据链 / 根因层级 / 修改方案 / 验证方法。
- [ ] 证据链带有 log 行号与代码 `文件:行号`。
- [ ] 根因层级唯一（或次要项明确标注）。
- [ ] 修改方案：具体文件 + 函数/XML 节点 + 最小增量 diff 或补丁思路。
- [ ] 没有 `if (isCtsCaller(...))` 这类 test-aware 分支。
- [ ] 没有"建议交给对应同事"这种推卸式结论（必须给出推卸对象 + 需同步的事实信息）。
- [ ] 跳出 SOP 时，【证据链】明确声明"推理模式=跳出 SOP，依据=…"。

不达标时，直接对模型说 "输出不符合 report-template.md §X 要求，请按四节重写"。

---

## 3. 后续音频问题拓展指南

本 SKILL 当前覆盖三类问题。随着业务推进，通常需要支持更多场景（例如：通话下行、蓝牙音频、AAudio 低时延、Spatial Audio、Haptic Generator、Keep-alive 录音、HFP/A2DP 编解码等）。

### 3.1 何时需要扩展

出现任一条件即可考虑扩展：

- 一个新类别问题在近 1–2 个月内重复出现 ≥ 3 次。
- 现有 workflow 的"SOP 失效时跳出"路径承载了大量未归档的专家推断。
- 用户反复针对同一类问题写相似的补充说明，证明 SOP 覆盖不足。

### 3.2 扩展操作流程（标准）

1. **定义新问题分类**：明确边界（适用/不适用）、主锚点关键字、典型日志/现象样本，写在本手册的"附录 C 草案"或临时笔记中。
2. **新建 workflow 文件**：
   - 路径：`workflows/<kebab-case-name>.md`，例如 `workflows/call-downlink.md`。
   - 结构沿用既有五段式：进入条件 / 证据收集 / 层级裁决 / 输出 / SOP 失效时跳出 / 常见陷阱。
   - 行数控制在 250 行以内；超长时把事实资料拆入 `references/`。
3. **更新顶层 [`SKILL.md`](SKILL.md)**：
   - `description` 追加新类别的触发词（注意总长度 ≤ 1024 字符）。
   - mermaid 分诊图追加一条判据边（→ 指向新 workflow）。
   - 《路由到工作流》列表追加新条目。
4. **丰富 [`references/log-keywords.md`](references/log-keywords.md)**：
   - 按"主锚点 / 辅助锚点"的格式追加新分组。
   - 仅加入**跨版本稳定**的关键字，避免依赖特定数字 id、特定版本 tag。
5. **丰富 [`references/code-map.md`](references/code-map.md)**：
   - 若新问题牵涉当前未列的目录或关键类/函数，按"目录 → 负责层 → 典型入口"的格式增补。
6. **新增或复用案例 [`examples/case-studies.md`](examples/case-studies.md)**：
   - 端到端写一个真实案例，展示 log 行 → 代码行 → 补丁思路全链路。
   - 每增加一个新类别，至少补一个对应案例，保证模型能学到该类别的推导范式。
7. **更新报告模板 [`references/report-template.md`](references/report-template.md)**（按需）：
   - 若新类别的【证据链】或【修改方案】需要特殊字段（例如 BT 问题需要 `bt_snoop.log`），在模板中新增可选小节。
8. **回归验证**：
   - 把历史 3 例该类别问题（越难越好）喂给 SKILL，观察产出是否仍满足四节契约与红线；
   - 喂一例**不属于**该新类别的问题，确认分诊仍能正确命中旧 workflow 而不误走新 workflow。
9. **登记变更**：按《附录 B：变更日志规范》在本手册末尾登记。

### 3.3 扩展时的六条硬约束

- **顶层 SKILL.md ≤ 200 行**。超了就往 `workflows/` / `references/` 下沉。
- **每个 workflow < 250 行**。再长就拆成 `workflows/<name>/main.md` + `workflows/<name>/advanced.md`，但需保留入口 `<name>.md`。
- **不允许跨目录复制关键字**。关键字只在 `references/log-keywords.md` 一处维护，workflow 只引用片段与锚点。
- **不允许按测试包/UID 切换系统行为**。任何新 workflow 的"修改方案"不得教模型写 `isCtsCaller(uid)` 之类。
- **路径一律正斜杠**。不出现 `workflows\foo.md` 这种 Windows 写法。
- **不引入自动化脚本**。SKILL 内不写需要本地安装依赖的脚本，保持跨环境可用。

### 3.4 典型扩展示例（参考骨架）

若要新增"通话下行音质问题"workflow：

```
workflows/call-downlink-quality.md:

# 通话下行音质问题工作流
## 一、进入条件
- issue 含"通话杂音/回声/音量偏小/单向听不见"
- main_log 含 audio_mode=IN_CALL、setParameters ... vt_ 等
## 二、证据收集
- 锚点：AudioService 的 setMode、TelecomManager 通话状态、AudioDeviceBroker 通信设备切换、
        HAL 侧 SetCallMode / setParameters "vt_"、Modem 侧 dsp_tune 等
## 三、层级裁决
- 3.1 通话模式未进入 IN_CALL → Telecom/Telephony
- 3.2 Modem/DSP 调音参数异常 → 调音工具/tuning
- 3.3 路由选择错误 → AudioPolicy/AudioDeviceBroker
- 3.4 音效/EC/NS 错配 → HAL 音效链
## 四、输出
## 五、SOP 失效时跳出
## 六、常见陷阱
```

按 §3.2 的步骤落地即可。

---

## 4. 效果调优与反馈机制

SKILL 不是一次写完就定型，必须通过"使用 → 观察 → 诊断 → 调整"的闭环持续优化。以下给出可操作的调优清单与反馈流程。

### 4.1 常见问题模式与对应调整

| 症状 | 可能原因 | 调整手段 |
|------|----------|----------|
| 模型没触发本 SKILL | description 缺少用户实际用的关键词 | 在 [`SKILL.md`](SKILL.md) 的 `description` 追加该词（注意 1024 字符上限） |
| 触发了本 SKILL 但跑错 workflow | mermaid 分诊边判据不精确，或关键字与别类冲突 | 细化分诊判据，必要时在 workflow §一《进入条件》增加"排除项" |
| 模型只给背景不给修改方案 | 模型忽略了输出契约 | 在对话中引用 [`references/report-template.md`](references/report-template.md)，要求按四节重写；若反复出现，给 report-template 的"使用要点"增加**强化语气** |
| 修改方案"太泛"、不落地 | workflow 的"代码锚点"段过薄，没给函数名 | 把具体入口类/方法补进 workflow + [`references/code-map.md`](references/code-map.md) |
| 搜不到关键字但问题真实存在 | 日志关键字词典过时（tag 被厂商改名/升级） | 更新 [`references/log-keywords.md`](references/log-keywords.md)；若是版本差异，在词条后加"版本：XX+ 起生效"的注释 |
| 出现 `isCtsCaller(uid)` 等违规建议 | 模型从旧 SOP/历史对话里复用了反模式 | 再次在 workflow 的"红线"节显式列出该反模式并给出替代方案 |
| 跨平台误用关键字（MTK 词条用到高通机型） | workflow 未强制要求按 `issue` 的芯片平台切换 | 在 workflow §二"证据收集"中把平台分支写成必选步骤 |
| 跳出 SOP 没留痕迹 | 报告模板的"推理模式"字段被忽略 | 加一个自检条目（已加），并在 report-template §3.4 禁止项中列为红线 |
| 报告太长、重点不突出 | workflow 罗列过多背景 | 把背景迁移到 `references/`，workflow 只保留"做什么"的指令 |
| 报告太短、缺关键证据 | SKILL 未强制要求 log 行号引用 | 加强 report-template §1.2 的"附行号"要求 |

### 4.2 调优流程（最小闭环）

1. **记录不满意样本**：保留一次 prompt + 模型输出 + 期望输出（简短说明差距），建议放 `z:\Audiocode\.cursor\skills\audio-bug-solver\_feedback/` 目录（新建、可选）。
2. **定位根因**：对照 §4.1 表判断属"触发问题 / 分诊问题 / 工作流问题 / 输出问题"四类之一。
3. **做最小修改**：改动集中在对应文件，避免一次性大改多个文件。
4. **回归样本**：重跑最初那条样本 + 历史 3–5 条代表性样本，确认不退化。
5. **登记变更**：在本手册末尾的《变更日志》追加一条，给清楚"改了什么、为什么、怎么验证"。

### 4.3 反馈与协作渠道

- **同步 SOP 源文档**：SKILL 来源于飞书 SOP 文档。当 SOP 更新（新增案例、修正结论）时，按 §3.2 的步骤同步到 workflow；**反向**：当 SKILL 在实战中修正了 SOP 的错误（例如本 SKILL 已修正的 `isCtsCaller(uid)` 反模式），应回写到飞书 SOP 原文，避免两处漂移。
- **团队内反馈**：鼓励使用者在遇到不满意时按 §4.2 §1 记录样本。样本可以匿名化但不要过度脱敏到失去调试信息。
- **周期性体检**：建议每季度一次，跑 10–20 例历史问题，统计"报告一次通过率 / 需返工率 / 红线违反次数"三项指标，红线违反必须 0。
- **大版本升级前复盘**：Android 主版本升级（涉及 audio HAL AIDL / AudioAttributes / AudioDeviceInfo 语义变化）时，集中复盘 `references/` 两份事实资料的准确性。

### 4.4 何时考虑"重写"而非"小改"

如果出现以下情况，不要继续打补丁，直接重构：

- `SKILL.md` 被补丁补到超过 200 行且结构混乱。
- 某个 workflow 已超过 250 行仍在继续叠加。
- `references/log-keywords.md` 出现同一关键字在多组重复登记，且语义冲突。
- mermaid 分诊图的判据互相覆盖，出现多条边同时命中同一证据。

重构流程：

1. 用 Git 基于当前版本打 tag（例如 `skill-audio-bug-solver-v1`）。
2. 按 §1.3 的目录约束重新设计大纲，保留命名不变以确保外部引用不失效。
3. 迁移内容：先迁 `SKILL.md` → `workflows/` → `references/` → `examples/`，逐文件验证。
4. 用既有历史样本回归，至少 5 条全类别覆盖。

---

## 附录 A：FAQ

**Q1. 我用的是 QCOM 平台，SKILL 里写的 MTK 关键字还能用吗？**
A：不能直接套用。`issue` 里务必注明芯片平台；SKILL 会切换到高通关键字（`audio_hw_primary` / `tinyalsa` / `msm_*`）。若 SKILL 没切换，直接提醒"本例芯片为 QCOM，请按高通关键字重新分析"。

**Q2. 问题跨了两类（既有 crash 又有 GMS），走哪条 workflow？**
A：按主证据走一条为主线，另一条在【根因层级】节标注为次要。通常 crash 优先（因为它通常是 GMS 失败的直接原因）。

**Q3. 日志里找不到任何 SKILL 列的关键字怎么办？**
A：进入"SOP 失效时跳出"模式。模型会显式声明跳出，用 Android 音频栈一般性机制推断，同时必须在报告里写清推断依据与不确定性。

**Q4. 可以让 SKILL 帮我直接改代码吗？**
A：可以。SKILL 输出的报告 §3【修改方案】本身就是以文件+函数+diff 的形式给出；确认方案后，你可以让模型继续 apply 到代码仓。但建议**先审**再 apply，避免对 audioserver/AudioPolicy 这类关键路径误改。

**Q5. `audio.primary.*.so`、`libvpnr.so` 这类 so 的 crash 能不能在系统侧改？**
A：分两类：
- **MTK HAL（`audio.primary.mediatek.so`）**：本分支内**源码开放**，在 `vendor/mediatek/proprietary/hardware/audio/common/V3/aud_drv/`（入口类详见 `references/code-map.md` §6），应直接定位到 `.cpp` 文件改代码并给出补丁，不要误判成"闭源只能转厂商"。
- **真正闭源的第三方算法 so**（`libvpnr.so` / `libaurisys*.so` / `libspeex*.so` / `libwebrtc*.so` 等）：只能用"生命周期防御 / 入参校验 / bypass 开关"做**规避**（挂载点通常在 MTK HAL 的 `AudioALSACaptureDataClientAurisysNormal.cpp` 等），并把 `BuildId` 与调用栈提交给算法厂商修底层。

**Q6. 我想加一个 `PROJECT-RULES.md` 覆盖部分 workflow 结论，行吗？**
A：不推荐。建议直接改对应 workflow，保持 SKILL 内单一事实来源。若是纯产品级差异，放到产品 overlay 中由系统属性控制，不要让 SKILL 维护产品分支。

---

## 附录 B：变更日志规范

每次对 SKILL 做非排版修改，请在此登记一条。格式：

```
## <YYYY-MM-DD> — <作者>
### 改动范围
- <文件 1>：<一句话说明>
- <文件 2>：<一句话说明>
### 改动动机
- <为什么要改，原问题样本链接>
### 回归验证
- <跑了哪些历史样本，结果如何>
```

示例：

```
## 2025-05-20 — 葛枫龙
### 改动范围
- workflows/audio-crash.md：问题 2 新增"Binder oneway 饿死"子场景
- references/log-keywords.md：G 组追加 `HangDetector`、`slow operation` 辅助锚点
### 改动动机
- 近一个月 5 例 audioserver SIGKILL 中，2 例根因为 binder thread pool 饿死而非互斥锁死锁，旧 workflow 无法识别
### 回归验证
- 回归 3 例历史死锁样本、2 例本次新样本，全部命中正确层级
```

### 变更日志（按时间倒序追加）

<!-- 在此追加新条目 -->

- 2026-04-21 — 初版：新增 `audio-bug-solver` SKILL，覆盖上行录音 / Audio Crash / GMS 测试失败三类问题；修正原 SOP 中的若干反模式（test-aware 分支、`App op 27` 数字硬编码、MTK/QCOM 关键字混用、offload profile 无条件删除）。
- 2026-04-21 — 强化结果导向：SKILL.md 新增"灵活变通与结果导向"原则与"SOP 失效时跳出条款"；三个 workflow 末尾各加一节"SOP 失效时的跳出"；report-template 新增"推理模式"字段。
- 2026-04-21 — 新增本《使用与维护指导手册》（README.md）。
- 2026-04-21 — 新增"kernel_log 按需读取"机制：主要实现集中在 [`workflows/audio-crash.md`](workflows/audio-crash.md) 新增的 §问题 6（触发判据 / 时间基线对齐 / 子系统锚点 / 三层时间线 / 底层状态三归类 / errno 速查 / 证据强度契约）；[`references/log-keywords.md`](references/log-keywords.md) 补入 L 组（USB / ALSA / ADSP / MTK tinysys / 同步阻塞 / 内核 Panic / errno / 易混点）作为触发时的查阅词典；[`references/report-template.md`](references/report-template.md) §1.2 追加一条"触发时才附 kernel 片段"的轻提示；本 README §2.2 `log_dir` 下加一条温和说明。日常录音类 / GMS 测试类问题无需读 kernel_log，避免噪声。
