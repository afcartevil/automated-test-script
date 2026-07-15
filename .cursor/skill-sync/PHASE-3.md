# Phase 3 — 审核发布 + GitLab 版本 + Bundle（可执行提案）

> **状态**：可执行提案（2026-07-14 定稿方向）  
> **前置**：Phase 2 已交付；遵守 [SELF-CHECK.md](./SELF-CHECK.md)  
> **目标**：Skill 整包 / 知识条目「先审后发」；通过后写入中心 `data/...` 并 **直推 GitLab master**（CI 账号）；版本靠 Git 历史；客户端可查单 Skill 历史；Bundle CRUD + 按包同步。  
> **文档路径**：`.cursor/skill-sync/`  
> **双仓**：客户端 `easyadapter` + 中心 `easyadapter_bff`

---

## 1. 交付目标

1. **审核闸门**：本机「提交服务器」/ 后台录入 → `pending_review`；**不**进入同事可 sync 的 manifest，**不**直写 live 权威目录（除可选 admin force）。
2. **审核通过即发布**：写入中心仓权威路径 `easyadapter_bff/data/...`，并 **`git commit` + `push origin master`**（CI 账号）。
3. **主仓镜像**：发布后另有通道把 `data/...` **同步到主仓** `easyadapter` 对应目录（见 §4.2），保证工程 Git 与中心一致可查。
4. **版本管理 = GitLab**：不自建 version 仓 / current 指针表；回滚用 Git revert 或再提一版审核。
5. **客户端历史**：每个 Skill 可查看其 Git 历史版本记录（commit、作者、时间、摘要；可选看文件列表）。
6. **知识库同轨**：条目审核通过 → 发布到中心 `data/...` → 同样 commit + push；并参与主仓镜像。
7. **Bundle**：中心维护 bundles 注册表；manifest 填真实 `bundle_ids`；同步中心支持「同步此包」。

---

## 2. 锁定决策

| 项 | 定稿 |
|----|------|
| 审核语义 | 待审 ≠ 已发布；manifest / pull **仅** published |
| 权威落盘（第一落点） | **中心仓** `easyadapter_bff` 的 `data/...` |
| 主仓 | **另同步**到 `easyadapter`（`skills/`、`knowledge-base/` 等约定路径） |
| Git 操作 | 审核 **通过后直推 `master`**，使用 **CI 服务账号**（非开 MR） |
| 版本机制 | **GitLab commit history**；不做自研 semver 多版本仓 |
| 包型待审暂存 | 中心本地 pending 目录即可（过审再写入 Git 跟踪的 `data/skills/...`） |
| 紧急直发 | 可选 `force_publish`：**仅 admin + 审计**；默认关闭给普通 token |
| 与 skill_draft | 内容型草稿可继续；**包型统一走 package submission**；通过后都走「写 data + git」 |
| Bundle | **与本 Phase 同批**（非顺延） |
| 历史 API | 中心按路径查 Git log（本机进程 `git log` 或 GitLab API）；Console 展示 |
| **同步权威源** | **同事 sync 的权威 = 中心 `data/` + manifest**；Git 仅承担版本/审计/主仓镜像。manifest 是否可见**不依赖** push 成功（见 §4.2 事务） |
| **Git 提交身份** | committer = CI 账号；author 尽量保留原提交者（`git commit --author`），便于 blame 追溯到人 |
| **并发写** | 中心对「写 `data/` + git」串行化：**单写者锁**（进程内 mutex + 仓库 `.git/index.lock` 兜底）；审核并发时排队执行 |
| **push 竞争** | push 前 `fetch` + `rebase`（或 `pull --rebase`）；失败重试 N 次；仍失败 → 保留本地 commit、标记 `push_pending`、告警，不丢内容 |
| **幂等** | 相同内容（整包 hash 未变）重复提交：不产生空 commit；审核通过对 hash 无变化时跳过 git（记审计即可） |
| **主仓直接编辑** | 见 §3.4：主仓 `skills/` 转为**镜像目标**，直接手改需走评审或纳入冲突告警 |

### 2.1 心智模型

```
改 Skill / 知识 → 提交中心（待审）→ 审核通过
  → 写入 easyadapter_bff/data/...
  → git commit + push master（CI）
  → 镜像同步到 easyadapter 主仓
  → 同事 Sync / pull 拿到已发布内容
  → 客户端可查看该 Skill 的 Git 历史
```

