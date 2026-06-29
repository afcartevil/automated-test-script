/**
 * TAHP — 极简 JIRA REST 客户端
 *
 * 服务于 AI Bug 分析子系统:
 *   - 用户输入 Bug ID（如 X6873OS162-1079）或完整 URL → 解析为 issue key
 *   - GET   /rest/api/2/issue/{key} → 返回标题/描述/状态/经办人/附件 等
 *   - POST  /rest/api/2/search       → JQL 批量查询
 *
 * 配置（按优先级）:
 *   1. 环境变量 TAHP_JIRA_BASE_URL（默认 http://jira.transsion.com）
 *   2. TAHP_JIRA_USERNAME + TAHP_JIRA_PASSWORD → Basic Auth
 *   3. TAHP_JIRA_TOKEN（PAT/Bearer）          → Authorization: Bearer
 *   4. TAHP_JIRA_COOKIE                       → 透传 Cookie（兼容内网 SSO）
 *
 * 设计原则:
 *   - 失败不抛异常打断 LLM 流水线 — 任何错误都包装为 { ok:false, error }
 *   - 永远附带 raw URL，便于上层在 LLM Prompt 中提示用户/Agent 自行 fetch
 *   - 不做缓存（数据量不大，且时效性优先）
 */
import { logger } from '../logger'

export interface JiraConfig {
  baseUrl: string
  username?: string
  password?: string
  token?: string
  cookie?: string
}

export interface JiraAttachment {
  id: string
  filename: string
  mimeType?: string
  size?: number
  url: string
  createdAt?: string
  author?: string
}

export interface JiraComment {
  id: string
  author?: string
  body: string
  createdAt?: string
}

export interface JiraIssue {
  key: string
  url: string
  summary: string
  status?: string
  priority?: string
  severity?: string
  reporter?: string
  assignee?: string
  components?: string[]
  labels?: string[]
  fixVersions?: string[]
  affectedVersions?: string[]
  createdAt?: string
  updatedAt?: string
  description?: string
  attachments: JiraAttachment[]
  comments: JiraComment[]
  customFields?: Record<string, unknown>
  raw?: unknown
}

export interface JiraIssueSummary {
  key: string
  url: string
  summary: string
  status?: string
  priority?: string
  assignee?: string
  updatedAt?: string
}

export interface JiraSearchResult {
  total: number
  issues: JiraIssueSummary[]
  jql: string
  truncated: boolean
}

export interface JiraResult<T> {
  ok: boolean
  data?: T
  error?: string
}

export interface JiraSelfInfo {
  name?: string
  displayName?: string
  emailAddress?: string
}

const DEFAULT_BASE_URL = 'http://jira.transsion.com'

export function getJiraConfig(): JiraConfig {
  return {
    baseUrl: (process.env.TAHP_JIRA_BASE_URL || DEFAULT_BASE_URL).replace(/\/+$/, ''),
    username: process.env.TAHP_JIRA_USERNAME || undefined,
    password: process.env.TAHP_JIRA_PASSWORD || undefined,
    token: process.env.TAHP_JIRA_TOKEN || undefined,
    cookie: process.env.TAHP_JIRA_COOKIE || undefined,
  }
}

/** 从原始输入解析 issue key（兼容 URL / 纯 key / 带空格） */
export function parseIssueKey(input: string): string | null {
  if (!input) return null
  const trimmed = input.trim()
  // 完整 URL: http(s)://host/browse/KEY[?...]
  const urlMatch = trimmed.match(/\/browse\/([A-Z][A-Z0-9_]+-\d+)/i)
  if (urlMatch) return urlMatch[1].toUpperCase()
  // 纯 key 形态
  const keyMatch = trimmed.match(/^([A-Z][A-Z0-9_]+-\d+)$/i)
  if (keyMatch) return keyMatch[1].toUpperCase()
  // 容错：任何位置出现的 KEY-NUM
  const inlineMatch = trimmed.match(/([A-Z][A-Z0-9_]+-\d+)/i)
  if (inlineMatch) return inlineMatch[1].toUpperCase()
  return null
}

