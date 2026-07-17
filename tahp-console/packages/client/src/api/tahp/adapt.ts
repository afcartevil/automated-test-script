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
}

export interface AdaptPrereqResolveResult {
  project_code: string
  campaign_id: string
  publication_id?: string
  from_os: string
  to_os: string
  domains: AdaptPrereqResolvedDomain[]
}

/** 从中心拉取前置项目列表 */
export function fetchPrereqProjects(): Promise<AdaptPrereqProject[]> {
  return tahpGet<AdaptPrereqProject[]>('/api/tahp/adapt/prereqs/projects')
}

/** 从中心 resolve 项目前置（默认整战役全部域） */
export function resolvePrereqsFromCenter(opts: {
  project_code: string
  campaign_id?: string
  workspace_id?: string
  domain_id?: string
}): Promise<AdaptPrereqResolveResult> {
  const qs = new URLSearchParams()
  qs.set('project_code', opts.project_code)
  if (opts.campaign_id) qs.set('campaign_id', opts.campaign_id)
  if (opts.workspace_id) qs.set('workspace_id', opts.workspace_id)
  if (opts.domain_id) qs.set('domain_id', opts.domain_id)
  return tahpGet<AdaptPrereqResolveResult>(`/api/tahp/adapt/prereqs/resolve?${qs}`)
}