### 2.2 状态机（Skill 包 / 知识条目共用概念）

| status | 含义 | manifest |
|--------|------|----------|
| `pending_review` | 已提交待审 | 否 |
| `rejected` | 已驳回（可再提交） | 否 |
| `published` / `active` | 已发布 | 是 |
| （Git） | 每次通过产生 commit | — |

对齐状态（本机 SyncCenter）增补：

| state | 含义 |
|-------|------|
| `submitted_pending` | 本地已提交、中心仍待审（或最新提交未通过） |
| `rejected` | 最近一次提交被驳回 |
| 既有 `synced` / `behind` / `local_only` | 相对 **已发布** hash |

---

## 3. 目录与 Git 约定

### 3.1 中心仓（`easyadapter_bff`）权威路径

| 内容 | 路径（相对中心仓根） |
|------|----------------------|
| 已发布 Skill 整包 | `data/skills/.claude/skills/<skill_id>/` |
| 知识条目等 | 现有 `data/knowledge-base/...`（与当前 BFF 一致，不另发明格式） |
| Bundle 注册表 | `data/.tahp/skill-bundles.json` |
| 待审包暂存（可不入 Git 或入 ignore） | `data/.tahp/pending-packages/<skill_id>/<submit_id>/` |
| 待审知识 / 草稿元数据 | 沿用现有 pending 存储；**通过后**写入正式路径再 commit |

说明：

- **已发布树**必须被中心仓 Git 跟踪，以便 `git log -- path` 出历史。
- pending 暂存 **默认不推远程**（`.gitignore`），避免未审内容进 master。

### 3.2 主仓镜像（`easyadapter`）

| 中心 | 主仓目标 |
|------|----------|
| `data/skills/.claude/skills/<id>/` | `skills/.claude/skills/<id>/` |
| 知识库已发布内容 | `knowledge-base/` 下约定子树（与现网布局对齐，实现时锁定一张表） |
| `data/.tahp/skill-bundles.json` | `{projectRoot}/.tahp/skill-bundles.cache.json`（只读缓存，可仍走 pull；可选是否入主仓 Git） |

镜像触发（实现选定一种并写死在文档/配置）：

1. **推荐**：中心 approve 流程末尾调用「主仓同步任务」（CI 账号对 `easyadapter` clone/pull → 复制路径 → commit → push `master`）；或  
2. 中心 push 后由 **GitLab CI**（bff pipeline）再推主仓。

失败策略：中心 data 已发布 + 已推 bff 成功，主仓镜像失败 → **告警 + 可重试**，不自动回滚中心发布（避免双写撕裂）；审计记 `main_repo_mirror_failed`。

### 3.3 Commit message 约定

```
publish(skill): <skill_id> [approve <actor>]
publish(kb): <entry_id> [approve <actor>]
publish(bundle): <bundle_id> [actor]
```

Body 可含：提交说明、关联 submit_id、包 hash。

### 3.4 主仓「双向写入」权威冲突（关键）

**现状风险**：主仓 `easyadapter/skills/.claude/skills/` 目前由同事**直接编辑并 `git commit`**（见当前 `git status` 大量 SKILL.md 改动）。若 P3 又把中心 `data/skills` **镜像覆盖**到主仓 master，会与人工直接提交**互相覆盖**，造成丢改动或反复冲突。这是 P3 必须先定策略的头号问题。

**定稿策略（默认方案 A，需产品确认）**：

| 方案 | 说明 | 取舍 |
|------|------|------|
| **A（推荐）单向权威** | 主仓 `skills/`、`knowledge-base/` 已发布子树声明为 **中心镜像产物**；**禁止**手工直接改后推 master，改动一律走「提交中心 → 审核」。镜像任务对目标子树用 **`central 内容为准`** 覆盖。 | 心智统一；需公告 + 可选 pre-commit/CI 拦截 |
| B 双向合并 | 允许两边改，镜像用 3-way merge | 冲突治理复杂，易撕裂，**不选** |
| C 分支隔离 | 中心只推 `skills-release` 分支，人改在 master | 同事需切分支，违背「同事无感」目标，**不选** |

**方案 A 落地要点**：

