/**
 * TAHP AI 适配调试 API
 */
import { tahpPost, tahpGet } from './client'

export interface AdaptConfig {
  domain: string
  projectCode: string
  soc: string
  kernelVersion: string
  preVendor?: string
  postVendor?: string
  formData: Record<string, any>
}

/**
 * 保存适配配置
 */
export function saveAdaptConfig(config: AdaptConfig): Promise<{ success: boolean }> {
  return tahpPost<{ success: boolean }>('/api/tahp/adapt/config/save', config)
}

/**
 * 获取已保存的适配配置
 */
export function getAdaptConfig(): Promise<AdaptConfig | null> {
  return tahpGet<AdaptConfig | null>('/api/tahp/adapt/config/get')
}

export interface AdaptAgentFormFieldMeta {
  name: string
  label: string
  required?: boolean
}

export interface AdaptAgentRunRequest {
  workspace_id?: string
  domain_id: string
  domain_label: string
  module: string
  related_skills: string[]
  form_data: Record<string, string>
  form_fields?: AdaptAgentFormFieldMeta[]
  user_notes?: string
  interaction_mode?: boolean
}

export function startAdaptAgentRun(req: AdaptAgentRunRequest): Promise<{ task_id: string; status: string; mode: string }> {
  return tahpPost<{ task_id: string; status: string; mode: string }>('/api/tahp/adapt/agent-run', req)
}

export function submitAdaptUserInput(
  taskId: string,
  payload: { request_id: string; values: Record<string, string> },
): Promise<{ request_id: string }> {
  return tahpPost(`/api/tahp/adapt/agent-run/${encodeURIComponent(taskId)}/user-input`, payload)
}

export function continueAdaptAgentRun(
  taskId: string,
  message: string,
): Promise<{ ok: boolean }> {
  return tahpPost(`/api/tahp/adapt/agent-run/${encodeURIComponent(taskId)}/continue`, { message })
}

export function respondAdaptApproval(
  taskId: string,
  payload: { approval_id: string; choice: string },
): Promise<{ approval_id: string; choice: string }> {
  return tahpPost(`/api/tahp/adapt/agent-run/${encodeURIComponent(taskId)}/approval`, payload)
}

export function completeAdaptAgentRun(taskId: string): Promise<{ ok: boolean }> {
  return tahpPost(`/api/tahp/adapt/agent-run/${encodeURIComponent(taskId)}/complete`)
}

export function cancelAdaptAgentRun(taskId: string): Promise<{ ok: boolean }> {
  return tahpPost(`/api/tahp/adapt/agent-run/${encodeURIComponent(taskId)}/cancel`)
}

export interface AdaptAgentPromptPreview {
  system_prompt: string
  user_prompt: string
  system_prompt_chars: number
  user_prompt_chars: number
}

export function previewAdaptAgentPrompts(req: AdaptAgentRunRequest): Promise<AdaptAgentPromptPreview> {
  return tahpPost<AdaptAgentPromptPreview>('/api/tahp/adapt/agent-prompt-preview', req)
}

export interface AdaptPrereqProject {
  code: string
  name: string
  product_line?: string
  active_campaign_id?: string | null
  active_publication_id?: string
  active_publication_sequence?: number
  updated_at: string
}

export interface AdaptPrereqFieldSchema {
  key: string
  label: string
  type: string
  required?: boolean
  options?: Array<{ label: string; value: string }>
  placeholder?: string
  source?: string
  category?: string
}

export interface AdaptPrereqResolvedDomain {
  workspace_id: string
  domain_id: string
  revision: number
  schema: AdaptPrereqFieldSchema[]
  form_data: Record<string, unknown>
  stale_fields: string[]
  incomplete_required: string[]
  updated_at?: string
  updated_by?: string
  line_layout_revision?: number
  layout_stale?: boolean
  related_skills?: string[]
}

export interface AdaptPrereqResolveResult {
  project_code: string
  campaign_id: string
  publication_id?: string
  from_os: string
  to_os: string
  line_id?: string
  layout_stale?: boolean
  domains: AdaptPrereqResolvedDomain[]
}

export interface AdaptPrereqResolveOpts {
  project_code: string
  campaign_id?: string
  workspace_id?: string
  domain_id?: string
}

export interface AdaptPrereqFetchOpts {
  force?: boolean
}

let projectsCache: AdaptPrereqProject[] | null = null
let projectsInflight: Promise<AdaptPrereqProject[]> | null = null
const resolveCache = new Map<string, AdaptPrereqResolveResult>()
const resolveInflight = new Map<string, Promise<AdaptPrereqResolveResult>>()

function normPart(value?: string | null): string {
  return value?.trim() ?? ''
}

function resolveCacheKey(opts: AdaptPrereqResolveOpts): string {
  return [
    normPart(opts.project_code),
    normPart(opts.campaign_id),
    normPart(opts.workspace_id),
    normPart(opts.domain_id),
  ].join('\0')
}

