# audio-feature-adaptation 使用说明

## 1. 这个 Skill 是做什么的

`audio-feature-adaptation` 用于在 **Android vendor 升级前后**，把 Transsion Audio 特性从旧分支迁移/适配到新分支。

- **会做什么**：按 SOP 修改宏控、复制/调整配置文件、输出 SCM 提醒和验证结果
- **不会做什么**：不替代 SOP 做主观判断；不处理 SOP 未覆盖的特性；不依赖其他 Skill

适用场景：平台升级、vnd 合入、新项目从旧项目移植 Audio 特性。

---

## 2. 如何触发

在 Cursor 对话中，用自然语言说明要做 **Audio 特性适配**，并带上必要信息。以下关键词容易命中该 Skill：

- Audio 特性适配、音频 SOP、音频参数迁移
- DTS、Dolby、大音量、HAC、超声波距感
- 低功耗系统语音通话、LE Audio offload、超声防误触、无网通讯
- `ProjectConfig.mk` 音频宏控、`aurisys_config`、Transsion 音频特性移植

**示例提示词：**

```text
请按 audio-feature-adaptation SOP，帮我把以下特性从旧 vendor 适配到新 vendor：
- 升级前路径：Z:\old\vendor
- 升级后路径：Z:\new\vendor
- 项目编译选项：lk7k_xxx_yyy
- 特性：dts、hac、ultrasound_proximity
```

---

## 3. 使用前必须准备的信息

| 输入项 | 说明 | 是否必填 |
|--------|------|----------|
| `base_code` | 升级前 vendor 绝对路径 | 是 |
| `base_code_sunmao` | 升级后 vendor 绝对路径 | 是 |
| `project_name` | SPUG 上的项目编译选项全名（如 `lk7k_xxx`） | 是 |
| `features` | 要适配的特性列表 | 是 |
| ADSP 支持情况 | 仅适配 `low_power_call` 时需要 | 条件必填 |
| ADSP 类型 | `HIFI` 或 `RV`，仅 `low_power_call` 时需要 | 条件必填 |

### 项目名解析规则

`project_name` 按 `_` 拆分：

- 第 1 段 → `project_name1`
- 第 2 段 → `project_name2`
- 项目目录默认为：`{project_name1}_{project_name2}`

升级后项目目录默认路径：

```text
{base_code_sunmao}/vendor/transsion/projects/{project_name1}_{project_name2}
```

平台名从该目录下的 `ProjectConfig.mk` 中读取 `MTK_PLATFORM`（小写）。

---

## 4. 支持的特性

| 内部名称 | 特性 | SOP 文件 |
|----------|------|----------|
| `dts` | DTS | `FEATURE_DTS.md` |
| `dolby` | Dolby | `FEATURE_DOLBY.md` |
| `super_volume` | 大音量 | `FEATURE_SUPER_VOLUME.md` |
| `hac` | 听力助手 HAC | `FEATURE_HAC.md` |
| `ultrasound_proximity` | 超声波距感 | `FEATURE_ULTRASOUND_PROXIMITY.md` |
| `low_power_call` | 低功耗系统语音通话 | `FEATURE_LOW_POWER_CALL.md` |
| `le_audio_offload` | 低功耗蓝牙音频 | `FEATURE_LE_AUDIO_OFFLOAD.md` |
| `usnd_anti_touch` | 超声距感口袋防误触 | `FEATURE_USND_ANTI_TOUCH.md` |
| `bttran_call` | 无网通讯 | `FEATURE_BTTRAN_CALL.md` |

多特性时：若你指定了顺序，按你的顺序；否则按上表顺序执行。

---

## 5. Agent 执行流程（你会看到什么）

1. 校验输入，推导项目目录和 `platform_name`
2. 阅读 `COMMONS.md` 和对应 `FEATURE_*.md`
3. 按 SOP 逐步修改/复制文件（已正确则跳过，并说明原因）
4. 验证宏控、文件存在性、关键 XML/JSON 节点
5. 按 `REPORT_TEMPLATE.md` 输出报告，包含 **SCM 属性** 和 **手动调试提醒**

