# 业务 Skill

`skills/.claude/skills/` 是 Hermes / Console 的运行时目录，由 **TAHP Console → 同步中心** 从服务端拉取落盘。

**不要** `git add` / `git commit` 此目录。版本与分发以中心为准，主仓 Git 不跟踪业务 Skill。

## 新克隆或 pull 后目录为空

1. 启动 Console（`tahp-console`）
2. 打开「同步中心」→ **同步全部**
3. 需要时再点「应用到 Agent」

## 改 Skill

本地编辑 → Console「提交服务器」（待审）→ 中心审核通过 → 同事「同步全部 / 同步此包」。
