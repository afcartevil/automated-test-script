/**
 * 从「升级项目关键信息表.xlsx」解析「升级中」项目节点信息
 */
import { existsSync } from 'fs'
import { join, resolve } from 'path'
import * as XLSX from 'xlsx'
import { tahpPaths } from './paths'

export const PROJECT_INFO_SHEET = '项目信息'
export const UPGRADING_STATUS = '升级中'
export const NODE_KEYS = ['STR4', 'STR4A', 'STR5', 'STR6'] as const

export type ProjectNodeKey = (typeof NODE_KEYS)[number]

export interface ProjectNodeEntry {
  name: string
  status: string
  nodes: Record<ProjectNodeKey, string | null>
}

const HEADER_ALIASES: Record<string, string> = {
  'STR 5': 'STR5',
  STR5: 'STR5',
}

const EXCEL_COLUMN_MAP: Record<ProjectNodeKey, string[]> = {
  STR4: ['STR4'],
  STR4A: ['STR4A'],
  STR5: ['STR5', 'STR 5'],
  STR6: ['STR6'],
}

export function defaultProjectInfoXlsxPath(): string {
  if (process.env.TAHP_PROJECT_INFO_XLSX) {
    return resolve(process.env.TAHP_PROJECT_INFO_XLSX)
  }
  return join(tahpPaths.projectRoot, 'docs', '升级项目关键信息表.xlsx')
}

export function normalizeHeader(header: string): string {
  const trimmed = String(header || '').trim()
  return HEADER_ALIASES[trimmed] || trimmed
}

export function parseProjectDate(value: unknown): string | null {
  if (value == null || value === '') return null

  if (value instanceof Date && !Number.isNaN(value.getTime())) {
    return formatDateParts(value.getFullYear(), value.getMonth() + 1, value.getDate())
  }

  const text = String(value).trim()
  if (!text) return null

  const isoMatch = text.match(/^(\d{4})[-/](\d{1,2})[-/](\d{1,2})/)
  if (isoMatch) {
    return formatDateParts(
      Number(isoMatch[1]),
      Number(isoMatch[2]),
      Number(isoMatch[3]),
    )
  }

  const parsed = new Date(text)
  if (!Number.isNaN(parsed.getTime())) {
    return formatDateParts(parsed.getFullYear(), parsed.getMonth() + 1, parsed.getDate())
  }

  return null
}

function formatDateParts(year: number, month: number, day: number): string {
  const y = String(year).padStart(4, '0')
  const m = String(month).padStart(2, '0')
  const d = String(day).padStart(2, '0')
  return `${y}/${m}/${d}`
}

function buildHeaderIndex(headers: string[]): Map<string, number> {
  const index = new Map<string, number>()
  headers.forEach((header, col) => {
    const normalized = normalizeHeader(header)
    if (normalized) index.set(normalized, col)
  })
  return index
}

function findColumn(headerIndex: Map<string, number>, names: string[]): number | undefined {
  for (const name of names) {
    const col = headerIndex.get(name)
    if (col != null) return col
  }
  return undefined
}

function readNodeDates(
  row: unknown[],
  headerIndex: Map<string, number>,
): Record<ProjectNodeKey, string | null> {
  const nodes = {} as Record<ProjectNodeKey, string | null>
  for (const key of NODE_KEYS) {
    const col = findColumn(headerIndex, EXCEL_COLUMN_MAP[key])
    nodes[key] = col != null ? parseProjectDate(row[col]) : null
  }
  return nodes
}

function readWorkbookRows(filePath: string): unknown[][] {
  const workbook = XLSX.readFile(filePath, { cellDates: true })
  const sheet = workbook.Sheets[PROJECT_INFO_SHEET]
  if (!sheet) {
    throw new Error(`工作表「${PROJECT_INFO_SHEET}」不存在`)
  }
  return XLSX.utils.sheet_to_json(sheet, {
    header: 1,
    defval: '',
    raw: false,
    dateNF: 'yyyy/mm/dd',
  }) as unknown[][]
}

export async function parseProjectInfoXlsx(filePath?: string): Promise<{
  sourcePath: string
  projects: ProjectNodeEntry[]
}> {
  const resolved = filePath ? resolve(filePath) : defaultProjectInfoXlsxPath()
  if (!existsSync(resolved)) {
    throw new Error(`项目信息表格不存在: ${resolved}`)
  }

  let rows: unknown[][]
  try {
    rows = readWorkbookRows(resolved)
  } catch (err) {
    const msg = (err as Error).message
    if (msg.includes('EBUSY') || msg.includes('locked')) {
      throw new Error('项目信息表格正在被占用，请关闭 Excel 后重试')
    }
    throw err
  }

  if (!rows.length) {
    throw new Error('项目信息表格为空')
  }

  const headers = rows[0].map((cell) => String(cell ?? '').trim())
  const headerIndex = buildHeaderIndex(headers)
  const nameCol = findColumn(headerIndex, ['项目名称'])
  const statusCol = findColumn(headerIndex, ['是否已完成升级'])

  if (nameCol == null || statusCol == null) {
    throw new Error('表格缺少「项目名称」或「是否已完成升级」列')
  }

  const projects: ProjectNodeEntry[] = []
  for (let i = 1; i < rows.length; i += 1) {
    const row = rows[i]
    if (!Array.isArray(row)) continue

    const name = String(row[nameCol] ?? '').trim()
    if (!name) continue

    const status = String(row[statusCol] ?? '').trim()
    if (status !== UPGRADING_STATUS) continue

    projects.push({
      name,
      status,
      nodes: readNodeDates(row, headerIndex),
    })
  }

  const relativeSource = resolved.startsWith(tahpPaths.projectRoot)
    ? resolved.slice(tahpPaths.projectRoot.length).replace(/^[/\\]/, '')
    : resolved

  return {
    sourcePath: relativeSource.replace(/\\/g, '/'),
    projects,
  }
}
