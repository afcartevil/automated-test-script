# audio-feature-selfcheck 使用说明

## 1. 这个 Skill 是做什么的

`audio-feature-selfcheck` 用于在 **vendor 升级完成后**，按 SOP **只读检查** Audio 特性是否已正确适配。

- **会做什么**：检查宏控、核对文件、给出「已适配 / 未适配 / 无法判断」结论和证据
- **不会做什么**：不修改任何代码或配置；不替代 SOP 下结论；不依赖其他 Skill

适用场景：升级合入后验收、发版前自查、确认某个特性宏控是否已打开。

---

## 2. 如何触发

在 Cursor 对话中说明要做 **Audio 特性自检**，并带上必要信息。以下关键词容易命中该 Skill：

- Audio 特性自检、音频特性自检、Audio 自检、音频功能自查
- 听力助手-MTK、HAC 自检、`MTK_HAC_SUPPORT`
- 升级后 vnd 自检、`ProjectConfig.mk` 音频宏控检查

**示例提示词：**

```text
请按 audio-feature-selfcheck SOP，检查升级后 vendor 的 HAC 是否已适配：
- 升级后路径：Z:\new\vendor
- 项目编译选项：lk7k_xxx_yyy
- 特性：hac_mtk
```

---

## 3. 使用前必须准备的信息

| 输入项 | 说明 | 是否必填 |
|--------|------|----------|
| `base_code_sunmao` | 升级后的 vnd/vendor 绝对路径 | 是 |
| `project_name` | SPUG 上的项目编译选项全名 | 是 |
| `features` | 要自检的特性列表 | 是 |

> 与 adaptation 不同：自检**只需要升级后路径**，不需要升级前路径。

### 项目名解析规则

`project_name` 按 `_` 拆分：

- 第 1 段 → `project_name1`
- 第 2 段 → `project_name2`
- 项目目录默认为：`{project_name1}_{project_name2}`

默认检查文件：

```text
{base_code_sunmao}/vendor/transsion/projects/{project_name1}_{project_name2}/ProjectConfig.mk
```

---

## 4. 当前支持的特性

| 内部名称 | 特性 | SOP 文件 | 检查要点 |
|----------|------|----------|----------|
| `hac_mtk` | 听力助手-MTK | `FEATURE_HAC_MTK.md` | `MTK_HAC_SUPPORT = yes` |

以下说法会归一化为 `hac_mtk`：听力助手-MTK、HAC-MTK、HAC、听力助手、`MTK_HAC_SUPPORT`。

> 其他特性（DTS、Dolby 等）当前 **尚未纳入自检 SOP**。若你需要，需先补充对应 `FEATURE_*.md` 再扩展。

---

## 5. 结论判定规则

每个特性有三种结论：

| 结论 | 含义 |
|------|------|
| **已适配** | SOP 要求的宏控/文件条件已满足 |
| **未适配** | 宏控缺失或值不符合 SOP |
| **无法判断** | 文件不存在、路径不确定、或同一宏控有多个冲突的有效赋值 |

### 宏控判定注意事项

- **注释行不算证据**（以 `#` 开头的行忽略）
- 同一宏控多个有效赋值且值不一致 → `无法判断`
- 必须给出：文件绝对路径、行号、命中行内容

### HAC-MTK 示例

在 `ProjectConfig.mk` 中存在有效行：

```makefile
MTK_HAC_SUPPORT = yes
```

→ 结论：**已适配**

---

## 6. Agent 执行流程（你会看到什么）

1. 校验输入，推导项目目录
2. 阅读 `COMMONS.md` 和对应 `FEATURE_*.md`
3. 只读检查宏控和文件（不修改任何东西）
4. 按 `REPORT_TEMPLATE.md` 输出报告

### 报告结构

- **输入摘要**：升级后路径、编译选项、项目目录、特性
- **自检结果**：每个特性的结论、检查文件、证据、阻塞项
- **汇总**：已适配 / 未适配 / 无法判断 的数量
- **开发者待确认**：需人工复核的问题

---

## 7. 辅助脚本（可选）

路径：`.cursor/skills/audio-feature-selfcheck/scripts/audio_feature_self_check.py`

脚本**只读**，用于解析项目名和检查宏控。

### 7.1 解析项目编译选项

```bash
python .cursor/skills/audio-feature-selfcheck/scripts/audio_feature_self_check.py inspect \
  --project-name lk7k_xxx_yyy
```

### 7.2 检查单个宏控

```bash
python .cursor/skills/audio-feature-selfcheck/scripts/audio_feature_self_check.py check-macro \
  --file "Z:/new/vendor/transsion/projects/lk7k_xxx/ProjectConfig.mk" \
  --macro MTK_HAC_SUPPORT \
  --expected yes
```

### 7.3 按特性一键自检

```bash
python .cursor/skills/audio-feature-selfcheck/scripts/audio_feature_self_check.py verify \
  --base-code-sunmao Z:\new\vendor \
  --project-name lk7k_xxx_yyy \
  --feature hac_mtk
```

---

## 8. 什么情况会暂停并问你

- 缺少升级后路径、编译选项或特性列表
- 编译选项拆不出 `project_name1` / `project_name2`
- 项目目录 `{project_name1}_{project_name2}` 不存在
- `ProjectConfig.mk` 不存在
- 宏控存在多个冲突的有效赋值
- 请求的特性不在当前 SOP 支持范围

---

## 9. 与 audio-feature-adaptation 的区别

| 维度 | audio-feature-adaptation | audio-feature-selfcheck |
|------|--------------------------|-------------------------|
| 目的 | **做适配**（改代码/配置） | **做自检**（只读检查） |
| 代码路径 | 升级前 + 升级后 | 仅升级后 |
| 操作 | 可修改文件 | 不修改任何文件 |
| 特性范围 | 9 个特性 | 当前仅 `hac_mtk` |
| 时机 | 升级/移植过程中 | 适配完成后验收 |

建议流程：

```text
audio-feature-adaptation（适配） → 编译验证 → audio-feature-selfcheck（验收）
```

---

## 10. 目录结构速查

```text
.cursor/skills/audio-feature-selfcheck/
├── SKILL.md                  # Skill 入口与硬性规则
├── USAGE.md                  # 本使用说明
├── INPUTS.md                 # 输入与路径推导
├── COMMONS.md                # 通用只读检查规则
├── FEATURE_HAC_MTK.md        # 听力助手-MTK 自检 SOP
├── REPORT_TEMPLATE.md        # 报告模板
└── scripts/
    └── audio_feature_self_check.py
```

---

## 11. 快速上手示例

**场景**：升级完成后，确认 lk7k 项目的 HAC 是否已适配。

```text
请使用 audio-feature-selfcheck 检查：
- 升级后路径：D:\code\vendor_new
- 编译选项：lk7k_cm7h
- 特性：听力助手-MTK
```

**期望输出示例：**

```markdown
## 自检结果

- hac_mtk:
  - 结论：已适配
  - 检查文件：D:\code\vendor_new\vendor\transsion\projects\lk7k_cm7h\ProjectConfig.mk
  - 检查项：MTK_HAC_SUPPORT = yes
  - 证据：第 42 行，MTK_HAC_SUPPORT = yes
  - 阻塞项：无
```

若结论为 **未适配** 或 **无法判断**，按报告中的阻塞项处理后再重新自检。
