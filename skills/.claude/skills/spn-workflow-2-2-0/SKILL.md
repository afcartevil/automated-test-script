---
name: spn-workflow
description: 处理 Android SPN、PLMN、运营商名称和 displayName 问题的 Jira 驱动工作流。读取 Jira 与用户提供的日志，识别 MTK/QCOM 平台和故障链路，输出证据化分析，按公司规范修改源码并展示 diff；用户确认后，根据 Jira 问题版本解析目标分支，通过 Harness 创建或更新 Gerrit CR。用户提到 SPN、运营商名称、手动搜网、状态栏网络名、MVNO、云网 SPN、displayName 或要求分析并提交相关 Jira 时使用。
version: 2.2.0
---

# SPN Workflow

统一执行 `Jira → 日志 → 分析 → 改码 → diff 确认 → 分支解析 → Gerrit`。优先使用 Harness 的结构化能力；不存在对应能力时才使用本地只读工具或经用户批准的 runner fallback。

## 输入

必需：

- Jira key/URL；
- 用户提供的日志文件、目录或压缩包。

改码前还必须明确：

- 与 Jira 问题版本对应的源码 workspace；
- 每个待修改 repo project；
- 唯一目标分支。

缺少日志时只输出采集清单，不猜根因。缺少 workspace 或目标分支时可以完成分析和建议，但不得改码或提交。

## 状态机与门禁

严格按顺序执行：

```text
INTAKE → ANALYZED → PATCHED → DIFF_APPROVED → BRANCH_RESOLVED → VERIFIED → SUBMITTED
```

- `ANALYZED`：平台、现象分类、关键时间线、链路断点和根因都有证据。
- `PATCHED`：仅修改根因相关文件，未提交。
- `DIFF_APPROVED`：用户明确确认 diff；仅“继续分析”不等于确认。
- `BRANCH_RESOLVED`：Jira 版本、项目矩阵、workspace manifest 三者一致，且每个 repo 只有一个目标分支。
- `VERIFIED`：编码规范、自检及可执行的最小编译通过。
- `SUBMITTED`：通过 `harness gerrit create/upload` 完成，返回 CR。

禁止跳过状态。分析请求不自动改码；改码请求不自动提交；未确认 diff 不得 commit/push。

## Harness 工具映射

| 任务 | 首选能力 |
|---|---|
| Jira 详情、评论、附件清单 | `harness --json jira get` |
| Jira 日志附件下载 | `harness --json jira download-logs` |
| 项目平台与分支矩阵 | `harness --json project-info search/detail` |
| 问题版本与主分支事实 | `harness --json version-server list-versions` |
| 精确分支、父分支、checkout | `harness --json branch-server info/checkout` |
| 跨版本源码证据 | `harness --json opengrok search/fetch` |
| 已有 SPN CR/topic 证据 | `harness --json gerrit search/get/files/diff` |
| workspace 状态与 diff | `harness --json git repo-status/repo-diff` |
| Linux workspace 操作 | `harness remote-runner` 语义化 action |
| 编码规范 | `harness --json coding-standards checklist` |
| 模块编译 | `harness build native` |
| 提交说明 | `harness --json gerrit commit-message` |
| 首次创建/追加 CR | `harness --json gerrit create/upload` |
| **CLI 路由与编排** | `harness --json knowledge route --path connectivity/sub/spn` |
| **读取 workflow 编排** | `harness --json knowledge read connectivity/sub/spn/workflow.yaml --source local` |
| **SkillHub 门禁** | `harness --json skillhub gate <skill-dir> --namespace team-com-dev --slug spn-workflow` |
| **看板上报（必做）** | `python assets/spn_dashboard_cli.py record ...`（见 [references/dashboard.md](references/dashboard.md)） |
| **看板查看（双 Tab）** | `python assets/spn_dashboard_cli.py remote --open`（CarrierConfig + SPN 同一界面） |

参数不确定时先执行：

