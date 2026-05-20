# MCP服务器系统

<cite>
**本文档引用的文件**
- [server.py](file://tahp-mcp-server/server.py)
- [config.py](file://tahp-mcp-server/config.py)
- [core/__init__.py](file://tahp-mcp-server/core/__init__.py)
- [adapters/__init__.py](file://tahp-mcp-server/adapters/__init__.py)
- [progress/tracker.py](file://tahp-mcp-server/progress/tracker.py)
- [progress/emitter.py](file://tahp-mcp-server/progress/emitter.py)
- [test_server.py](file://tahp-mcp-server/test_server.py)
- [pyproject.toml](file://tahp-mcp-server/pyproject.toml)
- [gate_check.py](file://scripts/gate_check.py)
- [tool.py (android-log-analyzer)](file://tools/android-log-analyzer/tool.py)
- [tool.py (code-review-checker)](file://tools/code-review-checker/tool.py)
- [config.yaml (knowledge-base)](file://knowledge-base/config.yaml)
- [requirements.txt](file://requirements.txt)
- [system-overview.md](file://docs/architecture/system-overview.md)
</cite>

## 目录
1. [引言](#引言)
2. [项目结构](#项目结构)
3. [核心组件](#核心组件)
4. [架构总览](#架构总览)
5. [详细组件分析](#详细组件分析)
6. [依赖分析](#依赖分析)
7. [性能考虑](#性能考虑)
8. [故障排除指南](#故障排除指南)
9. [结论](#结论)
10. [附录](#附录)

## 引言
本文件为 TAHP（TECNO AI Harness Platform）MCP（Model Context Protocol）服务器系统的全面技术文档。系统通过 MCP 标准协议，将 TAHP 的约束驱动开发能力封装为可被 AI Agent（如 Claude Code）调用的工具集合，覆盖诊断引擎与适配引擎两大核心场景。本文档重点阐述：
- MCP 服务器架构设计与组件职责
- 工具接口定义与适配器注册机制
- 配置管理与运行参数
- 任务生命周期管理、状态跟踪与纠偏机制
- 请求处理流程与通信协议
- API 接口规范（tahp_execute、tahp_status、tahp_correct 等）
- 错误处理策略与性能优化方案

## 项目结构
MCP 服务器位于 tahp-mcp-server 目录，采用“按功能分层”的组织方式：
- server.py：MCP 服务器入口与工具注册、请求分发
- config.py：配置管理（项目根目录、模块/领域、Playbook 映射、运行参数）
- core/__init__.py：核心工具实现（任务执行、状态查询、纠偏、门禁检查、知识库查询等）
- adapters/__init__.py：工具适配器注册中心，将 tools/ 下现有工具封装为 MCP 工具
- progress/：任务进度追踪与事件发射（tracker、emitter）
- test_server.py：功能验证脚本（演示工具调用与结果解析）

```mermaid
graph TB
subgraph "MCP服务器"
S["server.py<br/>服务器入口/工具注册/请求分发"]
C["config.py<br/>配置管理"]
CORE["core/__init__.py<br/>核心工具实现"]
ADP["adapters/__init__.py<br/>工具适配器注册中心"]
TRK["progress/tracker.py<br/>任务追踪器"]
EMIT["progress/emitter.py<br/>进度事件发射器"]
TEST["test_server.py<br/>功能验证脚本"]
end
S --> CORE
S --> ADP
S --> C
S --> TRK
S --> EMIT
CORE --> TRK
CORE --> EMIT
ADP --> |"动态导入"| TOOLS["tools/<tool>/tool.py"]
TEST --> S
```

图表来源
- [server.py:1-485](file://tahp-mcp-server/server.py#L1-L485)
- [config.py:1-176](file://tahp-mcp-server/config.py#L1-L176)
- [core/__init__.py:1-621](file://tahp-mcp-server/core/__init__.py#L1-L621)
- [adapters/__init__.py:1-239](file://tahp-mcp-server/adapters/__init__.py#L1-L239)
- [progress/tracker.py:1-343](file://tahp-mcp-server/progress/tracker.py#L1-L343)
- [progress/emitter.py:1-194](file://tahp-mcp-server/progress/emitter.py#L1-L194)
- [test_server.py:1-76](file://tahp-mcp-server/test_server.py#L1-L76)

章节来源
- [server.py:1-485](file://tahp-mcp-server/server.py#L1-L485)
- [config.py:1-176](file://tahp-mcp-server/config.py#L1-L176)
- [core/__init__.py:1-621](file://tahp-mcp-server/core/__init__.py#L1-L621)
- [adapters/__init__.py:1-239](file://tahp-mcp-server/adapters/__init__.py#L1-L239)
- [progress/tracker.py:1-343](file://tahp-mcp-server/progress/tracker.py#L1-L343)
- [progress/emitter.py:1-194](file://tahp-mcp-server/progress/emitter.py#L1-L194)
- [test_server.py:1-76](file://tahp-mcp-server/test_server.py#L1-L76)

## 核心组件
- MCP 服务器实例：基于 mcp.server.Server，注册工具清单并处理 call_tool 请求
- 配置管理：MCPServerConfig 提供项目根目录、模块/领域、Playbook 映射、运行参数等
- 核心工具实现：execute_tahp_task、get_tahp_status、correct_tahp_task、run_gate_check、list_tahp_tasks、query_knowledge
- 工具适配器：ToolRegistry 统一封装 tools/ 下工具，提供 call(name, params) 接口
- 进度追踪与事件发射：TaskTracker（线程安全）、ProgressEmitter（MCP 日志通知）

章节来源
- [server.py:93-485](file://tahp-mcp-server/server.py#L93-L485)
- [config.py:36-176](file://tahp-mcp-server/config.py#L36-L176)
- [core/__init__.py:110-621](file://tahp-mcp-server/core/__init__.py#L110-L621)
- [adapters/__init__.py:186-239](file://tahp-mcp-server/adapters/__init__.py#L186-L239)
- [progress/tracker.py:212-343](file://tahp-mcp-server/progress/tracker.py#L212-L343)
- [progress/emitter.py:33-194](file://tahp-mcp-server/progress/emitter.py#L33-L194)

## 架构总览
MCP 服务器通过 STDIO 通道与客户端（如 Claude Code）通信，遵循 MCP 协议的消息格式。服务器启动后注册工具清单，客户端发起工具调用时，服务器根据名称分发至对应处理器，并通过 ProgressEmitter 将进度事件推送至客户端。

```mermaid
sequenceDiagram
participant Client as "客户端(Claude Code)"
participant Server as "MCP服务器(server.py)"
participant Core as "核心工具(core/__init__.py)"
participant Tracker as "任务追踪(progress/tracker.py)"
participant Emitter as "进度发射(progress/emitter.py)"
Client->>Server : "list_tools()"
Server-->>Client : "工具清单"
Client->>Server : "call_tool(tahp_execute, args)"
Server->>Core : "execute_tahp_task(...)"
Core->>Tracker : "创建任务/更新阶段"
Core->>Emitter : "emit_progress(task)"
Emitter-->>Client : "MCP日志通知(进度)"
Core-->>Server : "执行结果"
Server-->>Client : "TextContent(JSON字符串)"
Client->>Server : "call_tool(tahp_status, {task_id})"
Server->>Core : "get_tahp_status(task_id)"
Core-->>Server : "任务详情"
Server-->>Client : "TextContent(JSON字符串)"
```

图表来源
- [server.py:327-448](file://tahp-mcp-server/server.py#L327-L448)
- [core/__init__.py:110-316](file://tahp-mcp-server/core/__init__.py#L110-L316)
- [progress/tracker.py:212-343](file://tahp-mcp-server/progress/tracker.py#L212-L343)
- [progress/emitter.py:47-130](file://tahp-mcp-server/progress/emitter.py#L47-L130)

## 详细组件分析

### 服务器启动与生命周期
- 启动流程：main() 调用 main_async()，通过 stdio_server() 建立 STDIO 通道，运行 MCP Server 并传入 InitializationOptions（server_name、server_version）
- 初始化回调：_on_server_initialized() 设置 ProgressEmitter 的 server 实例，记录可用模块与工具适配器

章节来源
- [server.py:461-485](file://tahp-mcp-server/server.py#L461-L485)
- [server.py:452-459](file://tahp-mcp-server/server.py#L452-L459)

### 工具注册与请求分发
- 工具清单：handle_list_tools() 返回所有 MCP 工具（tahp_execute、tahp_status、tahp_correct、tahp_gate_check、tahp_list_tasks、tahp_query_knowledge、tahp_analyze_log、tahp_code_review、tahp_api_migration）
- 请求分发：_dispatch_tool() 根据 name 将请求路由到对应处理器；对未知工具抛出参数错误
- 参数校验：tahp_execute/tahp_status/tahp_correct/tahp_query_knowledge 等均进行必需参数校验与合法性检查

章节来源
- [server.py:327-448](file://tahp-mcp-server/server.py#L327-L448)

### 核心工具实现（核心业务逻辑）
- execute_tahp_task：加载约束 → 分析设计文档 → 生成修改计划 → 执行 Pipeline → 质量门禁检查；期间通过 TaskTracker 更新阶段与步骤，ProgressEmitter 推送进度
- get_tahp_status：查询任务状态详情（阶段、进度、步骤、纠偏历史、门禁结果等）
- correct_tahp_task：接收纠偏反馈，记录纠偏历史并切换到纠正阶段，返回当前状态
- run_gate_check：对指定任务或模块执行质量门禁（P0/P1/P2），内部复用 scripts/gate_check.py 或简化检查
- list_tahp_tasks：列出任务（可选择包含已完成）
- query_knowledge：查询知识库（支持跨模块检索）

```mermaid
flowchart TD
Start(["开始: execute_tahp_task"]) --> LoadConstraints["加载约束文件"]
LoadConstraints --> AnalyzeDoc["分析设计文档"]
AnalyzeDoc --> GenPlan["生成修改计划"]
GenPlan --> ExecPipeline["执行Pipeline步骤"]
ExecPipeline --> GateCheck["质量门禁检查"]
GateCheck --> Complete["标记完成/失败"]
Complete --> End(["结束"])
```

图表来源
- [core/__init__.py:110-298](file://tahp-mcp-server/core/__init__.py#L110-L298)

章节来源
- [core/__init__.py:110-621](file://tahp-mcp-server/core/__init__.py#L110-L621)

### 工具适配器注册与调用
- ToolRegistry：扫描 tools/ 目录，动态导入各工具模块的 tool.py，封装为 ToolAdapter；若工具缺失则提供降级实现
- 适配器接口：ToolAdapter(handler) 统一暴露 call(params) -> dict
- 服务器侧调用：_dispatch_tool() 中对非核心工具（如 android_log_analyzer、code_review_checker、api_migration_db）通过 ToolRegistry.call() 调用

```mermaid
classDiagram
class ToolRegistry {
-config : MCPServerConfig
-tools : dict
+get(name)
+list_tools()
+call(name, params)
+to_dict()
}
class ToolAdapter {
+name : str
+description : str
+handler(params)
+to_mcp_tool_schema()
}
ToolRegistry --> ToolAdapter : "管理/注册"
```

图表来源
- [adapters/__init__.py:186-239](file://tahp-mcp-server/adapters/__init__.py#L186-L239)

章节来源
- [adapters/__init__.py:1-239](file://tahp-mcp-server/adapters/__init__.py#L1-L239)

### 任务生命周期与状态跟踪
- TaskPhase：pending → loading_constraints → analyzing_document → generating_plan → executing_pipeline → running_gate_check → completed/failed/cancelled/correcting
- TaskTracker：线程安全的任务存储与更新，支持清理旧任务、监听器回调
- ProgressEmitter：将阶段与步骤进度通过 MCP 日志消息推送给客户端，支持纠偏事件

```mermaid
stateDiagram-v2
[*] --> 等待执行
等待执行 --> 正在加载约束文件 : "开始"
正在加载约束文件 --> 正在分析设计文档
正在分析设计文档 --> 正在生成修改计划
正在生成修改计划 --> 正在执行Pipeline
正在执行Pipeline --> 正在运行质量门禁
正在运行质量门禁 --> 执行完成 : "成功"
正在运行质量门禁 --> 执行失败 : "失败"
正在运行质量门禁 --> 等待纠偏输入 : "收到纠偏"
等待纠偏输入 --> 正在执行Pipeline : "纠正后继续"
执行完成 --> [*]
执行失败 --> [*]
等待纠偏输入 --> [*]
```

图表来源
- [progress/tracker.py:18-30](file://tahp-mcp-server/progress/tracker.py#L18-L30)
- [progress/emitter.py:47-130](file://tahp-mcp-server/progress/emitter.py#L47-L130)

章节来源
- [progress/tracker.py:1-343](file://tahp-mcp-server/progress/tracker.py#L1-L343)
- [progress/emitter.py:1-194](file://tahp-mcp-server/progress/emitter.py#L1-L194)

### API 接口文档

#### tahp_execute
- 功能：按照设计文档执行 TAHP 开发任务，返回任务ID与执行结果
- 输入参数
  - document_path: string（必填，设计文档路径）
  - module: string（必填，telephony、kernel-driver、power-mgmt）
  - domain: string（必填，bug_analysis、code_adaptation、version_adaptation、carrier_porting）
  - constraints_extra: string[]（可选，额外约束文件路径列表）
- 输出
  - task_id: string
  - status: string（completed/failed）
  - modification_plan: object（包含任务元信息、约束摘要、生成时间等）
  - pipeline_results: array（Pipeline 步骤执行结果）
  - gate_result: object（门禁检查结果）
  - safety_red_lines: string[]
  - constraints_loaded: string[]
  - completed_at: string（ISO 8601）

章节来源
- [server.py:103-135](file://tahp-mcp-server/server.py#L103-L135)
- [core/__init__.py:110-298](file://tahp-mcp-server/core/__init__.py#L110-L298)

#### tahp_status
- 功能：查询任务执行状态
- 输入参数
  - task_id: string（必填）
- 输出
  - task_id: string
  - module: string
  - domain: string
  - phase: string（TaskPhase）
  - phase_label: string（中文标签）
  - progress: number（0.0-1.0）
  - status: string（MCP兼容状态）
  - status_message: string
  - steps: array（步骤详情）
  - corrections: array（纠偏历史）
  - is_terminal: boolean
  - error: string
  - result: object
  - gate_result: object

章节来源
- [server.py:137-153](file://tahp-mcp-server/server.py#L137-L153)
- [core/__init__.py:300-316](file://tahp-mcp-server/core/__init__.py#L300-L316)
- [progress/tracker.py:169-209](file://tahp-mcp-server/progress/tracker.py#L169-L209)

#### tahp_correct
- 功能：对正在执行的任务进行纠偏
- 输入参数
  - task_id: string（必填）
  - feedback: string（必填）
- 输出
  - task_id: string
  - status: string（correcting/error/not_found）
  - feedback: string
  - current_phase: string
  - corrections_count: number

章节来源
- [server.py:155-176](file://tahp-mcp-server/server.py#L155-L176)
- [core/__init__.py:318-363](file://tahp-mcp-server/core/__init__.py#L318-L363)
- [progress/emitter.py:112-129](file://tahp-mcp-server/progress/emitter.py#L112-L129)

#### tahp_gate_check
- 功能：对指定任务或模块执行质量门禁检查（P0/P1/P2）
- 输入参数
  - task_id: string（可选，与 module 二选一）
  - module: string（可选，与 task_id 二选一，telephony、kernel-driver、power-mgmt）
  - level: string（可选，默认 all，取值 P0/P1/P2/all）
- 输出
  - module: string
  - result: string（PASS/BLOCK/WARNING/ERROR）
  - checks: array（检查项详情）
  - total_checks: number
  - passed_checks: number
  - failed_checks: number

章节来源
- [server.py:178-204](file://tahp-mcp-server/server.py#L178-L204)
- [core/__init__.py:366-459](file://tahp-mcp-server/core/__init__.py#L366-L459)
- [gate_check.py:36-93](file://scripts/gate_check.py#L36-L93)

#### tahp_list_tasks
- 功能：列出所有任务
- 输入参数
  - include_completed: boolean（可选，默认 true）
- 输出
  - tasks: array（任务详情数组）
  - total: number

章节来源
- [server.py:206-219](file://tahp-mcp-server/server.py#L206-L219)
- [core/__init__.py:546-556](file://tahp-mcp-server/core/__init__.py#L546-L556)

#### tahp_query_knowledge
- 功能：语义查询知识库
- 输入参数
  - query: string（必填）
  - module: string（可选）
  - cross_module: boolean（可选，默认 false）
  - top_k: integer（可选，默认 5）
- 输出
  - query: string
  - module: string
  - cross_module: boolean
  - results: array（知识条目预览）
  - total: number
  - error: string（可选）

章节来源
- [server.py:221-251](file://tahp-mcp-server/server.py#L221-L251)
- [core/__init__.py:558-621](file://tahp-mcp-server/core/__init__.py#L558-L621)
- [config.yaml (knowledge-base):1-36](file://knowledge-base/config.yaml#L1-L36)

#### tahp_analyze_log
- 功能：解析 Android 日志（logcat/ril/atcmd），提取事件与错误
- 输入参数
  - log_content: string（必填）
  - log_type: string（可选，默认 logcat，取值 logcat/ril/atcmd）
  - filters: string[]（可选，过滤关键词）
- 输出
  - events: array（事件列表）
  - errors: array（错误列表）
  - statistics: object（统计信息）

章节来源
- [server.py:253-277](file://tahp-mcp-server/server.py#L253-L277)
- [tool.py (android-log-analyzer):1-50](file://tools/android-log-analyzer/tool.py#L1-L50)

#### tahp_code_review
- 功能：自动化代码审查，检查 P0/P1/P2 规则违规
- 输入参数
  - patch_content: string（必填）
  - check_level: string（可选，默认 P0，取值 P0/P1/P2）
- 输出
  - result: string（pass/warning/fail）
  - violations: array（违规详情）
  - score: number
  - critical_count: number
  - warning_count: number

章节来源
- [server.py:279-298](file://tahp-mcp-server/server.py#L279-L298)
- [tool.py (code-review-checker):1-33](file://tools/code-review-checker/tool.py#L1-L33)

#### tahp_api_migration
- 功能：查询 API 迁移规则库（list/search/add）
- 输入参数
  - action: string（可选，默认 list，取值 list/search/add）
  - module: string（可选，list 时使用）
  - old_api: string（可选，search 时使用）
- 输出
  - rules: array（规则列表）
  - total: number

章节来源
- [server.py:300-322](file://tahp-mcp-server/server.py#L300-L322)
- [adapters/__init__.py:101-119](file://tahp-mcp-server/adapters/__init__.py#L101-L119)

### 服务器与客户端通信协议
- 传输：STDIO（stdio_server），遵循 MCP 协议
- 工具清单：list_tools 返回 MCP Tool 对象（name/description/inputSchema）
- 工具调用：call_tool 接收 name 与 arguments，返回 TextContent（JSON 字符串）
- 进度推送：ProgressEmitter 通过 server.request_context.session.send_log_message 发送 info/warning 级日志，客户端可实时显示进度

章节来源
- [server.py:327-367](file://tahp-mcp-server/server.py#L327-L367)
- [progress/emitter.py:47-130](file://tahp-mcp-server/progress/emitter.py#L47-L130)

### 错误处理策略
- 参数校验：对必填字段缺失与非法值抛出 ValueError，并返回 JSON 错误信息
- 内部异常：捕获 Exception 并返回 Internal error JSON
- 任务状态：TaskTracker.fail_task 标记失败并更新状态消息
- 工具适配器：ToolRegistry.call 捕获异常并返回错误对象

章节来源
- [server.py:361-367](file://tahp-mcp-server/server.py#L361-L367)
- [core/__init__.py:289-297](file://tahp-mcp-server/core/__init__.py#L289-L297)
- [adapters/__init__.py:226-234](file://tahp-mcp-server/adapters/__init__.py#L226-L234)

## 依赖分析
- 外部依赖：mcp、pyyaml、click、rich
- 内部依赖：config、progress.tracker、progress.emitter、core、adapters
- 工具依赖：tools/<tool>/tool.py（动态导入），scripts/gate_check.py（门禁检查）

```mermaid
graph TB
PY["pyproject.toml<br/>依赖声明"] --> MCP["mcp>=1.9.0"]
PY --> YAML["pyyaml>=6.0"]
PY --> CLICK["click>=8.1"]
PY --> RICH["rich>=13.0"]
SRV["server.py"] --> CFG["config.py"]
SRV --> CORE["core/__init__.py"]
SRV --> ADP["adapters/__init__.py"]
SRV --> TRK["progress/tracker.py"]
SRV --> EMIT["progress/emitter.py"]
CORE --> GC["scripts/gate_check.py"]
ADP --> TOOL1["tools/android-log-analyzer/tool.py"]
ADP --> TOOL2["tools/code-review-checker/tool.py"]
```

图表来源
- [pyproject.toml:1-19](file://tahp-mcp-server/pyproject.toml#L1-L19)
- [server.py:61-82](file://tahp-mcp-server/server.py#L61-L82)
- [adapters/__init__.py:42-65](file://tahp-mcp-server/adapters/__init__.py#L42-L65)

章节来源
- [pyproject.toml:1-19](file://tahp-mcp-server/pyproject.toml#L1-L19)
- [requirements.txt:1-9](file://requirements.txt#L1-L9)

## 性能考虑
- 并发控制：MCPServerConfig.max_concurrent_tasks 控制最大并发任务数
- 超时控制：MCPServerConfig.task_timeout_sec 限制任务执行时间
- 进度映射：ProgressEmitter 使用阶段到进度的映射，确保整体进度平滑推进
- 结果截断：handle_call_tool 对过长结果进行截断并提示使用 tahp_status 查看详情
- 任务清理：TaskTracker 在达到上限时清理最早完成的任务，避免内存膨胀

章节来源
- [config.py:52-56](file://tahp-mcp-server/config.py#L52-L56)
- [progress/emitter.py:18-30](file://tahp-mcp-server/progress/emitter.py#L18-L30)
- [server.py:355-358](file://tahp-mcp-server/server.py#L355-L358)
- [progress/tracker.py:318-331](file://tahp-mcp-server/progress/tracker.py#L318-L331)

## 故障排除指南
- 工具未找到：检查 ToolRegistry 是否正确加载对应工具模块；确认 tools/<tool>/tool.py 存在并包含相应函数
- 任务状态异常：使用 tahp_status 查询 task_id，查看 phase、status、error 字段
- 门禁失败：检查 constraints/ 模块目录是否存在约束文件、是否包含 safety_red_lines、是否存在硬编码密钥
- 纠偏无效：确认任务未处于终态（completed/failed/cancelled），纠偏仅在 correcting 阶段有效

章节来源
- [adapters/__init__.py:218-234](file://tahp-mcp-server/adapters/__init__.py#L218-L234)
- [core/__init__.py:300-363](file://tahp-mcp-server/core/__init__.py#L300-L363)
- [gate_check.py:99-156](file://scripts/gate_check.py#L99-L156)

## 结论
MCP 服务器系统通过清晰的分层架构与标准化的 MCP 协议，将 TAHP 的约束驱动能力以工具形式暴露给 AI Agent。核心特性包括：
- 完整的工具清单与参数校验
- 任务生命周期管理与实时进度推送
- 纠偏机制与质量门禁检查
- 可扩展的工具适配器注册中心
- 稳健的错误处理与性能保障

该系统为诊断引擎与适配引擎提供了统一的执行与编排平台，支撑 TAHP 平台在双引擎场景下的自动化与智能化演进。

## 附录
- 系统架构概览与四域约束体系参见 [system-overview.md:1-420](file://docs/architecture/system-overview.md#L1-L420)
- 工具适配器与知识库配置参考：
  - [adapters/__init__.py:1-239](file://tahp-mcp-server/adapters/__init__.py#L1-L239)
  - [config.yaml (knowledge-base):1-36](file://knowledge-base/config.yaml#L1-L36)