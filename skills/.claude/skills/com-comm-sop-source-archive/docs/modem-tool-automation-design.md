# Modem 专业工具自动化封装设计文档

## 1. 文档目标

本文档用于定型“通信/Modem 专业平台工具自动化解析”的首版方案，重点回答四件事：

1. 为什么这类解析不能简单理解为“读文本日志”
2. 为什么当前更适合封装平台工具，而不是一开始就替代厂商工具
3. 首版自动化系统应该拆成哪些模块、接口和结果结构
4. 如何把自动解析结果接入当前 Skill 的输出规范与协作流程

这份设计文档对应的目标不是一次性做完所有平台，而是先建立一条 **可执行、可扩展、可降级** 的基础链路。

---

## 2. 背景与问题定义

从当前 `stability-analysis.md`、`log-collection.md` 与既有培训资料可以确认：Modem 相关问题分析通常不只依赖 `main_log / radio_log / system_log` 这类文本日志，还会涉及：

- `modem dump`
- `minidump`
- `_EE_INVALID`
- `__exp_main.txt`
- `DbgInfo`
- `ELF / AXF`
- 平台专有解析工具（例如 `logel`、`TNE` 风格工具）

这意味着自动化系统需要同时面对两类输入：

1. **可直接读的文本/半结构化日志**：可通过规则和脚本直接提取关键字段
2. **需要专有工具解码的二进制/专有格式日志**：必须依赖平台解析器、符号文件和版本匹配能力

因此，真正要解决的问题不是“如何完全绕开工具”，而是：

> 如何把人工打开专业工具的动作，重构成一条由程序调度、自动收集结果、统一输出判断的解析流水线。

---

## 3. 设计原则

### 3.1 先封装，再替代

首版不追求直接替代厂商工具，而是优先建设：

- 工具适配层
- 批处理调度层
- 统一结果模型
- 自动降级输出层

原因很现实：

- 专有 dump / 协议日志格式未必公开
- 缺少符号文件时很难做到可靠深度解码
- 同类工具通常已经包含平台多年沉淀的解析规则
- 先封装现有工具，能更快把人工流程转成自动流程

### 3.2 自动化必须允许降级

系统不应为了“看起来全自动”而假装知道根因。若工具缺失、符号文件不匹配或证据不足，系统必须输出：

- 当前定位层
- 当前结论
- 缺失证据
- 首选下一排查点
- 承接方与交接材料

这必须与当前 `SKILL.md` 中已经确定的降级规范保持一致。

### 3.3 工具执行与业务分析解耦

要把“调用工具”与“做业务判断”拆开：

- **工具层** 只负责执行与采集
- **标准化层** 只负责整理结构化结果
- **规则层** 只负责根据知识规则生成判断
- **输出层** 只负责生成人可读的交接内容

这样后续替换工具、扩新平台、接 LLM 总结时都不会互相污染。

---

## 4. 总体架构

首版建议采用五层结构。

### 4.1 输入接入层

职责：

- 接收日志包或任务描述
- 解压输入文件
- 识别平台（MTK / SPRD / Qcom）
- 识别问题域（Call / Network / SIM / Stability）
- 标记是否包含 dump、符号文件、摘要文件

典型输入包括：

- `main_log`
- `radio_log`
- `system_log`
- `modem log`
- `modem dump`
- `__exp_main.txt`
- `_EE_INVALID`
- `DbgInfo / ELF / AXF`

### 4.2 工具适配层

职责：

- 将不同平台工具封装为统一接口
- 判断当前任务是否适合该 adapter
- 生成工具调用计划
- 在 dry-run / real-run 模式下执行
- 回收工具输出文件和标准输出

首版建议先保留以下 adapter 位置：

- `MtkLogelAdapter`
- `TneAdapter`（后续）
- `SprdCrashAdapter`（后续）
- `QcomDiagAdapter`（后续）

### 4.3 批处理调度层

职责：

- 创建任务上下文与隔离工作目录
- 选择适配器
- 控制超时、失败重试、执行日志
- 汇总工具原始结果

这一层是“人工操作工具”与“自动化流水线”之间的桥。

### 4.4 标准化结果层

职责：

- 统一不同工具返回结构
- 将原始字段映射为 `ParseResult`
- 记录证据、缺失项、下一步建议

无论底层来自 `logel`、`TNE` 还是文本日志解析，最终都应汇聚成同一套 JSON 模型。

### 4.5 Skill 输出层

职责：

- 将标准化结果转成 Markdown/JSON 报告
- 对齐 `SKILL.md` 中的输出与降级规范
- 生成交接建议、承接方和材料清单

---

## 5. 目录与模块设计

首版骨架建议放在工作区 `tools/` 下，形成独立的 Python 包：

```text
tools/
  modem_auto_parser/
    __init__.py
    models.py
    registry.py
    orchestrator.py
    reporter.py
    cli.py
    adapters/
      __init__.py
      base.py
      mtk_logel.py
    README.md
```

### 5.1 `models.py`

定义核心数据结构：

- `ParseJob`
  - 任务 ID
  - 平台
  - 问题域
  - 输入根目录
  - 文件列表
  - 元信息（版本号、工单号、时间点等）

- `ParseResult`
  - `tool_name`
  - `tool_status`
  - `evidence`
  - `current_conclusion`
  - `missing_evidence`
  - `primary_next_step`
  - `next_owner`
  - `handover_materials`

### 5.2 `adapters/base.py`

定义统一接口：

- `can_handle(job)`：是否能处理该任务
- `build_command(job)`：生成调用计划
- `run(job)`：执行工具或返回降级结果

### 5.3 `adapters/mtk_logel.py`

