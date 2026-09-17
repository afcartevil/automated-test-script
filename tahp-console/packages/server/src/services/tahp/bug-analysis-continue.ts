/**
 * 智能诊断「补充信息继续分析」准入与会话策略。
 *
 * Agent Bridge 会回收闲置会话（默认 30 分钟），完成后仍允许基于落盘报告续跑。
 * 会话仍存活时走原 session 续聊，避免改变短时间内补充信息的既有路径。
 */

export interface BugContinueEligibilityInput {
  found: boolean
  status?: string
  dupJudgeRunning?: boolean
}

export interface BugContinueEligibility {
  can_continue: boolean
  reason?: string
}

export type BugContinueSessionMode = 'reuse_session' | 'rebuild_history'

export function evaluateBugContinueEligibility(
  input: BugContinueEligibilityInput,
): BugContinueEligibility {
  if (!input.found) {
    return { can_continue: false, reason: '找不到任务' }
  }
  const status = input.status || ''
  if (status === 'running' || status === 'pending' || status === 'waiting_user_input') {
    return { can_continue: false, reason: '任务正在运行中' }
  }
  if (input.dupJudgeRunning) {
    return { can_continue: false, reason: '正在尝试置重，请稍后再补充分析' }
  }
  if (status !== 'completed') {
    return { can_continue: false, reason: '仅已完成的分析任务可补充继续' }
  }
  return { can_continue: true }
}

export function resolveBugContinueSessionMode(sessionAlive: boolean): BugContinueSessionMode {
  return sessionAlive ? 'reuse_session' : 'rebuild_history'
}
