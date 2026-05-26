---
id: kb-kernel-driver-20260526-3557
title: TP触摸屏 BSP 适配调试经验 — MT6878
module: kernel-driver
category: practice_note
type: practice_note
author: user
domain: tp
tags:
  - kernel-driver
  - tp
  - adapt-debug
  - tp-adapt-dws-pin
  - tp-adapt-ko-order
  - tp-adapt-power-sequence
confidence: 0.85
referenced_by: []
source: chat_extract
created_at: '2026-05-26T08:31:57.033Z'
updated_at: '2026-05-26T08:31:57.033Z'
---

## 适配上下文

- 项目: X6876_H786
- SoC: MT6878
- Kernel: 6.1
- 升级路径: vendor14 → vendor16

## 关键对话摘要

**[问]** 你现在能直接读取当前的工程吗？介绍下当前工程的功能和目录有哪些，现在有哪些skill

**[答]** 坦白说，我无法直接读取你本地的工程文件。我没有访问文件系统的权限，看不到你的目录结构、代码内容，也没法直接了解你配置了哪些 skill。

不过，如果你能把工程的关键信息分享给我——比如贴一下目录结构、配置文件内容，或者描述一下项目是做什么的，我可以帮你分析功能、梳理结构，也能告诉你目前有哪些可用的 skill。

方便的话，直接把工程相关的信息丢过来，我马上帮你整理！

**[问]** 当前的TAHP工程里面有哪些skill

**[答]** 根据 TAHP 工程上下文，当前共有 **5 个 Skill**：

| 序号 | Skill 名称 | 功能描述 |
|------|-----------|---------|
| 1 | **carrier-porting-assistant** | 运营商需求移植助手 — 支持运营商定制需求的分析、代码移植、合规检查 |
| 2 | **kernel-panic-tracer** | 内核 Panic 追踪器 — 分析 Android 内核 panic、kernel oops、驱动 crash 的根因定位和修复建议 |
| 3 | **power-leak-detector** | 功

**[问]** 为啥你说的这几个skill我在skills库里都看不到了

**[答]** 你说得对，这确实很奇怪。我列出的这些 Skill 信息来自系统注入给我的 **TAHP 工程上下文**，这部分内容是预设的工程描述，我无法直接验证它和你本地实际的文件系统是否一致。

可能出现差异的原因：

1. **上下文是模板/占位内容** — TAHP 工程上下文可能是项目初始模板，跟当前实际工程不同步了
2. **Skill 文件已被重命名、删除或移动** — 你本地的 `skills/` 目录可能经过了重构，但上下文还没更新
3. **上下文本身过时** — 工程描述写死了，没有随实际代码自动同步

要不你贴一下 `skills/` 目录下实际能看到的内容？比如 `ls` 的输出或者

**[问]** 你再看下工程中是否有apikey-image-gen skill，你是否能够读取到

**[答]** 坦白说，**我没有在你的 TAHP 工程上下文中看到 `apikey-image-gen` 这个 Skill**。

当前上下文中注入的 Skill 列表只有 5 个：

1. carrier-porting-assistant
2. kernel-panic-tracer
3. power-leak-detector
4. telephony-bug-analyzer
5. telephony-version-adapter

至于你本地 `skills/` 目录下实际是否存在 `apikey-image-gen`，我确实无法直接读取。我只能"看到"系统注入给我的 TAHP 工程上下文，而这

**[问]** 你现在能是否能查询到本工程的知识库

**[答]** 根据当前注入给我的 TAHP 工程上下文，知识库索引中只有 **2 条记录**：

| 序号 | 知识条目 | 置信度 |
|------|---------|--------|
| 1 | RILJ GENERIC_FAILURE 错误分析 | 0.9 |
| 2 | PhoneInterfaceManager Phone对象生命周期 | 0.85 |

但我**无法直接查询知识库的具体内容**——我只能看到索引条目，看不到知识库中存储的详细分析文档。

如果你本地 `knowledge-base/` 目录下有更多内容，或者某些条目在索引中缺失，那说明上下文给我注入的知识库索引也不全。要不要
