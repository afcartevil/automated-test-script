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

export interface AdaptTaskResult {
  taskId: string
  domain: string
  status: 'pending' | 'running' | 'success' | 'failed'
  message?: string
}

/**
 * 启动 AI 适配调试任务
 */
export function launchAdaptTask(config: AdaptConfig): Promise<AdaptTaskResult> {
  return tahpPost<AdaptTaskResult>('/api/tahp/adapt/launch', config)
}

/**
 * 查询适配任务状态
 */
export function getAdaptTaskStatus(taskId: string): Promise<AdaptTaskResult> {
  return tahpGet<AdaptTaskResult>(`/api/tahp/adapt/status/${taskId}`)
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

export interface AdaptAgentRunRequest {
  domain_id: string
  domain_label: string
  module: string
  related_skills: string[]
  project: {
    projectCode: string
    soc: string
    kernelVersion: string
    preVendor: string
    postVendor: string
  }
  form_data: Record<string, string>
  user_notes?: string
}

export function startAdaptAgentRun(req: AdaptAgentRunRequest): Promise<{ task_id: string; status: string; mode: string }> {
  return tahpPost<{ task_id: string; status: string; mode: string }>('/api/tahp/adapt/agent-run', req)
}
