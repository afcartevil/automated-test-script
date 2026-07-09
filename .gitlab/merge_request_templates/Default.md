## Summary

<!-- 改了什么、为什么改（1–3 条） -->

-

## 变更范围

- **功能域**：（Console UI / BFF / Skill / 配置路径 / AI 自检 / 脚本 / 仅规范文档）
- **计划文件**：
- **实际文件**：（若与计划不一致请说明原因）
- **敏感链**：（路径 / unified-config / Skill .env / agent-bridge）是 / 否

## 验证

<!-- 已执行的命令；未跑请说明原因 -->

- [ ] `cd tahp-console && npm test`（相关用例：___）
- [ ] `cd tahp-console && npm run build`
- [ ] 手动冒烟：（路由 / 功能点）
- [ ] 路径类：确认 `projectRoot` 与 `jira_workspace` 落盘正确

## 风险与回滚

<!-- 可选：已知限制、需重启服务、配置迁移步骤 -->

## Checklist

- [ ] 未提交 `.env`、凭据、`.tahp/unified-config.json`
- [ ] 未改动无关文件或顺手重构
- [ ] 已遵守 `.cursor/rules/00-change-control.mdc`
