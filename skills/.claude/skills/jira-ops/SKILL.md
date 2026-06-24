---
name: jira-ops
description: Use when user messages include a Jira issue ID or link and the user wants Jira operations, multi-channel log download (FRBOX/SGBOX, Feishu, UNC, HTTP), archive extraction, or environment setup for jira-ops.
---

# Jira CLI Operator Skill

## Purpose

CLI entry: `scripts/api_jira.py`. Capabilities:

- Jira query / comment / attachments / changelog
- **Multi-channel log download** (from `modem-analysis-local` log-pipeline)
- **Recursive archive extraction** (zip / tar / gz / rar / 7z)
- **One-shot prepare**: download + extract (`prepare-logs`)
- **Environment doctor** (`setup-check`) and **`.env` persistence** (`env`)

---

## Agent 强制执行顺序（首次或报错时）

在下载/解压任何 Jira 日志之前，**必须**按序完成：

### Step 0 — 进入 skill 根目录并安装依赖

```bash
cd <jira-ops-skill-root>
pip install -r requirements.txt
python scripts/api_jira.py setup-check
```

若 `data.ready` 为 `false`，根据 `data.checks` 逐项修复（见下方配置表）。

### Step 1 — 收集并持久化用户配置

**规则**：缺少必填项时，在对话中一次性列出所需参数 + 格式示例，请用户按格式回复；收到后**立即写入持久化存储**（不要只记在对话里）。

| 配置项 | 是否必填 | 持久化方式 | 格式示例 |
|--------|----------|------------|----------|
| Jira 服务器 | **必填** | `config set`（同步 `.env`） | `http://jira.transsion.com/` |
| Jira 用户名 | **必填** | 同上 | `qing.li3` |
| Jira 密码 | **必填** | 同上 | `YourPassword` |
| `FEISHU_APP_ID` | 工单含飞书 `/file/` 时必填 | `.env` | `cli_a1b2c3d4e5f6g7h8` |
| `FEISHU_APP_SECRET` | 同上 | `.env` | `AbCdEfGhIjKlMnOpQrStUvWx` |
| `NETWORK_SERVERS` | 工单含 UNC `\\server\...` 时必填 | `.env` | 见下方 JSON 示例 |
| `SEVEN_ZIP_EXE` | 有 `.rar`/`.7z` 时建议 | `.env` | `C:\Program Files\7-Zip\7z.exe` |
| `CHROME_BINARY` | Box 浏览器兜底可选 | `.env` | `C:\Program Files\Google\Chrome\Application\chrome.exe` |
| `WORKSPACE_ROOT` | 可选，默认 `./jira_workspace` | `.env` | `D:\jira_logs` |

**Jira 凭据写入（推荐）**：

```bash
python scripts/api_jira.py config set --server "http://jira.transsion.com/" --user "<用户名>" --password "<密码>"
```

**Jira 凭据读取优先级**（改造后仍兼容旧配置）：

1. `~/.integration_bug_tool/env.yaml` 中的 `jira.user` / `jira.password`（integration bug tool，最高）
2. `~/.jira_cli_config.json`（`config set` / `config show`）
3. `jira-ops/.env` 中的 `JIRA_SERVER` / `JIRA_USERNAME` / `JIRA_PASSWORD`（仅在前两者缺字段时补足）

因此：原先通过 bug tool 或 `config set` 配好的 Jira 服务器、用户名、密码**无需改动**即可继续用；若只在 modem 风格 `.env` 里写了 `JIRA_*`，现在也会被识别。

**批量写入 `.env`（用户一次性提供 JSON 时）**：

```bash
python scripts/api_jira.py env init-from-user --json "{\"FEISHU_APP_ID\":\"cli_xxx\",\"FEISHU_APP_SECRET\":\"xxx\",\"NETWORK_SERVERS\":\"[{\\\"server\\\":\\\"10.205.101.200\\\",\\\"share\\\":\\\"fans_log\\\",\\\"username\\\":\\\"monkeytest\\\",\\\"password\\\":\\\"Monkey123\\\"}]\"}"
```

或逐项：

```bash
python scripts/api_jira.py env set FEISHU_APP_ID=cli_xxx FEISHU_APP_SECRET=xxx
python scripts/api_jira.py env set SEVEN_ZIP_EXE="C:\Program Files\7-Zip\7z.exe"
```

**`NETWORK_SERVERS` JSON 格式（整段作为单个字符串写入 `.env`）**：

```json
[
  {
    "server": "10.205.101.200",
    "share": "fans_log",
    "username": "monkeytest",
    "password": "Monkey123"
  }
]
```

**向用户索取配置时的对话模板**（复制并填空）：

