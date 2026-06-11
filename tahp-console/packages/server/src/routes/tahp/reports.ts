/**
 * 报告浏览路由.
 */
import Router from '@koa/router'
import { existsSync } from 'fs'
import { readFile } from 'fs/promises'
import { join } from 'path'
import { listReports, readReport } from '../../services/tahp/reports-fs'
import { tahpPaths } from '../../services/tahp/paths'
import {
  isAdaptAgentReportRaw,
  normalizeAdaptAgentReport,
} from '../../services/tahp/adapt-agent-report'

export const tahpReportsRoutes = new Router()

tahpReportsRoutes.get('/api/tahp/reports', async (ctx) => {
  try {
    const sub = typeof ctx.query.path === 'string' ? ctx.query.path : ''
    const entries = await listReports(sub)
    ctx.body = { success: true, data: entries }
  } catch (err) {
    ctx.status = 400
    ctx.body = { success: false, error: (err as Error).message }
  }
})

// ── 任务报告（根据 taskId 精准查询）──────────────────────────────────────────
tahpReportsRoutes.get('/api/tahp/reports/task/:id', async (ctx) => {
  const taskId = ctx.params.id
  if (!taskId) {
    ctx.status = 400
    ctx.body = { success: false, error: '缺少 task_id' }
    return
  }
  // 兼容两类任务报告路径：
  // 1) 传统适配报告: reports/<taskId>.json
  // 2) Agent 自动适配: reports/adapt-agent/<taskId>.json
  const candidates = [
    join(tahpPaths.reportsDir, `${taskId}.json`),
    join(tahpPaths.reportsDir, 'adapt-agent', `${taskId}.json`),
  ]
  const filePath = candidates.find(p => existsSync(p))
  if (!filePath) {
    ctx.status = 404
    ctx.body = { success: false, error: `报告不存在: ${taskId}` }
    return
  }
  try {
    const text = await readFile(filePath, 'utf-8')
    const raw = JSON.parse(text) as Record<string, unknown>
    const data = isAdaptAgentReportRaw(raw) ? normalizeAdaptAgentReport(raw) : raw
    ctx.body = { success: true, data }
  } catch (err) {
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

// ── 任务报告列表（只返回 task-adapt-*.json 文件）──────────────────────────
async function buildTaskReportSummary(filePath: string, relPath: string, mtime?: number) {
  try {
    const text = await readFile(filePath, 'utf-8')
    const raw = JSON.parse(text) as Record<string, unknown>
    const normalized = isAdaptAgentReportRaw(raw) ? normalizeAdaptAgentReport(raw) : null
    if (normalized) {
      return {
        task_id: normalized.task_id,
        module: normalized.module,
        domain: normalized.domain,
        domain_label: normalized.domain_label,
        started_at: normalized.started_at,
        completed_at: normalized.completed_at,
        duration_ms: normalized.duration_ms,
        files_modified: normalized.files_modified.length,
        report_type: 'adapt_agent' as const,
        mtime,
        path: relPath,
      }
    }
    return {
      task_id: raw.task_id as string,
      module: raw.module as string | undefined,
      domain: (raw.domain ?? raw.domainId) as string | undefined,
      started_at: (raw.started_at ?? raw.startedAt) as string | undefined,
      completed_at: (raw.completed_at ?? raw.completedAt) as string | undefined,
      duration_ms: raw.duration_ms as number | undefined,
      files_modified: (raw.files_modified as string[] | undefined)?.length ?? 0,
      mtime,
      path: relPath,
    }
  } catch {
    return null
  }
}

tahpReportsRoutes.get('/api/tahp/reports/tasks', async (ctx) => {
  try {
    const all = await listReports('')
    const rootReports = all.filter(e =>
      e.type === 'file' && e.name.startsWith('task-adapt-') && e.name.endsWith('.json'),
    )
    const agentDir = join(tahpPaths.reportsDir, 'adapt-agent')
    let agentReports: Array<{ name: string; path: string; mtime?: number }> = []
    if (existsSync(agentDir)) {
      const agentEntries = await listReports('adapt-agent')
      agentReports = agentEntries
        .filter(e => e.type === 'file' && e.name.startsWith('task-adapt-agent-') && e.name.endsWith('.json'))
        .map(e => ({ name: e.name, path: e.path, mtime: e.mtime }))
    }

    const summaries = await Promise.all([
      ...rootReports.map(e => buildTaskReportSummary(
        join(tahpPaths.reportsDir, e.name),
        e.path,
        e.mtime,
      )),
      ...agentReports.map(e => buildTaskReportSummary(
        join(tahpPaths.reportsDir, 'adapt-agent', e.name),
        e.path,
        e.mtime,
      )),
    ])
    const merged = summaries
      .filter(Boolean)
      .sort((a, b) => {
        const ta = Date.parse(a!.completed_at || '') || a!.mtime || 0
        const tb = Date.parse(b!.completed_at || '') || b!.mtime || 0
        return tb - ta
      })
    ctx.body = { success: true, data: merged }
  } catch (err) {
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

tahpReportsRoutes.get('/api/tahp/reports/content', async (ctx) => {
  const sub = typeof ctx.query.path === 'string' ? ctx.query.path : ''
  if (!sub) {
    ctx.status = 400
    ctx.body = { success: false, error: '缺少 path' }
    return
  }
  try {
    const text = await readReport(sub)
    ctx.body = { success: true, data: { path: sub, content: text } }
  } catch (err) {
    ctx.status = 400
    ctx.body = { success: false, error: (err as Error).message }
  }
})
