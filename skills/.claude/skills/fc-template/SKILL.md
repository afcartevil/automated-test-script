---
name: fc-template
description: Template for creating new func-check skills. Copy this directory to fc-<domain>-<scenario>, fill in check steps and optional scripts, then register in func-check-registry.md. Do not invoke directly in production.
---

# FC 模板：功能检查 skill

复制本目录创建新检查 skill，命名规范：`fc-<domain>-<scenario>`

- domain: `tp` / `vib` / `aikey`
- scenario: 具体场景，如 `touch`、`gesture`、`hal`

## 前置条件

- 设备已通过 `adb devices` 连接
- （按需补充：需 root / 需解锁 / 需特定 build）

## 检查步骤

1. （执行命令或脚本，Windows 用 PowerShell）
   ```text
   adb shell <command>
   ```
2. （人工操作说明，如滑动屏幕、按键）
3. （可选）运行 Python 脚本：
   ```powershell
   python "$env:USERPROFILE\.cursor\skills\func-check\fc-<domain>-<scenario>\scripts\check_xxx.py"
   ```
   说明见 [../RUN.md](../RUN.md)。

## Pass / Fail 判定

| 结果 | 条件 |
|------|------|
| Pass | （预期输出或行为） |
| Fail | （失败特征） |

## 输出格式

```
## 功能检查：{场景名}

**skill**: fc-<domain>-<scenario>
**结果**: Pass / Fail

| 检查项 | 命令/脚本 | 实际输出 | Pass/Fail |
|--------|----------|----------|-----------|
| ... | ... | ... | ... |

### 下一步
（Pass：结束；Fail：见 Fail 后续）
```

## Fail 后续

- 路由到 adaptation-debug skill：`（填写，如 tp-log-touch）`
- 或继续执行 registry 中下一项 fc skill

## 注册

在 `~/.cursor/skills/harness/tp-vib/func-check-registry.md` 对应区域添加一行。