```text
请提供以下配置（可直接按行回复 KEY=VALUE，或一个 JSON 对象）：

1) Jira（必填）
   JIRA_SERVER=http://jira.transsion.com/
   JIRA_USERNAME=你的域账号
   JIRA_PASSWORD=你的密码

2) 飞书 OpenAPI（若工单日志在 feishu.cn/file/ 链接里）
   FEISHU_APP_ID=cli_xxxxxxxx
   FEISHU_APP_SECRET=xxxxxxxx

3) UNC 网络共享（若工单含 \\10.x.x.x\share\... 路径，Windows）
   NETWORK_SERVERS=[{"server":"10.205.101.200","share":"fans_log","username":"xxx","password":"xxx"}]

4) 7-Zip（若日志为 .rar/.7z，可选）
   SEVEN_ZIP_EXE=C:\Program Files\7-Zip\7z.exe
```

写入后再次执行：

```bash
python scripts/api_jira.py setup-check
python scripts/api_jira.py env show
```

### Step 2 — 可选：Playwright（FRBOX/SGBOX 浏览器兜底）

仅当 `setup-check` 提示需要且 Box HTTP 下载失败时：

```bash
pip install playwright
python -m playwright install chromium
```

### Step 3 — 执行日志准备（推荐一站式）

```bash
python scripts/api_jira.py prepare-logs --issue "<JIRA_KEY>" --output-dir "./jira_workspace/<JIRA_KEY>"
```

成功时 `data.log_root_dirs` 为可分析的日志根目录列表。

---

## 标准工作流（已配置环境）

```bash
# 1) 查看日志来源分类
python scripts/api_jira.py list-log-sources --issue "OS162-37733"

# 2) 一站式下载+解压（推荐）
python scripts/api_jira.py prepare-logs --issue "OS162-37733"

# 或分步：
python scripts/api_jira.py download-logs --issue "OS162-37733" --output-dir "./jira_workspace/OS162-37733"
python scripts/api_jira.py extract-logs --input-dir "./jira_workspace/OS162-37733"
```

---

## 下载渠道

| 渠道 key | 识别 | 依赖 |
|----------|------|------|
| `box` | `frbox` / `sgbox.transsion.com` | PDS HTTP；失败时 Playwright |
| `feishu_file` | `feishu.cn/file/...` | `FEISHU_APP_ID` + `FEISHU_APP_SECRET` |
| `network_share` | `\\server\share\...` | `NETWORK_SERVERS` + Windows 可达共享 |
| `http_direct` | OSS / fanslog 直链 | `requests` |

扫描范围：**标题 + 描述 + 全部评论**（自动过滤 pipeline 导出标记行）。

## 解压支持格式

`.zip` `.tar` `.tgz` `.tar.gz` `.tbz2` `.tar.bz2` `.gz` `.bz2` `.rar` `.7z`

- `.rar`/`.7z` 需要本机 **7-Zip** 或 `SEVEN_ZIP_EXE`
- 默认**递归**解压嵌套压缩包；`--no-recursive` 可关闭

---

## 命令速查

| 命令 | 说明 |
|------|------|
| `setup-check` | 环境/依赖/配置体检 |
| `env show` / `env set` / `env init-from-user` | `.env` 管理 |
| `config set` / `config show` | Jira 凭据（`~/.jira_cli_config.json` + 同步 `.env`） |
| `list-log-sources` | 分类列出日志来源 |
| `download-logs` | 多渠道下载 |
| `extract-logs` | 递归解压 |
| `prepare-logs` | 下载 + 解压 |
| `get-issue` / `add-comment` / `download-attachments` / `get-changelog` | 基础 Jira 操作 |

### 新增 JIRA 评论（Agent / TAHP 备注结论）

在 **cwd = jira-ops/** 下执行：

```bash
# 单行
python scripts/api_jira.py add-comment --issue KM9OS151-1622 --comment "【TAHP 智能诊断】根因：..."

# 多行（推荐）
python scripts/api_jira.py add-comment --issue KM9OS151-1622 --comment-file D:/tmp/tahp-comment.md
```

返回 JSON：`{"ok":true,"data":{"issue_id":"...","comment_id":"...","body":"..."}}`。凭据走 `config set` / `.env` / integration bug tool（同 get-issue）。

**规则**：备注前须确认 `setup-check` 通过；Issue Key 必须存在；勿在评论中泄露未脱敏密码。

平台包装：`bash scripts/deploy.sh` / `.\scripts\deploy.ps1`（参数与 `api_jira.py` 相同）。

---

## 执行规则

1. **cwd** 必须是 `jira-ops/`（含 `SKILL.md` 的目录）。
2. 首次或 `setup-check` 失败 → **先配置再下载**。
3. 命令输出 JSON **原样返回**用户（`{"ok":true,"data":...}`）。
4. 日志任务优先 `prepare-logs`；仅需 URL 时用 `list-log-sources`。

---

## 文件

- `scripts/log_download/` — 下载、解压、env 模块
- `.env.example` — 配置模板
- `references/REFERENCE.md` — 命令详细说明
