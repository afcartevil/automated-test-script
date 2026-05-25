# 阶段 6：变更汇总 + 验证建议 + 未决项交付

**目标**：本阶段不再改文件，把前 5 个阶段的"改了什么 + 还差什么"拼成一份可交付给 leader / FAE / AFE 的总结，并附上验收建议。

## 一、变更总汇

按 repo 给一份 patch-set 风格的汇总，**仅列相对路径与改动要点**，不重复贴大段补丁。

```
[01-projects-repo]
modified  vendor/transsion/projects/{project_name_sunmao}/ProjectConfig.mk
            macros set: <列出本次写入的 N 个宏控>
deleted   vendor/transsion/projects/{project_name_sunmao}/audio/<不匹配的旧 PA 目录>
copied    vendor/transsion/projects/{project_name_sunmao}/audio/<PA>/...
modified  vendor/transsion/projects/{project_name_sunmao}/audio/<aurisys_config*.xml>
            path rewrite: /vendor/etc/audio_param -> /odm/etc/vconfig/audio/audio_param  (N hits)
modified  vendor/transsion/projects/{project_name_sunmao}/audio/audio_device.xml
            merged N diff blocks from pre-upgrade project xml
copied    vendor/transsion/projects/{project_name_sunmao}/audio/audiotest/<wav 文件>

[02-kernel-dts]
modified  kernel/<kernel-ver>/arch/arm64/boot/dts/mediatek/{project_name_sunmao}.dts
            nodes: <PA 节点 / tran_audio_controller / typec switch 节点>
            tran_pa_type=<X>, tran_typec_type=<Y>, gpios=<...>

[03-preloader-dws]
modified  vendor/mediatek/proprietary/bootable/bootloader/preloader/custom/{project_name_sunmao}/dct/dct/codegen.dws
            GPIOs: <N>

[04-dct-dws]
modified  vendor/mediatek/proprietary/tools/dct/dws/{platform_name}/{project_name_sunmao}.dws
            GPIOs: <N>

[05-custom-dws-factory]
modified  vendor/mediatek/proprietary/custom/{project_name_sunmao}/kernel/dct/dct/codegen.dws
            GPIOs: <N>
modified  vendor/mediatek/proprietary/custom/{project_name_sunmao}/factory/factory.ini
            menuitems commented: 5; Audio.Mic.Sets=<...>; Audio.Input.TypecHeadset=<...>
```

> 上面是格式示例，**真实内容必须由 SKILL 按实际改动填写**，不要直接粘贴本模板。

## 二、未决项清单（合并阶段 1~5 的"还差什么"）

按优先级排列。强制未决项（红色）必须在 PR/Gerrit 提交前闭环：

### 2.1 强制未决项（红线项，未闭环不应合入）

- [ ] `vnd12_to_vnd16` 专项：已通知 AFE 升级前后 ARSI API 版本 / PA 算法库版本 / 集成方式（AP / ADSP HIFI / ADSP RV55）/ PA 参数是否可复用？
- [ ] `vnd12_to_vnd16` 专项：已找 FAE 索取升级后的 PA 算法 so 并按 FAE 指示落位？
- [ ] aurisys 路径改写 100% 完成（Grep `/vendor/etc/audio_param` 应返回 0 命中）？
- [ ] 4 个 PA `*_SUPPORT` 宏控互斥？
- [ ] 3 处 DWS（preloader / tools/dct / proprietary/custom）GPIO 配置完全一致？

### 2.2 待开发者人工确认项（黄线项）

- 升级前文件值 vs 软件配置表值冲突的宏控清单（含每条冲突的取值来源）。
- PA 文件 OR 候选源中存在多个来源且内容不同的文件清单。
- audio_device.xml 中涉及节点移除/改名的 diff 清单（SKILL 已拒绝自动迁移）。
- audiotest 音源缺失清单（如有）。

### 2.3 跳出 SOP 的专家推断点（灰线项，建议复核）

> 这部分由 SKILL 在执行过程中显式声明，落在本节。如完全按 SOP 走完，则本节为空。

- 跳出点 1：`<阶段 X 步骤 Y>` ——理由：`<...>` ——本 SKILL 决策：`<...>`。
- 跳出点 2：...

## 三、验证建议

把 [references/verify-commands.md](../references/verify-commands.md) 中的 7 节作为"建议命令清单"附上，**不替开发者执行**。

简化版"首次起机三连"（开发者建议优先跑）：

1. `adb shell dumpsys media.audio_flinger` → 看 mixer / record 线程是否正常起。
2. `adb shell dmesg -T | grep -iE 'tran_audio_controller|aw87|fsm|oca|hl1280|sliptswitch'` → 看 driver probe。
3. `adb shell tinycap /sdcard/cap.wav -D 0 -d 0 -c 2 -r 48000 -t 5 && adb pull /sdcard/cap.wav` → 录音冒烟。

## 四、给 FAE / AFE 的咨询模板（vnd12 → vnd16 专用）

**仅在 `scenario == vnd12_to_vnd16` 时输出**。开发者可直接抄改并发邮件 / 群消息。

```
Hi FAE/AFE,

我们在做项目 {project_name_sunmao}（平台 {platform_name}）的 vnd12 非榫卯 → vnd16 榫卯升级，关于 PA 算法 so 移植，需要确认以下几点：

1. ARSI API 版本：升级前 vnd12 我们使用的是 1.6.0，升级后 vnd16 我们了解的是 1.9.0；是否正确？
2. 当前项目使用 PA 类型：{PA 类型 与型号}。请提供升级后该 PA 的算法 so，落位路径建议参考榫卯方案标准。
3. 算法集成方式（AP 侧 / ADSP HIFI / ADSP RV55）：我方平台 DTS 检测结果为 {ADSP 检测结果}。请确认集成方式。
4. PA 参数兼容性：升级前我们已有以下 PA 参数文件 <列举 AW_DSP.bin / preset_*.bin / ocs_params.bin>，升级后是否可直接复用？若不可复用，请提供升级后版本与 release notes。
5. aurisys_config_rv.xml / aurisys_config_hifi3.xml：vnd12 侧 SOP 未覆盖。请确认升级后侧使用哪一份模板（项目层 or 平台层），并提供模板。

谢谢，
{开发者签名}
```

## 五、阶段 6 输出契约

按 [SKILL.md §输出契约](../SKILL.md) 三栏：

| 项 | 内容 |
| --- | --- |
| 本阶段改了什么 | 无文件写入；产出"变更总汇" + "未决项清单" + "验证建议" + "FAE/AFE 咨询模板"（仅 vnd12→vnd16） |
| 还差什么 | 等价于 §2 未决项清单 |
| 是否继续 | 询问开发者"是否需要 SKILL 协助生成 commit message 草稿？"——但 **不替开发者执行 git/gerrit 操作**。 |

## 六、跳出条款

- 阶段 1~5 中任一强制未决项（红线项）仍未闭环 → 阶段 6 拒绝输出"全部完成"的乐观结论，必须显式标注"PR 不应在 X 项闭环前合入"。
- 开发者要求 SKILL 直接 `git commit` / `repo upload` → 拒绝并解释（见 [SKILL.md §安全红线](../SKILL.md)）。