function formatJiraConnectivityError(status: number, bodyText: string, cfg: JiraConfig): string {
  const snippet = bodyText.trim().slice(0, 240)
  if (status === 401) {
    return snippet
      ? `JIRA 鉴权失败（401）：用户名或密码错误。${snippet}`
      : 'JIRA 鉴权失败（401）：用户名或密码错误，请检查域账号与密码。'
  }
  if (status === 403) {
    return snippet
      ? `JIRA 拒绝访问（403）：${snippet}`
      : 'JIRA 拒绝访问（403）：账号无权限访问 REST API。'
  }
  if (status === 404) {
    return `JIRA 地址不可达（404）：请确认 TAHP_JIRA_BASE_URL 或服务器地址是否正确（当前 ${cfg.baseUrl}）。`
  }
  return snippet
    ? `JIRA 请求失败（${status}）：${snippet}`
    : `JIRA 请求失败（HTTP ${status}）`
}

function formatJiraNetworkError(err: Error, cfg: JiraConfig): string {
  const msg = err.message || '未知网络错误'
  if (/fetch failed|ENOTFOUND|ECONNREFUSED|ETIMEDOUT|timeout/i.test(msg)) {
    return `无法连接 JIRA 服务器（${cfg.baseUrl}）：${msg}`
  }
  return msg
}

/** 用 /rest/api/2/myself 校验 Basic Auth 凭据是否可用 */
export async function verifyJiraConnectivity(cfg: JiraConfig): Promise<JiraResult<JiraSelfInfo>> {
  if (!cfg.username?.trim() || !cfg.password) {
    return { ok: false, error: '请填写 JIRA 用户名和密码' }
  }

  const url = `${cfg.baseUrl}/rest/api/2/myself`
  try {
    const resp = await fetch(url, { headers: buildHeaders(cfg) })
    if (!resp.ok) {
      const text = await resp.text().catch(() => resp.statusText)
      return { ok: false, error: formatJiraConnectivityError(resp.status, text, cfg) }
    }
    const json: any = await resp.json()
    return {
      ok: true,
      data: {
        name: typeof json.name === 'string' ? json.name : undefined,
        displayName: typeof json.displayName === 'string' ? json.displayName : undefined,
        emailAddress: typeof json.emailAddress === 'string' ? json.emailAddress : undefined,
      },
    }
  } catch (err) {
    logger.warn({ err: (err as Error).message, baseUrl: cfg.baseUrl }, '[jira] verifyJiraConnectivity failed')
    return { ok: false, error: formatJiraNetworkError(err as Error, cfg) }
  }
}

function buildHeaders(cfg: JiraConfig): Record<string, string> {
  const h: Record<string, string> = {
    Accept: 'application/json',
    'Content-Type': 'application/json',
    'User-Agent': 'tahp-console-bug-analysis/0.1',
  }
  if (cfg.token) {
    h['Authorization'] = `Bearer ${cfg.token}`
  } else if (cfg.username && cfg.password) {
    h['Authorization'] = `Basic ${Buffer.from(`${cfg.username}:${cfg.password}`).toString('base64')}`
  }
  if (cfg.cookie) {
    h['Cookie'] = cfg.cookie
  }
  return h
}

function issueUrl(cfg: JiraConfig, key: string): string {
  return `${cfg.baseUrl}/browse/${key}`
}

function flattenDescription(raw: unknown): string {
  if (raw == null) return ''
  if (typeof raw === 'string') return raw
  // ADF / Atlassian Document Format (Cloud) — best-effort 平铺
  try {
    if (typeof raw === 'object' && raw !== null) {
      const out: string[] = []
      const walk = (n: any) => {
        if (!n) return
        if (typeof n.text === 'string') out.push(n.text)
        if (Array.isArray(n.content)) n.content.forEach(walk)
      }
      walk(raw)
      return out.join('').trim() || JSON.stringify(raw)
    }
  } catch { /* ignore */ }
  return String(raw)
}

