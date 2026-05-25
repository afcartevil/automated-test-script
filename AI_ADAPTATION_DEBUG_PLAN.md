# AI 适配调试功能开发规划

## 项目概览

**功能名称：** AI适配调试（AI Adaptation & Debugging）
**目标用户：** Android底层开发工程师 + QA
**预期成果：** 一套完整的AI驱动的代码适配和调试解决方案

---

## 第一阶段：需求澄清与业务建模（1-2周）

### 1.1 与业务owner的协作框架

**协作频率：** 每周2次同步会议
- **周一/周三 10:00** — 需求澄清 + 方案评审
- **周五 15:00** — 进度同步 + 问题复盘

**业务owner的核心职责：**
1. 定义清晰的业务边界和成功指标
2. 提供真实的使用场景和数据样本
3. 验证AI建议的准确性和可行性
4. 参与UI设计评审和可用性测试

### 1.2 需求澄清清单

需要从业务owner获取以下信息：

#### **A. 核心业务定义**
- [ ] AI适配调试的具体应用场景有哪些？
  - 场景1: _______________
  - 场景2: _______________
  - 场景3: _______________
- [ ] 每个场景中的典型输入/输出是什么？
- [ ] 目前的工作流程是怎样的？瓶颈在哪里？
- [ ] AI需要在其中扮演什么角色？

#### **B. 技术场景**
- [ ] 涉及的代码类型：(kernel driver / app / shared library / middleware)
- [ ] 涉及的Android版本：(12 / 13 / 14 / 15 等)
- [ ] 典型的适配问题有哪些类型？
  - API变更
  - ABI变更
  - 行为变更
  - 权限变更
  - 其他_______________
- [ ] 有没有历史bug数据/案例可参考？

#### **C. 成功标准**
- [ ] 预期提升的效率：多少倍？多少百分比？
- [ ] 准确性要求：误报率 < X% ？
- [ ] 性能要求：响应时间 < X秒？
- [ ] 覆盖度要求：能处理 X% 的问题？

#### **D. 约束与限制**
- [ ] 有没有安全、隐私、合规方面的要求？
- [ ] 有没有必须/禁止使用的特定技术栈？
- [ ] 与现有系统的集成约束是什么？

### 1.3 输出物：需求文档（BRD）

位置：`docs/requirements/ai-adaptation-debug-brd.md`

包含：
```
1. 业务背景 & 问题陈述
2. 目标用户画像 & 使用场景（3-5个详细场景）
3. 核心功能需求（按优先级）
4. 非功能需求（性能、安全、扩展性等）
5. 验收标准 & 成功指标
6. 风险识别与应对方案
7. 资源与时间表
```

**业务owner签核：** ____________________________

---

## 第二阶段：功能架构设计（2-3周）

### 2.1 功能分解（Work Breakdown Structure）

#### 核心功能模块

```
AI适配调试系统
├── 1. 问题识别模块
│   ├── 1.1 代码扫描 (Scanner)
│   ├── 1.2 问题检测 (Detector)
│   ├── 1.3 问题分类 (Classifier)
│   └── 1.4 风险评估 (Risk Assessor)
│
├── 2. 智能建议模块
│   ├── 2.1 方案生成 (Solution Generator)
│   ├── 2.2 方案评分 (Scorer)
│   ├── 2.3 代码生成 (Code Generator)
│   └── 2.4 测试生成 (Test Generator)
│
├── 3. 验证反馈模块
│   ├── 3.1 静态验证 (Static Verifier)
│   ├── 3.2 编译验证 (Build Verifier)
│   ├── 3.3 运行验证 (Runtime Verifier)
│   └── 3.4 反馈学习 (Feedback Learner)
│
├── 4. 交互界面模块
│   ├── 4.1 问题展示面板 (Issue Dashboard)
│   ├── 4.2 建议详情面板 (Suggestion Panel)
│   ├── 4.3 对比编辑器 (Diff Editor)
│   └── 4.4 批量操作 (Batch Operations)
│
└── 5. 集成接口模块
    ├── 5.1 代码库接入 (Git Integration)
    ├── 5.2 构建系统接入 (Build System Integration)
    ├── 5.3 CI/CD接入 (CI/CD Integration)
    └── 5.4 报告导出 (Report Export)
```

