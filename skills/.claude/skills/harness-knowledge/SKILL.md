---
name: harness-knowledge
description: harness 知识管理子 skill。覆盖 knowledge route（二级索引 L1 域/子域 + L2 场景，输出 search_scope、domain_resolution、置信度与 recommended_skill）、knowledge search、knowledge list 和 knowledge init。当 Agent 需要定位业务域/场景或查传音领域规则时调用。
version: 2.1.17
---

# Harness Knowledge 子 skill

## 何时进入

- 用户问题模糊、需要先识别领域；
- 已知有领域但需要查具体规则或 references；
- 怀疑命中某个 symptom（例如"audio bringup"、"rdtool 编译失败"）。

## 命令速查

```text
# Shortcut：候选领域路由器
harness --json +route "<query>"

# 候选领域路由器（带 confidence + ambiguous + recommended_skill）
harness --json knowledge route "<query>"
harness --json knowledge route "<query>" --top 3 --ambiguity-threshold 0.2

# symptom 全量搜索
harness --json knowledge search "<keyword>"

# 列出所有知识包
harness --json knowledge list
```

## route 输出结构（二级索引）

关键字段（以 `--json` 为准）：

| 字段 | 含义 |
|------|------|
| `search_scope` | `narrowed` = L1 命中 pack 且 L2 在候选 pack 内命中；`global` = 全库 symptom 检索 |
| `domain_resolution.matched_aliases` | L1 命中的 INDEX alias |
| `domain_resolution.candidate_packs` | L1 收窄到的 pack（`SKILL.md` 的 `name`） |
| `domain_resolution.candidates[]` | L1 详情：`path`、`level`（`domain`/`sub_domain`/`common`）、`matched_alias` |
| `matches[0].domain` | L2 业务域路径（如 `connectivity/knight`） |
| `matches[0].scenario_id` / `scenario_name` | L2 场景 |
| `matches[0].matched_symptoms` | L2 命中的 symptom 原文 |
| `knowledge_confidence_low` | `true` 时需人工确认场景 |
| `top_final_confidence` | 场景综合置信度（0–1） |

## 向用户说明索引路径（固定模板）

`knowledge route` 成功后，**必须用下面模板向用户说明 L1→L2 层级**（把 `{...}` 替换为 JSON 实际值；无匹配时用「未命中」变体）。

### 模板 A：`search_scope=narrowed`（二级索引命中）

```markdown
**知识索引结果**

根据您描述的任务「{query}」：

1. **L1 域索引（INDEX.yaml）**
   - 命中关键词：`{domain_resolution.matched_aliases 逗号连接}`
   - 收窄到：{candidates[0].level 中文：domain→业务域 / sub_domain→子域 / common→横切能力} **`{candidates[0].path}`**
   - 知识包 pack：`{domain_resolution.candidate_packs[0]}`

2. **L2 场景索引（scenarios.yaml）**
   - 业务域路径：`{matches[0].domain}`
   - 匹配场景：**{matches[0].scenario_name}**（`{matches[0].scenario_id}`）
   - 命中 symptom：{matches[0].matched_symptoms 前 2 条，逗号连接}

3. **索引模式**：`narrowed`（先定域/子域，再在 pack 内定场景）

4. **置信度**：{top_final_confidence} — {若 knowledge_confidence_low 为 false：可继续按该场景查 references；为 true：建议人工确认场景是否正确}

**建议下一步**：阅读 `{matches[0].skill_references[0] 或 skill_path}`
```

### 模板 B：`search_scope=global`（L1 未收窄或 L2 候选内未命中，全库检索）

```markdown
**知识索引结果**

根据您描述的任务「{query}」：

1. **L1 域索引**：未命中已注册的 domain/sub aliases（或 L2 在候选 pack 内无匹配），未收窄到单一 pack。

2. **L2 场景索引（全库）**
   - {若有 matches[0]：命中场景 **{scenario_name}**（`{scenario_id}`），pack=`{pack}`}
   - {若无 matches：未匹配到场景}

3. **索引模式**：`global`（全库 symptom 检索）

4. **置信度**：{top_final_confidence 或「无」} — {knowledge_confidence_low 为 true 时：建议补充更具体的模块/任务描述，或人工确认}

**建议下一步**：{若有 matches：阅读 references；若无：换关键词重试 `harness knowledge search`}
```

### 模板 C：无匹配

```markdown
**知识索引结果**

根据您描述的任务「{query}」：L1/L2 均未命中已知场景（`knowledge_confidence_low: true`）。

请补充：涉及的模块名（如 knight / audio / 整机编译）、具体业务活动（而非单点改代码任务），或确认该域是否尚未接入知识包。
```

### 示例（narrowed）

根据您描述的任务「netmonitor QoE hook」：

1. **L1 域索引**：命中 `netmonitor` → 子域 **connectivity/sub/knight**（pack: `connectivity-knight`）
2. **L2 场景**：`connectivity/knight` → **NetMonitor 业务变更**（`update-netmonitor`）
3. **索引模式**：`narrowed`
4. **置信度**：0.645 — 可继续查阅 netmonitor references

## 处理规则

- 如果用户请求已经能明确映射到版本查询、编译、刷机/设备、runner、OpenGrok 或安装诊断 CLI，**不要进入 knowledge**；直接使用对应子 skill 和 CLI。
- **`knowledge_confidence_low: false`** 且 **`ambiguous: false`**：按 `recommended_skill` 跳子 skill，并**用上面模板 A/B 向用户说明索引路径**。
- **`ambiguous: true`** 或 **`knowledge_confidence_low: true`**：用模板 B/C，**不要**自动跳子 skill；呈现 top 候选并请用户确认。
- **route 只建议不执行**：拿到 `recommended_cli` 后，必须先 `harness commands describe <cmd>` 校验参数契约再调用，不允许直接 spawn。

## 反馈

route 给出错误候选、knowledge search 命中后仍不能解决问题时，记反馈：

```text
harness --json feedback create --scenario knowledge-query --problem-type bad-result \
  --title "route 把 X 路由到 Y" --detail "..."
```