function pickAttachments(fields: any, cfg: JiraConfig): JiraAttachment[] {
  const arr = Array.isArray(fields?.attachment) ? fields.attachment : []
  return arr.map((a: any) => ({
    id: String(a.id ?? ''),
    filename: String(a.filename ?? a.name ?? 'attachment'),
    mimeType: a.mimeType,
    size: typeof a.size === 'number' ? a.size : undefined,
    url: a.content || a.self || `${cfg.baseUrl}/secure/attachment/${a.id}/${encodeURIComponent(a.filename || '')}`,
    createdAt: a.created,
    author: a.author?.displayName || a.author?.name,
  }))
}

function pickComments(fields: any): JiraComment[] {
  const comments = fields?.comment?.comments
  if (!Array.isArray(comments)) return []
  return comments.map((c: any) => ({
    id: String(c.id ?? ''),
    author: c.author?.displayName || c.author?.name,
    body: flattenDescription(c.body),
    createdAt: c.created,
  }))
}

function pickCustomFields(fields: any): Record<string, unknown> {
  if (!fields || typeof fields !== 'object') return {}
  const result: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(fields)) {
    if (!k.startsWith('customfield_')) continue
    if (v == null) continue
    if (typeof v === 'string' && !v.trim()) continue
    if (Array.isArray(v) && !v.length) continue
    result[k] = v
  }
  return result
}

/**
 * Fetch JIRA issue 详情. 失败时返回 { ok:false, error }.
 * 即使没有配置鉴权也尝试请求（部分内网 JIRA 允许匿名读）.
 */
export async function fetchIssue(key: string, cfg: JiraConfig = getJiraConfig()): Promise<JiraResult<JiraIssue>> {
  const upperKey = key.toUpperCase()
  const url = `${cfg.baseUrl}/rest/api/2/issue/${encodeURIComponent(upperKey)}?expand=renderedFields`
  try {
    const resp = await fetch(url, { headers: buildHeaders(cfg) })
    if (!resp.ok) {
      const text = await resp.text().catch(() => resp.statusText)
      return {
        ok: false,
        error: `JIRA ${resp.status}: ${text.slice(0, 240) || resp.statusText}`,
      }
    }
    const json: any = await resp.json()
    const fields = json.fields || {}
    const issue: JiraIssue = {
      key: json.key || upperKey,
      url: issueUrl(cfg, json.key || upperKey),
      summary: fields.summary || '',
      status: fields.status?.name,
      priority: fields.priority?.name,
      severity: fields.severity?.value || fields.severity?.name,
      reporter: fields.reporter?.displayName || fields.reporter?.name,
      assignee: fields.assignee?.displayName || fields.assignee?.name,
      components: Array.isArray(fields.components) ? fields.components.map((c: any) => c.name).filter(Boolean) : [],
      labels: Array.isArray(fields.labels) ? fields.labels : [],
      fixVersions: Array.isArray(fields.fixVersions) ? fields.fixVersions.map((v: any) => v.name).filter(Boolean) : [],
      affectedVersions: Array.isArray(fields.versions) ? fields.versions.map((v: any) => v.name).filter(Boolean) : [],
      createdAt: fields.created,
      updatedAt: fields.updated,
      description: flattenDescription(fields.description),
      attachments: pickAttachments(fields, cfg),
      comments: pickComments(fields),
      customFields: pickCustomFields(fields),
      raw: { key: json.key },  // 不存全量 raw，避免 report 过大
    }
    return { ok: true, data: issue }
  } catch (err) {
    logger.warn({ err: (err as Error).message, key: upperKey }, '[jira] fetchIssue failed')
    return { ok: false, error: (err as Error).message }
  }
}

const MAX_JQL_ISSUES = 50

