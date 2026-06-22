/**
 * AI Bug 分析 — 每任务一份排查日志.
 *
 * 写入位置: <HERMES_WEB_UI_HOME>/logs/bug-analysis/<taskId>.log
 * - 纯文本，按行追加（时间戳 + 级别 + 消息）
 * - 用于事后排查 LLM 调用、JIRA fetch、skill 选择等
 * - 同时记录 distill-pending.json（"沉淀为知识库"按钮的请求清单）
 *
 * 设计原则:
 *   - 写入失败永不抛异常（只 logger.warn），保护主 LLM 流水线
 *   - 自动建目录
 *   - 文件大小限制 5MB（超过自动截断保留尾部）
 */
import { appendFile, mkdir, readFile, stat, truncate, writeFile } from 'fs/promises'
import { existsSync } from 'fs'
import { join, resolve } from 'path'
import { config } from '../../config'
import { logger } from '../logger'

const LOG_ROOT = resolve(config.appHome, 'logs', 'bug-analysis')
const DISTILL_QUEUE_FILE = join(LOG_ROOT, 'distill-pending.json')
const MAX_LOG_SIZE = 5 * 1024 * 1024

export type BugLogLevel = 'info' | 'warn' | 'error' | 'debug'

async function ensureDir() {
  try {
    if (!existsSync(LOG_ROOT)) await mkdir(LOG_ROOT, { recursive: true })
  } catch (err) {
    logger.warn({ err: (err as Error).message }, '[bug-log] mkdir failed')
  }
}

function pad2(n: number) {
  return n < 10 ? `0${n}` : String(n)
}

function nowStamp(): string {
  const d = new Date()
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())} ${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}.${String(d.getMilliseconds()).padStart(3, '0')}`
}

function logPathFor(taskId: string): string {
  // 简单的 path safety 过滤
  const safe = taskId.replace(/[^a-zA-Z0-9_\-]/g, '_')
  return join(LOG_ROOT, `${safe}.log`)
}

async function rotateIfTooLarge(file: string) {
  try {
    if (!existsSync(file)) return
    const st = await stat(file)
    if (st.size <= MAX_LOG_SIZE) return
    const keep = Math.floor(MAX_LOG_SIZE / 2)
    const content = await readFile(file, 'utf-8')
    const tail = content.slice(content.length - keep)
    await truncate(file, 0)
    await writeFile(file, `--- rotated, keeping last ${keep} bytes ---\n${tail}`, 'utf-8')
  } catch {
    /* ignore rotation failures */
  }
}

/** 追加一条任务级日志（同步语义，但异步写盘）. */
export async function appendBugLog(taskId: string, level: BugLogLevel, message: string, extra?: Record<string, unknown>): Promise<void> {
  if (!taskId) return
  await ensureDir()
  const file = logPathFor(taskId)
  await rotateIfTooLarge(file)
  let line = `[${nowStamp()}] [${level.toUpperCase()}] ${message}`
  if (extra && Object.keys(extra).length) {
    try {
      line += ` ${JSON.stringify(extra)}`
    } catch { /* skip */ }
  }
  try {
    await appendFile(file, line + '\n', 'utf-8')
  } catch (err) {
    logger.warn({ err: (err as Error).message, taskId }, '[bug-log] append failed')
  }
}

/** 同步入口：调用方不需要 await（用于 fire-and-forget 的事件流） */
export function logBug(taskId: string, level: BugLogLevel, message: string, extra?: Record<string, unknown>): void {
  appendBugLog(taskId, level, message, extra).catch(() => { /* swallowed */ })
}

/** 读取整份日志（用于 UI "下载日志"） */
export async function readBugLog(taskId: string): Promise<string> {
  const file = logPathFor(taskId)
  if (!existsSync(file)) return ''
  return readFile(file, 'utf-8')
}

export function bugLogPath(taskId: string): string {
  return logPathFor(taskId)
}

export function bugLogDir(): string {
  return LOG_ROOT
}

/** 删除任务日志文件（删除历史记录时调用） */
export async function deleteBugLog(taskId: string): Promise<void> {
  const file = logPathFor(taskId)
  try {
    if (existsSync(file)) await import('fs/promises').then(fs => fs.unlink(file))
  } catch (err) {
    logger.warn({ err: (err as Error).message, taskId }, '[bug-log] delete failed')
  }
}

/** 从 distill 队列移除指定任务记录 */
export async function removeDistillRequestsForTask(taskId: string): Promise<void> {
  if (!existsSync(DISTILL_QUEUE_FILE)) return
  try {
    const text = await readFile(DISTILL_QUEUE_FILE, 'utf-8')
    const arr = JSON.parse(text)
    if (!Array.isArray(arr)) return
    const next = arr.filter((r: DistillRequestRecord) => r.task_id !== taskId)
    if (next.length === arr.length) return
    await writeFile(DISTILL_QUEUE_FILE, JSON.stringify(next, null, 2), 'utf-8')
  } catch (err) {
    logger.warn({ err: (err as Error).message, taskId }, '[bug-log] distill remove failed')
  }
}

// ─── 知识沉淀按钮（"沉淀为知识库/skill"）——目前只记录请求，等待二阶段实现 ─────

export interface DistillRequestRecord {
  task_id: string
  jira_key?: string
  module?: string
  title?: string
  requested_at: string
  note?: string
  source: 'bug-analysis'
}

/** "沉淀为知识库/Skill" 按钮的占位实现 —— 把请求追加到 distill-pending.json. */
export async function recordDistillRequest(rec: DistillRequestRecord): Promise<void> {
  await ensureDir()
  let arr: DistillRequestRecord[] = []
  try {
    if (existsSync(DISTILL_QUEUE_FILE)) {
      const text = await readFile(DISTILL_QUEUE_FILE, 'utf-8')
      arr = JSON.parse(text)
      if (!Array.isArray(arr)) arr = []
    }
  } catch { arr = [] }
  arr.push(rec)
  try {
    await writeFile(DISTILL_QUEUE_FILE, JSON.stringify(arr, null, 2), 'utf-8')
  } catch (err) {
    logger.warn({ err: (err as Error).message }, '[bug-log] distill record write failed')
  }
}

export async function listDistillRequests(): Promise<DistillRequestRecord[]> {
  if (!existsSync(DISTILL_QUEUE_FILE)) return []
  try {
    const text = await readFile(DISTILL_QUEUE_FILE, 'utf-8')
    const arr = JSON.parse(text)
    return Array.isArray(arr) ? arr : []
  } catch { return [] }
}
