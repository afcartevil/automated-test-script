/**
 * 判官校准 —— 拿人工独立打分比对判官结论。
 *
 * 一致率过低说明 rubric 写得太主观，此时所有评测分数都不可信，
 * 应该先收紧判分标准再谈质量对比。
 */
import type { CalibrationReport, CaseVerdict, EvalCaseResult } from './types'

/** 低于此一致率则判官结论不可用 */
export const MIN_AGREEMENT_RATE = 0.8
/** 少于此样本量，一致率没有统计意义 */
export const MIN_LABELED_SAMPLES = 10

function judgeVerdictOf(result: EvalCaseResult): CaseVerdict | null {
  if (result.score) return result.score.verdict
  // 判官没跑出结论（error）时无从比对
  return null
}

export function computeAgreement(results: EvalCaseResult[]): CalibrationReport {
  const disagreements: CalibrationReport['disagreements'] = []
  let labeled = 0
  let agreed = 0

  for (const result of results) {
    const human = result.human_label?.verdict
    const judge = judgeVerdictOf(result)
    if (!human || !judge) continue

    labeled++
    if (human === judge) {
      agreed++
    } else {
      disagreements.push({
        case_id: result.case_id,
        judge,
        human,
        note: result.human_label?.note,
      })
    }
  }

  return {
    labeled,
    agreed,
    agreement_rate: labeled > 0 ? agreed / labeled : 0,
    disagreements,
  }
}

/** 样本不足时不下结论，避免用 2 个样本就宣称判官可信 */
export function isJudgeTrustworthy(report: CalibrationReport): boolean {
  return report.labeled >= MIN_LABELED_SAMPLES && report.agreement_rate >= MIN_AGREEMENT_RATE
}
