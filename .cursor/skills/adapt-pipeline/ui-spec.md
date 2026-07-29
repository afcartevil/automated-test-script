# adapt-pipeline — UI 交互设计

> 配套 [SKILL.md](SKILL.md) · [数据契约](reference.md)
> 技术栈沿用现状：**Vue 3 Composition API + Pinia + Naive UI + scoped SCSS**。
> **不引入新 UI 库**，复用 `EaShell` / `EaCard` / `EaPageHead` / `EaInnerTabs` / `EaPill`。

## 设计第一原则

**UI 由数据驱动，不硬编码节点。**
步进条、节点详情、人工动作按钮全部按 `GET /runs/:runId/timeline` 返回的 `nodes[]` 渲染。
新增一个业务节点时，UI **零改动**即可显示；只有想要专属可视化时才补一个渲染器。

---

## 1. 页面与路由

| 项 | 值 |
|---|---|
| 路由 | `/tahp/pipeline` |
| name | `tahp.pipeline` |
| 视图 | `views/tahp/AdaptPipelineView.vue` |
| 导航入口 | `EaShell.vue` 顶栏，置于「AI 适配调试」之后 |

页头三个 Tab（`EaInnerTabs`）：

| key | 标签 | 说明 |
|---|---|---|
| `board` | 运行看板 | 默认，实时进度主战场 |
| `create` | 新建运行 | 4 步向导 |
| `workflow` | 流程编排 | 节点启停与顺序（F9） |

---

## 2. 组件树

```
AdaptPipelineView.vue
├── PipelinePageHeader.vue           Tab 切换 + 全局状态摘要
├── [board]
│   └── PipelineBoard.vue
│       ├── PipelineRunList.vue      左侧 run 列表（可折叠）
│       └── PipelineRunDetail.vue
│           ├── PipelineRunHeader.vue      项目/状态/迭代/操作
│           ├── EaStageStepper.vue         ★ 通用步进条
│           ├── PipelineNodeList.vue       左栏：节点树
│           ├── PipelineNodePanel.vue      中栏：渲染器分发
│           │   ├── stage-panels/AdaptPanel.vue
│           │   ├── stage-panels/BuildPanel.vue
│           │   ├── stage-panels/FlashPanel.vue
│           │   ├── stage-panels/SelfCheckPanel.vue
│           │   ├── stage-panels/TriagePanel.vue
│           │   ├── stage-panels/GerritPanel.vue
│           │   └── stage-panels/DefaultPanel.vue   ★ 兜底
│           ├── PipelineHumanPanel.vue     右栏：人工介入队列
│           │   └── PipelineResumePicker.vue   恢复点选择器
│           └── PipelineIterationBar.vue   底部：迭代收敛条
├── [create] PipelineCreateWizard.vue
└── [workflow] PipelineWorkflowEditor.vue
```

通用组件（放 `components/common/`，供其他页面复用）：

| 组件 | 用途 |
|---|---|
| `EaStageStepper.vue` | 动态阶段步进条 |
| `EaLogViewer.vue` | 日志流：虚拟滚动 + 自动跟随 + 搜索 + 级别过滤 |

> `EaLogViewer` 必须做**虚拟滚动**。编译日志动辄数万行，现状各页面的 `<pre class="log-body">` 会卡死。

---

## 3. 运行看板整体布局

