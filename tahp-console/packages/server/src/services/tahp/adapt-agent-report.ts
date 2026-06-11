/**
 * 将 adapt-agent 原始报告 JSON 规范化为报告 UI 使用的统一结构。
 */
import { tahpSkillMdPath } from './context-injector'
import { parseAdaptAuditSummary, type AuditCheckItem } from './adapt-audit-summary'

export type { AuditCheckItem, AuditCheckStatus } from './adapt-audit-summary'
export { parseAdaptAuditSummary, AUDIT_STATUS_LABEL } from './adapt-audit-summary'

export interface AdaptAgentFileChange {
  path: string
  action: string
  tool: string
  at?: string
}

export interface AdaptAgentSkillRef {
  skill_id: string
  path: string
  source: 'configured' | 'read_file' | 'skill_view'
}

export interface NormalizedAdaptAgentReport {
  task_id: string
  report_type: 'adapt_agent'
  module?: string
  domain?: string
  domain_label?: string
  started_at?: string
  completed_at?: string
  duration_ms?: number
  status?: string
  files_modified: string[]
  file_changes: AdaptAgentFileChange[]
  skills_used: AdaptAgentSkillRef[]
  related_skills?: string[]
  llm_response?: string
  audit_report?: string
  audit_skill?: string
  audit_summary?: AuditCheckItem[]
  form_data?: Record<string, string>
  domain_id?: string
}

const WRITE_TOOLS = new Set([
  'write', 'write_file', 'edit', 'str_replace', 'str_replace_based_edit_tool',
  'apply_patch', 'Write', 'Edit', 'MultiEdit', 'patch',
])

const READ_ONLY_TOOLS = new Set(['read_file', 'read', 'Read'])

function asString(v: unknown): string | undefined {
  return typeof v === 'string' && v.trim() ? v.trim() : undefined
}

function extractSkillIdFromSkillMdPath(filePath: string): string | undefined {
  const norm = filePath.replace(/\\/g, '/')
  const m = norm.match(/\/skills\/(?:[^/]+\/)*([^/]+)\/SKILL\.md$/i)
  return m?.[1]
}

function parsePreviewPath(preview?: string): string | undefined {
  if (!preview) return undefined
  const m = preview.match(/path=([^)]+)/)
  return m?.[1]?.trim()
}

function parsePreviewSkillName(preview?: string): string | undefined {
  if (!preview) return undefined
  const m = preview.match(/name=([^)]+)/)
  return m?.[1]?.trim()
}

