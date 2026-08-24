/**
 * 本机任务上下文：从「我的任务 → 去执行」钉住当前 project/campaign/domain。
 * 仅进程内，12h 过期；不上中心、不进 Hermes。
 */
export const TASK_CONTEXT_TTL_MS = 12 * 60 * 60 * 1000

export type TaskContext = {
  package_id: string
  project_code: string
  campaign_id: string
  domain_id: string
  kind: string
  set_at: string
}

let current: TaskContext | null = null

export function setTaskContext(input: {
  package_id?: string
  project_code?: string
  campaign_id?: string
  domain_id?: string
  kind?: string
}): TaskContext {
  const project_code = String(input.project_code || '').trim()
  if (!project_code) throw new Error('缺少 project_code')
  current = {
    package_id: String(input.package_id || '').trim(),
    project_code,
    campaign_id: String(input.campaign_id || '').trim(),
    domain_id: String(input.domain_id || '').trim().toLowerCase(),
    kind: String(input.kind || '').trim(),
    set_at: new Date().toISOString(),
  }
  return current
}

export function getTaskContext(now = Date.now()): TaskContext | null {
  if (!current) return null
  const setAt = Date.parse(current.set_at)
  if (!Number.isFinite(setAt) || now - setAt > TASK_CONTEXT_TTL_MS) {
    current = null
    return null
  }
  return current
}

export function clearTaskContext(): void {
  current = null
}

/** 用户未另选项目时，优先用未过期的 task-context。 */
export function preferTaskContextProject(
  candidate?: string,
  now = Date.now(),
): { project_code: string; campaign_id?: string; domain_id?: string } | null {
  const ctx = getTaskContext(now)
  if (!ctx) return null
  const picked = String(candidate || '').trim()
  if (picked && picked !== ctx.project_code) return null
  return {
    project_code: ctx.project_code,
    campaign_id: ctx.campaign_id || undefined,
    domain_id: ctx.domain_id || undefined,
  }
}