- 镜像范围**精确到已发布子树**（`skills/.claude/skills/<id>/`、约定 kb 子树），不动主仓其它文件（`tahp-console/`、`.cursor/` 等照常人工提交）。
- 镜像前 `fetch`+`rebase`；若目标子树有**未经评审的人工改动**与本次发布冲突 → **不静默覆盖**，改为告警 + 记 `main_repo_mirror_conflict`，人工介入。
- 提供**过渡期开关** `TAHP_MAIN_REPO_MIRROR_ENFORCE`：`warn`（仅告警，先不覆盖）→ `enforce`（以中心为准覆盖）。先 `warn` 跑一段时间收敛存量直接改动，再切 `enforce`。
- 可选 pre-commit（主仓 `.cursor/rules` 已有校验入口）：提示「skills/ 请走同步中心提交，勿直接改」。

> **未确认前**：Step 3D 主仓镜像默认 **`warn` 模式**，不真正覆盖主仓，避免破坏现有协作。

---

## 4. API 契约（相对 Phase 2 变更）

### 4.1 提交（待审，不发布）

```
# 本机
POST /api/tahp/skills/publish-package     → 改为「提交审核」（命名可保留，语义变）
POST /api/tahp/skills/publish-packages

# 中心（机器 token）
POST /api/tahp/sync/skill/:id/package/submit
  body: { archive_b64, message?, local_hash? }
  → { submit_id, status: 'pending_review' }

# 禁止默认行为：POST .../package 直接解压进 live
# 可选：POST .../package?force=1 仅 admin
```

知识库：沿用 / 收紧 `POST /api/tahp/sync/submit` → `pending_review`；通过才进 published 集合。

### 4.2 审核

```
GET  /api/tahp/skill-submissions/pending
GET  /api/tahp/skill-submissions/:submit_id           # 详情 + 与已发布的 diff 摘要
POST /api/tahp/skill-submissions/:submit_id/review
  body: { action: 'approve' | 'reject', comment? }
```

**approve 服务端事务（全程持单写者锁；见 §2 并发写）：**

```
0) 取写者锁（进程内 mutex；获取失败则排队/返回 busy）
1) 幂等检查：新整包 hash == 当前已发布 hash → 跳过 2~4，仅记审计并置 published
2) 写入 data/skills/.../<id>/（先写临时目录，校验通过再原子替换目标目录）
3) git add <该 id 子树>；git commit --author="<原提交者>" -m "publish(skill): <id> [approve <actor>]"
4) git fetch + rebase origin/master；git push origin master
     └─ 冲突/被拒：重试 N 次；仍失败 → 保留本地 commit，标记 push_pending + 告警（不回滚 data）
5) 主仓镜像（异步任务；warn/enforce，见 §3.4）
6) 审计 skill_package_approved（含 sha、hash、submit_id、actor）
7) 更新 submission=published；释放锁
8) 通知提交者（见 §4.6）
```

**原子性与失败语义**：

- data 写入用「临时目录 + rename」，避免半包状态被 manifest 读到。
- **manifest 立即可见**（源于 data 目录）——即使第 4 步 push 失败，同事仍可 sync；Git 仅落后于 data，由 `push_pending` 重试补齐。
- 任何一步抛错都必须**释放锁**（finally）。

**reject**：不写 data、不 git、置 `rejected` + comment、通知提交者。

**rollback（不新增版本仓，用 Git）**：

```
POST /api/tahp/skill-submissions/rollback
  body: { skill_id, to_sha }      # to_sha 来自 history
# 服务端：git checkout <to_sha> -- <该 id 子树> → commit "revert(skill): <id> to <short_sha>"
#         → push → 主仓镜像 → 审计 skill_package_rolled_back
```

知识条目审核通过：写 entry → commit + push bff → 镜像主仓知识树 → 审计 → 通知；事务/锁/幂等/回滚规则同上。

### 4.3 历史（客户端可视）

```
GET /api/tahp/sync/skill/:id/history?limit=50
→ {
    id,
    commits: Array<{
      sha, short_sha, title, author_name, author_email,
      committed_at, message
    }>
  }

# 本机代理（方便浏览器）
GET /api/tahp/skills/:id/history → 转发中心
```

