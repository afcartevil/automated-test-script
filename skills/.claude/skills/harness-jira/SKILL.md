---
name: harness-jira
description: harness Jira 查询子 skill。覆盖 jira get/search/parse-key 与 config setup-jira；用于读取 Jira issue、从 URL 提取 issue key、用 JQL 搜索，不负责修改 Jira。
version: 2.1.17
---

# Harness Jira 子 skill

Jira issue 读取/搜索是 CLI 可直接解决的问题：优先运行 `harness jira ...`，不要先 `knowledge route/search`。只有 CLI 报权限/认证错误需要解释配置，或用户要求背景知识时才查 references/knowledge。

## 何时进入

- 用户给 Jira URL 或 issue key（如 `USICPRO-545892`）并要求查看、总结、提取字段或评论；
- 用户要求按 JQL 搜索 issue；
- 用户要配置 Jira 凭据。

## 命令速查

```text
harness --json jira parse-key "http://jira.transsion.com/browse/USICPRO-545892"
harness --json jira get --issue USICPRO-545892
harness --json jira get --url "http://jira.transsion.com/browse/USICPRO-545892"
harness --json jira get --issue USICPRO-545892 --no-comments
harness --json jira search --jql "issuekey = USICPRO-545892" --max-results 10
harness --json config setup-jira --non-interactive --jira-username <user> --jira-api-token <ldap-password>
```

不确定参数时先查契约：

```text
harness --json commands describe jira get
harness --json commands describe jira search
harness --json commands describe jira parse-key
```

## 凭据

- 默认读取 `~/.tran_harness/env.yaml` / `jira.*`；没有显式 Jira 凭据时，CLI 会尝试复用齐治账号/LDAP 密码默认值。
- 不要在回答、反馈、日志摘要里回显 `--jira-api-token`、LDAP 密码或 bearer token。
- 缺凭据时先用 `harness --json config setup-jira --print-only --non-interactive` 看缺失字段/脱敏预览，再只询问缺失值。

## 返回处理

- `get` 返回 issue key、summary、status、assignee、reporter、description、comments、attachments 等结构化字段；按用户目标总结，不要原样倾倒长评论。
- 用户给 URL 时，可以直接 `get --url`；需要先提取 key 时用 `parse-key`。
- 搜索使用用户给定 JQL；不要发明过宽 JQL，例如没有约束地扫全库。
- Jira CLI 是只读查询；修改 issue、流转状态、加评论等能力当前没有暴露成 harness CLI。

## 反馈

```text
harness --json feedback create --scenario jira --problem-type missing-tool-option \
  --tool "harness jira get/search" --detail "..."
```
