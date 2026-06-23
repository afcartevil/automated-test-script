---
name: apn-edit
description: "Edit APN XML in this repo. Invoke when user asks to add/update/delete APN entries."
---

# APN Edit

当用户提出要修改某个安卓版本的 APN 参数时，定位目标 APN 条目并做最小化修改并通过飞书机器人把修改内容发出。

## 触发场景

- “修改/新增/删除 APN”
- “修改 apns-conf.xml”
- 任何包含 APN 参数变更 + Android 版本/分支信息 的需求

## 前置约束

- 修改 `apns-conf.xml` 前必须先查看字段定义：`references/apn-schema.md`
- 只做与需求直接相关的最小改动，不重排、不格式化无关内容

## 工作流

### Step 0：确认目标版本/分支与目标文件

- 根据用户需求中的平台/安卓版本，确认应修改的目标文件路径
- 如有歧义，优先用仓库内的既有目录结构与文件名进行定位（例如不同版本目录下的 `apns-conf.xml`）
- **平台与文件范围：**
  - **MTK**：配置文件分布在 4 个安卓版本目录（见 `references/apn-schema.md`）
  - **高通**：**仅**修改 `master_w/apns-conf.xml`（高通平台无 W 以下安卓版本，不涉及 `apns-conf.xml`、`master_s/`、`master_u/`）

#### 按 `type` 决定 MTK 要改哪些文件（硬性规则）

先根据目标条目的 `type` 判断修改范围，**不要**默认只改 `master_w/`：

| `type` 类别 | 典型 `type` 值 | MTK 必须修改的文件 |
|------------|---------------|-------------------|
| **上网 / 彩信** | `default`、`supl`、`mms`、`dun` 及含上述的组合（如 `default,supl`） | **全部 4 个文件**：`apns-conf.xml`、`master_s/apns-conf.xml`、`master_u/apns-conf.xml`、`master_w/apns-conf.xml` |
| **IMS / XCAP / 补充业务** | `ims`、`xcap` 等 | 按需求涉及的安卓版本修改对应文件（可能只涉及部分版本目录） |

- **上网/彩信类 MTK 变更必须在同一次编辑中覆盖全部 4 个安卓版本文件**，禁止只改 `master_w` 或只改用户点名的某一个版本文件。
- **反例**：玻利维亚 736 上网/彩信变更只提交 `master_w/apns-conf.xml` 到 MTK 主干——这是不完整提交。
- **高通**：无论 `type` 为何，始终**仅**修改 `master_w/apns-conf.xml`。

### Step 1：定位目标 APN 条目

- 用唯一标识组合定位：`mcc+mnc`、`carrier`、`apn`、`type`
- 仅读取命中行及其上下文，避免整文件加载

### Step 2：应用修改（最小化变更）

- 只修改需求涉及的属性字段
- 不改变无关条目的顺序、缩进、换行风格
- 若 `type` 为上网/彩信类且平台为 **MTK**：在 4 个版本文件中做**相同的最小化变更**（同一 PLMN + `type` 条目在各文件中保持同步）

### Step 3：验证修改

- 重新读取已修改的条目片段，确认字段和值准确
- 输出变更 diff，确保无额外改动

### Step 4：Review（提交前必做）

- **必须先读**仓库根目录 `.agent/test-suggestion.md`（APN review 规则清单）
- 按 `references/apn-review.md` 流程，对本次 diff 逐条对照规则检查
- 输出 review 报告（每条规则：通过 / 不通过 + 说明）
- **任一规则不通过**：修正后回到 Step 3，不得提交
- **全部通过**：方可进入 Gerrit 提交

## 提交到 Gerrit

- 使用 `gerrit-submit` skill 完成提交与推送

## Step 5：主干提交后评估并同步量产分支

- 当 APN 变更先提交到 `master`（MTK）或 `com_master_qcomw`（高通）后，必须根据以下规则给出“建议同步分支”并询问用户是否执行同步。
- 规则：
  - `type` 涉及 IMS 或 XCAP（如 `ims`、`xcap`）：直接询问用户是否需要同步量产分支（仅当前平台）。
  - `type` 涉及上网或彩信（如 `default`、`supl`、`mms`）：必须**跨平台**同步——MTK 侧同步**全部 4 个安卓版本文件**（`apns-conf.xml`、`master_s/`、`master_u/`、`master_w/`）；高通侧**仅**同步 `master_w/apns-conf.xml`；并同步到另一平台主干与全部量产分支。
- 主干分支：
  - MTK：`master`
  - 高通：`com_master_qcomw`
- 量产分支清单：
  - MTK：`tOS16.2.0_mtk_sys_release`、`tOS16.3.0_mtk_sys_release`
  - 高通：`tOS16.2.0_qcom_sys_release`、`tOS16.3.0_qcom_sys_release`
- 跨平台同步示例（上网/彩信）：
  - 首次提交到 `master`（MTK 主干）后，建议同步目标还包括：`com_master_qcomw`（高通主干，仅改 `master_w/apns-conf.xml`）、高通两个量产分支、MTK 两个量产分支。
  - 首次提交到 `com_master_qcomw`（高通主干，仅 `master_w/apns-conf.xml`）后，建议同步目标还包括：`master`（MTK 主干）、MTK 各版本对应文件、MTK 两个量产分支、高通两个量产分支。
- 若用户同意同步：
  - 量产分支提交必须沿用主干相同的 commit message 与 `Change-Id`。
  - 先从主干提交中提取完整 commit message（含自动生成的 `Change-Id: I...` 行），量产分支提交时原样复用。
  - 不允许修改 `Change-Id`，避免生成新的变更链。
  - 仍需遵循最小化提交原则：只 add 实际修改文件，禁止 `git add .`。

## Step 6：通过webhook连接飞书机器人把修改内容发出去

webhook: https://open.feishu.cn/open-apis/bot/v2/hook/f857fb31-275d-41f7-90c3-ccdd79f37d98

## 关键文件

- `references/apn-schema.md`
- `references/apn-review.md` — review 执行流程
- `.agent/test-suggestion.md` — **APN review 规则清单（SSOT）**
