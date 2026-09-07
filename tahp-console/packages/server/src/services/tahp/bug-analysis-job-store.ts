/**
 * TAHP — JQL 批量分析 Job 落盘
 *
 * 为什么需要落盘：
 *   批量队列串行执行，单条子任务是一次完整 Agent 会话（可能几十分钟），
 *   整条队列跑上百单会持续数小时到数十小时。jobCtx / taskCtx 都在进程内存里，
 *   BFF 一重启进度就全丢（子任务报告本身在 reports/bug-analysis/ 里还在）。
 *
 *   这里把「队列清单 + 每单终态」落到 reports/bug-analysis/jobs/<jobId>.json，
 *   重启后可以还原进度视图，并按未完成清单续跑。
 *
 * 落盘只记录调度所需的最小信息，不复制报告正文。
 */
import { existsSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'fs'
import { join } from 'path'
import { logger } from '../logger'

export type PersistedBugJobStatus = 'running' | 'completed' | 'failed' | 'interrupted'

export interface PersistedBugJobTask {
  task_id: string
  jira_key: string
  jira_url: string
  status: string
  error?: string
}

export interface PersistedBugJob {
  job_id: string
  type: 'batch'
  jql?: string
  extra_context?: string
  /** 指定代码源原始输入（续跑时透传给新 job） */
  code_source?: string
  resumed_from?: string
  /** 每单分析完成后自动回写 Jira comment 并尝试置重 */
  auto_post_comment_and_dup?: boolean
  started_at: string
  updated_at: string
  status: PersistedBugJobStatus
  total: number
  completed: number
  failed: number
  tasks: PersistedBugJobTask[]
}

const JOB_ID_RE = /^[A-Za-z0-9._-]+$/

export function isSafeJobId(jobId: string): boolean {
  return !!jobId && JOB_ID_RE.test(jobId) && !jobId.includes('..')
}

export function bugJobDir(reportsDir: string): string {
  const dir = join(reportsDir, 'bug-analysis', 'jobs')
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true })
  return dir
}

function bugJobPath(reportsDir: string, jobId: string): string {
  return join(bugJobDir(reportsDir), `${jobId}.json`)
}

export function saveBugJob(reportsDir: string, job: PersistedBugJob): void {
  if (!isSafeJobId(job.job_id)) return
  try {
    writeFileSync(
      bugJobPath(reportsDir, job.job_id),
      JSON.stringify({ ...job, updated_at: new Date().toISOString() }, null, 2),
      'utf-8',
    )
  } catch (err) {
    logger.warn({ err: (err as Error).message, jobId: job.job_id }, '[bug-analysis] persist job failed')
  }
}

export function readPersistedBugJob(reportsDir: string, jobId: string): PersistedBugJob | null {
  if (!isSafeJobId(jobId)) return null
  const p = bugJobPath(reportsDir, jobId)
  if (!existsSync(p)) return null
  try {
    return JSON.parse(readFileSync(p, 'utf-8')) as PersistedBugJob
  } catch {
    return null
  }
}

export function listPersistedBugJobs(reportsDir: string): PersistedBugJob[] {
  const dir = bugJobDir(reportsDir)
  let files: string[] = []
  try {
    files = readdirSync(dir).filter(f => f.endsWith('.json'))
  } catch {
    return []
  }
  const jobs: PersistedBugJob[] = []
  for (const f of files) {
    try {
      const job = JSON.parse(readFileSync(join(dir, f), 'utf-8')) as PersistedBugJob
      if (job?.job_id) jobs.push(job)
    } catch { /* skip corrupt */ }
  }
  return jobs.sort((a, b) => String(b.started_at || '').localeCompare(String(a.started_at || '')))
}

export function deletePersistedBugJob(reportsDir: string, jobId: string): void {
  if (!isSafeJobId(jobId)) return
  const p = bugJobPath(reportsDir, jobId)
  if (!existsSync(p)) return
  try { rmSync(p, { force: true }) } catch { /* ignore */ }
}

/** 终态子任务：不需要续跑。 */
export function isTerminalPersistedStatus(status: string): boolean {
  return status === 'completed' || status === 'failed' || status === 'cancelled'
}

/**
 * 续跑候选：进程被中断时停在 pending / running / waiting_user_input 的单子。
 * 这些单子没有可信结论，需要重新跑一遍。
 */
export function unfinishedJobTasks(job: PersistedBugJob): PersistedBugJobTask[] {
  return (job.tasks || []).filter(t => !isTerminalPersistedStatus(String(t.status || '')))
}

/** 重跑候选：明确失败的单子。 */
export function failedJobTasks(job: PersistedBugJob): PersistedBugJobTask[] {
  return (job.tasks || []).filter(t => String(t.status || '') === 'failed')
}