### 2.2 功能优先级划分（MVP → P1 → P2）

**MVP（最小可行产品）—— 第1个月完成**

| # | 功能 | 业务owner输入 | 技术复杂度 | 预期效果 |
|---|------|-------------|-----------|---------|
| 1 | 单文件代码扫描 | 上传.java/.kt文件 | ⭐⭐ | 检出10+类问题 |
| 2 | 问题智能分类 | 选择Android版本 | ⭐⭐ | 精准度>85% |
| 3 | 基础建议生成 | 点击问题→生成建议 | ⭐⭐⭐ | 生成3-5个方案 |
| 4 | 代码对比展示 | 原始代码 vs 建议代码 | ⭐ | 清晰的diff视图 |
| 5 | 建议反馈 | 采纳/拒绝建议记录 | ⭐ | 收集用户反馈 |

**P1 功能 —— 第2-3个月完成**

| # | 功能 | 依赖 |
|---|------|------|
| 6 | 批量文件处理 | 功能1 |
| 7 | 关联问题链接 | 功能2 |
| 8 | 构建验证集成 | 工具链 |
| 9 | 测试用例生成 | 功能3 |
| 10 | 适配报告导出 | 功能4 |

**P2 功能 —— 长期优化**

| # | 功能 |
|---|------|
| 11 | 深度学习模型优化 |
| 12 | 跨工程项目协同 |
| 13 | A/B测试框架 |

### 2.3 与TAHP架构的映射

```
TAHP 现有框架：
constraints/telephony/code-adaptation.yaml
        ├── scope.includes: ["<module>/src", "<module>/test"]
        ├── domain: "code_adaptation"
        └── metadata: {...}

AI适配调试的约束配置：
constraints/adaptation-debug/
├── module.yaml
│   ├── name: "adaptation-debug"
│   ├── domain: ["code_adaptation", "verification"]
│   ├── scope:
│   │   includes: ["tahp-console/packages/client/src/views/adaptation-debug",
│   │              "tahp-mcp-server/handlers/adaptation_handler.py",
│   │              "knowledge-base/adaptation-patterns/"]
│   │   excludes: [".git", "build/", "*.lock"]
│   └── quality_gates: "P1"
│
├── code-adaptation.yaml      ← 具体业务规则
├── eval-data/case_001.yaml   ← 评测数据
└── knowledge/patterns.yaml   ← 知识库
```

### 2.4 输出物：功能规格说明书（FSD）

位置：`docs/design/ai-adaptation-debug-fsd.md`

包含：
```
1. 系统架构图 (C4 diagrams)
2. 数据流图 (dataflow diagrams)
3. 功能模块详细说明
   - 输入/输出接口
   - 处理逻辑
   - 错误处理
   - 性能指标
4. 集成点 & 依赖关系
5. 扩展性设计
6. 版本演进规划
```

**业务owner签核：** ____________________________

---

## 第三阶段：技术方案设计（1-2周）

### 3.1 技术栈决策

**问题识别模块：**
```
├── 静态分析工具: Android Lint + Custom Rules (YAML)
├── AST解析: tree-sitter (支持多语言)
├── 规则引擎: Constraint-based (constraints/)
└── 输出格式: JSON
```

**智能建议模块：**
```
├── LLM主模型: Claude Haiku / Sonnet (via Anthropic SDK)
├── 提示工程: 
│   ├── Few-shot examples from knowledge-base/
│   ├── Domain context from constraints/
│   └── Historical patterns from eval-data/
├── 并发处理: async/await (Node.js) + queuing
└── 缓存: Redis (热问题快速命中)
```

**验证反馈模块：**
```
├── 静态验证: TypeScript compiler (tahp-console-server)
├── 编译验证: 调用 `build-verifier` tool
├── 运行验证: 沙箱执行环境
└── 反馈循环: 自适应提示微调
```