```text
harness --json commands describe <command path>
```

不得凭记忆猜 Harness 参数，不得用 raw API、手拼 `git push refs/for/*` 或 `repo upload` 绕过 Harness。

## Phase 1：Jira intake

执行：

```text
harness --json jira get --issue <JIRA_KEY>
```

提取并记录：

- summary、description、复现步骤、期望/实际结果；
- 项目、问题版本、Android/TOS 版本、build type；
- 国家、运营商、SIM MCCMNC、驻网 MCCMNC；
- 单/双卡、实体卡/eSIM、自动驻网/手动搜网；
- 附件、评论、已有 CR；
- assignee、状态和优先级。

Jira 字段为空时从日志补证；冲突时以原始日志和结构化项目/版本查询为准，并在报告中标明冲突。

## Phase 2：日志检查与平台识别

先列出日志清单，再确定复现时间窗。优先读取 `radio`、`main/system`、`properties`、`dumpsys`，不要无差别扫描所有大文件。

平台强特征：

- MTK：`MtkRIL`、`MtkServiceStateTracker`、`MtkSpnOverride`、`MtkSIMRecords`、`mt[0-9]+`。
- QCOM：`QTIRILJ`、`QtiRIL`、`QtiServiceStateTracker`、`QcomSpnOverride`、`QtiSIMRecords`、`sm[0-9]+`。

只有 `RILJ`、`SpnOverride`、`lookupOperatorName` 等公共特征时不得定平台。平台无法确认时停止源码分流，并请求设备属性或 radio 日志。

按现象只选择一条主链路：

1. 状态栏/锁屏/通知栏；
2. 手动搜网列表；
3. SIM displayName/nameSource；
4. MVNO/子品牌；
5. 云网 SPN；
6. 注入、编译或启动异常。

详细决策树按平台读取：

- MTK：[references/mtk.md](references/mtk.md)
- QCOM：[references/qcom.md](references/qcom.md)

## Phase 3：证据化分析

至少建立以下时间线：

```text
SIM state → subId → SIM MCCMNC/EF_SPN → 注册 PLMN/NITZ/EONS
→ lookup 结果 → SERVICE_PROVIDERS_UPDATED → SystemUI/displayName
```

每个结论必须包含：

- 原始日志路径、时间戳和关键行；
- 输入值与输出值；
- 断点所在类/函数；
- 配置、源码或历史 CR 的独立佐证。

区分事实和推断：

- `已证实`：日志或源码直接证明；
- `高概率`：证据链完整但缺设备侧状态；
- `待确认`：需要补抓日志、dumpsys 或 SIM 文件。

输出格式见 [references/report-template.md](references/report-template.md)。

进入 `ANALYZED` 后**必须**上报看板（未上报不算分析闭环）：

```text
python <spn-workflow>/assets/spn_dashboard_cli.py --json record \
  --jira-id <JIRA_KEY> \
  --platform MTK|QCOM \
  --fault-link <状态栏/锁屏|手动搜网|displayName|MVNO|云网SPN|注入/编译|其他> \
  --operator-mccmnc <MCCMNC> \
  --workflow-state ANALYZED \
  --auto-score \
  --confidence 已证实|高概率|待确认 \
  --has-timeline --has-log-evidence --has-breakpoint
```

脚本路径优先：当前 Cursor skill 目录 `~/.cursor/skills/spn-workflow/assets/spn_dashboard_cli.py`；或 SkillHub 缓存中的同路径。上报失败时保留本地 pending，后续 `flush`；不得伪造已上报。详情见 [references/dashboard.md](references/dashboard.md)。

## Phase 4：源码定位与修复设计

1. 用 `project-info detail` 确认平台和分区分支。
2. 用 OpenGrok 查权威分支源码；无对应分支时，以 Jira 版本 workspace + Gerrit 历史为准。
3. 用 Gerrit 查询相关 SPN topic/CR，确认是否为移植遗漏或已有修复。
4. 明确 repo project、文件、函数、修改理由和回归风险。
5. Java/Kotlin 修改前执行：