function filterResolvedDomains(
  data: AdaptPrereqResolveResult,
  opts: AdaptPrereqResolveOpts,
): AdaptPrereqResolveResult {
  const workspaceId = normPart(opts.workspace_id)
  const domainId = normPart(opts.domain_id)
  if (!workspaceId && !domainId) return data
  return {
    ...data,
    domains: data.domains.filter((d) => {
      if (workspaceId && d.workspace_id !== workspaceId) return false
      if (domainId && d.domain_id !== domainId) return false
      return true
    }),
  }
}

function samePrereqSet(data: AdaptPrereqResolveResult, opts: AdaptPrereqResolveOpts): boolean {
  const wanted = normPart(opts.campaign_id)
  if (!wanted) return true
  return normPart(data.campaign_id) === wanted
}

function readResolveCache(opts: AdaptPrereqResolveOpts): AdaptPrereqResolveResult | null {
  const exact = resolveCache.get(resolveCacheKey(opts))
  if (exact && samePrereqSet(exact, opts)) return filterResolvedDomains(exact, opts)

  const project = normPart(opts.project_code)
  if (!project) return null
  const wantedSet = normPart(opts.campaign_id)

  // 指定了哪一套前置：只认这一套，绝不拿同一项目码的另一套顶替
  if (wantedSet) {
    const hit = resolveCache.get(resolveCacheKey({
      project_code: project,
      campaign_id: wantedSet,
    }))
    if (hit && samePrereqSet(hit, opts)) return filterResolvedDomains(hit, opts)
    return null
  }

  // 未指定套别：用该项目最近一次全量前置（调试页不带套别）
  const fallback = resolveCache.get(resolveCacheKey({ project_code: project }))
  if (fallback) return filterResolvedDomains(fallback, opts)
  return null
}

function writeResolveCache(opts: AdaptPrereqResolveOpts, data: AdaptPrereqResolveResult): void {
  resolveCache.set(resolveCacheKey(opts), data)
  if (data.campaign_id) {
    resolveCache.set(resolveCacheKey({
      ...opts,
      project_code: data.project_code,
      campaign_id: data.campaign_id,
    }), data)
  }
  if (!normPart(opts.workspace_id) && !normPart(opts.domain_id)) {
    resolveCache.set(resolveCacheKey({ project_code: data.project_code }), data)
    if (data.campaign_id) {
      resolveCache.set(resolveCacheKey({
        project_code: data.project_code,
        campaign_id: data.campaign_id,
      }), data)
    }
  }
}

/** 同步读取已缓存的前置项目列表（尚无缓存时返回 null） */
export function peekPrereqProjects(): AdaptPrereqProject[] | null {
  return projectsCache
}

/** 清空会话内前置缓存（测试 / 强制刷新） */
export function clearAdaptPrereqCache(): void {
  projectsCache = null
  projectsInflight = null
  resolveCache.clear()
  resolveInflight.clear()
}

/** 从中心拉取前置项目列表（会话内共享缓存，谁先拉谁写入） */
export function fetchPrereqProjects(opts?: AdaptPrereqFetchOpts): Promise<AdaptPrereqProject[]> {
  if (!opts?.force) {
    if (projectsCache) return Promise.resolve(projectsCache)
    if (projectsInflight) return projectsInflight
  }
  const req = tahpGet<AdaptPrereqProject[]>('/api/tahp/adapt/prereqs/projects')
    .then((data) => {
      projectsCache = data
      return data
    })
    .finally(() => {
      if (projectsInflight === req) projectsInflight = null
    })
  projectsInflight = req
  return req
}

/** 从中心 resolve 项目前置（默认整战役全部域；会话内按项目/战役/域共享） */
export function resolvePrereqsFromCenter(
  opts: AdaptPrereqResolveOpts,
  fetchOpts?: AdaptPrereqFetchOpts,
): Promise<AdaptPrereqResolveResult> {
  const key = resolveCacheKey(opts)
  if (!fetchOpts?.force) {
    const cached = readResolveCache(opts)
    if (cached) return Promise.resolve(cached)
    const inflight = resolveInflight.get(key) ?? (
      !normPart(opts.workspace_id) && !normPart(opts.domain_id)
        ? undefined
        : resolveInflight.get(resolveCacheKey({
            project_code: opts.project_code,
            campaign_id: opts.campaign_id,
          }))
    )
    if (inflight) {
      return inflight.then(data => filterResolvedDomains(data, opts))
    }
  }
  const qs = new URLSearchParams()
  qs.set('project_code', opts.project_code)
  if (opts.campaign_id) qs.set('campaign_id', opts.campaign_id)
  if (opts.workspace_id) qs.set('workspace_id', opts.workspace_id)
  if (opts.domain_id) qs.set('domain_id', opts.domain_id)
  const req = tahpGet<AdaptPrereqResolveResult>(`/api/tahp/adapt/prereqs/resolve?${qs}`)
    .then((data) => {
      writeResolveCache(opts, data)
      return data
    })
    .finally(() => {
      if (resolveInflight.get(key) === req) resolveInflight.delete(key)
    })
  resolveInflight.set(key, req)
  return req
}
