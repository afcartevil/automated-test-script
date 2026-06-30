import { tahpGet, tahpPost } from './client'

export type SkillConfigStatus = 'not_configured' | 'configuring' | 'configured'

export interface SkillConfigListItem {
  id: string
  label: string
  description?: string
  depends_on?: string[]
  status: SkillConfigStatus
  completed_at?: string
  note?: string
  active_task_id?: string
}

export interface SkillConfigListResp {
  manifest_path: string
  skills: SkillConfigListItem[]
}

export interface SkillConfigPreview {
  id: string
  label: string
  description?: string
  skill_md: string
  skill_md_path: string
  manifest_path: string
}

export function fetchSkillConfigList(): Promise<SkillConfigListResp> {
  return tahpGet<SkillConfigListResp>('/api/tahp/skill-config')
}

export function fetchSkillConfigManifestPath(): Promise<{ path: string }> {
  return tahpGet<{ path: string }>('/api/tahp/skill-config/manifest-path')
}

export function fetchSkillPreview(skillId: string): Promise<SkillConfigPreview> {
  return tahpGet<SkillConfigPreview>(`/api/tahp/skill-config/${encodeURIComponent(skillId)}/preview`)
}

export function startSkillConfig(skillId: string, force = false): Promise<{ task_id: string; status: string }> {
  return tahpPost(`/api/tahp/skill-config/${encodeURIComponent(skillId)}/start`, { force })
}

export function continueSkillConfig(taskId: string, message: string): Promise<{ task_id: string }> {
  return tahpPost(`/api/tahp/skill-config/tasks/${encodeURIComponent(taskId)}/continue`, { message })
}

export function respondSkillConfigApproval(
  taskId: string,
  payload: { approval_id: string; choice: string },
): Promise<{ approval_id: string; choice: string }> {
  return tahpPost(`/api/tahp/skill-config/tasks/${encodeURIComponent(taskId)}/approval`, payload)
}

export function resetSkillConfig(skillId: string): Promise<{ skill_id: string; status: string }> {
  return tahpPost(`/api/tahp/skill-config/${encodeURIComponent(skillId)}/reset`)
}
