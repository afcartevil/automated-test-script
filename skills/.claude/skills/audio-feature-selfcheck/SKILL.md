---
name: audio-feature-selfcheck
description: 协助 Android 开发者按照 Audio 特性自检 SOP 检查升级后 vendor 分支中的音频特性是否已适配。用户提到 Audio 特性自检、音频特性自检、Audio 自检、音频功能自查、听力助手-MTK、HAC 自检、MTK_HAC_SUPPORT、ProjectConfig.mk 音频宏控检查或升级后 vnd 自检时使用。
---

# Audio 特性自检

使用该 Skill 协助开发者按照 Audio 特性自检 SOP，对升级后的 vnd/vendor 分支执行只读自检。

## 硬性规则

1. 只执行 SOP 已定义的自检步骤，不自行扩展未覆盖特性的结论。
2. 执行该 Skill 时，不读取、不调用、不依赖任何其他 Skill。
3. 自检过程只读，不修改代码、配置或日志文件。
4. 必填输入缺失、路径无法确定、目标文件不存在、宏控冲突或 SOP 未覆盖当前特性时，必须先询问开发者再继续。
5. 注释行中的宏控不能作为有效适配证据。
6. 同一宏控存在多个有效赋值且互相冲突时，结论为 `无法判断`，并列出冲突位置。
7. 输出必须包含输入摘要、分特性结论、证据和阻塞项。

## 必要输入

自检前先阅读 [INPUTS.md](INPUTS.md)，并收集：

- 升级后的 vnd/vendor 侧绝对路径
- 从 SPUG 获取的项目编译选项
- 需要自检的 Audio 特性列表

## 执行流程

1. 按 [INPUTS.md](INPUTS.md) 解析并校验输入。
2. 推导 `base_code_sunmao`、`project_name`、`project_name1`、`project_name2` 等上下文。
3. 阅读 [COMMONS.md](COMMONS.md)，遵守通用只读检查、宏控判定和阻塞规则。
4. 只读取本次请求特性对应的参考文件：
   - 听力助手-MTK: [FEATURE_HAC_MTK.md](FEATURE_HAC_MTK.md)
5. 按 SOP 顺序执行每个选中特性。若用户指定多个特性的顺序，优先保持用户顺序。
6. `scripts/audio_feature_self_check.py` 只能作为可选辅助工具，用于输入解析和宏控自检；脚本不得替代 SOP 判断。
7. 按 [REPORT_TEMPLATE.md](REPORT_TEMPLATE.md) 输出结果。

## 支持特性

当前 SOP 已固化：

- `hac_mtk`：听力助手-MTK

如果开发者请求的特性不在支持清单中，必须说明当前 SOP 未覆盖该特性，并询问是否需要补充 SOP 步骤后再扩展。

## 阻塞问题

遇到以下情况必须询问开发者并暂停：

- 缺少升级后的 vnd/vendor 绝对路径
- 缺少项目编译选项
- 缺少需要自检的特性
- 编译选项无法按 `_` 至少拆出 `project_name1` 和 `project_name2`
- `{base_code_sunmao}/vendor/transsion/projects/{project_name1}_{project_name2}` 不存在
- SOP 指定的检查文件不存在
- 宏控存在多个有效赋值且互相冲突
- 请求的特性超出当前 SOP 支持范围

## 输出约定

始终包含：

- 输入摘要：升级后路径、项目编译选项、项目目录、选中特性
- 分特性自检结果：`已适配`、`未适配` 或 `无法判断`
- 证据：检查文件、命中宏控、有效行内容或缺失说明
- 阻塞项：需要开发者补充或确认的问题
