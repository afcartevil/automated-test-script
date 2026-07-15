# Phase 4 — 治理闭环（大纲）

> **状态**：大纲。须在 Phase 3 验收后细化。  
> **目标**：冲突感知、审计可追溯、文档 SOP 收敛。  
> **自检**：须遵守 [SELF-CHECK.md](./SELF-CHECK.md)。

## 1. 交付目标

1. 启用 `ahead` / `conflict` 状态与提交流程引导。
2. 中心审计：`bundle_publish`、可选各机 last_synced（若采集）。
3. 文档：团队发布走中心；import 明确为离线/首次兜底。
4. 更新 `.cursor/rules/tahp-skills-hermes.mdc` 与 README 相关段落。

## 2. 预估工作

- status 算法增强（本地 mtime/未提交检测策略需评审，避免误报）
- 审计 API / 报表 UI（中心）
- 文档与 onboarding 文案

## 3. 待细化项

- [ ] ahead 判定是否依赖 git status（可能过重）
- [ ] 是否做 WebSocket 即时推送
- [ ] 可执行提案落盘

## 4. 依赖

- Phase 1–3 主路径稳定（含审后 Git 直推与主仓镜像）

## 5. 与 Phase 3 边界

- **不在 P4 重复**：审核闸门、GitLab 版本、Bundle CRUD（见 [PHASE-3.md](./PHASE-3.md)）
- **P4 侧重**：ahead/conflict、审计报表增强、团队 SOP / rules 文案收敛
