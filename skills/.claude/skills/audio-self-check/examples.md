# Audio 自检示例

以下示例用于指导该 Skill 的实际调用方式。示例中的路径和项目名可替换为当前任务实际值。

## 示例 1：仅执行宏控 + DTS + Dolby（不做铃声）

### 示例输入

```text
请按 audio-self-check-sop 执行音频自检。
代码基础路径=z:/workspace/mtk/cm8_rd
项目名=cm8_h973
升级前音效代码路径=z:/workspace/mtk/cm8_rd_a15_ref
音频软件配置表:
- TRAN_AUDIO_FS1589N_SUPPORT=yes
- TRAN_AUDIO_AW87XXX_SUPPORT=yes
暂不做铃声检查。
```

### 期望输出（中文）

```markdown
# 音频自检结论

## 执行范围
- 本次执行章节：一、音频软件配置；二、DTS 音效自检；三、杜比音效自检
- 跳过章节及原因：四、铃声资源配置确认（用户未触发）；五、PA参数路径检查（用户未要求）

## 检查结果
- 音频软件配置：存在差异，ProjectConfig.mk 缺少 TRAN_AUDIO_AW87XXX_SUPPORT 宏定义
- DTS音效自检：通过，submix 已去除，且与 Android 15 参考定义一致
- 杜比音效自检：通过，fromSystemDevice 各通道定义与 Android 15 一致
- 铃声资源配置确认：未执行，未提供铃声检查类型
- PA参数路径检查：未执行，用户未要求

## 差异与改动清单
- 差异项：TRAN_AUDIO_AW87XXX_SUPPORT（期望 yes，实际缺失）
- 改动项：无

## 风险与待确认
- 请用户确认是否补齐 TRAN_AUDIO_AW87XXX_SUPPORT 宏控后再继续处理

## 总结结论
- 本次音频自检已完成核心配置核对，DTS 与 Dolby 配置正常，存在 1 项宏控差异待用户确认。
```

## 示例 2：执行 TECNO 铃声检查

### 示例输入

```text
请按 audio-self-check-sop 执行铃声检查。
代码基础路径=z:/workspace/mtk/cm8_rd
项目名=cm8_h973
铃声检查：TECNO铃声检查
升级后铃声资源路径=z:/workspace/mtk/cm8_rd/vendor/vendor/transsion/projects/cm8_h973/audio/tones
```

### 期望输出（中文）

```markdown
# 音频自检结论

## 执行范围
- 本次执行章节：四、升级前后铃声资源配置确认（4.2 TECNO 铃声检查）
- 跳过章节及原因：其余章节用户未要求

## 检查结果
- 音频软件配置：未执行，用户未要求
- DTS音效自检：未执行，用户未要求
- 杜比音效自检：未执行，用户未要求
- 铃声资源配置确认：存在差异，ringtones 缺少 `MorningSun`，notifications 多出 `Notify_Test`
- PA参数路径检查：未执行，用户未要求

## 差异与改动清单
- 差异项：
  - ringtones 缺失：MorningSun
  - notifications 多余：Notify_Test
- 改动项：无（铃声检查章节仅对比，不修改文件）

## 风险与待确认
- 请用户确认是否以参考文档为准补齐/删除差异音频资源

## 总结结论
- TECNO 铃声资源存在差异，建议按参考文档修正后复检。
```

## 示例 3：执行 PA 参数路径检查并按规则修改

### 示例输入

```text
请按 audio-self-check-sop 执行 PA 参数路径检查并完成允许范围内修改。
代码基础路径=z:/workspace/mtk/cm8_rd
项目名=cm8_h973
```

### 期望输出（中文）

```markdown
# 音频自检结论

## 执行范围
- 本次执行章节：五、PA 参数路径检查
- 跳过章节及原因：一至四章节用户未要求

## 检查结果
- 音频软件配置：未执行，用户未要求
- DTS音效自检：未执行，用户未要求
- 杜比音效自检：未执行，用户未要求
- 铃声资源配置确认：未执行，用户未要求
- PA参数路径检查：已按规则修改，平台参数与 PA 参数路径均已更新到 odm 路径

## 差异与改动清单
- 差异项：发现历史路径 `/vendor/etc/audio_param` 与 SOP 目标路径不一致
- 改动项：
  - `aurisys_config*.xml`：`mtk_bessound` 的 `param_path` 改为 `/odm/etc/vconfig/audio/audio_param`
  - `aurisys_config*.xml`：`mtk_speech_enh` 的 `param_path` 改为 `/odm/etc/vconfig/audio/audio_param`
  - `aurisys_config*.xml`：`aurisys_demo` 的 `param_path` 改为 `/odm/etc/vconfig/audio/audio_param`
  - `aurisys_config*.xml`：`smartpa_aw88xxx` 的 `param_path` 改为 `/odm/etc/vconfig/audio/pa_param`

## 风险与待确认
- 请用户确认本次改动是否提交到当前分支；如需回归验证，请补充音频播放与通话场景测试结果

## 总结结论
- PA 参数路径已按 SOP 完成修正，建议联调验证后合入。
```

## 使用建议

- 若任务只覆盖某一章节，结论中必须标注“未执行”的章节及原因。
- 若存在“仅对比不修改”的章节，改动清单必须保持为“无”。
- 所有结论必须使用中文，避免英文替代。
