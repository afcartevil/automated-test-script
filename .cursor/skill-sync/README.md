# Skill 同步管理 — 设计与执行文档索引

> **用途**：本目录是 Skill 更新/分发机制的**权威执行文档**。后续 AI Coding 与人工开发必须严格按对应 Phase 文档执行，避免上下文丢失或幻觉偏离。
>
> **双仓**：客户端 `E:/TAHP/easyadapter`，中心 `E:/TAHP/easyadapter_bff`。文档以本仓为准；中心仓见 `easyadapter_bff/docs/skill-sync/` 镜像索引。
>
> **路径说明**：权威目录为 `.cursor/skill-sync/`（可入库）。根目录规则 `docs/` 会匹配任意名为 docs 的目录，故不使用 `docs/` 或 `.cursor/docs/`。

## 文档列表

| 文档 | 状态 | 说明 |
|------|------|------|
| [00-overview.md](./00-overview.md) | 已定稿 | 总体架构、决策项、阶段总览、现状诊断 |
| [PHASE-1.md](./PHASE-1.md) | **当前执行批次** | Phase 1 可执行提案（文件清单、API、验收） |
| [PHASE-2.md](./PHASE-2.md) | 待 Phase 1 验证后细化 | 包型 Skill 全量分发 |
| [PHASE-3.md](./PHASE-3.md) | 待细化 | Bundle 管理 |
| [PHASE-4.md](./PHASE-4.md) | 待细化 | 治理闭环 |
| [SELF-CHECK.md](./SELF-CHECK.md) | **强制** | 每 Step/Phase 完成后的自检规范与交付报告模板 |

## 使用约定

1. **开发前**：阅读 `00-overview.md` + 当前 Phase 文档全文 + [SELF-CHECK.md](./SELF-CHECK.md)。
2. **开发中**：只改当前 Phase「必须改」文件列表；超出须先更新文档并获确认。
3. **提案→确认→执行**：每 Phase 开工前输出文件级提案，用户确认后再写代码；提案定稿后**同步更新本目录文档**。
4. **Phase 切换**：上一 Phase 验收通过后，再把下一 Phase 从「大纲」细化成「可执行提案」并落盘。
5. **双仓同步**：涉及 sync 契约时，`manifest` / API 变更必须两边同批修改。
6. **开发后强制自检**（不可跳过）：
   - 无测试失败、无 build 失败、无未处理运行时异常
   - `git diff` 不得出现未说明的规划外修改
   - 若有特殊情况必须改清单外文件：先告知原因与必要性，更新 Phase 文档，再在自检报告中单列
   - 每次交付回复必须含 [SELF-CHECK.md](./SELF-CHECK.md) 规定的「自检报告」块

## 已确认决策（摘要）

| # | 决策 | 结论 |
|---|------|------|
| 1 | 包型 Skill | 中心需托管完整附件（scripts/references 等）→ Phase 2 |
| 2 | 交付节奏 | Phase 1 单独首批交付、验证后再推进 P2/P3/P4 |
| 3 | 中心部署 | 已可用：`http://10.205.0.65:8660/`（经 `TAHP_CENTRAL_URL`/`TOKEN`，不硬编码） |
| 4 | Bundle 权威 | 中心权威，pull 时下发只读缓存 |
| 5 | Bundle 策略 | 混合：`func_type+module` 自动聚合 + 显式注册 |
| 6 | 同步频率 | 默认 5 分钟 + UI 可关；即时推送后期 |
| 7 | import | 保留，UI 降权为高级/首次 |

## 当前进度

- [x] 总体方案定稿
- [x] Phase 1 可执行提案落盘
- [x] Phase 1 开发（代码已完成，待联调冒烟确认）
- [ ] Phase 1 验证通过（手工冒烟）
- [ ] Phase 2 细化提案落盘
- [ ] Phase 2 开发
- [ ] Phase 3 / 4

## 变更记录

| 日期 | 说明 |
|------|------|
| 2026-07-13 | 初版：总览 + Phase 1 可执行提案 + P2/P3/P4 大纲 |
| 2026-07-13 | 增补 SELF-CHECK.md；使用约定增加「开发后强制自检」 |
| 2026-07-13 | 文档迁至 `.cursor/skill-sync/`（规避 gitignore 对任意 `docs/` 的匹配） |
| 2026-07-13 | Phase 1 代码实现完成；等待手工冒烟勾选 |