数据源优先级：中心工作区对 `data/skills/.claude/skills/<id>` 的 `git log`；若无 `.git` 则调 GitLab API（项目 + path）。**SHA 与 GitLab 一致**，便于同事在网页打开 commit。

### 4.4 Bundle

```
GET    /api/tahp/skill-bundles
PUT    /api/tahp/skill-bundles          # admin，写 data/.tahp/skill-bundles.json 后 commit+push
POST   /api/tahp/skill-bundles/publish  # 可选显式发布（若与 PUT 合并则文档注明）

# Manifest skill 项
bundle_ids: string[]   # 由注册表解析，不再恒为 []
```

本机：

```
GET  /api/tahp/skills/sync-status?bundle_id=
POST /api/tahp/skills/sync  body 可带 bundle_id
```

### 4.5 知识库路径映射（3D 前必须锁定）

> 现状：中心 `data/knowledge-base/...`；主仓 `knowledge-base/`。需在实现 3D **前**锁定一张精确映射表，避免镜像误伤 `.kb-data/` 索引（该目录规则**禁止手改**，见 `00-change-control`）。

| 中心 `data/` | 主仓 | 是否镜像 |
|--------------|------|----------|
| `knowledge-base/.kb-data/entries/<id>.json` | `knowledge-base/.kb-data/entries/<id>.json` | **是** |
| `skills/.claude/skills/<id>/`（相对 data） | `skills/.claude/skills/<id>/` | **是** |
| `.kb-data/search-index.json`、`audit-log*` | 任意 | **否**（各端本地重建） |

已锁定（2026-07-15）。镜像模式：`TAHP_MAIN_REPO_MIRROR_ENABLED` + `TAHP_MAIN_REPO_MIRROR_ENFORCE=warn|enforce`。

### 4.6 提交者反馈（通知）

- **最小实现**：`sync-status` 增加本机最近提交结果聚合（`submitted_pending` / `rejected` + comment），SyncCenter 轮询即可感知，无需额外推送通道。
- 中心记录 `submission.reviewed_by` / `reviewed_at` / `comment`，供本机拉取展示。
- 可选（不在 P3 必做）：中心侧站内通知 / 邮件。

---

## 5. UI

### 5.1 本机 Skill 同步中心（`SkillSyncCenter`）

- 「提交服务器」= 入待审；文案明确 **非立即发布**。
- 展示 `submitted_pending` / `rejected`；已发布且 hash 一致不显示提交。
- Skill 行或详情：**「历史版本」** → 列表（时间、作者、摘要、短 SHA）；链到 GitLab commit URL（可配置 `TAHP_GITLAB_SKILL_PROJECT_URL`）。
- Bundle：按正式 Bundle 分组；「同步此包」。

### 5.2 中心 BFF 后台

- Skill 待审队列：文件列表 / 包 hash / 提交说明 / **与当前已发布的 diff 摘要**（新增/修改/删除文件数；SKILL.md 文本 diff）/ 通过 / 驳回（必填/可选原因）。
- 知识库待审：沿用并接 git 发布。
- Bundle CRUD 页。
- 展示最近发布 commit SHA + 状态（`published` / `push_pending`）；镜像 `warn`/`enforce` 模式与冲突告警。
- 只有 `reviewers.json` 中的审核员可执行 approve/reject；`force_publish` 仅 admin。

---

## 6. 影响文件清单（实现时分 Step 批改，单批建议 ≤8）

### 6.1 easyadapter_bff（必须）

| # | 文件 / 区域 | 动作 |
|---|-------------|------|
| 1 | `src/services/skill-package.ts` 等 | 待审暂存；approve 写入 live |
| 2 | `src/services/git-publish.ts`（新） | commit/push bff；触发/执行主仓镜像 |
| 3 | `src/routes/sync.ts` | submit 入队；history；默认禁止直写 live |
| 4 | 审核路由（skill-submissions / 扩展 drafts、entries） | approve 链式 git |
| 5 | Bundle 服务 + routes | `skill-bundles.json` CRUD |
| 6 | 后台 client 待审 + Bundle UI | |
| 7 | 审计 action 枚举 | `skill_package_*` / `kb_*` / `bundle_*` / `main_repo_mirror_*` |
| 8 | 配置 | CI 账号、仓库 URL、主仓路径映射（**仅 env，不入库密钥**） |
| 9 | `docs/skill-sync/` + smoke | |
| 10 | `.gitignore` | pending 暂存不入库 |

