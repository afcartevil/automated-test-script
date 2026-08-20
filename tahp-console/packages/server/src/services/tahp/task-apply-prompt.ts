/**
 * 自检 / 流水线上报成功后，缓存「用本报告勾选」弹层数据。
 * 无 pending 行则不弹。
 */
import { logger } from '../logger'
import { readCentralUserSession } from './central-user-session'
import { centralClient } from './sync/central-client'

export type ApplyPrompt = {
  run: { run_id: string; project_code: string; status?: string; dimension?: string; domain_id?: string }
  packages: Array<{
    package_id: string
    title: string
    domain_label: string
    pending_items: Array<{ line_id: string; item_id: string; title: string }>
  }>
  also_pass_default: boolean
  domain_unspecified?: boolean
}

let lastPrompt: ApplyPrompt | null = null

export function getApplyPrompt(): ApplyPrompt | null {
  return lastPrompt
}

export function clearApplyPrompt(): void {
  lastPrompt = null
}

export async function offerApplyPrompt(runId: string, sessionToken?: string): Promise<void> {
  const token = sessionToken || readCentralUserSession()?.token || ''
  if (!token || !runId) return
  try {
    const data = await centralClient.applyCandidates(token, runId)
    const packages = (data.packages || []).filter(p => p.pending_items?.length)
    if (!packages.length) return
    lastPrompt = {
      run: data.run,
      packages,
      also_pass_default: data.run?.status === 'pass',
      domain_unspecified: data.domain_unspecified,
    }
  } catch (err) {
    logger.debug({ err: (err as Error).message, runId }, '[task-apply] candidates skipped')
  }
}