**交互界面模块：**
```
├── 前端框架: Vue 3 + Composition API (现有)
├── UI组件库: Naive UI (现有)
├── 代码编辑器: Monaco Editor
├── Diff展示: vue-diff (高性能diff组件)
└── 实时通信: Socket.IO (现有 /chat-run namespace)
```

### 3.2 API设计

**后端 MCP 工具注册：**

```python
# tahp-mcp-server/server.py 新增工具

_list_tools():
    return [
        {
            "name": "tahp_scan_adaptation_issues",
            "description": "扫描代码中的适配问题",
            "inputSchema": {
                "properties": {
                    "file_path": {"type": "string"},
                    "target_android_version": {"type": "string"},
                    "scope": {"type": "string", "enum": ["API", "ABI", "behavior"]}
                }
            }
        },
        {
            "name": "tahp_generate_adaptation_solution",
            "description": "为检出的问题生成AI建议方案",
            "inputSchema": {...}
        },
        {
            "name": "tahp_verify_adaptation_fix",
            "description": "验证建议的修复是否可行",
            "inputSchema": {...}
        }
    ]
```

**前端 HTTP 接口：**

```
POST /api/adaptation-debug/scan
  body: { file_content, target_version, options }
  response: { issues: [...], scan_time_ms }

POST /api/adaptation-debug/suggest
  body: { issue_id, context, preferences }
  response: { solutions: [...], generation_time_ms }
  
GET /api/adaptation-debug/report/:report_id
  response: { issues, solutions, statistics, export_formats }
```

**前端 WebSocket 事件（Socket.IO）：**

```javascript
// 在 /chat-run 或新 /adaptation-debug namespace
socket.emit('scan_start', { file_path, options })
socket.on('scan_progress', { progress: 0.5, current_file })
socket.on('scan_complete', { issues: [...], total_time })

socket.emit('suggest_start', { issue_id })
socket.on('suggestion_streaming', { chunk })
socket.on('suggestion_complete', { solutions: [...] })
```

### 3.3 数据模型设计

```typescript
// 问题模型
interface AdaptationIssue {
  id: string;
  file_path: string;
  line: number;
  severity: "critical" | "warning" | "info";
  type: "APIChange" | "ABIChange" | "BehaviorChange";
  description: string;
  affectedVersions: string[];
  context: {
    code_snippet: string;
    surrounding_code: string;
  };
  suggested_solution_ids: string[];
  created_at: timestamp;
  status: "unresolved" | "accepted" | "rejected" | "verifying";
}

// 建议方案模型
interface AdaptationSolution {
  id: string;
  issue_id: string;
  rank: number;  // 1,2,3 等
  approach: string;
  fixed_code: string;
  reasoning: string;
  confidence_score: 0.0-1.0;
  estimated_effort: "low" | "medium" | "high";
  verification_status: "pending" | "passed" | "failed";
  user_feedback: {
    adopted: boolean;
    notes: string;
    rating: 1-5;
  };
  created_at: timestamp;
}

// 报告模型
interface AdaptationReport {
  id: string;
  project_name: string;
  scan_scope: string[];  // file paths
  target_version: string;
  timestamp: timestamp;
  statistics: {
    total_files: number;
    total_issues: number;
    by_severity: { critical, warning, info };
    by_type: { APIChange, ABIChange, ... };
    resolution_rate: percent;
  };
  issues: AdaptationIssue[];
  export_formats: ["pdf", "html", "json"];
}
```

### 3.4 输出物：技术设计文档（TDD）

位置：`docs/design/ai-adaptation-debug-tdd.md`

包含：
```
1. 系统架构图 (前后端 + MCP)
2. API 完整定义 (OpenAPI 3.0)
3. 数据库 Schema (如有)
4. 关键算法设计
5. 性能指标与优化策略
6. 安全与隐私设计
7. 可观测性设计 (logging, metrics, tracing)
8. 第三方依赖列表与选型理由
```

---

## 第四阶段：UI/UX 设计（2-3周）

### 4.1 页面流程图

使用 `frontend-design` skill 指导的工作流：

