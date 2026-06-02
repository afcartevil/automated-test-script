---
name: harness-knowledge
description: harness 知识管理子 skill。覆盖 knowledge route（候选领域路由器，输出 confidence + ambiguous + recommended_skill）、knowledge search（symptom 关键词全量搜索）、knowledge list（列出 27 个知识包）和 knowledge init（新建知识包脚手架）。当 Agent 拿到一个模糊的用户问题、需要定位到某个领域，或要查传音业务领域规则时调用。
version: 2.1.14
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

## route 输出结构

```json
{
  "status": "ok",
  "query": "audio bringup",
  "matches": [
    {"pack": "multimedia-audio", "score": 6.0,
      "matched_terms": ["audio", "bringup"],
      "skill_path": "knowledge_packs/multimedia/sub/audio/SKILL.md",
      "references": [...], "risk_tags": [...], "layers": [...]}
  ],
  "confidence": "high",
  "ambiguous": false,
  "recommended_skill": "harness-build",
  "recommended_cli": ["harness knowledge search \"audio bringup\""],
  "note": "route only suggests; always verify via `harness commands describe`"
}
```

## 处理规则

- 如果用户请求已经能明确映射到版本查询、编译、刷机/设备、runner、OpenGrok 或安装诊断 CLI，**不要进入 knowledge**；直接使用对应子 skill 和 CLI。
- **`confidence: high`**：可以直接按 `recommended_skill` 跳子 skill。
- **`confidence: medium`** + **`ambiguous: false`**：跳，但回答里说明用了哪个候选。
- **`ambiguous: true`** 或 **`confidence: low/none`**：**不要**自动跳，反问用户更精确的描述，或同时呈现 top 2 候选。
- **route 只建议不执行**：拿到 `recommended_cli` 后，必须先 `harness commands describe <cmd>` 校验参数契约再调用，不允许直接 spawn。

## 反馈

route 给出错误候选、knowledge search 命中后仍不能解决问题时，记反馈：

```text
harness --json feedback create --scenario knowledge-query --problem-type bad-result \
  --title "route 把 X 路由到 Y" --detail "..."
```
