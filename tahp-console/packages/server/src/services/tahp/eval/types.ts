/**
 * 评估层数据模型（bug-analysis / adapt / retrieval 共用）
 *
 * 评测集落 {工程根}/.tahp-config/evals/{suite}/cases/，不入库；
 * 评测结果落 {reportsDir}/evals/{suite}/{runId}/。
 */

/** 评测域 */
export type EvalSuite = 'bug-analysis' | 'adapt' | 'retrieval'

export const EVAL_SUITES: EvalSuite[] = ['bug-analysis', 'adapt', 'retrieval']

export function isEvalSuite(value: unknown): value is EvalSuite {
  return value === 'bug-analysis' || value === 'adapt' || value === 'retrieval'
}

/** 单条评分维度 */
export interface Rubric {
  id: string
  /** 加权权重，须 > 0 */
  weight: number
  /** 必过项：未通过则整例直接判 fail，不参与加权 */
  must?: boolean
  /** 判分标准（写给判官看的自然语言；客观项可留空说明） */
  criterion: string
  /**
   * 评分来源：
   * - objective：由确定性信号打分（适配完成/编译/自检/路由命中）
   * - llm：走 LLM-as-judge（默认，兼容 bug-analysis）
   */
  scoring?: 'objective' | 'llm'
}

export type EvalCaseSourceType = 'jira' | 'local' | 'adapt_agent' | 'pipeline' | 'retrieval_query'

/**
 * 适配客观信号快照。
 * null = 该信号本用例不适用（不算分）；undefined = 未知。
 */
export interface AdaptObjectiveSignals {
  adapt_completed?: boolean
  files_modified_count?: number
  skills_used?: string[]
  /** 期望命中的 skill（与 skills_used 求交） */
  expected_skills?: string[]
  build_pass?: boolean | null
  build_has_artifact?: boolean | null
  selfcheck_pass?: boolean | null
  selfcheck_passed?: number
  selfcheck_failed?: number
  selfcheck_total?: number
  pipeline_passed?: boolean | null
}

/**
 * 检索 / skill 路由客观信号。
 * null = 本用例不适用（如 historical 意图不评 top1 skill）。
 */
export interface RetrievalObjectiveSignals {
  query?: string
  actual_intent?: string
  expected_intent?: string
  intent_matched?: boolean
  explicit_override?: boolean
  top1_skill?: string | null
  expected_top1_skill?: string | null
  top1_matched?: boolean | null
  topk_skills?: string[]
  expected_topk?: string[]
  topk_hit_ratio?: number | null
  preferred_ids?: string[]
  preferred_boosted?: boolean | null
  mode_override_ok?: boolean | null
}

export interface EvalCaseSource {
  type: EvalCaseSourceType
  /** jira 模式 */
  jira_key?: string
  /** local 模式 */
  log_path?: string
  problem_description?: string
  /** 转存来源：bug task / adapt task */
  origin_task_id?: string

  /** adapt_agent / pipeline */
  domain_id?: string
  domain_label?: string
  module?: string
  related_skills?: string[]
  form_data?: Record<string, string>
  form_fields?: Array<{ name: string; label?: string; required?: boolean }>
  user_notes?: string
  workspace_id?: string
  origin_pipeline_run_id?: string
  /** 离线打分用的冻结信号（转存时从历史 run/报告抽取） */
  frozen_signals?: AdaptObjectiveSignals

  /** retrieval_query */
  query?: string
  expected_intent?: string
  expected_top1_skill?: string | null
  expected_top_k_skills?: string[]
  retrieval_mode?: string
  preferred_skill_ids?: string[]
  /** false：该意图策略不产出 skill_hits，top1/topk 记 N/A */
  expect_skill_ranking?: boolean
}

