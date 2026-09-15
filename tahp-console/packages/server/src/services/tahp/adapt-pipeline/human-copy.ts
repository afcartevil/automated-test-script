import type { HumanAction, PipelineRun } from './types'

/** 旧人工门文案 → 当前展示（不迁数据也能刷新历史 run） */
export function rewriteLegacyHumanCopy(text: string): string {
  return String(text ?? '')
    .replace(/请选择恢复点继续，或终止流水线。/g, '请在下方选择恢复点继续。')
    .replace(/通过后可选择恢复点继续/g, '通过后请在下方选择恢复点继续')
}

export function isResumePickerGate(nodeKey: string, reason?: string): boolean {
  return nodeKey === 'human_review' || reason === 'stage_failed'
}

export function refreshLegacyHumanActions(
  nodeKey: string,
  reason: string | undefined,
  actions: HumanAction[] | undefined,
): HumanAction[] {
  const list = actions ?? []
  if (!isResumePickerGate(nodeKey, reason)) return list
  return list.filter(action =>
    action.id !== 'abort'
    && action.id !== 'confirm_done'
    && action.label !== '终止流水线',
  )
}

export function refreshLegacyHumanOnRun(run: PipelineRun): boolean {
  let changed = false
  for (const [nodeKey, stage] of Object.entries(run.stages ?? {})) {
    if (!stage) continue
    if (stage.human) {
      const nextMessage = rewriteLegacyHumanCopy(stage.human.message)
      const nextActions = refreshLegacyHumanActions(
        nodeKey,
        stage.human.reason,
        stage.human.actions,
      )
      if (nextMessage !== stage.human.message) {
        stage.human.message = nextMessage
        changed = true
      }
      const prevIds = (stage.human.actions ?? []).map(a => a.id).join(',')
      const nextIds = nextActions.map(a => a.id).join(',')
      if (prevIds !== nextIds || (stage.human.actions ?? []).length !== nextActions.length) {
        stage.human.actions = nextActions
        changed = true
      }
    }
    const prevText = typeof stage.progress?.text === 'string' ? stage.progress.text : undefined
    if (prevText) {
      const nextText = rewriteLegacyHumanCopy(prevText)
      if (nextText !== prevText) {
        stage.progress = { ...stage.progress, text: nextText }
        changed = true
      }
    }
  }
  return changed
}
