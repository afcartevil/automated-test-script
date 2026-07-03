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