export interface EvalCase {
  id: string
  suite?: EvalSuite
  title?: string
  source: EvalCaseSource
  rubric: Rubric[]
  labels?: string[]
  created_at: string
  updated_at?: string
  /** bug：带 corrections；adapt：可标记曾失败的 origin */
  had_corrections?: boolean
  /**
   * 执行模式：
   * - rerun：重跑业务 Agent（adapt agent / bug 分析）
   * - offline：只对确定性信号 / 本地路由打分（pipeline / retrieval 默认）
   */
  mode?: 'rerun' | 'offline'
}

/** 判官对单条 rubric 的结论 */
export interface RubricVerdict {
  id: string
  pass: boolean
  /** 达成度 0..1 */
  score: number
  reason: string
  /** 判官引用的原文片段 / 客观证据 */
  evidence?: string
}

/** 判官输出（解析后、未加权） */
export interface JudgeVerdict {
  rubrics: RubricVerdict[]
  summary?: string
}

export type CaseVerdict = 'pass' | 'warn' | 'fail'

/** 加权聚合后的单例得分 */
export interface CaseScore {
  /** 加权总分 0..1 */
  total: number
  verdict: CaseVerdict
  /** 未通过的 must rubric id */
  must_failed: string[]
  rubrics: RubricVerdict[]
  summary?: string
}

/**
 * 变体指纹 —— 两次评测可比的前提。
 * skills_hash 变了说明 skill 改过，分数变化不能归因于模型。
 */
export interface EvalVariant {
  /** 被评模型（跑 Agent 用） */
  model?: string
  /** 判官模型（仅 LLM 项） */
  judge_model?: string
  /** skills 目录内容摘要 */
  skills_hash: string
  /** judge / objective 口径版本 */
  prompt_version: string
}

export type EvalCaseStatus = 'passed' | 'warned' | 'failed' | 'error'

/** 人工独立打分 —— 用于校准判官，判断这套 rubric 是否够客观 */
export interface HumanLabel {
  verdict: CaseVerdict
  note?: string
  labeled_at: string
}

export interface EvalCaseResult {
  case_id: string
  status: EvalCaseStatus
  /** 本次产生的任务 id（bug / adapt），用于跳回原报告 */
  task_id?: string
  /** 关联的流水线 run（offline pipeline 用例） */
  pipeline_run_id?: string
  score?: CaseScore
  duration_ms?: number
  error?: string
  human_label?: HumanLabel
  /** 本次实际用到的客观信号（adapt / retrieval） */
  objective_signals?: AdaptObjectiveSignals | RetrievalObjectiveSignals
}

/** 判官与人工的一致率。低于阈值说明 rubric 太主观，分数不可信 */
export interface CalibrationReport {
  labeled: number
  agreed: number
  agreement_rate: number
  disagreements: Array<{
    case_id: string
    judge: CaseVerdict
    human: CaseVerdict
    note?: string
  }>
}

/** summary.json 中的逐例简报（完整明细在 cases/{caseId}.json） */
export interface EvalCaseBrief {
  case_id: string
  title?: string
  status: EvalCaseStatus
  total?: number
  verdict?: CaseVerdict
  task_id?: string
  error?: string
}

export type EvalRunStatus = 'running' | 'completed' | 'failed' | 'aborted'

export interface EvalRunSummary {
  run_id: string
  suite: EvalSuite
  started_at: string
  completed_at?: string
  status: EvalRunStatus
  variant: EvalVariant
  total: number
  passed: number
  warned: number
  failed: number
  errored: number
  /** 已判分用例的平均加权分 0..1 */
  avg_score: number
  /** passed / total */
  pass_rate: number
  cases: EvalCaseBrief[]
  error?: string
}

/** 与 baseline 对比的结果 */
export interface EvalComparison {
  baseline_run_id: string
  current_run_id: string
  pass_rate_delta: number
  avg_score_delta: number
  /** baseline 通过、当前不通过的用例 */
  regressed: string[]
  /** baseline 不通过、当前通过的用例 */
  improved: string[]
  /** 变体是否一致（不一致时分数差异不可单一归因） */
  variant_matched: boolean
}