```
┌──────────────────────────────────────────────────────────────────────────┐
│  运行看板 │ 新建运行 │ 流程编排                          ⚠ 2 项待人工处理  │
├──────────┬───────────────────────────────────────────────────────────────┤
│ 运行列表  │  KM9 · tOS16.3.0    ●运行中   第2轮/共3轮   已运行 3h12m       │
│          │                                [暂停] [终止] [从…恢复]          │
│ ●KM9  2轮│ ├─────────────────────────────────────────────────────────────┤
│ ✓X6885   │ │ ①前置 ─ ②适配 ─ ③编译 ─ ④烧录 ─ ⑤自检 ─ ⑥分析 ─ ⑦审核 ─ ⑧提交│
│ ✗LJ8     │ │  ✓14s   ✓1h48m  ●52m    ○      ○      ○      ○      ○      │
│ ○CM5     │ │                    ╰──────── 第2轮回环 ────────╯             │
│          │ ├──────────┬────────────────────────────┬────────────────────┤
│  [+新建]  │ │ 节点      │ 编译 · 进行中 52m           │ 人工介入 (2)        │
│          │ │          │                            │  （见 6.4 恢复点） │
│          │ │ ✓前置(5域)│ 模式：增量  组件：krn,vext  │ ┌────────────────┐ │
│          │ │ ✓适配     │ ────────────────────────── │ │⚠ 编译能力未接入 │ │
│          │ │   ✓TP     │ repo    ✓ 完成 6m          │ │节点：编译       │ │
│          │ │   ✓LCM    │ build   ● 进行中 46m       │ │手工编译后点继续 │ │
│          │ │   ✓充电   │ package ○ 等待             │ │[已完成][跳过]  │ │
│          │ │   ✓Sensor │ ────────────────────────── │ └────────────────┘ │
│          │ │   −音频   │ <EaLogViewer>              │ ┌────────────────┐ │
│          │ │ ●编译     │                            │ │⚠ 3 用例失败待审 │ │
│          │ │ ○烧录     │                            │ │[查看结论][继续]│ │
│          │ │ ○自检     │                            │ └────────────────┘ │
│          │ ├──────────┴────────────────────────────┴────────────────────┤
│          │ │ 迭代收敛  第1轮 ✗3失败 ──── 第2轮 ●进行中                    │
│          │ │           ●──────────────────●- - - - - -○                 │
└──────────┴───────────────────────────────────────────────────────────────┘
```

栅格：左列表 `240px`（可折叠至 `48px`）· 主区自适应 · 三栏为 `220px / 1fr / 300px`。
窗口 `< 1400px` 时右栏收为浮层抽屉，由顶部「⚠ N 项待人工处理」徽章唤起。

---

## 4. EaStageStepper（核心组件）

### 4.1 单节点视觉

```
   ┌──────────────┐
   │ ② 适配        │  ← 序号 + label
   │ ✓  1h48m      │  ← 状态图标 + 耗时
   │ 5/5 域        │  ← summary_line（可选）
   └──────────────┘
```

### 4.2 状态视觉规范

配色对齐 **EasyAdapter V26 Soft Fill**（`variables.scss` / `ea-v26.scss`），步进节点做成 soft-fill 小卡片（同首页模块卡），不用 Naive 默认蓝绿硬套：

| status | 背景 soft-fill | 前景 | 图标 | 附加 |
|---|---|---|---|---|
| `pending` | `#f4f5f8` | `--faint` | ○ | 低对比 |
| `running` | `--indigo-bg` `#eef0fb` | `--indigo-fg` / `--accent` `#5256d4` | ◐ | **softPulse** |
| `waiting_human` | `--amber-bg` `#fbf2e2` | `--amber-fg` | ⚠ | **呼吸闪烁**，权重最高 |
| `done` | `--emerald-bg` `#e8f4ee` | `--emerald-fg` | ✓ | — |
| `failed` | `--rose-bg` `#fbecef` | `--rose-fg` | ✗ | — |
| `skipped` | `--surface-2` | `--faint` | − | 虚线边 + 删除线 |

主按钮：`--accent` 实心白字。次要按钮：`--accent-soft` 底 + accent 字（同首页「反馈问题」）。卡片圆角 `18–20px`，顶栏白底 + accent 胶囊导航，**不用深色顶栏**。

> `waiting_human` 是唯一会呼吸闪烁的状态。设计意图：人一眼看到「卡在哪、要我做什么」。

### 4.3 连接线

| 场景 | 样式 |
|---|---|
| done → done | 2px 实线绿 |
| done → running | 绿到蓝渐变 |
| 未到达 | 1px 虚线灰 |
| 跳过的节点两侧 | 灰虚线，节点缩至 60% 宽 |

### 4.4 回环边

`is_loop_target === true` 的节点（默认是 `build`），从 `human_review` 画一条**下方弧线**指回：

```
    ③编译 ────────── ⑤自检 ── ⑥分析 ── ⑦审核
      ▲                                   │
      ╰──────── 第2轮 ────────────────────╯
```

弧线标注当前迭代号；仅在 `iteration > 1` 时显示。

### 4.5 交互

| 操作 | 行为 |
|---|---|
| 单击节点 | 中栏切到该节点详情；URL 追加 `?node=build` 便于分享 |
| hover | tooltip：全称、状态、起止时间、`summary_line`、不可用原因 |
| 禁用节点（`enabled:false`） | 不渲染 |
| 节点数 > 8 | 横向滚动 + 两侧渐隐遮罩，当前节点自动滚入视野 |

