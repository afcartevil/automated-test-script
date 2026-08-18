# SPN 远程数据看板

SPN 看板作为 **CarrierConfig 远程看板的副页面**（同一 HTML，顶部 Tab 切换）。  
**Agent 在 ANALYZED / SUBMITTED 必须上报**，否则他人用本 skill 解决问题不会进入统计。

## Agent 强制步骤

### 1. 分析完成（ANALYZED）— 必做

输出分析报告后立刻执行：

```bash
python "%USERPROFILE%\.cursor\skills\spn-workflow\assets\spn_dashboard_cli.py" --json record \
  --jira-id <JIRA_KEY> \
  --platform MTK \
  --fault-link "状态栏/锁屏" \
  --operator-mccmnc 25016 \
  --workflow-state ANALYZED \
  --auto-score \
  --confidence 已证实 \
  --has-timeline --has-log-evidence --has-breakpoint
```

`--auto-score` 会按平台/链路/时间线/日志证据/断点/置信度计算 `accuracy_score` 与 `PASS|FAIL|CONDITIONAL`。

缺日志导致无法完成证据链时：仍可 record，但 `--confidence 待确认` 且对应 `--no-has-*`，结果多为 `CONDITIONAL`/`FAIL`。

### 2. Gerrit 提交成功（SUBMITTED）— 必做

```bash
python "%USERPROFILE%\.cursor\skills\spn-workflow\assets\spn_dashboard_cli.py" --json record \
  --jira-id <JIRA_KEY> \
  --platform MTK \
  --fault-link "状态栏/锁屏" \
  --operator-mccmnc 25016 \
  --workflow-state SUBMITTED \
  --pass-fail PASS \
  --accuracy-score 100 \
  --change-url "https://gerrit.../+/12345" \
  --branch <TARGET_BRANCH> \
  --submit-phase post
```

### 3. 补传 / 查看 / 里程碑

```bash
# 补传 pending
python .../spn_dashboard_cli.py --json flush

# 远程摘要
python .../spn_dashboard_cli.py --json summary

# 里程碑检查（默认满 30 单起通知，不检查成功率）
python .../spn_dashboard_cli.py check --min-total 30
python .../spn_dashboard_cli.py --json check --min-total 30

# 打开看板（CarrierConfig 页 + SPN Tab）
harness carrierconfig dashboard remote --open
```

## 里程碑提醒（满 30 单）

当**远程** `spn/dashboard/record` 记录数达到 **30 单起** 时桌面通知（**默认不检查成功率**）：

```bash
python "%USERPROFILE%\.cursor\skills\spn-workflow\assets\spn_dashboard_cli.py" check
python .../spn_dashboard_cli.py --json check --min-total 30
# 可选同时检查成功率：--min-success-rate 90
# 强制再通知：--force-notify
# 清状态重计：--reset-state
```

档位：30 → 60 → 90 … 每满一个 30 档再通知一次。

状态文件：`~/.tran_harness/spn/dashboard_milestone_state.json`

### Windows 每日 9:00 自动检查

双击安装：

`spn-workflow/assets/安装-每日9点SPN看板检查.bat`

或命令行：

```bash
python "%USERPROFILE%\.cursor\skills\spn-workflow\assets\spn_dashboard_cli.py" --json install-daily --time 09:00
```

- 计划任务名：`Harness-SPN-Dashboard-Daily-Check`
- Runner：`~/.tran_harness/spn/run_daily_check.cmd`
- 日志：`~/.tran_harness/spn/daily_check.log`

卸载：

```bash
python .../spn_dashboard_cli.py --json uninstall-daily
```

脚本路径回退：

1. `~/.cursor/skills/spn-workflow/assets/spn_dashboard_cli.py`
2. SkillHub 缓存：`~/.tran_harness/cache/skillhub-skills/team-com-dev--spn-workflow/*/assets/spn_dashboard_cli.py`

本地 pending：`~/.tran_harness/spn/dashboard_pending.jsonl`

## 打开看板（双 Tab：CarrierConfig + SPN）

**推荐入口（spn-workflow 自带，不依赖 CarrierConfig 正式包）：**

```bash
python "%USERPROFILE%\.cursor\skills\spn-workflow\assets\spn_dashboard_cli.py" remote --open
```

生成路径：

- `~/.tran_harness/spn/dashboard/remote_dashboard.html`
- 同步副本：`~/.tran_harness/carrierconfig/dashboard/remote_dashboard.html`

同一 HTML 顶部 Tab：**CarrierConfig | SPN**，分别拉取全团队远程数据。

兼容旧入口（本机若仍有 carrierconfig 脚本）：

```bash
harness carrierconfig dashboard remote --open
```

## 后端事件格式

`command_path` 固定 `spn/dashboard/record`：

```json
{
  "event_id": "evt-spn-dash-TOS163-46389-...",
  "command_path": "spn/dashboard/record",
  "command_category": "SPN",
  "params": {
    "record_type": "spn_dashboard_stat",
    "domain": "connectivity-spn-workflow",
    "jira_id": "TOS163-46389",
    "accuracy_score": 95,
    "pass_fail": "PASS",
    "platform": "MTK",
    "fault_link": "状态栏/锁屏",
    "operator_mccmnc": "25016",
    "workflow_state": "ANALYZED"
  }
}
```

## 字段

| 字段 | 说明 |
|---|---|
| `jira_id` | Jira 单号 |
| `platform` | MTK / QCOM |
| `pass_fail` | PASS / FAIL / CONDITIONAL |
| `fault_link` | 状态栏/锁屏、手动搜网、displayName、MVNO、云网SPN、注入/编译、其他 |
| `operator_mccmnc` | 运营商 PLMN |
| `workflow_state` | ANALYZED / SUBMITTED 等 |
| `accuracy_score` | 证据完整度评分 |

## 门禁

- `spn.dashboard.record.on.analyzed`：未上报不得宣称 ANALYZED 闭环
- `spn.dashboard.record.on.submitted`：有 Gerrit CR 时未上报不得宣称 SUBMITTED 闭环
- 上报失败：保留 pending，`flush` 重试；在最终报告写明失败原因，**不得伪造 event_id**