```
首页启动
  ↓
选择工作模式 → [快速扫描 / 深度分析 / 批量处理]
  ↓
配置参数 (目标版本, scope, 输出格式)
  ↓
上传/选择代码源 (单文件 / 文件夹 / Git仓库)
  ↓
[扫描进行中] 实时进度条 + 日志
  ↓
问题列表展示 + 过滤/排序
  ↓
选中问题 → 查看详情 + 建议方案 (1/3)
  ↓
[生成建议中] 流式展示
  ↓
方案对比 (左原始 / 右建议) + 差异高亮
  ↓
操作选项 [采纳 / 拒绝 / 编辑 / 测试 / 反馈]
  ↓
生成报告 [下载 / 分享 / 归档]
```

### 4.2 关键页面设计

#### Page 1: 扫描配置面板

```
┌─────────────────────────────────────────────┐
│ AI 适配调试 > 新建扫描                         │
├─────────────────────────────────────────────┤
│                                             │
│  [分步指引] [快速配置] [高级选项]              │
│                                             │
│  1️⃣  选择扫描类型 ▼                          │
│      ○ 快速扫描 (仅检测明显问题)             │
│      ○ 深度分析 (完整AST分析 ~3min)         │
│      ○ 批量处理 (多文件并行处理)             │
│                                             │
│  2️⃣  目标Android版本 ▼                      │
│      [Android 12] [13] [14] [15]           │
│      多选: ☑ 13  ☑ 14  ☐ 15               │
│                                             │
│  3️⃣  问题类型过滤 ☑ API变更  ☑ 权限变更   │
│      ☑ ABI变更  ☑ 行为变更  ☑ 其他       │
│                                             │
│  4️⃣  上传代码                               │
│      ┌─────────────────────────────┐       │
│      │ 拖拽文件 / 文件夹 / Git URL    │       │
│      │ 或 [浏览] 选择文件             │       │
│      │ ℹ️  支持: .java .kt .xml      │       │
│      └─────────────────────────────┘       │
│      📁 main/java/com/example/App.java     │
│      📁 build.gradle                       │
│                                             │
│  输出格式 ☑ 在线查看  ☑ PDF报告  ☑ JSON  │
│                                             │
│  [←返回] [重置] [开始扫描→]                   │
│                                             │
└─────────────────────────────────────────────┘
```

#### Page 2: 扫描进度与结果列表

```
┌─────────────────────────────────────────────┐
│ AI 适配调试 > 扫描结果                        │
├─────────────────────────────────────────────┤
│ 扫描进度:  [████████████░░░░] 60%  已用时: 1m │
│ 当前:  App.java (5/12)                     │
│                                             │
│ ┌─ 问题统计 ──────────────────────────────┐ │
│ │ 🔴 严重 3   🟡 警告 12   🔵 信息 5      │ │
│ │ 总计: 20 个问题 · 平均优先级: 2.3/5     │ │
│ └──────────────────────────────────────────┘ │
│                                             │
│ [过滤] 严重度: 全部▼  类型: 全部▼          │
│ [排序] 严重度↓  文件名  行号                │
│                                             │
│ ┌─ 检测到的问题 ────────────────────────────┐ │
│ │ 🔴 [3:5]   API已弃用: AsyncTask          │ │
│ │    App.java:123                         │ │
│ │    → 迁移方案: WorkManager / 生成对比   │ │
│ │                                          │ │
│ │ 🟡 [12:14] 权限模型变更: READ_PHONE_STATE│ │
│ │    AndroidManifest.xml:45               │ │
│ │    → 迁移方案: 运行时权限 / 生成对比    │ │
│ │                                          │ │
│ │ 🟡 [14:17] 行为变更: PackageManager API │ │
│ │    ServiceManager.java:89               │ │
│ │    → 迁移方案: 使用新API / 生成对比    │ │
│ └──────────────────────────────────────────┘ │
│                                             │
│ [← 重新扫描] [📊 生成报告] [💾 导出JSON]    │
└─────────────────────────────────────────────┘
```

#### Page 3: 问题详情与建议对比