### 4.6 Props

```typescript
defineProps<{
  nodes: TimelineNode[]        // 直接来自 TimelineView.nodes
  activeKey: string | null
  iteration: number
}>()
defineEmits<{ (e: 'select', key: string): void }>()
```

组件**不含任何业务判断**，纯展示。这是它能被复用、且新增节点零改动的前提。

---

## 5. 中栏：节点详情渲染器

### 5.1 分发机制

```typescript
// PipelineNodePanel.vue
const RENDERERS: Record<string, Component> = {
  adapt: AdaptPanel,
  build: BuildPanel,
  flash: FlashPanel,
  selfcheck: SelfCheckPanel,
  triage: TriagePanel,
  gerrit: GerritPanel,
}
const panel = computed(() => RENDERERS[props.node.key] ?? DefaultPanel)
```

**未注册 → `DefaultPanel`，绝不白屏。** 新增节点即使没写渲染器也能正常查看进度与日志。

### 5.2 DefaultPanel（兜底）

三段式，任何节点都成立：

1. **摘要 KV 表** — 渲染 `summary` 的键值对
2. **日志** — `EaLogViewer`，数据来自 `GET /runs/:runId/logs/:node`
3. **外部引用** — 把 `refs` 里的 id 渲染成可点链接（能识别的跳对应页面，不能识别的显示纯文本 id）

### 5.3 各专用渲染器要点

| 渲染器 | 核心内容 | 深链 |
|---|---|---|
| `AdaptPanel` | 域表格：域名 / 状态 / 耗时 / 变更文件数 / Skill | 行内「详情」跳 `/tahp/adapt-debug` 监控视图 |
| `BuildPanel` | 顶部「模式 + 本轮编译组件」清单（**必须显式展示，防漏编**）；子阶段 repo/build/package 进度；日志 | — |
| `FlashPanel` | 设备卡片 + 刷机进度条 + 日志（复用 `utils/flash-progress.ts` 解析） | — |
| `SelfCheckPanel` | 通过/失败/进行中统计环；失败用例列表（可展开看 message） | 跳自检报告 Tab |
| `TriagePanel` | 分析结论 Markdown 摘要 + 关键证据 | 跳 `/tahp/bug-analysis` |
| `GerritPanel` | 按域的 CR 列表：域 / 仓 / 文件数 / CR 链接 / 状态；冲突项红色高亮 | 外链 Gerrit |

> `BuildPanel` 的「本轮编译组件」清单是**安全设计**，不是装饰。增量编译漏组件会导致自检结果失真且无报错，必须让人能核对。

---

## 6. 右栏：人工介入面板

所有需要人的地方统一汇聚到这里，用户不需要去猜该点哪儿。

### 6.1 卡片结构

```
┌──────────────────────────────┐
│ ⚠  编译能力尚未接入            │  ← reason 对应的标题
│    节点：编译 · 等待 12m       │  ← 节点 + 等待时长
│                              │
│ 请在构建机手工完成编译后继续。   │  ← message
│                              │
│ [已手工完成，继续]  [跳过]      │  ← actions[]，按 HumanAction 渲染
└──────────────────────────────┘
```

- 按钮由 `human.actions[]` 动态生成，`danger: true` 渲染为红色
- `action.fields` 非空时点击弹出 `NModal` 收集字段再提交
- 提交 → `POST /runs/:runId/human-action`

### 6.2 提示强度

| 位置 | 表现 |
|---|---|
| 页头 | `⚠ N 项待人工处理` 徽章，N>0 时橙色 |
| 步进条 | 对应节点呼吸闪烁 |
| 右栏 | 卡片置顶，按等待时长倒序 |
| 浏览器标题 | `(N) TAHP 适配流水线` |

**不使用**系统通知或声音——内网工具，避免打扰。

### 6.3 空态

无待办时显示浅色占位：「当前无需人工介入」+ 当前节点名，不留空白区域。

### 6.4 恢复点选择器

节点失败或停在 `human_review` 时，人工卡片内嵌 `PipelineResumePicker.vue`。它回答的问题是「我修完了，从哪儿接着跑」。