首版只做 MTK/logel 风格占位实现：

- 有工具路径时，拼接命令计划
- 没有工具路径时，返回 degraded 结果
- 输出缺失项中明确标记 `tool_path`

### 5.4 `registry.py`

维护 adapter 列表并负责按任务选择适配器。

### 5.5 `orchestrator.py`

串联：

- 适配器选择
- 任务执行
- 结果标准化

### 5.6 `reporter.py`

把 `ParseResult` 输出为 Markdown，结构对齐业务规范：

- `Current Conclusion`
- `Evidence`
- `Missing Evidence`
- `Primary Next Step`
- `Handover`

### 5.7 `cli.py`

提供最小命令行入口：

- 读取 JSON 任务文件
- 触发执行
- 输出 JSON / Markdown

---

## 6. 统一结果模型

建议统一输出如下结构：

```json
{
  "job_id": "job-001",
  "platform": "mtk",
  "domain": "stability",
  "tool_name": "logel",
  "tool_status": "degraded",
  "evidence": {
    "baseband_version": "MOLY.LR12A.R3",
    "input_files": ["crash.dmp", "__exp_main.txt"]
  },
  "current_conclusion": "已识别为 MTK 稳定性场景，首版骨架已选中 logel 解析路径，但当前未配置工具路径，暂无法完成真实 dump 解码。",
  "missing_evidence": [
    "tool_path",
    "matched_dbginfo"
  ],
  "primary_next_step": "优先补齐 logel 工具路径与匹配版本的 DbgInfo/AXF。",
  "next_owner": "Modem平台工具维护方",
  "handover_materials": [
    "问题时间点",
    "原始 dump 包",
    "baseband 版本",
    "__exp_main.txt"
  ]
}
```

这套模型的意义是：

- 上层不再关心底层到底用了什么工具
- 后续可直接接规则引擎或 LLM
- 可以稳定输出缺失项、结论和交接材料

---

## 7. 执行流程设计

首版任务流建议如下：

```text
日志包输入
→ 输入接入层识别平台/问题域
→ Adapter Registry 选择可处理工具
→ Adapter 生成调用计划
→ 如果工具条件不满足，则直接降级输出
→ 如果条件满足，则执行工具并采集结果
→ Orchestrator 标准化结果
→ Reporter 输出 Markdown/JSON
```

### 7.1 为什么要支持 dry-run

因为在当前工作区里：

- 未必有真实专有工具
- 未必有 license
- 未必有匹配版本符号文件

如果没有 dry-run，骨架阶段根本无法推进。支持 dry-run 后，至少能先把：

- 任务识别
- adapter 选择
- 缺失项提示
- 报告输出

这些能力先跑通。

---

## 8. 错误处理与降级策略

### 8.1 工具路径缺失

输出：

- 当前结论：已识别需要专有工具，但工具路径未配置
- 缺失证据：`tool_path`
- 首选下一步：补配置
- 承接方：工具维护方 / 平台支持方

### 8.2 符号文件缺失

输出：

- 当前结论：可定位到工具解析层，但无法做可靠深度解码
- 缺失证据：`matched_dbginfo` / `matched_axf`
- 首选下一步：补齐匹配版本符号文件
- 承接方：平台构建/版本维护方

### 8.3 平台不可识别

输出：

- 当前结论：仅能定位到“待识别平台日志包”
- 缺失证据：平台标识、版本信息
- 首选下一步：补齐日志目录结构与版本号
- 承接方：日志提供方

### 8.4 结果不足以下最终结论

必须对齐 Skill 规范输出：

1. 当前只能定位到哪一层
2. 还缺哪些证据
3. 下一步日志或对比动作
4. 当前结论与首选下一排查点
5. 若需他人承接，写清角色/团队与交接材料

---

## 9. 首版实现范围

### 9.1 本轮落地内容

本轮骨架只承诺这些内容：

- 设计文档落盘
- Python 包骨架建立
- MTK/logel 占位 adapter
- 统一结果模型
- Markdown 报告输出
- 最小 CLI
- 最小单元测试

### 9.2 本轮明确不做

本轮不包含：

- 真实厂商工具集成
- GUI 自动化
- 符号文件自动下载
- 多平台并发调度服务
- LLM 自动归因增强

这些都属于下一阶段工作，先别把锅做成火箭发动机。

---

## 10. 后续扩展路线

建议按下面顺序推进：

1. **先接 MTK/logel 真工具路径**
   - 配置工具路径
   - 验证真实命令行调用
   - 接回结果文件采集

2. **再补符号文件管理**
   - 根据版本号匹配 `DbgInfo / AXF / ELF`
   - 解决真实解析所需依赖问题

3. **再扩到 TNE / SPRD / Qcom**
   - 每个平台一个 adapter
   - 统一输出，不复制业务规则

4. **接规则引擎**
   - 将 `stability-analysis.md` 中的判断逻辑代码化
   - 输出更接近业务分析的判断结果

5. **最后再接 Skill/LLM 输出增强**
   - 自动生成交接文案
   - 自动引用专题规则
   - 输出更贴近售后支持场景

---

## 11. 验收标准

首版完成后，至少要满足：

- 能通过任务 JSON 创建 `ParseJob`
- 能为 MTK/dmp 场景选中 `MtkLogelAdapter`
- 在未配置工具时能稳定输出 degraded 结果
- 能生成对齐 Skill 规范的 Markdown 报告
- 通过最小单元测试
- 命令行帮助可正常输出

如果这几项都过了，说明“从人工点工具到自动解析流水线”的底座已经搭起来了。后面扩平台、接真工具、接知识规则，都是在这个底座上加楼层，不是重打地基。
