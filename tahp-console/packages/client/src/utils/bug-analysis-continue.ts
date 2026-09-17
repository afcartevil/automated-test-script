/** 已完成的智能诊断任务可补充信息继续分析；不依赖 Agent 会话是否仍存活。 */

export function canOfferBugContinueAnalysis(input: {
  taskId?: string | null
  status?: string
  running?: boolean
  pending?: boolean
  waitingUserInput?: boolean
  dupJudgeRunning?: boolean
}): boolean {
  return Boolean(input.taskId)
    && input.status === 'completed'
    && !input.running
    && !input.pending
    && !input.waitingUserInput
    && !input.dupJudgeRunning
}