### 6.2 easyadapter / tahp-console（必须）

| # | 文件 / 区域 | 动作 |
|---|-------------|------|
| 1 | `skill-sync` 路由 / central-client | submit 语义；history 代理 |
| 2 | `sync/status.ts` | pending / rejected 状态 |
| 3 | `SkillSyncCenter.vue` + i18n | 文案 + 历史面板 + Bundle |
| 4 | 契约类型 / 测试 | 与中心对齐 |
| 5 | `.cursor/skill-sync/*` | 本文与 overview/README |

### 6.3 明确不做（P3）

- 自研多版本 blob 仓、current_version 指针表  
- 审核通过后再开 GitLab MR（已定直推 master）  
- ahead/conflict 完整治理（→ Phase 4）  
- 大改 `hermes-agent-main/`

---

## 7. 执行顺序（Step）

| Step | 仓 | 工作 | 验收要点 |
|------|-----|------|----------|
| **0** | 文档 | 本文 + overview/README 定稿；锁定 §4.5 kb 映射；确认 §3.4 方案 A、§12 未决项 | 决策表一致 |
| **3A-pre** | bff | **存量入库引导**：确保 `data/skills`、发布 kb 子树已被 Git 跟踪（首次 import commit）；配好 CI 凭据（本地联调可用本机 git 身份） | `git log -- <path>` 有基线 |
| **3A** | bff | pending 入队；`POST .../package` 默认禁直写 live；approve 写 data（临时目录+rename）；写者锁 | 提交后同事 pull 不到；并发审核不撞锁 |
| **3B** | bff | `git-publish`：commit（--author 原提交者）+ fetch/rebase/push master；`push_pending` 重试；幂等跳空 commit；知识库 approve 同链路 | GitLab 出现 commit；push 失败可重试补齐 |
| **3C** | bff+client | history API + rollback + SyncCenter 历史 UI（链 GitLab） | 单 Skill 列 commits；可回滚到某 sha |
| **3D** | bff | 主仓镜像任务（默认 `warn`）+ 冲突/失败告警审计；kb 映射按 §4.5 | `warn` 下有报告；切 `enforce` 后主仓同步 |
| **3E** | bff+client | Bundle CRUD + bundle_ids + 按包同步 | 「同步此包」可用 |
| **3F** | 双仓 | 单测 / smoke / build + [SELF-CHECK](./SELF-CHECK.md) | 报告勾选通过 |

每 Step 结束必须按 SELF-CHECK 执行；清单外改动先更新本文再改代码。**Step 顺序保证**：先闸门（3A）再 Git（3B），确保任何时刻「未审内容不进 master」。

---

## 8. 配置（env，示例名）

| 变量 | 用途 | 默认/示例 |
|------|------|-----------|
| `TAHP_GIT_PUBLISH_ENABLED` | 是否启用审后 Git（关=仅写 data） | `0` |
| `TAHP_GIT_REPO_DIR` | 中心仓工作区根（含 `data/`） | — |
| `TAHP_GIT_REMOTE` | 远端名 | `origin` |
| `TAHP_GIT_BRANCH` | 目标分支 | `master` |
| `TAHP_GIT_COMMITTER_NAME` / `EMAIL` | CI 提交身份（committer） | `tahp-ci` |
| `TAHP_GIT_PRESERVE_AUTHOR` | 是否用原提交者作 author | `1` |
| `TAHP_GIT_PUSH_RETRY` | push 失败重试次数 | `3` |
| `TAHP_GIT_CREDENTIAL` / SSH key | 凭据 **仅环境/密钥库，禁止入库** | — |
| `TAHP_MAIN_REPO_MIRROR_ENABLED` | 是否镜像主仓 | `0` |
| `TAHP_MAIN_REPO_MIRROR_ENFORCE` | `warn`（仅告警）/ `enforce`（覆盖） | `warn` |
| `TAHP_MAIN_REPO_DIR` / `URL` | 主仓本地工作区 / 远端 | — |
| `TAHP_MAIN_REPO_PATHMAP` | 中心→主仓 路径映射（或代码内锁定） | — |
| `TAHP_GITLAB_SKILL_WEB_BASE` | 客户端拼 commit 链接（如 `https://gitlab.transsion.com/neng.zhou/easyadapter_bff/-/commit/`） | — |
| `TAHP_ALLOW_FORCE_PUBLISH` | 是否允许 admin 直发跳审 | `0` |

