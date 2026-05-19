# TAHP 评估与质量门禁规范

> **版本**: v2.0 | **日期**: 2026-05-19 | **适用范围**: 所有Skill评估、代码质量检查、系统效果度量
> **状态**: Approved
> **v2.0 变更**: 适配知识库体系 — 新增知识库健康度评估维度，执行结果自动沉淀触发知识库质量检查

---

## 1. 评估体系总览

### 1.1 三层评估架构

```
┌────────────────────────────────────────────────────────┐
│                    L5: 评估与观测层                      │
│                                                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │ Skill质量评估 │  │ 代码质量门禁 │  │ 系统效果度量 │    │
│  │              │  │              │  │              │    │
│  │ 测试集准确率 │  │ 编译/Lint    │  │ 人力节省     │    │
│  │ EvoSkill分数 │  │ 风格/安全    │  │ Bug分析效率  │    │
│  │ 跨任务迁移   │  │ 回归测试     │  │ 适配成功率   │    │
│  └─────────────┘  └─────────────┘  └─────────────┘    │
│         ↑                ↑                ↑             │
│    skills/         constraints/     reports/metrics/    │
│         ↑                ↑                ↑             │
│    knowledge-base/   ← 知识底座（v3.0 新增）              │
└────────────────────────────────────────────────────────┘
```

### 1.2 知识库健康度评估 (v3.0 新增)

知识库是整个系统的知识底座，需要定期评估其健康度：

| 维度 | 指标 | 目标值 | 检查方式 |
|------|------|--------|---------|
| **覆盖率** | 已接入模块的知识条目数 | ≥20条/模块 | knowledge_stats.py |
| **增长性** | 本周新增知识条目 vs 上周 | 正增长 | Git log + SQLite KB |
| **利用率** | 知识条目被引用(检索命中)的比例 | ≥60% | SQLite KB query log |
| **质量** | 高置信度(≥0.8)条目占比 | ≥70% | 置信度统计 |
| **时效性** | 最近30天有更新的条目占比 | ≥30% | updated_at 字段 |
| **沉淀率** | 执行任务后自动沉淀成功率 | ≥80% | 沉淀触发日志 |

---

## 2. Skill质量评估

### 2.1 评估指标体系

| 指标 | 权重 | 计算方式 | 目标值 | 说明 |
|------|------|---------|--------|------|
| **准确率 (Accuracy)** | 40% | 正确案例数 / 总案例数 | ≥ 85% | 在测试集上的正确率 |
| **完整性 (Completeness)** | 20% | 必填字段填写率 | 100% | 产出报告的必填维度覆盖率 |
| **一致性 (Consistency)** | 15% | 相同输入产出一致率 | ≥ 90% | 相同输入多次执行的结果稳定性 |
| **时效性 (Efficiency)** | 15% | 平均完成时间 | ≤ 5min/案例 | 单个案例平均处理时间 |
| **可解释性 (Explainability)** | 10% | 证据引用率 | ≥ 80% | 分析结论有日志/代码证据支撑的比例 |

### 2.2 测试集管理规范

#### 数据集结构

```
eval-data/
├── {module}/
│   ├── train/                   # 训练/进化集（60%）
│   │   ├── case-001.yaml
│   │   ├── case-001-input.txt   # 原始日志/输入
│   │   └── case-001-expected.json
│   ├── val/                     # 验证集（20%）
│   │   └── ...
│   └── test/                    # 测试集（20%）
│       └── ...
└── shared/                      # 跨模块共享案例
    └── ...
```

#### 数据集质量要求

| 要求 | 标准 | 检查方式 |
|------|------|---------|
| 最小案例数 | 每模块 ≥ 15个（train 9 / val 3 / test 3） | 计数检查 |
| 案例真实性 | 必须来自真实Bug/问题，不允许虚构 | Owner审核确认 |
| 输入完整性 | 每个案例包含完整日志和设备信息 | 字段检查 |
| 标注一致性 | 同一Owner标注的所有案例标准一致 | 交叉验证 |
| 时间分布 | 案例覆盖近6个月的不同版本 | 时间戳检查 |
| 难度分布 | easy:medium:hard ≈ 3:5:2 | 难度标签统计 |

#### 难度分级标准

```yaml
difficulty:
  easy:
    description: "单模块、单层、明显日志错误"
    example: "logcat直接显示NullPointerException"
    ratio: "30%"

  medium:
    description: "跨层分析、需推导、日志不直接指向根因"
    example: "RILJ层超时导致Framework层回调失败"
    ratio: "50%"

  hard:
    description: "跨模块、间歇性、需综合多源信息"
    example: "特定网络条件下VoLTE切换失败，涉及IMS+RILC+Modem"
    ratio: "20%"
```

### 2.3 评估流程

