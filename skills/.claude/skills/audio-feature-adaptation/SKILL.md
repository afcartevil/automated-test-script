---
name: audio-feature-adaptation
description: 协助 Android 开发者在升级前后 vendor 分支之间完成 Audio 特性适配。用户提到 Audio 特性适配、音频 SOP、DTS、Dolby、大音量、HAC、超声波距感、低功耗系统语音通话、LE Audio offload、超声防误触、无网通讯、音频参数迁移、ProjectConfig.mk 音频宏控、aurisys_config 或 Transsion 音频特性移植时使用。
---

# Audio 特性适配

使用该 Skill 协助开发者将 Transsion Android Audio 特性从升级前 vendor 分支适配到升级后 vendor 分支。

## 硬性规则

1. 只执行请求特性的 SOP 步骤，不自行增加 SOP 之外的适配动作。
2. 执行该 Skill 时，不读取、不调用、不依赖任何其他 Skill。
3. 必填输入缺失、路径无法唯一确定、目标文件已有冲突适配、或 SOP 未覆盖当前分支/平台形态时，必须先询问开发者再继续。
4. 所有修改必须幂等：宏控或文件内容已经正确时，只报告跳过原因，不重复改写。
5. 不得遗漏 SCM 提醒。即使没有代码文件变更，SCM 提醒仍是 SOP 输出的一部分。
6. 修改 XML/JSON/MK 文件前，先检查当前内容，并保留无关的项目已有改动。
7. 修改后先验证关键宏控、复制文件和必要 XML/JSON 节点，再报告完成。

## 必要输入

修改前先阅读 [INPUTS.md](INPUTS.md)，并收集：

- 升级前 vendor 绝对路径
- 升级后 vendor 绝对路径
- 从 SPUG 获取的升级前项目编译选项
- 需要适配的特性列表
- 适配低功耗系统语音通话时，需要 ADSP 支持情况和 ADSP 类型

## 执行流程

1. 按 [INPUTS.md](INPUTS.md) 解析并校验输入。
2. 推导 `base_code`、`base_code_sunmao`、`project_name`、`project_name1`、`project_name2` 和 `platform_name`。
3. 阅读 [COMMONS.md](COMMONS.md)，遵守通用宏控、文件复制、XML/JSON、验证和提问规则。
4. 只读取本次请求特性对应的参考文件：
   - DTS: [FEATURE_DTS.md](FEATURE_DTS.md)
   - Dolby: [FEATURE_DOLBY.md](FEATURE_DOLBY.md)
   - 大音量: [FEATURE_SUPER_VOLUME.md](FEATURE_SUPER_VOLUME.md)
   - 听力助手 HAC: [FEATURE_HAC.md](FEATURE_HAC.md)
   - 超声波距感: [FEATURE_ULTRASOUND_PROXIMITY.md](FEATURE_ULTRASOUND_PROXIMITY.md)
   - 低功耗系统语音通话: [FEATURE_LOW_POWER_CALL.md](FEATURE_LOW_POWER_CALL.md)
   - 低功耗蓝牙音频: [FEATURE_LE_AUDIO_OFFLOAD.md](FEATURE_LE_AUDIO_OFFLOAD.md)
   - 超声距感口袋防误触: [FEATURE_USND_ANTI_TOUCH.md](FEATURE_USND_ANTI_TOUCH.md)
   - 无网通讯: [FEATURE_BTTRAN_CALL.md](FEATURE_BTTRAN_CALL.md)
5. 按 SOP 顺序执行每个选中特性。若用户指定多个特性的顺序，优先保持用户顺序；否则按上方顺序执行。
6. `scripts/audio_feature_adapt.py` 只能作为可选辅助工具，用于信息检查、宏控检查、特性计划和验证；脚本不得替代 SOP 判断。
7. 按 [REPORT_TEMPLATE.md](REPORT_TEMPLATE.md) 输出结果。

## 阻塞问题

遇到以下情况必须询问开发者并暂停：

- 编译选项无法按 `_` 至少拆出 `project_name1` 和 `project_name2`
- 升级后项目目录无法唯一确定
- `MTK_PLATFORM` 缺失、重复或相互矛盾
- 请求低功耗系统语音通话适配，但 ADSP 支持情况或类型未知
- SOP 指定的路径、宏控、XML 节点、`param_id` 或场景在目标分支中不存在
- 目标文件已存在，且内容与准备复制的源文件不同
- 当前平台需要 SOP 明确分支之外的处理方式

## 输出约定

始终包含：

- 输入摘要：路径、项目名、平台、选中特性
- 分特性执行结果：修改文件、复制文件、跳过项和阻塞项
- 验证摘要：宏控值、文件存在性、关键节点/属性
- 开发者待处理事项：SOP 中所有 SCM 属性和手动调试提醒
