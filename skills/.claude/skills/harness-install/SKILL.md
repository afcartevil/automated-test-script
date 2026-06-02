---
name: harness-install
description: harness 安装、诊断、配置、版本发现和反馈子 skill。覆盖 install（自动检测客户端 / 安装 skill）、agent install-skill（强制更新 skill）、version check/update（manifest 驱动的版本发现和升级）、config show/set/path/setup-env（持久化 knowledge URL / token / telemetry 凭据 / qizhi 配置文件）、doctor（环境检查 + diagnostic bundle）、mcp install/show/uninstall（legacy MCP 配置）、feedback create/submit（反馈记录）。
version: 2.1.14
---

# Harness Install 子 skill

## 何时进入

- 第一次安装 harness / 配置 Agent；
- 升级到最新版本；
- 诊断本地环境（adb / fastboot / runner / knowledge service / telemetry）；
- 配置文件（qizhi / opengrok 凭据）；
- 用户主动反馈或工具失败时记录反馈。

## 安装与升级

```text
# 自动检测已安装的 Claude/Codex/Cursor/Trae 客户端并装 skill
harness --json install --target auto --force

# 仅装 / 升级 skill（不重装客户端）
harness --json agent install-skill --target auto --force

# 升级 CLI 到 manifest 指向的最新版
harness --json version check
harness --json version update --dry-run
harness --json version update
```

## 诊断

```text
# 检查 python / git / harness / knowledge / cli commands / mcp tools
harness --json doctor

# 输出脱敏诊断 bundle（反馈附件）
harness doctor --bundle
```

## 配置

```text
# 查看 / 设置 / 定位配置
harness --json config show --effective
harness --json config set update.manifest <path-to-manifest.json>
harness --json config path

# 本地凭据统一在 ~/.tran_harness/env.yaml（齐治 / OpenGrok / Spug / Jira）；也可用 setup-env / setup-jira 写入
harness --json config setup-env --non-interactive --qizhi-user <user> --qizhi-target-host <host> --qizhi-target-password <cmdb-password> --qizhi-bastion-password <ldap-password>
harness --json config setup-jira --non-interactive --jira-username <user> --jira-api-token <ldap-password>
```

## MCP（legacy 可选）

```text
harness --json mcp install --target claude-user
harness --json mcp show    --target claude-user
harness --json mcp uninstall --target claude-user
```

新业务能力默认走 CLI，不写 `.mcp.json` 到业务仓。

可选 legacy MCP 客户端出现 `uv_spawn EPERM` 时，说明客户端在 harness 启动前就失败了；从普通可信终端 / 项目重试。

## 反馈

```text
# 反馈记录（用户主动报问题，或 Agent 发现 CLI 覆盖缺口）
harness --json feedback submit --scenario install --problem-type missing-guidance \
  --title "<标题>" --detail "<详细描述>"

# 同时附 diagnostic bundle（更有价值）
harness --json feedback submit --scenario remote-runner --problem-type bad-result \
  --title "..." --detail "..." --doctor-bundle <path-to-bundle.zip>
```

## 边界

- skill 安装写到 `~/.<client>/skills/`，不写到业务仓。
- `mcp install` 默认只配 `claude-user`；要装多客户端用 `--target all`。
- 反馈正文不要包含 token / webhook / 设备 SN / 完整私有路径。

## 升级流程要点（飞书风格 4 步极简）

执行约束：Agent 必须通过 shell / terminal tool 真正执行命令，不要把 `functions.shell` / JSON 工具调用格式贴到聊天正文；当前 shell 已是 PowerShell 时，不要再嵌套 `powershell -Command "..."` 执行含 `$ver` / `$expected` 的脚本，避免变量被外层提前展开。

1. 共享目录读 `manifest.json` 拿 `cli.latest_file` + `cli.versions.<v>.sha256`；
2. `Copy-Item` 到本地临时目录，`Get-FileHash` 校验 SHA-256；
3. `npm install -g <local-tgz>`（或 `npx --package <tgz> harness install --force`）；
4. `harness doctor` + `harness version check` 复核。

详见 `docs/agent-npx-cli-sop.md`。