```
┌────────────────────────────────────────┐
│ ⚠  编译失败 · 等待人工处理               │
│    节点：编译 · 等待 8m                  │
│                                        │
│  检测到代码已变更（12 个文件）  [查看]    │
│                                        │
│  从哪里继续：                            │
│   ◉ 编译                      推荐      │
│   ○ 烧录        ⚠ 编译产物已过期        │
│   ○ AI 自检     ⚠ 设备镜像已过期        │
│                                        │
│  范围： ◉ 增量续跑   ○ 全部重来          │
│                                        │
│              [继续]  [终止流水线]        │
└────────────────────────────────────────┘
```

| 项 | 规格 |
|---|---|
| 数据源 | `GET /runs/:runId/resume-points`，卡片展开时拉取 |
| 候选列表 | 按 workflow 顺序排列，**不过滤** unsafe 项 |
| `safe` | 正常可选；`recommended` 项默认选中并标「推荐」徽章 |
| `unsafe` | 灰显文字 + 橙色 ⚠ + `hint` 原因；仍可点选 |
| 选中 unsafe | 弹 `NDialog` 二次确认，列出全部 `missing` 产物，确认后带 `force: true` 提交 |
| 「代码已变更」提示 | 后端 `source` 指纹比对结果；`[查看]` 展开变更文件列表 |
| 范围 | 单选 `continue` / `restart`，默认 `continue`；对 `flash` / `selfcheck` / `gerrit` 隐藏（两者等价） |
| 提交 | `POST /runs/:runId/resume`，或作为 `confirm_done` 的 payload |

> unsafe 项**故意不隐藏**。隐藏会让人觉得工具在跟自己作对；灰显 + 标原因才能让人做知情决定。
> 但默认选中项永远是 safe 的 —— 不小心一路回车不会造成错误结论。

运行头部的 `[从…恢复]` 按钮唤起同一个组件（以弹窗形式），run 处于 `waiting_human` / `failed` 时可用。

---

## 7. 底部：迭代收敛条

```
迭代收敛    第1轮 ✗ 3 失败 ───── 第2轮 ● 进行中 ───── (上限 3 轮)
             ●─────────────────────●- - - - - - - - - -○
```

这是整个页面**信息密度最高**的一块——它直接回答「这个项目还要几轮能收敛」。

| 元素 | 规格 |
|---|---|
| 节点 | 每轮一个圆点，颜色同状态规范 |
| 标注 | `第N轮` + 结果（`✗ M 失败` / `✓ 通过` / `● 进行中`） |
| 上限 | 末尾灰字标注 `(上限 N 轮)`；`iteration === max` 时整条变橙并提示「已达迭代上限」 |
| 交互 | 点击历史轮次 → 中栏切换到该轮**只读归档视图**，标题带「第 N 轮 · 历史」，禁用所有操作按钮 |

`iterations.length <= 1` 时整条隐藏，避免首轮出现无意义 UI。

---

## 8. 实时数据流

```
Socket.IO /tahp-run
   └─ pipeline.*  ──→ usePipelineStore
                         ├─ runs: Map<runId, TimelineView>
                         └─ logs: Map<`${runId}:${node}`, string[]>   环形缓冲 2000 行
```

### 8.1 加载与订阅

1. 进入看板 → `GET /runs`（列表）
2. 选中 run → `GET /runs/:runId/timeline`（全量快照）
3. 订阅 `pipeline.*`，按 `run_id` 增量更新
4. 只有**当前展开的节点**才拉 `GET /runs/:runId/logs/:node`

### 8.2 性能约束

| 约束 | 做法 |
|---|---|
| 日志刷屏 | `pipeline.node_log` 客户端节流合批（≥200ms） |
| 大量日志 | `EaLogViewer` 虚拟滚动 + 环形缓冲 2000 行 |
| 不订阅底层事件 | 看板**不订阅** `task.*` / 自检 SSE；点进详情才按 `refs` 复用现有 store |
| 断线 | Socket 断开 → 降级 5s 轮询 `timeline`；恢复后重新拉一次全量快照对齐 |

### 8.3 一致性

Socket 事件只做增量更新。任何以下时机都**重新拉一次 `timeline` 全量对齐**：切换 run、断线重连、`pipeline.node_changed`。避免长时间增量累积漂移。

---

## 9. 新建运行向导

`NSteps` 四步，每步校验通过才能下一步。

