# modem-log-pipeline (Phase 1, Windows)

> Modem 故障分析的 **日志准备阶段**（原 `modem-analysis-unified` skill 中的 Step 1–8）。
> 仅负责从 Jira 抓取上下文、下载/解压/过滤日志、用 ELT/NLT/Wireshark 导出 trace，最后打包成统一目录结构。
>
> AI 分析阶段（L0/L1/L2/L3）已拆分到 Linux 端的 `modem-analysis-unified` skill，本工程不再涉及 AI 分析。

## 一、定位

- **运行平台**：Windows（依赖 ELT / NLT / Wireshark / 7-Zip 等本地工具链）
- **不属于 skill**：本目录是一个独立工程，与 `.agents/skills/` 下任何 skill 都没有依赖关系
- **与 Phase 2 的契约**：通过 `{WORKSPACE_ROOT}/{issue_key}/job_manifest.json` 文件传递所有必需信息（严格遵循 `schemas/job_manifest.schema.json`）

## 二、目录结构

```
modem-log-pipeline/
├── run_pipeline.py              # 主入口
├── pipeline_steps/
│   ├── fetch_issue_context.py
│   ├── download_box_logs.py
│   ├── recursive_extract.py
│   ├── filter_log_roots.py
│   ├── pcap_to_txt.py
│   ├── fetch_mddb_for_logs.py
│   ├── export_traces.py
│   ├── package_trace_outputs.py
│   ├── publish_to_samba.py          # Step 9：推 Samba
│   ├── jira_post_publish_comment.py # 发布后可选 Jira 评论
│   ├── aliyun_pds_downloader.py
│   └── get_modem_info_from_snapshot.py
├── templates/
│   └── jira_publish_comment.template.example
├── _shared/
│   ├── modem_analysis_runtime.py    # manifest load/save 等
│   ├── check_environment.py
│   ├── install_python_deps.py
│   ├── job_manifest.example.json
│   └── domain_patterns.md
├── schemas/
│   └── job_manifest.schema.json     # Phase 1 ↔ Phase 2 契约
├── requirements.txt
├── .env.example                     # 复制为 .env 并填写
└── README.md
```

## 三、安装

```powershell
# 1. 创建虚拟环境（推荐）
python -m venv .venv
.venv\Scripts\Activate.ps1

# 2. 安装依赖
pip install -r requirements.txt

# 3. 复制并填写环境变量
Copy-Item .env.example .env
# 用编辑器打开 .env，至少填写 WORKSPACE_ROOT、JIRA_SERVER、JIRA_USERNAME、JIRA_PASSWORD
```

**必须配置的外部依赖：**
- `7-Zip`（解压用）→ 配置 `SEVEN_ZIP_EXE`
- `Wireshark`（pcap 导出，可选）→ 配置 `WIRESHARK_PATH`
- `ELT / NLT`（trace 导出，可选）→ 配置 `ELT_HOME` / `NLT_HOME`

## 四、运行

### Jira 持续扫描（自动导出框架，`jira_export_watcher.py`）

按两条 JQL 做差集得到待处理单，**依次**调用 `run_pipeline.py --issue-key <KEY>` 做日志准备；每轮结束后默认休眠 30 分钟。需配置 `WORKSPACE_ROOT` 与 Jira 凭据。

```powershell
# 无限循环（Ctrl+C 优雅退出；当前单跑完才退出）
python jira_export_watcher.py

# 只跑一轮
python jira_export_watcher.py --once

# QCOM 测试机：扫 X6878-16 等前缀 + qcom 评论模板 / export-flag
python jira_export_watcher.py --platform qcom --once

# SPRD 测试机
python jira_export_watcher.py --platform sprd --once

# 只验证 JQL 差集，不导出
python jira_export_watcher.py --dry-run

# 只扫描不跑 pipeline
python jira_export_watcher.py --scan-only --once
```

配置两条完整 JQL（见 `.env.example`），watcher 每轮做差集：

- `JIRA_EXPORT_WATCHER_JQL_ALL`：全部待扫描范围  
- `JIRA_EXPORT_WATCHER_JQL_EXPORTED`：已导出（评论含 `text ~ "modem-log-pipeline-export-flag"`，用正向检索，勿 `NOT text ~`）  

待处理 = ALL 命中 key − EXPORTED 命中 key。旧变量 `JIRA_EXPORT_WATCHER_JQL` 等同 `JQL_ALL`。

