# TAHP Cursor Rules

本目录为 **Cursor Agent 编码规范**，不修改应用运行时逻辑。

## 始终生效

| 文件 | 说明 |
|------|------|
| `00-change-control.mdc` | 变更范围、敏感链、文件分区 |
| `tahp-verify-commit.mdc` | 验证命令、git 提交、MR 要求 |

## 按文件自动加载

| 文件 | 触发 glob |
|------|-----------|
| `tahp-console-dev.mdc` | `tahp-console/**` |
| `tahp-paths-config.mdc` | paths / jira-workspace / unified-config / agent-bridge / 相关 Skill |
| `tahp-skills-hermes.mdc` | `skills/.claude/skills/**` |
| `tahp-self-check.mdc` | AI 自检前后端与 Python 用例 |

## 复杂流程 Skill

`.cursor/skills/` 下为任务级工作流（如 AI 自检集成），在对应规则中引用。

## 设计与执行文档

- Skill 同步管理：`.cursor/skill-sync/`（Phase 提案与强制自检）

## 合并请求模板

- GitLab: `.gitlab/merge_request_templates/Default.md`
- GitHub: `.github/PULL_REQUEST_TEMPLATE.md`

根目录 `CLAUDE.md`、`AGENTS.md` 指向本目录。