```
┌─────────────────────────────────────────────┐
│ 问题 #3: API已弃用 - AsyncTask              │
├─────────────────────────────────────────────┤
│                                             │
│ 基本信息:                                    │
│ · 文件: App.java:123                       │
│ · 严重度: 🔴 严重                           │
│ · 影响版本: Android 13+                     │
│ · 状态: 未处理 ⚪ → 已采纳 ✅               │
│                                             │
│ 问题描述:                                    │
│ AsyncTask 在 Android 13 中已被弃用。        │
│ 建议使用 WorkManager 或 Coroutines。        │
│                                             │
│ ┌─ 代码对比 (1/3 方案) ─────────────────┐  │
│ │                                       │  │
│ │ 原始代码              建议方案 (置信度: 92%)│
│ │ ─────────────         ─────────────  │  │
│ │ class MyTask extends  class MyWorker │  │
│ │   AsyncTask {           extends ListenableWorker {│
│ │   @Override                │  │  │  │  │
│ │   protected Void           │  override val result│  │
│ │   doInBackground(...) {    │    = ListenableFuture<Result> │  │
│ │     // 做某事          │  │  │  │  │
│ │     return null;       │    override suspend fun │  │
│ │   }                       │    doWork(): Result {│  │
│ │ }                         │    // 做某事    │  │
│ │                           │    return Result.success() │  │
│ │ [💬 收起代码解释]          │  } }              │  │
│ │                                       │  │
│ │ 🔍 关键变更:                          │  │
│ │ 1. 从 AsyncTask → ListenableWorker   │  │
│ │ 2. 实现 doWork() 而非 doInBackground│  │
│ │ 3. 返回 Result 而非 Void             │  │
│ │                                       │  │
│ └──────────────────────────────────────┘  │
│                                             │
│ 其他方案:                                    │
│ [2] 使用 Coroutines (置信度: 88%)   →展开  │
│ [3] 使用 Kotlin Flow (置信度: 76%)  →展开  │
│                                             │
│ 相关问题:                                    │
│ 🔗 #5: Handler 迁移 (同模块)              │
│ 🔗 #8: ThreadPool 使用 (关联修复)          │
│                                             │
│ 操作:                                        │
│ [❌ 拒绝] [✅ 采纳此方案] [🔧 编辑代码]    │
│ [🧪 生成测试] [🔗 查看相关] [💬 反馈]    │
│                                             │
└─────────────────────────────────────────────┘
```

#### Page 4: 批量操作与报告生成

```
┌─────────────────────────────────────────────┐
│ AI 适配调试 > 批量处理                       │
├─────────────────────────────────────────────┤
│                                             │
│ 选中问题: 20/20 [全选] [取消全选]            │
│                                             │
│ 批量操作:                                    │
│ ┌──────────────────────────────────────┐   │
│ │ 操作 ▼                               │   │
│ │ ○ 全部采纳 (推荐)                     │   │
│ │ ○ 导出为补丁文件 (.patch)            │   │
│ │ ○ 生成测试用例                       │   │
│ │ ○ 开启构建验证                       │   │
│ │ ○ 生成适配报告                       │   │
│ └──────────────────────────────────────┘   │
│                                             │
│ 报告配置:                                    │
│ 📋 报告标题: ______________________        │
│ 📝 附加说明: ______________________        │
│ 📅 包含时间戳: ☑                          │
│ 👤 负责人: ______________________          │
│ 🏷️  标签: AI-Adaptation, Android-14      │
│                                             │
│ [预览报告] [生成PDF] [生成HTML]           │
│                                             │
└─────────────────────────────────────────────┘
```

### 4.3 设计规范与组件清单

调用 `frontend-design` skill 完成的设计工作：

