# 主干提交移植 · 详细步骤

> **输出模板**：[PORT_REPORT_TEMPLATE.md](PORT_REPORT_TEMPLATE.md)

## 流程概览

```text
0  源链接 + 目标基线 + 干净工作区
1  拉取源 patch
2  分析 diff / 依赖链
3  目标预检查（已合入？路径存在？）
4  cherry-pick 或手工移植
5  解决冲突
6  基线差异适配
7  自检与报告
```

---

## 步骤 0：确认输入

### 必填

- `SOURCE`：一条或多条 **提交链接**（来自用户或 [TRUNK_COMMITS.md](TRUNK_COMMITS.md)）  
- `TARGET_REPO`：目标仓库本地绝对路径  
- `TARGET_BRANCH`：目标分支名  

### 可选

- `SOURCE_REMOTE`：拉源 commit 的 remote 名  
- 移植原因 / JIRA（写入报告）

### 检查

```bash
cd <TARGET_REPO>
git status -sb
git branch --show-current
```

| 条件 | 下一步 |
|------|--------|
| 分支正确、用户接受当前状态 | 步骤 1 |
| 分支错误 | `git checkout TARGET_BRANCH` 后再继续 |

---

## 步骤 1：拉取源提交

### Gerrit 链接

从 URL 解析 `project`、`change number`；常用：

```bash
# repo / gerrit review 环境（按项目规范）
repo download <project> <change>/<patchset>

# 或 git fetch（remote 已配置时）
git fetch <remote> refs/changes/XX/<NNN>/<PS>
git show FETCH_HEAD > /tmp/port-<NNN>.patch
```

### 仅 Change-Id

```bash
git fetch --all
git log --all --grep="Ixxxxxxxxxxxxxxxx" --format="%H %s" -n 5
```

### 无法拉取

向用户索要：`.patch` 文件、`git format-patch` 输出、或可读 Gerrit 的账号方式。

---

## 步骤 2：分析 diff 与依赖

### 操作

1. `git show <commit> --stat` 列出文件。  
2. `git show <commit> -p` 阅读逻辑变更。  
3. 读 commit message：`Depends-On`、`cherry picked from`。  
4. 对照 Wiki **依赖** 列；缺前置则 **先移植依赖** 或报告阻塞。

### 输出（内部）

- 文件列表（按模块分组）  
- 是否 touch：Android.bp / Makefile / sepolicy / overlay  
- 建议策略：**A cherry-pick** / **B 手工**

---

## 步骤 3：目标基线预检查

```bash
cd <TARGET_REPO>
git checkout <TARGET_BRANCH>
git log --oneline --grep="<Change-Id>" -n 3
# 对关键文件
git log -1 -- <path/to/key/file>
```

| 结果 | 动作 |
|------|------|
| 已有同 Change-Id | 步骤 7 报告「已存在」，可选 `git show` 对比差异 |
| 无该提交，文件存在 | 步骤 4A 或 4B |
| 源有、目标无此路径 | 步骤 4B，评估是否需新增文件或改路径 |

---

## 步骤 4A：cherry-pick

```bash
git cherry-pick -x <source-commit-hash>
```

多提交：

```bash
git cherry-pick -x <hash1> <hash2>   # 按 Wiki 顺序
```

失败时 **不要** `cherry-pick --abort` 除非用户要求；保留冲突标记供步骤 5 处理。

---

## 步骤 4B：手工移植

适用：cherry-pick 冲突极大、路径不一致、或仅需部分 hunk。

1. 在目标分支对每文件打开源/目标对照。  
2. 按 **语义** 合入：保留目标基线上的平台定制注释与宏。  
3. 同步修改 **调用方 / 头文件 / bp.mk**。  
4. 每文件完成后 `git add`；全部完成后 `git commit`，message 含：

   ```text
   Port from <Change-Id / gerrit link>

   Cherry-picked/adapted for <TARGET_BRANCH>.
   ```

---

## 步骤 5：冲突解决

### 原则

- **业务逻辑** 以源提交意图为准（修复/功能）。  
- **平台/项目定制** 以目标基线为准（SKU 宏、transsion 扩展）。  
- 无法判断时：在报告中 **列出冲突片段** 请用户裁定。

### 常用命令

```bash
git diff --name-only --diff-filter=U
git add <resolved-files>
git cherry-pick --continue   # 或 git commit
```

---

## 步骤 6：基线差异适配

检查项：

- [ ] API 级别差异（Android 版本 bump）  
- [ ] 头文件路径 / 命名空间变化  
- [ ] `Android.bp` / `Android.mk` 模块名是否需注册  
- [ ] sepolicy / init.rc / overlay 是否漏改  
- [ ] 仅源分支存在的辅助函数：在目标实现等价逻辑或抽公共层  

---

## 步骤 7：自检与报告

### 建议自检

```bash
git diff --stat HEAD~1
git log -1 --format=fuller
# 可选：对修改模块执行用户提供的编译命令
```

### 报告

填写 [PORT_REPORT_TEMPLATE.md](PORT_REPORT_TEMPLATE.md)。