```
自动评估流程:

1. 加载测试集 (test/)
   └─ 读取每个案例的 input 和 expected

2. 执行Skill
   └─ 对每个测试案例运行当前Skill

3. 对比评估
   ├─ 准确率: root_cause_layer 匹配
   ├─ 完整性: required_outputs 全部填写
   ├─ 严重程度: severity 与期望一致（允许偏差1级）
   └─ 修复方向: fix_type 与期望一致

4. 生成评估报告
   ├─ 总分计算（加权平均）
   ├─ 分项得分
   ├─ 失败案例分析
   └─ 改进建议

5. 质量门禁判定
   ├─ 总分 ≥ 80 → PASS
   ├─ 总分 60-79 → WARNING（允许上线但需改进）
   └─ 总分 < 60 → FAIL（不允许上线）
```

---

## 3. 代码质量门禁

### 3.1 门禁检查项

#### P0 - 必须通过（任一失败即BLOCK）

| # | 检查项 | 工具 | 标准 | 超标处理 |
|---|--------|------|------|---------|
| 1 | 编译检查 | Android build system | 零error | BLOCK |
| 2 | Scope合规 | 路径匹配约束文件 | 零违规 | BLOCK |
| 3 | 安全红线 | 自定义检查规则 | 零违规 | BLOCK + 通知安全负责人 |
| 4 | API真实性 | grep + API索引 | 零幻觉 | BLOCK |

#### P1 - 应当通过（累计超过阈值则WARNING）

| # | 检查项 | 工具 | 标准 | 超标处理 |
|---|--------|------|------|---------|
| 5 | 编码风格 | checkpatch.pl / clang-format | 零warning | WARNING |
| 6 | 新增Lint错误 | Android Lint | 零新增 | WARNING |
| 7 | 废弃API使用 | @Deprecated扫描 | 零使用 | WARNING |
| 8 | TODO/FIXME关联 | 正则匹配Bug ID | 100%关联 | WARNING |

#### P2 - 建议通过（记录但不阻塞）

| # | 检查项 | 工具 | 标准 |
|---|--------|------|------|
| 9 | 代码复杂度 | 圈复杂度分析 | 单方法 ≤ 15 |
| 10 | 重复代码 | PMD/CPD | ≤ 3% |
| 11 | 注释覆盖率 | 注释行/代码行 | 公开API ≥ 80% |

### 3.2 门禁执行流程

```
代码提交 → P0检查 → P1检查 → P2检查 → 门禁报告
              │          │          │
           全通过     ≤2项超标   记录即可
              │          │          │
              ↓          ↓          ↓
           ┌──────────────────────┐
           │   Gate Decision      │
           │                      │
           │ P0全通过 + P1≤2 → OK │
           │ P0任一失败    → BLOCK│
           │ P1>2项超标    → WARN │
           └──────────────────────┘
```

---

## 4. EvoSkill进化评估

### 4.1 进化效果度量

| 指标 | 计算方式 | 基线参考 |
|------|---------|---------|
| **准确率提升** | 新Skill准确率 - 基线准确率 | 目标: ≥ +10pp |
| **泛化能力** | 跨任务测试集准确率 | 目标: ≥ +5pp |
| **进化效率** | 达到目标准确率的迭代次数 | 目标: ≤ 10轮 |
| **收敛性** | 连续无改进轮数 | 停止阈值: 5轮 |

### 4.2 进化监控

```yaml
evolution_monitoring:
  metrics_per_iteration:
    - timestamp
    - iteration_number
    - skill_variant_id
    - accuracy_score
    - completeness_score
    - frontier_position       # 是否进入Pareto前沿
    - improvement_delta        # 相对上一轮的提升量

  alert_conditions:
    - condition: "accuracy下降超过5pp"
      action: "暂停进化，人工检查约束文件是否被错误修改"
    - condition: "连续5轮无改进"
      action: "终止进化，保留当前Frontier最优Skill"
    - condition: "进化超过20轮仍未达标"
      action: "终止进化，输出分析报告，建议优化约束文件"
```

### 4.3 Frontier管理

```
Pareto Frontier 维护规则:

- 保留最多 N 个Skill变体（默认N=3）
- 新Skill只有在以下情况才替换已有Skill:
  ✓ 准确率更高（且其他指标不低于）
  ✓ 准确率相同但效率更高
  ✓ 准确率略低但泛化能力显著更好
- 每次替换都记录原因和对比数据
- 被替换的Skill保留在 archive/ 目录，不删除
```

---

## 5. 系统效果度量

### 5.1 效率指标

| 指标 | 定义 | 采集方式 | 目标 |
|------|------|---------|------|
| **Bug分析人力节省** | (人工平均时间 - AI平均时间) / 人工平均时间 | 时间日志对比 | ≥ 30% |
| **代码适配成功率** | 一次性通过门禁的次数 / 总尝试次数 | 门禁记录 | ≥ 80% |
| **Skill复用率** | 被跨模块引用的Skill数 / 总Skill数 | 引用计数 | ≥ 40% |
| **Owner投入时间** | 每模块维护约束文件的平均时间 | 时间日志 | ≤ 4h/月 |
| **False Positive率** | AI判定为Bug但实际不是的比例 | 人工审核 | ≤ 15% |

### 5.2 周报模板