### 报告结构

- **输入摘要**：路径、项目、平台、特性
- **执行结果**：每个特性的修改/复制/跳过/阻塞项
- **验证结果**：宏控、文件、XML/JSON 节点
- **开发者待处理**：SCM 属性、需人工跟进的调试项

---

## 6. 辅助脚本（可选）

路径：`.cursor/skills/audio-feature-adaptation/scripts/audio_feature_adapt.py`

脚本**只读**，不修改文件，用于辅助 Agent 做检查和验证。

### 6.1 推导项目上下文

```bash
python .cursor/skills/audio-feature-adaptation/scripts/audio_feature_adapt.py inspect \
  --base-code Z:\old\vendor \
  --base-code-sunmao Z:\new\vendor \
  --project-name lk7k_xxx_yyy
```

### 6.2 检查宏控

```bash
python .cursor/skills/audio-feature-adaptation/scripts/audio_feature_adapt.py check-macros \
  --macro "Z:/new/vendor/transsion/projects/lk7k_xxx/ProjectConfig.mk:MTK_HAC_SUPPORT=yes"
```

### 6.3 生成特性适配计划

```bash
python .cursor/skills/audio-feature-adaptation/scripts/audio_feature_adapt.py plan-feature \
  --project-name lk7k_xxx_yyy \
  --platform-name mt6789 \
  --feature dts --feature hac
```

### 6.4 适配后验证

```bash
python .cursor/skills/audio-feature-adaptation/scripts/audio_feature_adapt.py verify \
  --file-exists "Z:/new/vendor/.../某个文件" \
  --macro "Z:/new/vendor/.../ProjectConfig.mk:TRAN_DTS_SUPPORT=yes"
```

---

## 7. 什么情况会暂停并问你

以下情况 Agent **不会擅自继续**，会先向你确认：

- 项目编译选项拆不出 `project_name1` / `project_name2`
- 升级后项目目录找不到或匹配到多个
- `MTK_PLATFORM` 缺失、重复或冲突
- 低功耗通话适配但 ADSP 信息未知
- SOP 指定的路径/宏控/XML 节点在目标分支不存在
- 目标文件已存在且与源文件内容冲突
- 请求的特性不在 SOP 支持列表中

---

## 8. 与 audio-feature-selfcheck 的区别

| 维度 | audio-feature-adaptation | audio-feature-selfcheck |
|------|--------------------------|-------------------------|
| 目的 | **做适配**（改代码/配置） | **做自检**（只读检查） |
| 代码路径 | 升级前 + 升级后 | 仅升级后 |
| 操作 | 可修改文件 | 不修改任何文件 |
| 时机 | 升级/移植过程中 | 适配完成后验收 |

建议流程：**先 adaptation 完成适配 → 再 selfcheck 验收**。

---

## 9. 目录结构速查

```text
.cursor/skills/audio-feature-adaptation/
├── SKILL.md              # Skill 入口与硬性规则
├── USAGE.md              # 本使用说明
├── INPUTS.md             # 输入与路径推导
├── COMMONS.md            # 通用适配规则
├── FEATURE_*.md          # 各特性 SOP
├── REPORT_TEMPLATE.md    # 报告模板
└── scripts/
    └── audio_feature_adapt.py
```

---

## 10. 快速上手示例

**场景**：lk7k 项目升级后，需要适配 DTS 和 HAC。

```text
请使用 audio-feature-adaptation：
- 升级前：D:\code\vendor_old
- 升级后：D:\code\vendor_new
- 编译选项：lk7k_cm7h
- 特性：dts、hac
```

Agent 完成后，你应收到：修改了哪些文件、宏控是否通过、以及需要在 SCM/产线侧配置的 property 列表。