```yaml
设计系统:
  色彩体系:
    primary: #1890FF (Naive UI blue)
    severity:
      critical: #FF3B30
      warning: #FF9500
      info: #17C950
  
  排版:
    heading_lg: 24px / bold / #222
    body: 14px / regular / #666
    caption: 12px / regular / #999
  
  间距:
    sm: 8px
    md: 16px
    lg: 24px
  
  组件库:
    - NButton (primary / secondary / text)
    - NCard (elevated / outlined)
    - NTable (with virtual scroll for 1000+ rows)
    - NTree (file tree for code navigation)
    - NDiffEditor (Monaco + vue-diff)
    - NProgress (upload / scan progress)
    - NBadge (issue count / severity tags)
    - NTabs (results / report / history)
    - NDrawer (issue detail panel)
    - NModal (confirm actions / settings)
    - NPopover (hover tooltips / code snippets)
    - NUpload (drag-drop file input)

无障碍性 (A11Y):
  - ARIA labels for all interactive elements
  - 键盘导航支持 (Tab / Enter / Escape)
  - 屏幕阅读器兼容
  - 色盲友好 (通过形状+颜色区分)

响应式设计:
  - Desktop: 1920px (full sidebar + content)
  - Tablet: 1024px (collapsible sidebar)
  - Mobile: 768px (drawer sidebar + full-width content)
```

### 4.4 输出物：UI设计规范 (UI Kit + Prototype)

位置：`docs/design/ai-adaptation-debug-ui.md`

包含：
```
1. 页面流程图 (user journeys)
2. 页面原型 (wireframes)
3. 高保真设计稿 (Figma link)
4. 设计规范 & 组件库
5. 可用性测试计划 & 结果
6. 响应式设计验证
```

**业务owner与UX设计师签核：** ____________________________

---

## 第五阶段：开发执行计划（6-8周）

### 5.1 开发工作分解（WBS）

#### Sprint 1 (第1-2周): 基础设施搭建

```
[ ] 后端 MCP 工具框架
  [x] 1.1 创建 adaptation_handler.py
  [ ] 1.2 注册到 server.py (_list_tools / _dispatch_tool)
  [ ] 1.3 编写单元测试
  [ ] 1.4 文档：工具使用说明

[ ] 前端路由与页面骨架
  [ ] 2.1 创建 /views/adaptation-debug/ 目录
  [ ] 2.2 主页面组件 (AdaptationDebugPage.vue)
  [ ] 2.3 子页面路由配置
  [ ] 2.4 导航菜单集成

[ ] 数据模型与存储
  [ ] 3.1 定义 TypeScript interfaces (models/)
  [ ] 3.2 创建本地缓存 (Pinia store)
  [ ] 3.3 API 客户端 (api/)

预期产出: 后端可正常响应工具调用, 前端路由完整但无业务逻辑
```

#### Sprint 2 (第3-4周): MVP 核心功能

```
[ ] 问题扫描功能
  [ ] 2.1 文件上传处理 (drag-drop + 文件选择)
  [ ] 2.2 调用 tahp_scan_adaptation_issues 工具
  [ ] 2.3 结果列表展示 (NTable)
  [ ] 2.4 问题过滤与排序
  [ ] 2.5 单元测试 (>80% coverage)

[ ] 建议生成功能
  [ ] 3.1 问题点击 → 详情面板弹出
  [ ] 3.2 调用 tahp_generate_adaptation_solution (流式)
  [ ] 3.3 方案列表展示 (carousel 或 tab)
  [ ] 3.4 代码对比编辑器集成

[ ] 用户交互
  [ ] 4.1 采纳/拒绝操作 + 状态管理
  [ ] 4.2 实时反馈收集 (rating / notes)
  [ ] 4.3 进度条与加载状态

预期产出: 单文件快速扫描 + 建议生成完整流程可用
质量门禁: 编译通过 + E2E测试 (3个关键路径)
```

#### Sprint 3 (第5-6周): 扩展与验证

```
[ ] 批量处理
  [ ] 1.1 多文件同时扫描 (并行处理)
  [ ] 1.2 批量采纳建议 (with progress bar)
  [ ] 1.3 扫描历史记录 & 对比

[ ] 验证集成
  [ ] 2.1 构建验证 (调用 build-verifier tool)
  [ ] 2.2 编译检查结果展示
  [ ] 2.3 失败提示与日志下载

[ ] 报告生成
  [ ] 3.1 统计信息聚合 (总问题数、分布、采纳率)
  [ ] 3.2 PDF/HTML 报告导出
  [ ] 3.3 报告模板定制

预期产出: 完整的扫描→建议→验证→报告流程
质量门禁: 集成测试通过 + 性能基准 (扫描<3min for 100 files)
```

