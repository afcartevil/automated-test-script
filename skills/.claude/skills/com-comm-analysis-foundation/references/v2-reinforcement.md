# V2 Reinforcement Reference

## 1. 目的

本文件用于记录雏鹰培训资料的 V2 补强结果与后续锁定批次，避免再次出现“先大范围预读、后长时间不落盘”的失控链路。

执行原则只有一句话：**一批只补一个很明确的增量，不做跨主题预读。**

---

## 2. 本轮已吸收的 V2 增量

## 2.1 Call 上层来去电链路补强（已拆分沉淀到 `call-framework-analysis.md`）

本轮新增价值：

- 把拨号入口前的 **Dialer → Telecom** 链路补细
- 把来电通知后的 **PstnIncomingCallNotifier → TelecomManager → InCallService** 链路补细
- 让 Call 专题在“上层入口未进 Telecom”“来电已到但 UI 没拉起”这两类问题上的断点判断更准
- 在结构改造后，这部分内容不再混在 Call 总览页，而是独立沉淀到上层专题文件中

已沉淀位置：

- `references/call-framework-analysis.md` -> `4. V2 补强：雏鹰资料补充的上层链路观察点`

## 2.2 Network：PLMN 选择流程补强（已并入 `network-analysis.md`）

本轮新增价值：

- 补清了 `RPLMN / EPLMN / EHPLMN / HPLMN / VPLMN / FPLMN` 等概念在搜网与驻网行为中的含义
- 补细了自动 / 手动搜网下的 PLMN 选择策略，以及为什么手动模式不会随意自动回切
- 补充了 `FPLMN`、forbidden LA 与搜网时延因素（双卡共享 RF、PS 业务挂起）的实战判断点

已沉淀位置：

- `references/network-analysis.md` -> `5.5 V2 补强：PLMN 选择流程与搜网时延观察点`

---

## 3. 已锁定的下一批高价值 V2 文档

下面这些文档已确认高价值，但**尚未抽取正文内容**；后续必须按单主题小批次处理。

### 3.1 Network 补强候选

1. `22届雏鹰培训/APN介绍-张献中.pptx`
   - 预期补强：APN 分类、配置来源、数据业务承载差异


### 3.2 SIM 补强候选

1. `22届雏鹰培训/SIM卡识卡流程--通信开发部谷昂20221017.pptx`
   - 预期补强：检卡时序、上电/复位/ATR 细节、卡槽分层分析
2. `21届雏鹰培训/第二阶段/SIM/SIM_debug_SOP(5029096788).pdf`
   - 预期补强：SIM debug 案例化排查

### 3.3 Stability 补强候选

1. `22届雏鹰培训/Modem调试SOP_朱鹏博.pdf`
   - 预期补强：dump 抓取、Modem 调试入口、平台协作材料
2. `22届雏鹰培训/展锐平台Modem Crash处理流程-刘三灵.pdf`
   - 预期补强：SPRD crash 分析与材料准备

### 3.4 Call / IMS 补强候选

1. `21届雏鹰培训/第二阶段/CS-IMS通话业务介绍-李克春-v1.0.pptx`
   - 预期补强：CS/IMS 域切换、业务流程和典型失败断点
2. `21届雏鹰培训/第二阶段/IMS业务流程简述.pptx`
   - 预期补强：IMS 注册、会话建立、VoLTE / VoWiFi 链路

---

## 4. 后续批次建议

为了避免再次卡住，后续 V2 建议严格按下面方式推进：

1. 一次只处理一个主题
2. 一次只抽取 1 份主文档，必要时最多补 1 份同主题辅助文档
3. 抽完就立刻写回：
   - 已有专题：直接补到对应 `references/*.md`
   - 新增横向知识：写到新的独立 references 文件
4. 每批结束必须能看到明确文件落盘

建议顺序：

1. Network：`APN介绍`
2. SIM：`SIM卡识卡流程`
3. Stability：`Modem调试SOP`
4. Call / IMS：`CS-IMS通话业务介绍`


---

## 5. 当前结论

- V1 主体知识层已经成形
- V2 已完成两批可控补强：Call 上层链路、Network 的 PLMN 选择流程
- 其余高价值雏鹰文档已完成锁定，但应继续按“小批次逐主题落盘”推进，而不是一次性全读全写

