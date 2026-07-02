# 报告模板

执行该 Skill 后，最终回复使用以下结构。

```markdown
## 输入摘要

- 升级前 vendor 路径：`<base_code>`
- 升级后 vendor 路径：`<base_code_sunmao>`
- 项目：`<project_name>` (`<project_name1>_<project_name2>`)
- 平台：`<platform_name>`
- 特性：`<features>`

## 执行结果

- `<feature>`:
  - 已修改：`<文件或无>`
  - 已复制：`<文件或无>`
  - 已跳过：`<项目和原因>`
  - 阻塞项：`<问题或无>`

## 验证结果

- 宏控：`<通过/失败摘要>`
- 文件：`<通过/失败摘要>`
- XML/JSON 节点：`<通过/失败摘要>`

## 开发者待处理

- SCM 属性：
  - `<property>`
- 手动跟进：
  - `<手动调试或确认项>`
```

如果因为不确定项停止执行，将未回答的问题放在 `阻塞项` 下，不要声称该特性已完成。
