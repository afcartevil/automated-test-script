---
name: harness-opengrok
description: harness OpenGrok 源码搜索子 skill。覆盖 opengrok search（按 def/ref/full/path/hist 搜索）和 opengrok fetch（按文件路径 + 行范围获取源码）。用于跨版本只读源码取证、定位函数 / 符号 / 历史；不用于改代码。Git Bash 上 `--file-path /xxx` 会被 MSYS 自动转换，CLI 已加自动恢复，但建议传 `//xxx` 或设 `MSYS_NO_PATHCONV=1` 显式避免。
version: 2.1.17
---

# Harness OpenGrok 子 skill

## 何时进入

- 需要源码证据回答（函数定义、引用、文件历史）；
- 需要跨版本对比；
- Agent 不应只凭记忆改代码，OpenGrok 能提供权威。

## 命令速查

```text
# 搜索（def / ref / full-text / path / commit hist）
harness opengrok search --branch tOS_mtk_A16_trunk --def AudioFlinger --top 10
harness --json opengrok search --branch tOS_mtk_A16_trunk --def AudioFlinger --top 10
harness --json opengrok search --ref opengrokRequest --top 10
harness --json opengrok search --full "wifi scan" --path "frameworks/" --top 10
harness --json opengrok search --hist "telephony bringup" --top 10

# 获取文件片段
harness --json opengrok fetch --file-path /frameworks/av/services/audioflinger/AudioFlinger.cpp --start-line 1 --end-line 120
```

## Git Bash MSYS 路径自动恢复

如果你在 Git Bash 里直接传 `--file-path /hardware/samsung/nfc/...`，MSYS 会把它改写成 `<git_install_root>/hardware/...`。CLI 已在 `cli/opengrok.py` 加了 `_normalize_msys_path` 自动剥离前缀并 stderr 输出 warning。

**推荐写法**（任选其一避开转换）：

```bash
harness opengrok fetch --file-path //hardware/samsung/nfc/1.2/SecNfc.h ...
MSYS_NO_PATHCONV=1 harness opengrok fetch --file-path /hardware/samsung/nfc/1.2/SecNfc.h ...
```

## 边界

- OpenGrok 是只读证据，不修改代码。
- 在最终回答中说明源码路径、分支和行范围（可追溯）。
- 不要凭记忆改代码，OpenGrok 能提供权威源码证据时优先使用。

## 反馈

```text
harness --json feedback create --scenario opengrok --problem-type bad-result \
  --tool "harness opengrok fetch" --detail "..."
```
