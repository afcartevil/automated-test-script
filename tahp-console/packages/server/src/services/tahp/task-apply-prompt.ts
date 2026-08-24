/**
 * 自检 / 流水线上报成功后，缓存「用本报告勾选」弹层队列。
 * 进程内数组：弹层展示中仍可入队；提交/跳过只出队头。
 */
import { logger } from '../logger'
import { readCentralUserSession } from './central-user-session'
import { centralClient } from './sync/central-client'

export type ApplyPrompt = {
  run: { run_id: string; project_code: string; campaign_id?: string; status?: string; dimension?: string; domain_id?: string }
  packages: Array<{
    package_id: string
    title: string
    domain_label: string
    pending_items: Array<{ line_id: string; item_id: string; title: string }>
  }>
  also_pass_default: boolean
  domain_unspecified?: boolean
  campaign_unspecified?: boolean
}

const queue: ApplyPrompt[] = []

export function getApplyPrompt(): ApplyPrompt | null {
  return queue[0] || null
}

export function listApplyQueue(): ApplyPrompt[] {
  return [...queue]
}

/** 提交或跳过当前头，留下后续 run。 */
export function clearApplyPrompt(): void {
  queue.shift()
}

export function resetApplyQueue(): void {
  queue.length = 0
}

export async function offerApplyPrompt(runId: string, sessionToken?: string): Promise<void> {
  const token = sessionToken || readCentralUserSession()?.token || ''
  if (!token || !runId) return
  try {
    const data = await centralClient.applyCandidates(token, runId)
    const packages = (data.packages || []).filter(p => p.pending_items?.length)
    if (!packages.length) return
    if (queue.some(p => p.run.run_id === runId)) return
    queue.push({
      run: data.run,
      packages,
      also_pass_default: data.run?.status === 'pass' && !data.campaign_unspecified,
      domain_unspecified: data.domain_unspecified,
      campaign_unspecified: data.campaign_unspecified,
    })
  } catch (err) {
    logger.debug({ err: (err as Error).message, runId }, '[task-apply] candidates skipped')
  }
}
