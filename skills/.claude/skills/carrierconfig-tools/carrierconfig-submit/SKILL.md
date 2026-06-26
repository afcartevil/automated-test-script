---
name: carrierconfig-submit
description: >
  更新 jira_issue_notes 台账记录，执行 Git 提交推送到 Gerrit，并通过飞书通知变更。
  触发词："提交 CarrierConfig"、"推送 gerrit"、"更新台账"、"submit carrierconfig"、
  "git提交"、"push到gerrit"、"飞书通知"、以及 carrierconfig-edit 完成后自动衔接。
---

# CarrierConfig Submit Skill

## 用途

在 XML 配置修改完成后，完成三件事：
1. 更新 `jira_issue_notes` 台账
2. Git commit + push 到 Gerrit
3. 通过飞书 webhook 发送变更通知

---

## 前置条件

必须已完成 `carrierconfig-edit` 的修改，且用户已确认 diff 正确。

---

## 操作流程

### Step 1：预填 jira_issue_notes

从前序步骤的上下文中自动提取信息，预填台账记录：

| 字段 | 来源 |
|------|------|
| `jira_id` | jira-reader 输出 |
| `description` | Jira 标题/摘要 |
| `mccmnc` | carrier-lookup 输出 |
| `carrier_id` | carrier-lookup 输出 |
| `carrier_name` | carrier-lookup 输出 |
| `target_file` | carrierconfig-edit 实际修改的文件 |
| `change_note` | "key1=value1; key2=value2" |

**填写规则**：
- `target_file` 必须是最终实际修改的文件路径
- `change_note` 写清楚 key 和值，如 `carrier_volte_available_bool=false`
- 若改动回退，需在 `change_note` 写明"已回退+原因"
- 同一 Jira 涉及多个运营商时，`jira_id` 和 `description` 仅在首行填写；后续行这两列留空

输出预填表格供用户确认：

```
## 台账预填

| jira_id | description | mccmnc | carrier_id | carrier_name | target_file | change_note |
|---------|-------------|--------|------------|--------------|-------------|-------------|
| AR-20250409-0421 | [CarrierConfig] 伊拉克41820 xcap参数 | 41820 | 1657 | Zain | carrier_config_mtk_all_project.xml | carrier_xcap_restricted_bool=true |

请确认台账信息是否正确。
```

### Step 2：写入台账

用户确认后，将预填记录新增到 `shared/data/carrier_keys_matrix.xlsx` 的 `jira_issue_notes` 工作表。

### Step 3：提交前自检

精简为 3 项人工确认：

- [ ] **台账已更新** — jira_issue_notes 有且仅一条有效记录
- [ ] **XML 完整** — 修改后的 XML 结构完整，无重复冲突
- [ ] **注释格式** — TDD 注释成对，Jira ID 正确

### Step 4：Git Commit

```bash
# 1. 确认当前分支（应已在正确分支上）
git branch --show-current

# 2. 仅 add 修改的文件（禁止 git add .）
git add <具体文件路径>

# 3. Commit
git commit -m "ID:AR-20250409-0421
DESCRIPTION:[CarrierConfig] {需求描述摘要}
TYPE:conf
AFFECT_PROJECTS:ALL
TEST_SUGGESTIONS:对照归档表验证"
```

**Commit 格式规范**：
```
ID:AR-20250409-0421
DESCRIPTION:[CarrierConfig] {需求描述}
TYPE:conf
AFFECT_PROJECTS:ALL
TEST_SUGGESTIONS:对照归档表验证
```

**红线**：
- ID 固定为 `AR-20250409-0421`，不可修改
- DESCRIPTION 填用户给的需求描述
- TYPE / AFFECT_PROJECTS / TEST_SUGGESTIONS 不可修改
- **禁止 `git add .`** — 改了什么文件就 add 什么文件

### Step 5：Push 到 Gerrit

```bash
git push origin HEAD:refs/for/<branch>
```

分支映射：
- MTK 主干 → `refs/for/master`
- QCOM 主干 → `refs/for/com_master_qcomw`

**推送前检查**：
- 确认在正确分支上
- 若推送报错，先尝试自行解决（如 rebase、解决冲突）

### Step 6：飞书通知

通过 webhook 发送变更摘要到飞书群：

```
POST https://open.feishu.cn/open-apis/bot/v2/hook/f857fb31-275d-41f7-90c3-ccdd79f37d98
```

通知内容模板：
```json
{
  "msg_type": "interactive",
  "card": {
    "header": {
      "title": {"tag": "plain_text", "content": "CarrierConfig 变更通知"},
      "template": "blue"
    },
    "elements": [
      {"tag": "div", "text": {"tag": "lark_md", "content": "**Jira**: {jira_id}"}},
      {"tag": "div", "text": {"tag": "lark_md", "content": "**描述**: {description}"}},
      {"tag": "div", "text": {"tag": "lark_md", "content": "**运营商**: {carrier_name} ({mccmnc})"}},
      {"tag": "div", "text": {"tag": "lark_md", "content": "**修改文件**: {target_file}"}},
      {"tag": "div", "text": {"tag": "lark_md", "content": "**变更内容**: {change_note}"}},
      {"tag": "div", "text": {"tag": "lark_md", "content": "**分支**: {branch}"}}
    ]
  }
}
```

---

## 异常处理

| 异常 | 处理方式 |
|------|----------|
| 推送被拒绝（非 fast-forward） | `git pull --rebase` 后重试 |
| 推送被拒绝（缺少 Change-Id） | 检查 commit-msg hook 是否安装 |
| 台账写入失败 | 提示用户手动填写，不阻塞 git 提交 |
| 飞书通知失败 | 不阻塞流程，记录失败信息 |

---

## 禁止事项

1. **禁止 `git add .`** — 只 add 实际修改的文件
2. **禁止修改 commit 格式** — ID 固定，其他字段不可改
3. **禁止跳过台账** — jira_issue_notes 是必做步骤
4. **禁止在错误分支提交** — 先确认分支再 commit

---

## 与其他 Skill 的衔接

```
carrierconfig-edit → diff 确认 ──→ carrierconfig-submit（本 skill）
                                   ├── Step 1-2: 更新台账
                                   ├── Step 3: 自检
                                   ├── Step 4-5: Git 提交推送
                                   └── Step 6: 飞书通知
```
