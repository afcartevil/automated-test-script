---
name: drv-video-trunk-commit-port
description: >-
  将飞书 Wiki「主干提交记录」中的 Gerrit/Git 提交链接对应改动，移植到用户指定的另一代码基线（分支/项目）。
  支持按 Wiki 索引选提交、拉取 patch、cherry-pick 或手工合入、冲突处理与基线差异适配。
  当用户要求代码移植、合入主干提交、cherry-pick 到基线、从 U4clwnheoiNw52k1txucw8AFnoV 移植提交时使用。
  若 TRUNK_COMMITS.md 未同步提交链接，须先补齐索引或请用户直接提供提交 URL。
---

# 主干提交 · 基线代码移植

## 文档角色

| 角色 | 含义 | 在本流程中的位置 |
|------|------|------------------|
| **主干提交索引** | [飞书 Wiki](https://transsioner.feishu.cn/wiki/U4clwnheoiNw52k1txucw8AFnoV) 中的记录表，**核心是提交链接** | 选定要移植的 change；见 [TRUNK_COMMITS.md](TRUNK_COMMITS.md) |
| **源提交（Source）** | 链接指向的 Gerrit change / git commit | **移植内容**：以 patch/diff 为准 |
| **目标基线（Target）** | 用户指定的仓库路径 + 分支 | **合入目的地**：所有修改最终落在此基线 |

**原则**：以 **提交链接拉到的实际 diff** 为移植范围；Wiki 文字说明仅作辅助，**不得**在未看到 patch 的情况下臆造改动的文件或逻辑。

## 适用范围

- 把 Wiki 中登记的 **单个或多个** 主干提交移植到 **另一基线**（如项目分支、旧平台分支、OD/非 OD 基线）
- 用户直接给出 Gerrit URL / Change-Id / commit hash，要求合入指定基线
- **不负责**：无提交链接的「仿写功能」、与 Wiki 无关的全新开发（除非用户明确只要参考某链接）

## 前置条件

| 输入 | 必需性 | 说明 |
|------|--------|------|
| **目标基线** | 必需 | 本地仓库根路径 + 分支名（如 `tOS_mtk_A15_xxx`） |
| **要移植的提交** | 必需 | Wiki 条目 ID / 提交链接列表 / Change-Id |
| **源仓库 remote** | 推荐 | 能 `git fetch` 到源 commit；或提供已下载的 `.patch` |
| `TRUNK_COMMITS.md` | 推荐 | 从 Wiki 选提交时使用；可直接给链接则不必 |

## 工作流总览

```
步骤 0  确认源提交链接 + 目标基线 + 移植顺序（多提交时）
  → 步骤 1  拉取源 patch（Gerrit/git）
  → 步骤 2  分析 diff 与依赖（是否需前置提交）
  → 步骤 3  检查目标基线（是否已含、路径是否存在）
  → 步骤 4  选择策略：cherry-pick / 手工应用 / 分文件移植
  → 步骤 5  执行合入并解决冲突
  → 步骤 6  基线差异适配（宏、路径、API 差异）
  → 步骤 7  自检 + 输出移植报告（PORT_REPORT_TEMPLATE.md）
```

分步说明见 [PORTING_STEPS.md](PORTING_STEPS.md)；常见坑见 [PORTING_PITFALLS.md](PORTING_PITFALLS.md)。

## 步骤 0：锁定源与目标

1. **源**：从用户输入或 `TRUNK_COMMITS.md` 的 **提交链接** 列取得 URL；记录 Change-Id、标题、依赖备注。  
2. **目标**：`TARGET_REPO` 路径、`TARGET_BRANCH`；确认当前 `git status` 干净（或用户允许在 dirty 树工作）。  
3. **顺序**：多提交时按 Wiki **依赖/合入顺序** 排列；有 `Depends-On` 的必须先移植前置 change。  
4. 若链接不可用：停止并列出需用户提供的 patch / `repo download` 命令。

## 步骤 1～2：获取并分析源 patch

**获取（任选可行方式）**：

```bash
# Gerrit（示例，以实际 remote 名为准）
git fetch <remote> refs/changes/<末两位>/<change-num>/<patchset> && git show FETCH_HEAD

# 已有 commit hash
git show <hash> --format=fuller

# Change-Id
git log --all --grep="Ixxxxxxxx" --oneline -n 5
```

**分析要点**：

- 修改文件列表与模块（frameworks / device / vendor / kernel）  
- 是否改 mk/bp/overlay/sepolicy（移植时要同步）  
- 是否依赖同主题其他 change（看 commit message / Wiki 备注）

可用 [opengrok-aosp-search](../opengrok-aosp-search/SKILL.md) 在 **源分支** 上对照上下文；在 **目标分支** 上查目标文件是否已有部分改动。

## 步骤 3：目标基线预检查

在 `TARGET_REPO` 上：

```bash
git checkout <TARGET_BRANCH>
git log --oneline --grep="<Change-Id>" -n 3    # 是否已合入
git merge-base HEAD <source-commit>            # 分岔程度
```

| 结果 | 动作 |
|------|------|
| 已存在同 Change-Id | 报告「已合入」，仅做差异核对 |
| 文件在目标不存在或路径不同 | 走 **手工移植**（步骤 4B） |
| 历史相关、可直接 pick | **cherry-pick**（步骤 4A） |

## 步骤 4～6：合入与适配

- **4A cherry-pick**：`git cherry-pick -x <hash>`；冲突按 [PORTING_STEPS.md](PORTING_STEPS.md) 解决。  
- **4B 手工移植**：按文件应用 hunk，保留目标基线已有定制（不要整文件覆盖除非用户确认）。  
- **适配**：处理 `ifdef`、平台宏、类名/路径差异；缺失依赖时 **列出阻塞项**，不静默删逻辑。

## 步骤 7：输出

按 [PORT_REPORT_TEMPLATE.md](PORT_REPORT_TEMPLATE.md) 输出：源链接、目标分支、实际改动的文件列表、冲突处理摘要、未决项与建议编译验证模块。

## Wiki 索引维护

1. 打开 [Wiki](https://transsioner.feishu.cn/wiki/U4clwnheoiNw52k1txucw8AFnoV)，同步表格到 [TRUNK_COMMITS.md](TRUNK_COMMITS.md)。  
2. **必须保留「提交链接」列**（Gerrit / git web URL）。  
3. 有 Feishu MCP 时：`convert_feishu_wiki_to_document_id` → `get_feishu_document_raw_content`。

## 参考文件

| 文件 | 用途 |
|------|------|
| [TRUNK_COMMITS.md](TRUNK_COMMITS.md) | Wiki 提交链接索引 |
| [PORTING_STEPS.md](PORTING_STEPS.md) | 详细移植步骤与命令 |
| [PORTING_PITFALLS.md](PORTING_PITFALLS.md) | 冲突与基线差异处理 |
| [PORT_REPORT_TEMPLATE.md](PORT_REPORT_TEMPLATE.md) | 移植结果报告 |
| [CASES.md](CASES.md) | 典型案例 |