#### Sprint 4 (第7-8周): 优化与发布

```
[ ] 性能优化
  [ ] 1.1 大文件处理性能测试
  [ ] 1.2 缓存策略优化
  [ ] 1.3 前端渲染优化 (虚拟滚动)

[ ] 用户体验优化
  [ ] 2.1 可用性测试 (5+ 真实用户)
  [ ] 2.2 反馈迭代
  [ ] 2.3 帮助文档与视频教程

[ ] 文档与交接
  [ ] 3.1 API 文档完成 (OpenAPI)
  [ ] 3.2 用户手册与操作指南
  [ ] 3.3 运维文档 (部署、监控、故障排查)
  [ ] 3.4 代码审查与技术交接

[ ] 发布准备
  [ ] 4.1 质量门禁检查 (gate_check P0/P1)
  [ ] 4.2 安全审计
  [ ] 4.3 灰度发布计划

预期产出: 可生产环境上线的稳定版本
```

### 5.2 开发进度追踪表

| Sprint | 起止日期 | 目标 | 依赖 | 风险 | 业务owner参与 |
|--------|---------|------|------|------|--------------|
| 1 | 第1-2周 | 框架完成 | - | 工具API变更 | 周二评审 |
| 2 | 第3-4周 | MVP可用 | Sprint1 | LLM服务延迟 | 每日demo |
| 3 | 第5-6周 | 功能完整 | Sprint2 | 构建系统集成 | 中期验收 |
| 4 | 第7-8周 | 生产上线 | Sprint3 | 用户反馈量大 | 最终发布评审 |

### 5.3 业务owner的参与方式

#### 定期同步
- **每周一 10:00** — Sprint规划 + 优先级调整
- **每周三 14:00** — 演示 Demo + 反馈收集
- **每周五 16:00** — 问题复盘 + 下周计划

#### 关键决策点
- [ ] **Sprint 2 末** — 能否进入 Sprint 3？(需完成5个关键E2E测试)
- [ ] **Sprint 3 末** — 验证集成效果是否满足需求？
- [ ] **Sprint 4 初** — 可用性测试反馈：是否需要大调整？
- [ ] **发布前** — 最终验收签核

#### 数据与反馈
- 业务owner 提供：
  - ✅ 真实的代码样本 (不同类型的适配问题)
  - ✅ 验收标准与成功指标
  - ✅ 用户可用性测试反馈
  - ✅ 生产环境的优先级调整

- 开发团队提供：
  - ✅ 周进度报告 (完成率、风险)
  - ✅ 技术决策说明
  - ✅ 性能数据与优化建议

---

## 第六阶段：持续改进与迭代（发布后）

### 6.1 发布后的 KPI 监控

```
关键指标:
├── 功能覆盖率: 能处理 X% 的真实适配问题
├── 建议准确率: 采纳率 > 75% (用户认可)
├── 响应时间: 扫描 <3min, 建议 <10s
├── 学习效果: 随着用户反馈，模型精度提升 >5%/月
└── 满意度: NPS 评分 > 50
```

### 6.2 反馈循环

```
用户反馈
    ↓
收集 (评分、评论、日志)
    ↓
分析 (提取问题、优先级排序)
    ↓
迭代计划 (bug修复、功能改进、性能优化)
    ↓
模型微调 (few-shot examples 更新、提示词优化)
    ↓
验证 (eval-data 扩展、基准测试)
    ↓
发布 v1.1, v1.2, ...
```

### 6.3 长期规划（6-12个月）

| 时间 | 目标 | 推动者 |
|------|------|--------|
| 第1个月 | MVP 上线，收集50+真实用例 | Dev Team |
| 第2-3个月 | 基于反馈迭代优化，精度提升至 >85% | Dev + Owner |
| 第4-6个月 | 扩展到多模块（kernel-driver, power-mgmt），统一框架 | Dev Team + Cross-module Owners |
| 第7-12个月 | 深度学习模型微调，本地化LLM部署方案研究 | ML Team + Dev |

