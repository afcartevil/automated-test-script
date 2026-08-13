# Android Communication Overseas Support Skill

## 目标
为海外印度研发站点构建一个面向售后问题分析的业务 Skill，帮助新团队基于 SOP 和培训资料快速完成问题归类、信息收集、初步分析、升级判断与结果输出。

## 业务背景
- 主团队：Android 通信研发团队
- 使用场景：海外印度站点培训与日常售后问题分析
- 初期目标：让海外团队能够根据 SOP 文档快速上手处理与分析售后问题
- 后续目标：在海外释放文档基础上，持续吸收雏鹰培训文档中的专业知识，逐步完善 Skill 的知识深度与严谨性

## 新的实施策略

### 设计原则
1. **海外文档优先**：先以 `海外研发培训文档/`（培训资料库内相对路径）的 8 个对外培训 PDF 作为 V1 基线，抽取文本归档于 `source-text/overseas/`。
2. **雏鹰资料补强**：再从 21/22 届雏鹰培训材料中筛选与 Call / Network / SIM / Stability / Modem / 日志抓取 / 典型案例相关的 PDF、PPTX、PPT、DOCX、TXT 进行专业增强。
3. **只处理可读文件**：当前纳入范围的文件类型为 `pdf / pptx / ppt / docx / txt`；明确排除 `mp4 / db`。
4. **边读边沉淀**：不依赖对话上下文长期记忆；每处理一批资料，立即沉淀为结构化知识文件。
5. **双层知识结构**：
   - `SKILL.md`：角色、触发条件、处理流程、边界、输出规范
   - `references/`：按专题拆分的知识文档、术语表、案例索引、升级规则
6. **持续演进**：Skill 设计为可迭代版本，便于后续新增海外培训文档后继续补齐。

## 分阶段执行方案

### Phase 1：文档地图与优先级收敛（已启动）
- 盘点所有可读文档
- 区分海外发布文档与雏鹰内部沉淀文档
- 形成按主题域分组的候选资料清单

### Phase 2：海外培训文档抽取（V1 基线知识）
处理对象：8 个海外培训 PDF
- 框架侧 Call 问题分析
- 协议侧 Call 问题分析
- 网络问题分析
- SIM 卡问题分析（上层/Modem）
- 稳定性问题分析（Modem）

产出：
- 问题分类树
- 必要输入信息清单
- 逐步分析 SOP
- 根因定位逻辑
- 结论输出模板

### Phase 3：雏鹰专业资料补强（V2 深化）
处理对象：从 21/22 届资料中筛选出的高价值文档
- 通话流程与 IMS 业务流程
- SIM 卡识卡 / 检卡 / 协议知识
- Modem Crash / Modem 调试 / Log 抓取
- 数据业务 / 网络注册 / APN / PLMN
- 真实问题案例与分析报告

产出：
- 更细的判断分支
- 常见误判与排查陷阱
- 真实案例映射
- 上下层联动分析知识

### Phase 4：Skill 打包
输出结构：
- `SKILL.md`
- `references/call-analysis.md`
- `references/network-analysis.md`
- `references/sim-analysis.md`
- `references/stability-analysis.md`
- `references/log-collection.md`
- `references/case-studies.md`
- `references/terminology-glossary.md`
- `references/escalation-rules.md`
- `references/source-inventory.md`

### Phase 5：验证与迭代
- 用典型售后问题做场景验证
- 检查是否能正确归类、正确收集信息、正确引用知识
- 补齐遗漏知识点和输出边界

## 风险与控制
- 风险：海外文档可能覆盖不全，导致分析链条断裂
  - 控制：用雏鹰资料补充专业深度
- 风险：资料很多，单次处理可能遗漏
  - 控制：按主题域分批抽取并写入文件
- 风险：不同讲师术语不统一
  - 控制：建立统一术语表与别名映射
- 风险：对外培训文档偏简略，无法支撑复杂案例
  - 控制：引入内部案例文档与日志抓取 SOP 做增强

## 当前状态
- 已完成：初步目录扫描与可读文件范围确认
- 进行中：梳理优先处理的海外 PDF 与雏鹰补强资料清单
- 下一步：开始抽取海外 8 个 PDF 的文本与结构化知识