> 联调降级：`TAHP_GIT_PUBLISH_ENABLED=0` 时，审核仅写 `data/`（P2 行为 + 闸门），不碰 Git，便于本地验证审核流。

---

## 9. 风险

| 风险 | 缓解 |
|------|------|
| 直推 master 误发 | 审核员权限；force 仅 admin；审计 + GitLab revert/rollback API |
| **主仓与人工直改互相覆盖** | §3.4 方案 A 单向权威；镜像默认 `warn`；冲突告警不静默覆盖；公告 + 可选 pre-commit 拦截 |
| 并发审核写乱工作树 | 单写者锁（mutex + `.git/index.lock` 兜底）；审核排队 |
| push 竞争（remote 已动） | fetch+rebase 后 push；重试；`push_pending` 保底不丢内容 |
| commit 成功 push 失败 | manifest 源于 data 立即可见；后台重试补 push；状态可见 |
| 半包写入被读到 | 临时目录 + 原子 rename |
| 大文件/二进制入库致仓库膨胀 | 单文件/整包体积上限校验；`.gitignore` 运行时产物；必要时评估 Git LFS（P3 只做体积拦截，不强上 LFS） |
| 误镜像 `.kb-data/` 索引 | §4.5 明确排除；索引各端本地重建 |
| data 目录曾未入库 | 3A-pre 首次 import commit 建基线 |
| CI 账号权限过大 | 最小 scope；仅目标两仓 write；凭据仅密钥库 |
| 历史 API 慢 | limit + 仅单 skill path；可缓存 |
| 提交测试/临时 skill（如 `SKILL - test.md`、`kb-skill-live-test`） | 提交侧校验命名与结构；沿用 P2 排除清单 + 拒绝非法包 |
| 与 P2 直发行为不兼容 | 升级说明：旧 `publish-package` 改语义；文档与 UI 文案同步；提供 `force_publish` 过渡 |

---

## 10. 验收清单

1. 本机提交 skill 包后，manifest **无**新 hash；其它机器 sync 不变。  
2. 中心审核通过后：`data/skills/.../<id>` 更新，GitLab **bff 仓 master** 出现约定 commit（author=原提交者，committer=CI）。  
3. 幂等：内容未变的重复提交审核通过**不产生空 commit**。  
4. push 失败注入（断网模拟）：data 已发布、manifest 可见、状态 `push_pending`，恢复后可重试补齐。  
5. 并发审核两个包：串行完成，无 `.git` 锁报错、无交叉写坏。  
6. 主仓镜像 `warn` 模式：仅出告警报告，不改主仓；`enforce` 模式：主仓对应子树与中心一致。  
7. 客户端打开该 Skill「历史版本」可见 commit 列表并能跳 GitLab；可回滚到历史 sha。  
8. 驳回：不写 live、不推 Git、提交者可见 rejected + 原因。  
9. 知识条目审核通过同样产生 Git commit；`.kb-data/` 索引未被镜像。  
10. Bundle 创建后 manifest.`bundle_ids` 非空；「同步此包」只拉该包内 behind 项。  
11. SELF-CHECK 全文通过；密钥/CI 凭据未入库。

---

## 11. 未决项（已于 2026-07-14 按默认建议锁定）

| # | 项 | 定稿 |
|---|-----|------|
| 1 | §3.4 主仓权威 | **方案 A**；镜像默认 `warn`，再切 `enforce` |
| 2 | `force_publish` | **保留**，默认关闭（`TAHP_ALLOW_FORCE_PUBLISH=0`） |
| 3 | Git author/committer | author=原提交者，committer=CI |
| 4 | 大包体积 | **上限拒绝**（默认 50MB）；不做 LFS |
| 5 | kb 路径映射 | 3B/3D 前读码锁定（§4.5） |
| 6 | bundles 缓存入主仓 Git | **否**（pull 缓存） |

---

## 12. 开工

Step 0 已锁定。实现按 Step 3A → 3B → …；**顺序红线**：闸门（3A）先于 Git 直推（3B）。每 Step「必须改 ≤8」可增量，超出须先更新本文。
