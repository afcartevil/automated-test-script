# modem-analysis-local

Modem 通信问题分析的 Cursor Agent Skill：在本机完成 Jira 日志准备与 L0~L3 AI 分析，产出可回写 Jira 的结构化报告。

## 安装

1. 将 `modem-analysis-local/` 放到 Cursor skill 目录，例如：
   - 项目：`<project>/.cursor/skills/modem-analysis-local/`
   - 全局：`~/.cursor/skills/modem-analysis-local/`
2. 在 skill 根目录：
   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   copy .env.example .env
   copy .env log-pipeline\.env
   ```
3. 编辑 `.env`：`WORKSPACE_ROOT`、Jira；按需配置飞书、7-Zip、ELT/NLT 等（见 `references/setup.md`）。

## 使用

对 Agent 说例如：

- `分析 OS162-37733`
- `只帮我把 OS162-37733 的 log 准备好`
- `D:\modem_workspace\OS162-37733 已有 manifest，直接分析`

执行细节见 `SKILL.md`。

## 包内目录

| 目录 | 作用 |
|------|------|
| `log-pipeline/` | Jira → 下载 → 解压 → trace → `job_manifest.json` |
| `analysis_skills/` | L0 / L1 / L2 / L3 分析 |
| `scripts/` | manifest 写回、可选 finalize |
| `schemas/` | `job_manifest.schema.json`（`schema_version` `1.1.0`） |

## 版本与机密

- Skill 版本：`SKILL.md` frontmatter `version`
- 交付时不要打包 `.env` 及 `WORKSPACE_ROOT` 下的 issue 数据
