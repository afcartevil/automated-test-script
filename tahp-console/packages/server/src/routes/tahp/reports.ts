/**
 * 报告浏览路由.
 */
import Router from '@koa/router'
import { existsSync } from 'fs'
import { readFile } from 'fs/promises'
import { join } from 'path'
import { listReports, readReport } from '../../services/tahp/reports-fs'
import { tahpPaths } from '../../services/tahp/paths'

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
    const data = JSON.parse(text)
    ctx.body = { success: true, data }
  } catch (err) {
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

// ── 任务报告列表（只返回 task-adapt-*.json 文件）──────────────────────────
tahpReportsRoutes.get('/api/tahp/reports/tasks', async (ctx) => {
  try {
    const all = await listReports('')
    // 只保留任务报告 JSON 文件（task-adapt-* 命名）
    const taskReports = all.filter(e => e.type === 'file' && e.name.startsWith('task-adapt-') && e.name.endsWith('.json'))
    // 读取每个文件的 summary（只读前512字节，避免全量加载）
    const summaries = await Promise.all(taskReports.map(async (e) => {
      try {
        const text = await readFile(join(tahpPaths.reportsDir, e.name), 'utf-8')
        const json = JSON.parse(text)
        return {
          task_id:      json.task_id,
          module:       json.module,
          domain:       json.domain,
          started_at:   json.started_at,
          completed_at: json.completed_at,
          duration_ms:  json.duration_ms,
          files_modified: (json.files_modified as string[] | undefined)?.length ?? 0,
          mtime:        e.mtime,
          path:         e.path,
        }
      } catch { return null }
    }))
    ctx.body = { success: true, data: summaries.filter(Boolean) }
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
