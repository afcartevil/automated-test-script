/**
 * 报告目录扫描 — 用于 ReportsView.
 */
import { existsSync } from 'fs'
import { readdir, stat, readFile } from 'fs/promises'
import { join, relative, resolve, sep } from 'path'
import { tahpPaths } from './paths'

export interface ReportEntry {
  type: 'file' | 'dir'
  name: string
  path: string  // 相对 reportsDir 的 POSIX 风格路径
  size?: number
  mtime?: number
}

function ensureInside(base: string, candidate: string): string {
  const abs = resolve(candidate)
  const rel = relative(resolve(base), abs)
  if (rel.startsWith('..') || rel.includes(`..${sep}`)) {
    throw new Error(`路径越界: ${candidate}`)
  }
  return abs
}

function toPosix(p: string): string {
  return p.split(sep).join('/')
}

export async function listReports(subPath = ''): Promise<ReportEntry[]> {
  if (!existsSync(tahpPaths.reportsDir)) return []
  const target = ensureInside(tahpPaths.reportsDir, join(tahpPaths.reportsDir, subPath))
  const entries = await readdir(target, { withFileTypes: true })
  const result: ReportEntry[] = []
  for (const e of entries) {
    const fullPath = join(target, e.name)
    const s = await stat(fullPath)
    const rel = toPosix(relative(tahpPaths.reportsDir, fullPath))
    result.push({
      type: e.isDirectory() ? 'dir' : 'file',
      name: e.name,
      path: rel,
      size: e.isFile() ? s.size : undefined,
      mtime: s.mtimeMs,
    })
  }
  return result.sort((a, b) => (b.mtime || 0) - (a.mtime || 0))
}

const MAX_REPORT_SIZE = 5 * 1024 * 1024

export async function readReport(subPath: string): Promise<string> {
  const target = ensureInside(tahpPaths.reportsDir, join(tahpPaths.reportsDir, subPath))
  if (!existsSync(target)) throw new Error(`报告不存在: ${subPath}`)
  const s = await stat(target)
  if (s.size > MAX_REPORT_SIZE) throw new Error(`报告过大 (${(s.size / 1024 / 1024).toFixed(1)}MB)，请下载查看`)
  return readFile(target, 'utf-8')
}