function extractPathsFromExecuteCodePreview(preview?: string): string[] {
  if (!preview) return []
  const paths: string[] = []
  const patterns = [
    /file_path\s*=\s*r?["']([^"']+)["']/g,
    /write_file\s*\(\s*r?["']([^"']+)["']/g,
    /open\s*\(\s*r?["']([^"']+)["']/g,
  ]
  for (const re of patterns) {
    let m: RegExpExecArray | null
    while ((m = re.exec(preview)) !== null) {
      const p = m[1]?.trim()
      if (p && !p.endsWith('SKILL.md')) paths.push(p)
    }
  }
  return paths
}

/** 从 Agent 正文「文件修改清单」等章节回退提取路径（execute_code 场景） */
export function extractFilesFromLlmResponse(text: string): AdaptAgentFileChange[] {
  if (!text?.trim()) return []
  const seen = new Set<string>()
  const result: AdaptAgentFileChange[] = []

  const push = (path: string, action: string) => {
    const norm = path.trim().replace(/\//g, '\\')
    if (!norm || norm.endsWith('SKILL.md') || seen.has(norm)) return
    if (!/^[A-Za-z]:\\/.test(norm) && !norm.startsWith('/')) return
    seen.add(norm)
    result.push({ path: norm, action, tool: 'llm_report' })
  }

  const listSection = text.match(/## 文件修改清单([\s\S]*?)(?=\n## |\n---\n\n##|$)/)?.[1] || ''
  for (const line of listSection.split('\n')) {
    if (!line.startsWith('|') || /路径|------/.test(line)) continue
    const pathMatch = line.match(/`([A-Za-z]:[^`]+)`/)
    if (pathMatch) {
      push(pathMatch[1], /新建/.test(line) ? 'create' : 'modify')
    }
  }

  for (const m of text.matchAll(/\*\*绝对路径\*\*[：:]\s*`([^`]+)`/g)) {
    push(m[1], 'create')
  }

  for (const m of text.matchAll(/open\s*\(\s*r?["']([A-Za-z]:[^"']+\.\w+)["']/g)) {
    push(m[1], 'modify')
  }

  return result
}

/** 从 toolsUsed / fileChanges / llm_response 提取实际写入的文件 */
export function extractAdaptAgentFileChanges(raw: Record<string, unknown>): AdaptAgentFileChange[] {
  const seen = new Set<string>()
  const result: AdaptAgentFileChange[] = []

  const push = (path: string, tool: string, action = 'modify') => {
    const norm = path.trim()
    if (!norm || norm.endsWith('SKILL.md') || seen.has(norm)) return
    seen.add(norm)
    result.push({ path: norm, action, tool })
  }

  const fileChanges = (raw.fileChanges ?? raw.file_changes) as AdaptAgentFileChange[] | undefined
  if (Array.isArray(fileChanges)) {
    for (const c of fileChanges) {
      if (!c?.path) continue
      if (READ_ONLY_TOOLS.has(c.tool)) continue
      if (WRITE_TOOLS.has(c.tool)) {
        push(c.path, c.tool, c.action || 'modify')
      }
    }
  }

  const toolsUsed = raw.toolsUsed as Array<{ name: string; preview?: string }> | undefined
  if (Array.isArray(toolsUsed)) {
    for (const t of toolsUsed) {
      if (WRITE_TOOLS.has(t.name)) {
        const p = parsePreviewPath(t.preview)
        if (p) push(p, t.name, t.name === 'write_file' ? 'create' : 'modify')
      }
      if (t.name === 'execute_code') {
        for (const p of extractPathsFromExecuteCodePreview(t.preview)) {
          push(p, 'execute_code', 'modify')
        }
      }
    }
  }

  const llmText = asString(raw.llm_response) || asString(raw.llmResponse) || ''
  for (const fc of extractFilesFromLlmResponse(llmText)) {
    push(fc.path, fc.tool, fc.action)
  }

  return result
}

/** 提取工程 Skill 完整路径（排除 read_file/write_file/terminal 等内置工具名） */
export function extractAdaptAgentSkillRefs(raw: Record<string, unknown>): AdaptAgentSkillRef[] {
  const map = new Map<string, AdaptAgentSkillRef>()

  const add = (skillId: string, path: string, source: AdaptAgentSkillRef['source']) => {
    const id = skillId.trim()
    if (!id) return
    const fullPath = path.includes('SKILL.md') ? path : tahpSkillMdPath(id)
    if (!map.has(id)) map.set(id, { skill_id: id, path: fullPath, source })
  }

  const related = raw.relatedSkills ?? raw.related_skills
  if (Array.isArray(related)) {
    for (const id of related) {
      if (typeof id === 'string') add(id, tahpSkillMdPath(id), 'configured')
    }
  }

  const toolsUsed = raw.toolsUsed as Array<{ name: string; preview?: string }> | undefined
  if (Array.isArray(toolsUsed)) {
    for (const t of toolsUsed) {
      if (t.name === 'read_file') {
        const p = parsePreviewPath(t.preview)
        if (p?.endsWith('SKILL.md')) {
          const id = extractSkillIdFromSkillMdPath(p)
          if (id) add(id, p, 'read_file')
        }
      }
      if (t.name === 'skill_view') {
        const id = parsePreviewSkillName(t.preview)
        if (id) add(id, tahpSkillMdPath(id), 'skill_view')
      }
    }
  }

  return [...map.values()]
}

/** 判断是否为 adapt-agent 报告（camelCase 字段） */
export function isAdaptAgentReportRaw(raw: Record<string, unknown>): boolean {
  return !!(raw.domainId || raw.domainLabel || raw.fileChanges || raw.toolsUsed)
    || String(raw.task_id || '').startsWith('task-adapt-agent-')
}

/** 规范化为报告详情 API 响应 */
export function normalizeAdaptAgentReport(raw: Record<string, unknown>): NormalizedAdaptAgentReport {
  const fileChanges = extractAdaptAgentFileChanges(raw)
  const skillsUsed = extractAdaptAgentSkillRefs(raw)

  const auditReport = asString(raw.audit_report) || asString(raw.auditReport)
  const llmResponse = asString(raw.llm_response) || asString(raw.llmResponse)

  return {
    task_id: asString(raw.task_id) || asString(raw.taskId) || '',
    report_type: 'adapt_agent',
    module: asString(raw.module),
    domain: asString(raw.domain) || asString(raw.domainId),
    domain_id: asString(raw.domainId) || asString(raw.domain),
    domain_label: asString(raw.domainLabel),
    started_at: asString(raw.started_at) || asString(raw.startedAt),
    completed_at: asString(raw.completed_at) || asString(raw.completedAt),
    duration_ms: typeof raw.duration_ms === 'number' ? raw.duration_ms : undefined,
    status: asString(raw.status),
    files_modified: fileChanges.map(c => c.path),
    file_changes: fileChanges,
    skills_used: skillsUsed,
    related_skills: Array.isArray(raw.relatedSkills)
      ? raw.relatedSkills.filter((x): x is string => typeof x === 'string')
      : Array.isArray(raw.related_skills)
        ? raw.related_skills.filter((x): x is string => typeof x === 'string')
        : undefined,
    llm_response: llmResponse,
    audit_report: auditReport,
    audit_skill: asString(raw.audit_skill) || asString(raw.auditSkillId),
    audit_summary: (auditReport || llmResponse)
      ? parseAdaptAuditSummary(auditReport || '', llmResponse)
      : undefined,
    form_data: (raw.formData ?? raw.form_data) as Record<string, string> | undefined,
  }
}