```text
harness --json coding-standards checklist --language java --severity mandatory
```

6. 仅在 Jira 对应 workspace 中修改；加密 Windows 视图不可写时，使用 remote-runner 的语义化 action。

修复原则：

- 优先修正时序、来源选择或查找链，不用 MCCMNC 硬编码掩盖通用缺陷；
- 配置缺失才修改 `spn-conf.xml`/`plmn-conf.xml`；
- 不混改 MTK/QCOM；
- 不扩大到无关清理；
- 公司问题单注释使用当前仓既有格式，Jira ID 必须正确，start/end 成对。

## Phase 5：diff 交付

修改后按 repo 分别输出：

- repo project、目标文件和修改摘要；
- 完整 diff/stat；
- 根因到代码变更的对应关系；
- 风险和验证项。

不得 stage、commit 或 push。明确询问用户是否确认 diff。用户要求调整时返回 `PATCHED`，修改后重新展示 diff。

## Phase 6：按 Jira 问题版本解析分支

用户确认 diff 后读取 [references/submission.md](references/submission.md)，执行分支解析门禁。

核心规则：

- Jira 的版本名称是输入，不直接等于 Gerrit 分支；
- `version.spug.branch` 只代表 TOS/系统主分支，不代表所有 sys/vnd/nonhlos repo；
- 结合 `project-info detail` 的 `branches_by_partition`、`branch-server info` 和 workspace manifest revision；
- 每个 repo project 单独解析目标分支；
- 有多个候选、workspace 与 Jira 版本不一致、或 repo revision 无法映射时，停止并让用户选择。

输出《提交计划》，包含 Jira 版本、平台、workspace、repo、目标分支、文件、提交类型。用户确认 diff 不等于确认一个存在歧义的分支。

## Phase 7：自检、编译与 Gerrit

提交前：

1. 重新检查 repo diff，确保无无关文件；
2. 执行 mandatory 编码规范检查；
3. 检查 import、空值、线程/时序、display source 优先级及注释；
4. 能模块编译时使用 `harness build native`，不能编译时明确原因和替代验证；
5. 使用 `harness gerrit commit-message` 生成公司模板；
6. 首次 CR 用 `harness gerrit create`；已有 Change-Id 追加 patch set 用 `harness gerrit upload`；
7. 每个 git project 独立提交，不使用 `git add .`。

真实 Gerrit 写操作前再次展示最终提交计划并取得明确确认。

Gerrit 创建/上传成功进入 `SUBMITTED` 后，**必须**再次上报看板：

```text
python <spn-workflow>/assets/spn_dashboard_cli.py --json record \
  --jira-id <JIRA_KEY> \
  --platform MTK|QCOM \
  --fault-link <...> \
  --operator-mccmnc <MCCMNC> \
  --workflow-state SUBMITTED \
  --pass-fail PASS \
  --accuracy-score 100 \
  --change-url <GERRIT_CR_URL> \
  --branch <TARGET_BRANCH> \
  --submit-phase post
```

仅分析不改码时，在 Phase 3 上报一次即可；有提交时 ANALYZED + SUBMITTED 各一次。

## 最终交付

报告：

- Jira 与问题版本；
- 平台判定和日志证据；
- 根因、修复策略与改动文件；
- 验证结果和未执行项；
- 每个 repo 的目标分支、commit/CR 链接；
- 刷机后复测清单；
- 看板上报结果（`event_id` / upload status）。

## 边界

- 本 skill 不修改 Jira 状态或评论。
- 用户提供的日志默认只读，不修改或覆盖。
- 不记录密码、token、设备 SN、完整个人路径。
- 不把 personal workspace、盘符或用户名写死到公共文档。
- runner 不可用时可以完成分析和 patch 设计，但不得伪造 diff、编译或提交结果。