---

## 附录：项目制度与质量保证

### A. 质量门禁体系

```
code-adaptation 模块的 constraints/adaptation-debug/module.yaml 配置:

quality_gates:
  P0:  # 代码提交必须通过
    - 编译无误 (TypeScript strict mode)
    - Scope 合规 (只改 scope.includes 中的文件)
    - 安全检查 (无密钥/token硬编码)
    - API真实性验证 (tahp_ 工具真实存在)
  
  P1:  # 代码审查警告
    - 代码风格一致性 (ESLint / Prettier)
    - 单元测试覆盖率 >80%
    - 函数/类型文档完整
  
  P2:  # 记录但不阻塞
    - 代码复杂度 (cyclomatic < 10)
    - 重复率 < 5%
```

验证命令：
```bash
# 本地验证
python scripts/gate_check.py constraints/adaptation-debug/ --level P0

# CI/CD (GitLab)
.gitlab-ci.yml 中自动运行
```

### B. 测试策略

```
测试类型 | 覆盖范围 | 所有者 | 执行时机 |
---------|---------|-------|---------|
单元测试 | 各个函数/方法 | Dev | 每个Commit |
集成测试 | 页面 <-> API <-> LLM | Dev | 每个Sprint末 |
E2E测试 | 完整用户旅程 | Owner + QA | 发布前 |
性能测试 | 响应时间、并发处理 | Dev | Sprint 3+ |
可用性测试 | 5-10个真实用户 | Owner + UX | Sprint 4 |
兼容性测试 | 浏览器、设备 | QA | 发布前 |
```

### C. 文档要求

| 类别 | 文档路径 | 维护者 | 频率 |
|------|---------|--------|------|
| 业务需求 | docs/requirements/ai-adaptation-debug-brd.md | Owner | 需求变更时 |
| 功能规格 | docs/design/ai-adaptation-debug-fsd.md | PM + Dev | Sprint规划时 |
| 技术设计 | docs/design/ai-adaptation-debug-tdd.md | Arch | 架构变更时 |
| UI规范 | docs/design/ai-adaptation-debug-ui.md | Designer | 设计评审时 |
| API文档 | docs/api/adaptation-debug-api.yaml (OpenAPI) | Dev | API变更时 |
| 用户手册 | docs/user-guide/adaptation-debug.md | Owner + Dev | 功能发布时 |
| 运维手册 | docs/operations/adaptation-debug-ops.md | DevOps | 上线时 |

---

## 总结与关键成功因素

### 关键成功因素 (CSF)

1. **需求清晰度** → 前期充分沟通，避免返工
2. **业务owner参与度** → 每周同步、真实数据提供、反馈及时
3. **技术可行性验证** → Sprint 1-2 做好 POC，尽早发现风险
4. **质量意识** → 从一开始就关注编译门禁、测试覆盖率
5. **灵活迭代** → 反馈快速响应，不死守原计划

### 里程碑与预期

| 里程碑 | 时间 | 预期成果 |
|--------|------|---------|
| 需求澄清完成 | 第2周末 | 签核的BRD文档 |
| 技术方案评审通过 | 第3周末 | 评审的TDD + FSD |
| MVP 演示 | 第4周末 | 可工作的原型 |
| 功能完整版本 | 第6周末 | 所有P0功能可用 |
| 用户测试完成 | 第7周末 | 反馈收集并优化 |
| **生产上线** | **第8周末** | **可持续运维的产品** |

---

**下一步行动：**

1. 邀请业务owner参加**需求澄清启动会议**（第一周）
2. 使用本文档中的"1.2 需求澄清清单"逐条填写
3. 建立**周期同步机制**（见第5.3节）
4. 创建项目 Jira/Linear 看板，导入本WBS
5. 在 Git 创建 `feature/adaptation-debug` 分支，开始功能开发

如需进一步讨论架构细节或user story编写，随时反馈！
