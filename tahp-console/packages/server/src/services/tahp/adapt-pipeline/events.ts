import { appendFileSync, existsSync, mkdirSync, readFileSync } from 'fs'
import { join } from 'path'
import { tahpPaths } from '../paths'
import { getTaskStream } from '../task-stream'

function pipelineLogDir(runId: string): string {
  return join(tahpPaths.reportsDir, 'adapt-pipeline', runId)
}

function nodeLogPath(runId: string, node: string): string {
  return join(pipelineLogDir(runId), `${node}.log`)
}

/** 发布 pipeline.* 事件，payload 必带 run_id */
export function emitPipelineEvent(type: string, payload: Record<string, unknown>): void {
  const runId = payload.run_id != null ? String(payload.run_id) : ''
  getTaskStream().publish({
    type,
    task_id: runId || undefined,
    payload: runId ? { run_id: runId, ...payload } : payload,
    ts: Date.now(),
  })
}

export function appendPipelineLog(runId: string, node: string, line: string): void {
  const dir = pipelineLogDir(runId)
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true })
  const stamped = `[${new Date().toISOString()}] ${line}\n`
  appendFileSync(nodeLogPath(runId, node), stamped, 'utf-8')
  emitPipelineEvent('pipeline.node_log', { run_id: runId, node, line })
}

export function readPipelineLogs(runId: string, node: string, tail = 500): string[] {
  const path = nodeLogPath(runId, node)
  if (!existsSync(path)) return []
  const content = readFileSync(path, 'utf-8')
  const lines = content.split(/\r?\n/).filter(Boolean)
  if (tail <= 0 || lines.length <= tail) return lines
  return lines.slice(-tail)
}
