# modem-analysis-local 配置与使用指南

> Skill 版本 1.0.0 · 适用于 Windows 本机日志准备 + L0→L3 AI 故障分析  
> English: [Feishu doc](https://transsioner.feishu.cn/docx/EHS1dacmxoNAdOxp2Uicr6Grn5e) · `references/feishu-setup-guide-en.md`

## 概述

`modem-analysis-local` 是 Cursor Agent Skill，在本机完成：

- **日志准备**（`log-pipeline/`）：Jira 拉单 → 下载 → 解压 → trace 导出 → 生成 `job_manifest.json`
- **分层分析**（`analysis_skills/`）：L0 基础指标 → L1 业务判断 → L2 域内分析 → L3 最终结论
- **可选脚本**（`scripts/`）：manifest 写回、飞书看板更新

**Skill 根目录（`SKILL_ROOT`）**：`SKILL.md` 所在目录。下文命令均在该目录下执行。

---

## 一、Python 环境安装

### 1.1 前置条件

- **Python 3.9+**（建议 3.10/3.11）
- **Windows**（日志 pipeline 当前以 Windows 为主）
- 磁盘：单 issue 工作区约数 GB，请将 `WORKSPACE_ROOT` 设在**本地 SSD**（如 `D:\` / `E:\`），勿直接指向 UNC 网络盘

### 1.2 安装 Skill 到 Cursor

将 `modem-analysis-local/` 放到以下任一位置：

| 范围 | 路径示例 |
|------|----------|
| 项目级 | `<project>/.cursor/skills/modem-analysis-local/` |
| 全局 | `~/.cursor/skills/modem-analysis-local/` |

本仓库示例：`<project>/.agents/skills/modem-analysis-local/`

### 1.3 创建虚拟环境并安装依赖

在 **Skill 根目录**执行：

```powershell
cd <SKILL_ROOT>
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

`requirements.txt` 主要包含：

| 包 | 用途 |
|----|------|
| `requests`, `python-dotenv` | HTTP / 环境变量 |
| `jira`, `pygerrit2` | Jira / Gerrit（日志准备） |
| `jsonschema` | `job_manifest.json` 校验 |

### 1.4 可选依赖

| 场景 | 操作 |
|------|------|
| **Box 网盘浏览器下载** | 取消 `requirements.txt` 中 `playwright` 注释，然后 `python -m playwright install chromium` |
| **finalize 上传 NAS（无系统 smbclient）** | 取消 `smbprotocol` 注释后 `pip install` |
| **环境自检** | `python log-pipeline\_shared\check_environment.py`（若存在） |

### 1.5 外部工具（日志导出，按需）

| 工具 | 环境变量 | 用途 |
|------|----------|------|
| 7-Zip | `SEVEN_ZIP_EXE` | 解压 rar/7z |
| ELT / NLT | `ELT_HOME`, `NLT_HOME` | MTK trace 导出 |
| Wireshark | `WIRESHARK_PATH` | PCAP → txt |
| Qualcomm QUTS | `QUTS_PYTHON_PATH` | QCOM diag 导出 |

详见 Skill 内 `references/setup.md`。

---

## 二、`.env` 配置

### 2.1 配置文件关系

存在两份 `.env`，**内容需保持一致**（至少 `WORKSPACE_ROOT`、Jira、解压工具路径一致）：

| 文件 | 读取方 |
|------|--------|
| `<SKILL_ROOT>/.env` | 分析层、部分脚本 |
| `<SKILL_ROOT>/log-pipeline/.env` | `run_pipeline.py` 及各 pipeline 步骤 |

**推荐流程：**

```powershell
cd <SKILL_ROOT>
copy .env.example .env
# 编辑 .env 填写必填项
copy .env log-pipeline\.env
```

若需 pipeline 高级项（Samba 发布、Jira watcher、Gerrit 等），可参考 `log-pipeline/.env.example` 在 `log-pipeline/.env` 中补充，并保证与根目录 `.env` 不冲突。

### 2.2 必填项

| 变量 | 说明 | 示例 |
|------|------|------|
| `WORKSPACE_ROOT` | 本机工作区根目录；产出 `{WORKSPACE_ROOT}/{issue_key}/job_manifest.json` | `D:\modem_workspace` |
| `JIRA_SERVER` | Jira API 地址 | `http://jira.transsion.com` |
| `JIRA_USERNAME` | Jira 账号 | — |
| `JIRA_PASSWORD` | Jira 密码或 API Token | — |

### 2.3 常用可选项（日志导出 / 本机 pipeline）

| 变量 | 说明 |
|------|------|
| `SEVEN_ZIP_EXE` | 7-Zip 可执行文件路径 |
| `WIRESHARK_PATH` | Wireshark 安装目录 |
| `ELT_HOME` / `NLT_HOME` | MTK 导出工具根目录 |
| `QUTS_PYTHON_PATH` | QUTS 自带 Python（QCOM 导出） |
| `SMB_PUBLISH_ENABLED` | `0` = 仅本机分析不上传 Samba；`1` = pipeline 结束后发布 zip |

### 2.4 飞书相关（**一般不用设置**）

本 Skill 以**本机 Cursor 分析**为主，多数场景**无需配置**下列变量，可保持为空或注释掉：

| 变量 | 用途 | 本地分析是否要配 |
|------|------|------------------|
| `FEISHU_APP_ID` / `FEISHU_APP_SECRET` | 飞书文件下载、L2-EE 历史表、看板 upsert | 通常 **否** |
| `FEISHU_DASHBOARD_APP_TOKEN` / `FEISHU_DASHBOARD_TABLE_ID` | 分析看板多维表格 | 通常 **否** |
| `FEISHU_DASHBOARD_ENABLED` | pipeline Step 10 写看板 | 通常 **否**（默认跳过即可） |
| `JIRA_BROWSE_URL_BASE` | 仅在看板中展示 Jira 链接时用 | 不配看板则 **否** |

仅当团队明确要求「写飞书看板 / 查 EE 历史表 / 从飞书拉附件」时再填写；详见 `log-pipeline/.env.example` 中飞书段落。

### 2.5 Gerrit（可选）

用于 pipeline 中关联变更（如 `fetch_mddb_for_logs.py` 查 Gerrit）。**不做 MDDB/补丁关联时可留空。**

| 变量 | 说明 | 示例 |
|------|------|------|
| `GERRIT_URL` | Gerrit 站点 | `https://gerrit.transsion.com` |
| `GERRIT_USERNAME` | 你的 Gerrit 账号 | — |
| `GERRIT_PASSWORD` | 密码或 HTTP 访问 Token | — |

```ini
# ----- Gerrit（可选） -----
GERRIT_URL=https://gerrit.transsion.com
GERRIT_USERNAME=
GERRIT_PASSWORD=
```

须同步到 `log-pipeline\.env`（与根目录 `.env` 一致）。

### 2.6 `NETWORK_SERVERS`（Jira 含 UNC 日志路径时建议配置）

`download_box_logs.py` 用该 JSON 列表解析 Jira 评论/描述里的 **`\\server\share\...`** 路径并挂载访问。若日志只在 Box/HTTP 链接、无 UNC，可留空 `[]`。

**格式**：单行 JSON 数组，每项包含 `server`、`share`、`username`、`password`（多台服务器可写多个对象）。

```ini
# ----- 网络共享服务器（download_box_logs.py 解析 UNC 路径用） -----
NETWORK_SERVERS=[{"server":"10.205.101.200","share":"fans_log","username":"<user>","password":"<pass>"},{"server":"10.150.152.37","share":"fans_log","username":"<user>","password":"<pass>"}]
```

说明：

- 与 `log-pipeline/.env.example` 中默认粉丝日志服务器列表一致时可整段复制；**凭据勿写入文档或提交 Git**
- 修改后执行 `copy .env log-pipeline\.env` 同步

### 2.7 其他 Pipeline 扩展项（见 `log-pipeline/.env.example`）

完整自动化 / 发布场景才需要，例如：

- `SMB_*`：Samba 发布目标与凭据
- `QCOM_*`：高通导出行为开关
- `JIRA_EXPORT_WATCHER_*`：Jira 持续扫描自动导出

### 2.8 安全提醒

- **勿将 `.env` 提交 Git**；交付、分享 Skill 时不要打包 `.env` 及 `WORKSPACE_ROOT` 下 issue 数据
- 文档与示例中密码请用占位符，勿粘贴真实凭据

---

## 三、使用方法

### 3.1 对 Cursor Agent 的自然语言指令

| 模式 | 用户说法示例 | Agent 行为 |
|------|--------------|------------|
| **full** | 「分析 OS162-37733」 | 日志准备 + L0→L3 + 输出报告 |
| **prepare-only** | 「只下载处理 log」「只准备 OS162-37733 的 log」 | 仅跑 pipeline，给出 manifest 路径 |
| **analyze-only** | 「log 已准备好，直接分析 OS162-37733」 | 跳过 pipeline，从 L0 开始 |
| **manifest** | 「分析这个 manifest」+ 路径 | 使用指定 `job_manifest.json` |

### 3.2 手动执行：日志准备（Step 0）

```powershell
cd <SKILL_ROOT>
$env:PYTHONIOENCODING = "utf-8"
python log-pipeline\run_pipeline.py --issue-key <ISSUE_KEY>
```

成功后在以下路径生成 manifest：

```text
{WORKSPACE_ROOT}/{issue_key}/job_manifest.json
```

失败则根据 pipeline 终端输出排查（Jira、下载、解压、导出工具等）。

### 3.3 AI 分析流程（Step 1～4）

Agent 按顺序读取并执行各层 `SKILL.md`（**由 AI 分析，不要直接跑各层 `scripts/run_*.py`**）：

| 步骤 | Skill | 写回字段 |
|------|-------|----------|
| L0 | `analysis_skills/modem-l0-baseline/` | `analysis.l0_baseline` |
| L1 | `analysis_skills/modem-l1-business-judge/` | `analysis.l1_business`（`primary_domain`） |
| L2 | 按域：`ee` / `call` / `data` / `sim`；`other` 跳过 | `analysis.l2_domains.<domain>` |
| L3 | `analysis_skills/modem-l3-conclusion/` | `analysis.l3_conclusion`、`analysis.final_report` |

每完成一层应**立即写回** manifest（见 `references/manifest-update-guide.md`）。

### 3.4 日志检索辅助

```powershell
$env:PYTHONIOENCODING = "utf-8"
python analysis_skills\log-search-read\scripts\log_search_read.py --manifest <MANIFEST_PATH> list
python analysis_skills\log-search-read\scripts\log_search_read.py --manifest <MANIFEST_PATH> search --query "SIM_STATE"
```

### 3.5 交付格式

完整分析结束后，Agent 输出：

```text
[FINAL_REPORT_BEGIN]
<manifest.analysis.final_report 原文>
[FINAL_REPORT_END]
```

不得改写、压缩或翻译 `final_report` 正文。

### 3.6 可选：更新飞书看板（**一般不用**）

本地分析默认**不依赖**飞书看板。仅当用户**明确要求**且已配置 `FEISHU_*` 时：

```powershell
python scripts\finalize_analysis.py --manifest <MANIFEST_PATH> --skip-upload --skip-delete
```

### 3.7 manifest 写回方式

1. 首选：对 JSON 做精确 `str_replace`
2. 备选：`python scripts/update_manifest.py --manifest <path> --stage l0 --data-file <json>`

禁止：用 `python -c` 拼 JSON、整文件重写 manifest。

---

## 四、目录结构速查

```text
modem-analysis-local/
├── SKILL.md              # Agent 主流程
├── README.md
├── requirements.txt
├── .env.example          # 根配置模板
├── log-pipeline/         # 日志准备
├── analysis_skills/      # L0～L3
├── scripts/              # manifest / finalize
├── schemas/              # job_manifest.schema.json
└── references/           # setup、manifest 指南等
```

---

## 五、常见问题

| 现象 | 处理建议 |
|------|----------|
| pipeline 找不到 Jira/下载失败 | 检查 `.env` 与 `log-pipeline\.env` 是否同步、`JIRA_SERVER` 是否可达 |
| 解压/导出失败 | 配置 `SEVEN_ZIP_EXE`、`ELT_HOME`/`NLT_HOME` 或 `QUTS_PYTHON_PATH` |
| 工作区很慢 | 将 `WORKSPACE_ROOT` 改到本地 SSD，避免 UNC |
| stdout 出现 `SKILL_FAILED:` | 原样汇报并终止（脚本级失败） |
| 证据不足 | 各层在 manifest 中记录 `gaps`、降低 `confidence`，不视为 SKILL_FAILED |

---

## 六、相关文件

- 主流程：`SKILL.md`
- 环境细节：`references/setup.md`
- Manifest 写回：`references/manifest-update-guide.md`
- Pipeline 全量环境变量：`log-pipeline/.env.example`
- 英文版指南：[Feishu](https://transsioner.feishu.cn/docx/EHS1dacmxoNAdOxp2Uicr6Grn5e) · `references/feishu-setup-guide-en.md`
