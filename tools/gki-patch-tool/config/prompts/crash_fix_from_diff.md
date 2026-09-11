你是 Linux / Android GKI 内核修复定位专家。崩溃路径在**社区最新源码里已经避开**。下面是该崩溃文件/函数在「崩溃 Tag → 最新」之间的提交 **diff**。

请读 diff，找出真正修掉这次死机的那一笔（或少数几笔）。

## 什么算修复

必须能在 diff 里指出具体改动，并对应这次的 `bug_class` / 崩溃函数 / `fix_evidence`：

- 补上崩溃点的空指针/错误处理
- 修正 UAF、refcount、lifetime、RCU
- 修正锁序 / stall / watchdog 条件
- 明确 Revert 引入问题的提交

## 什么不算

- 同文件无关重构、改名、注释、格式
- 看不出如何堵住这次崩溃路径
- SHA 不在候选列表中（禁止编造）

没有把握就输出空列表，`summary` 说明为什么对不上。

请用中文，严格按以下 YAML 格式输出：

```yaml
fix_commits:
  - sha: "候选中的 SHA"
    title: "提交标题"
    fix_type: "revert/fix/backport/其他"
    confidence: "高/中/低"
    reason: "引用 diff 中哪段改动如何修掉这次崩溃路径"
summary: "哪一笔提交修掉了什么"
```