未自定义 `JIRA_EXPORT_WATCHER_JQL_ALL` 时，默认 `created >=` **滚动下界**：`JIRA_EXPORT_WATCHER_CREATED_LOOKBACK_DAYS=1` 表示仅扫描**今天**创建的单（避免长期无 log、无 export-flag 评论的老单反复进差集）；可改为 `7` 等。固定下界用 `JIRA_EXPORT_WATCHER_CREATED_SINCE=YYYY-MM-DD`。

默认会按 **summary 精确子串** 跳过无 log 的印度/俄罗斯粉丝单（`【粉丝反馈】【印度】`、`【粉丝反馈】【EE1】`）；可用 `JIRA_EXPORT_WATCHER_SKIP_FAN_NO_LOG=0` 关闭。

`--platform`（`mtk` / `qcom` / `sprd`）：不传则用 `JIRA_EXPORT_WATCHER_AFFECTS_VERSION_PREFIXES`；`qcom`/`sprd` 分别读 `JIRA_EXPORT_WATCHER_PREFIXES_QCOM` / `_SPRD`，并切换默认 `JQL_EXPORTED` 的 export-flag 与 `JIRA_PUBLISH_COMMENT_TEMPLATE_*`（仅影响扫描范围与 Samba 成功后的 Jira 评论，pipeline 步骤仍与 MTK 相同）。

**QCOM trace 导出（Step 7）**：在含 `.qmdl2` / `.qdss` 的目录上调用 `pipeline_steps/qcom/export_modem_log.py`（需安装 QUTS，见 `pipeline_steps/qcom/DESIGN.md`）。每个源文件对应一个 txt，保存在 `{group_dir}/qcom_export/`；**默认每条 Diag 包一行**（便于 `log-search-read` 按行搜索）。`qcom_export/` 里已有匹配 txt 时会跳过重复导出，改格式后需删除旧 `qcom_export/` 再跑。环境变量见 `.env.example`。

### 完整流程

```powershell
python run_pipeline.py --issue-key OS162-37733
```

### 本地已有产物，仅推送到 Samba（Step 9）

日志已在 `{WORKSPACE_ROOT}\{issue_key}\` 下准备好（含 `job_manifest.json`）时，不必重跑 Step 1–8：

```powershell
# 按单号（manifest 路径 = WORKSPACE_ROOT\issue_key\job_manifest.json）
python run_pipeline.py --publish-only --issue-key OS162-37733