```markdown
# TAHP 周报 - Week {N}

## 本周概要
- Skill进化: {新增/更新数}
- Bug分析: {总数} / {准确数} (准确率: {X}%)
- 代码适配: {总数} / {通过门禁数} (通过率: {X}%)
- 门禁拦截: {P0: N} / {P1: N} / {P2: N}

## 效果趋势
| 指标 | 上周 | 本周 | 变化 |
|------|------|------|------|
| Bug分析准确率 | {X}% | {Y}% | {+/-Npp} |
| 代码适配通过率 | {X}% | {Y}% | {+/-Npp} |
| 平均处理时间 | {X}min | {Y}min | {+/-Nmin} |

## 失败案例Top 3
1. {case-id}: {失败原因摘要}
2. ...
3. ...

## 下周计划
- {具体计划}
```

---

## 6. 持续改进机制

### 6.1 反馈闭环

```
开发者使用Skill → 发现问题 → 提交反馈
                                      │
                                      ↓
                            系统记录反馈
                                      │
                                      ↓
                            EvoSkill分析反馈
                                      │
                          ┌───────────┤
                          ↓           ↓
                    约束不足?    Skill不足?
                          ↓           ↓
                    更新约束文件   启动进化循环
                          ↓           ↓
                    通知Owner     自动优化Skill
                          ↓           ↓
                          └─────→ 合并 ←──────┘
                                    │
                                    ↓
                              更新版本，重新评估
```

### 6.2 定期评审

| 评审类型 | 频率 | 参与人 | 内容 |
|---------|------|--------|------|
| **约束文件评审** | 每月 | Owner + TL | 审查约束完整性、准确性 |
| **Skill质量评审** | 每月 | TL + 开发者代表 | 审查Skill效果、用户反馈 |
| **系统效果评审** | 每季度 | 部门经理 + TL | 审查整体ROI、决定资源投入 |
| **安全评审** | 每季度 | 安全负责人 | 审查安全红线、权限管理 |

### 6.3 版本管理

```
Skill版本号规范: MAJOR.MINOR.PATCH

MAJOR: Skill结构重大变更（触发条件: 评估方法变更）
MINOR: Skill逻辑优化（触发条件: 准确率提升 ≥ 5pp）
PATCH: Skill小修复（触发条件: 修复个别失败案例）

Git分支策略:
  main       ← 稳定版本，通过所有门禁
  develop    ← 开发版本，正在进化的Skill
  feature/*  ← 实验性功能
  archive/*  ← 被替换的旧版本
```

---

## 7. 评估自动化

### 7.1 自动评估命令

```bash
# 运行单个模块评估
python scripts/evaluate.py --module telephony --split test

# 运行全部模块评估
python scripts/evaluate.py --all-modules

# 运行EvoSkill进化
python scripts/run-evolution.py --module telephony --iterations 20

# 生成周报
python scripts/weekly-report.py --week {N}

# 检查门禁
python scripts/gate-check.py --module telephony --level P0
```

### 7.2 CI集成（Phase 2目标）

```yaml
# .github/workflows/tahp-eval.yml
name: TAHP Skill Evaluation
on:
  push:
    paths: ['skills/**', 'constraints/**']
  schedule:
    - cron: '0 2 * * 1'  # 每周一凌晨2点

jobs:
  evaluate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Evaluate Skills
        run: |
          pip install -r requirements.txt
          python scripts/evaluate.py --all-modules --split test
      - name: Quality Gate
        run: python scripts/gate-check.py --all-modules --level P0
      - name: Generate Report
        run: python scripts/weekly-report.py --auto
```

---

> **评估不是为了给AI打分，而是为了持续提升系统对开发者的价值。** 评估数据驱动约束文件的优化和Skill的进化，最终目标是让开发者更高效地解决问题。

---

## 8. 知识库质量门禁 (v3.0 新增)

### 8.1 知识沉淀门禁

每次执行任务后，系统自动检查知识沉淀状态：

| 检查项 | 级别 | 条件 | 处理方式 |
|--------|------|------|---------|
| 沉淀完整性 | P1 | Bug分析后必须生成案例 | 自动补充缺失字段 |
| 置信度校验 | P2 | 新沉淀条目置信度 ≥0.6 | 低于阈值标记为 draft |
| 去重检查 | P2 | 与已有条目相似度 <0.9 | 相似条目合并提示 |
| 标签完整性 | P2 | 至少有 2 个标签 | 自动补充标签 |

### 8.2 知识提取门禁

从知识库自动提取约束时的质量检查：

| 检查项 | 级别 | 条件 | 处理方式 |
|--------|------|------|---------|
| 约束完整性 | P0 | 覆盖4种domain的必填字段 | 不完整则不生成Skill |
| 约束一致性 | P1 | 规则之间无矛盾 | 标记矛盾并要求Owner处理 |
| 约束具体性 | P1 | 无模糊描述 | 标记模糊规则 |
| 提取置信度 | P0 | 整体置信度 ≥0.75 | 低于阈值不自动生效 |

### 8.3 知识库评估命令

```bash
# 查看知识库统计报告
python scripts/knowledge_stats.py --module {module}

# 查看全量统计
python scripts/knowledge_stats.py --all

# 触发知识库健康检查
python scripts/knowledge_stats.py --health-check
```