/** JQL 批量查询. */
export async function searchJQL(
  jql: string,
  cfg: JiraConfig = getJiraConfig(),
  maxResults = MAX_JQL_ISSUES,
): Promise<JiraResult<JiraSearchResult>> {
  if (!jql?.trim()) return { ok: false, error: '空 JQL' }
  const url = `${cfg.baseUrl}/rest/api/2/search`
  const limited = Math.max(1, Math.min(maxResults, MAX_JQL_ISSUES))
  try {
    const resp = await fetch(url, {
      method: 'POST',
      headers: buildHeaders(cfg),
      body: JSON.stringify({
        jql,
        maxResults: limited,
        fields: ['summary', 'status', 'priority', 'assignee', 'updated'],
      }),
    })
    if (!resp.ok) {
      const text = await resp.text().catch(() => resp.statusText)
      return { ok: false, error: `JIRA ${resp.status}: ${text.slice(0, 240) || resp.statusText}` }
    }
    const json: any = await resp.json()
    const issues: JiraIssueSummary[] = (json.issues || []).map((i: any) => ({
      key: i.key,
      url: issueUrl(cfg, i.key),
      summary: i.fields?.summary || '',
      status: i.fields?.status?.name,
      priority: i.fields?.priority?.name,
      assignee: i.fields?.assignee?.displayName || i.fields?.assignee?.name,
      updatedAt: i.fields?.updated,
    }))
    return {
      ok: true,
      data: {
        total: typeof json.total === 'number' ? json.total : issues.length,
        issues,
        jql,
        truncated: (typeof json.total === 'number' && json.total > issues.length),
      },
    }
  } catch (err) {
    logger.warn({ err: (err as Error).message, jql: jql.slice(0, 120) }, '[jira] searchJQL failed')
    return { ok: false, error: (err as Error).message }
  }
}

/** 用于在 LLM Prompt 中渲染简洁的 JIRA 摘要文本（带链接 + 字段） */
export function formatIssueForPrompt(issue: JiraIssue, maxBytes = 6000): string {
  const lines: string[] = []
  lines.push(`# JIRA Bug 单 ${issue.key}`)
  lines.push(`Link: ${issue.url}`)
  lines.push(`标题: ${issue.summary}`)
  if (issue.status) lines.push(`状态: ${issue.status}`)
  if (issue.priority) lines.push(`优先级: ${issue.priority}`)
  if (issue.severity) lines.push(`严重程度: ${issue.severity}`)
  if (issue.assignee) lines.push(`经办人: ${issue.assignee}`)
  if (issue.reporter) lines.push(`报告人: ${issue.reporter}`)
  if (issue.components?.length) lines.push(`组件: ${issue.components.join(', ')}`)
  if (issue.labels?.length) lines.push(`标签: ${issue.labels.join(', ')}`)
  if (issue.affectedVersions?.length) lines.push(`影响版本: ${issue.affectedVersions.join(', ')}`)
  if (issue.fixVersions?.length) lines.push(`修复版本: ${issue.fixVersions.join(', ')}`)
  if (issue.createdAt) lines.push(`创建时间: ${issue.createdAt}`)
  if (issue.updatedAt) lines.push(`更新时间: ${issue.updatedAt}`)
  if (issue.description) {
    lines.push('')
    lines.push('## 描述')
    lines.push(issue.description.slice(0, 3000))
    if (issue.description.length > 3000) lines.push('...(描述截断)')
  }
  if (issue.attachments.length) {
    lines.push('')
    lines.push('## 附件（请使用日志下载/分析 Skill 获取）')
    for (const a of issue.attachments.slice(0, 20)) {
      lines.push(`- ${a.filename}${a.size ? ` (${(a.size / 1024).toFixed(1)} KB)` : ''} — ${a.url}`)
    }
  }
  if (issue.comments.length) {
    lines.push('')
    lines.push('## 关键评论（最近 5 条）')
    for (const c of issue.comments.slice(-5)) {
      lines.push(`- [${c.author || '匿名'} @ ${c.createdAt || '?'}] ${c.body.slice(0, 300)}${c.body.length > 300 ? '...' : ''}`)
    }
  }
  let text = lines.join('\n')
  if (text.length > maxBytes) text = text.slice(0, maxBytes) + '\n...(JIRA 摘要截断)'
  return text
}