# 或显式指定 manifest 路径（issue 目录可不在 WORKSPACE_ROOT 下）
python run_pipeline.py --publish-only --manifest "D:\data\OS162-37733\job_manifest.json"
```

仍读取 `.env` 中的 `SMB_*`；`--publish-only` 会临时打开 `SMB_PUBLISH_ENABLED`（与 `--skip-publish` 互斥）。

也可直接调用步骤脚本：

```powershell
python pipeline_steps\publish_to_samba.py --manifest "D:\data\OS162-37733\job_manifest.json"
```

### 从指定 manifest 续跑完整 pipeline

```powershell
# manifest 路径任意；目录约定为 {某根}\{issue_key}\job_manifest.json
python run_pipeline.py --manifest "Z:\data_store\OS162-37733\job_manifest.json"
# 若 manifest 内无 issue_key，需同时传：--issue-key OS162-37733
```

将按 Step 1–9 重新执行（各步骤是否跳过已存在产物，由各 `pipeline_steps` 模块自行决定）。

## 五、输出契约

每次成功运行后，会在 `{WORKSPACE_ROOT}/{issue_key}/` 下产出：

```
{WORKSPACE_ROOT}/{issue_key}/
├── job_manifest.json          # 状态与契约
├── DUT/                       # DUT 设备日志（规范化命名）
│   ├── ota.txt
│   ├── ps.txt
│   ├── system.txt
│   ├── sip.txt
│   ├── icd.txt
│   ├── l1.txt
│   ├── l2.txt
│   ├── ps_raw.txt
│   ├── radio_log              # 子目录
│   ├── main_log               # 子目录
│   └── *_pcap.txt             # 若有 PCAP 导出
└── REF/                       # REF 设备日志（如有）
```

**关键约束（schema 强校验）：**
- `manifest 所在目录` 隐式等同于 `workspace_root`
- 所有 `final_log_root` / `trace_exports.aggregated_files` / `copied_support_files` 字段一律存 **相对于 manifest 所在目录** 的相对路径（POSIX 风格）
- `jira.{summary, description, platform, chip_vendor, sw_version, ...}` 等字段必填（允许空字符串，但字段必须存在）

详见 `schemas/job_manifest.schema.json`。

## 六、与 Phase 2 协作

```
┌─────────────────────────────────────────────────────────────┐
│                          Windows                             │
│   modem-log-pipeline                                         │
│        ↓ Step 1~8                                            │
│   {WORKSPACE_ROOT}\{issue_key}\  (本地 SSD)                  │
│        ↓ Step 9: robocopy /MIR                               │
│   \\SMB_HOST\SMB_SHARE\{SMB_REMOTE_SUBPATH}\{date}\{issue}.zip │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼ (Samba 中转)
┌─────────────────────────────────────────────────────────────┐
│                           Linux                              │
│   sync_issue_from_share.sh (smbclient 直连)                  │
│        ↓                                                     │
│   $WORKSPACE_ROOT/{issue_key}/  (本地)                       │
│        ↓                                                     │
│   modem-analysis-unified skill                               │
│        - sync_issue_from_share.py（从 Samba 拉到本地）        │
│        - L0 → L1 → L2 → L3                                   │
└─────────────────────────────────────────────────────────────┘
```

要点：
- 双端各自有本地 workroot；Samba 仅作中转
- Linux 端用 `smbclient` 拉取，**不挂载**
- manifest 中所有路径相对 manifest 所在目录，拷到任何机器都能正常解析

## 七、Samba 发布（Step 9）

完成 Step 8 后，自动把 `{WORKSPACE_ROOT}\{issue_key}\` 整目录推到 Samba：

```powershell
# .env 关键字段
SMB_PUBLISH_ENABLED=1
SMB_PUBLISH_REQUIRED=0      # 0 = 发布失败仅告警；1 = 失败则 pipeline 整体失败
SMB_HOST=10.205.4.20
SMB_SHARE=sw_temp
SMB_REMOTE_SUBPATH=通信开发部
SMB_USERNAME=...
SMB_PASSWORD=...
```

- 发布命令：`net use \\HOST\SHARE pwd /user:USER` + `robocopy LOCAL UNC /MIR /Z /R:2 /W:5 /MT:8`
- robocopy 退出码 **0–7 视为成功**，≥8 才算失败（标准约定）
- 跳过本次发布：`python run_pipeline.py --issue-key XXX --skip-publish`
- 发布结果写回 `manifest._meta.phase1_smb_publish`（仅记录，Phase 2 不依赖）
- 默认 **保留** `{issue_key}/downloads/` 及解压后的完整目录（`PIPELINE_KEEP_LOCAL_FILES=1`，Step 4 不删文件、Step 8 不删 downloads）。若需省磁盘，设 `PIPELINE_KEEP_LOCAL_FILES=0` 或 `DELETE_LOCAL_FILES_AFTER_PIPELINE=1`

### 发布后 Jira 评论（可选）

当 **Samba 发布成功**（robocopy 判定 OK）时，可按模板向当前单追加一条评论：

| 环境变量 | 说明 |
|---|---|
| `JIRA_COMMENT_AFTER_PUBLISH` | `1` 开启；`0` 关闭（默认） |
| `JIRA_PUBLISH_COMMENT_TEMPLATE` | 模板文件路径：相对工程根 `modem-log-pipeline/`，或绝对路径 |

模板为 **UTF-8 文本**，使用 Python `string.Template` 语法，占位符 **`$issue_key`**、`$unc_base`、`$published_at`、`$robocopy_exit`、`$phase1_host`、`$manifest_path`、`$robocopy_mode`（勿用 `{curly}`，避免与路径字面量混淆）。示例见 `templates/jira_publish_comment.template.example`；复制后改路径并指向自己的模板即可。

评论发送失败**不会**导致 Step 9 失败；结果写入 `manifest._meta.phase1_smb_publish.jira_comment`。

自测渲染（不发 Jira）：

```powershell
python pipeline_steps\jira_post_publish_comment.py --issue-key OS162-37733 --dry-run
```

## 八、错误处理

| 步骤 | 失败影响 |
|---|---|
| 1 jira-issue-fetch | 必须成功，否则停止 |
| 2 box-log-download | 必须成功，否则停止 |
| 3 archive-recursive-extract | 必须成功，否则停止 |
| 4 modem-log-structure-filter | 必须成功，否则停止 |
| 5 pcap-export | 可选，失败仅记录警告 |
| 6 mddb-fetcher | 可选，失败仅记录警告 |
| 7 elt-nlt-export | 可选，失败仅记录警告 |
| 8 trace-aggregate-and-package | 必须成功，并执行 schema 校验 |
| 9 samba-publish | 默认软失败（`SMB_PUBLISH_REQUIRED=0`），可改为硬失败 |

## 九、相关项目

- Phase 2 (Linux skill)：`.agents/skills/modem-analysis-unified/`
- 旧版整合 skill（已 DEPRECATED）：`.agents/skills/modem-analysis-unified-legacy/`