| 步 | 内容 | 校验 |
|---|---|---|
| 1 · 选项目 | 项目下拉（`GET /prereqs/projects`）+ 战役选择 | 必选 |
| 2 · 确认前置 | 按域折叠面板；`incomplete_required` 字段红标可就地补填；可勾选/取消域 | 所有启用域必填项非空 |
| 3 · 配置执行 | 编译上下文（mapped_root / workspace / components / variant）· 目标设备 · 用例策略（推荐/固定）· 迭代上限 | 路径必须在 `mapped_root` 下 |
| 4 · 确认启动 | 只读展示完整计划：域清单、流程节点（标注哪些当前不可用将转人工）、预计人工介入点 | — |

第 4 步**必须显式列出当前不可用的能力**，例如「编译：能力未接入，将在该节点等待人工确认」。让用户启动前就知道会在哪儿停。

---

## 10. 流程编排 Tab（F9）

对应「动态增删节点」的 UI 出口。**初版做只读 + 开关即可，不做拖拽**（避免过度开发）。

```
┌────────────────────────────────────────────────────────┐
│ 标准适配流水线  v1                        [恢复默认][保存]│
├────────────────────────────────────────────────────────┤
│ ☑ ① 前置信息    prereq        不可用时：失败    ✓可用    │
│ ☑ ② AI 适配     adapt         不可用时：失败    ✓可用    │
│ ☑ ③ 编译        build         不可用时：转人工  🔧未接入 │
│ ☑ ④ 烧录        flash         不可用时：转人工  ✓可用    │
│ ☑ ⑤ AI 自检     selfcheck     不可用时：转人工  ✓可用    │
│ ☑ ⑥ AI 故障分析 triage        不可用时：跳过    ✓可用    │
│ ☑ ⑦ 人工审核    human_review  —               ✓可用    │
│ ☐ ⑧ 提交 Gerrit gerrit        不可用时：转人工  🔧未接入 │
├────────────────────────────────────────────────────────┤
│ 最大迭代轮次：[ 3 ]                                      │
└────────────────────────────────────────────────────────┘
```

- 复选框 → `enabled`
- 「不可用时」下拉 → `onUnavailable`
- 右侧能力状态来自 `GET /capabilities`，实时反映 `probe()` 结果
- 保存 → `PUT /workflow`，后端 `validateWorkflow` 不通过时返回具体错误并**拒绝保存**
- 顺序调整与新增节点：**F9 之后再议**，当前通过改 `workflow.json` 完成

---

## 11. 空态与异常态

| 场景 | 表现 |
|---|---|
| 无任何 run | 居中插画 + 「还没有运行记录」+ 主按钮「新建运行」 |
| 中心未配置 | 新建向导第 1 步顶部黄条：「未配置 TAHP 中心连接，无法拉取项目前置」+ 跳配置页链接 |
| Agent Bridge 未运行 | 页头红条 + 新建按钮禁用（适配阶段必然失败，提前拦住） |
| run 加载失败 | 中栏错误卡片 + 「重试」 |
| 节点无日志 | 日志区占位「该节点暂无日志输出」 |
| run 已达迭代上限 | 迭代条变橙 + 右栏卡片「已达迭代上限，请人工决策」+ `[继续加一轮] [终止]` |

---

## 12. 文案与国际化

- 所有用户可见文案进 locale 文件，遵循 `tahp-console-dev` 规则
- 节点 `label` 由**后端**下发（来自 `StageDefinition.label`），前端不维护映射表——保证新增节点无需改前端
- 状态文案统一：`等待中 / 进行中 / 待人工处理 / 已完成 / 失败 / 已跳过`

---

## 13. 验收清单

- [ ] 步进条节点完全由 `timeline.nodes` 驱动，代码中无节点 key 硬编码
- [ ] 新增一个后端节点后，不改前端即可在步进条出现并用 `DefaultPanel` 查看
- [ ] `waiting_human` 节点闪烁，页头徽章计数正确，右栏卡片可提交
- [ ] 恢复点选择器默认选中 safe 的推荐项；unsafe 项灰显但可见、附原因、点选后弹二次确认
- [ ] 未改代码时烧录失败，恢复点推荐 `flash` 而非 `build`
- [ ] 迭代 ≥2 时回环弧线与收敛条正确显示，可点击查看历史轮次
- [ ] 编译日志 5 万行不卡顿（虚拟滚动生效）
- [ ] Socket 断开后降级轮询，恢复后状态与后端一致
- [ ] 窗口 `<1400px` 时右栏转抽屉且可正常操作
- [ ] 刷新页面后当前节点、日志、待办完整恢复
