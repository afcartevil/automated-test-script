import { tahpPost, tahpGet, tahpRequest } from './client'

// ─── 前置条件字段定义 ─────────────────────────────────────────────────────────
export interface AdaptFieldDef {
  name:        string
  label:       string
  type:        'text' | 'select' | 'textarea'
  required:    boolean
  placeholder?: string
  options?:    Array<{ label: string; value: string }>
}

// ─── 动态域定义 ───────────────────────────────────────────────────────────────
export interface DynamicDomain {
  id:            string
  label:         string
  icon:          string
  color:         string
  module:        string
  status:        'active' | 'disabled'
  skillId:       string
  relatedSkills: string[]
  fields:        AdaptFieldDef[]
}

// ─── 技能创建请求 ─────────────────────────────────────────────────────────────
export interface CreateSkillRequest {
  skillId:      string
  domainLabel:  string
  domainId?:    string
  module:       string          // 必选：驱动、通信、内核、功耗温升、自定义
  funcType:     string          // 必选：Bug分析、代码适配、版本适配、运营商移植等
  icon?:        string
  color?:       string
  adaptFields?: AdaptFieldDef[]
  content?:     string
  description?: string
}

// ─── 技能信息（列表项）───────────────────────────────────────────────────────
export interface SkillInfo {
  skillId:     string
  domainId:    string
  domainLabel: string
  module:      string
  icon:        string
  color:       string
  status:      string
  description: string
  adaptFields: AdaptFieldDef[]
  createdAt:   string
}

// ─── API 函数 ─────────────────────────────────────────────────────────────────

export function createAdaptSkill(req: CreateSkillRequest): Promise<{ skillId: string; path: string; domainId: string; domainLabel: string }> {
  return tahpPost('/api/tahp/skills/create', req)
}

export function listAdaptSkills(): Promise<{ skills: SkillInfo[]; total: number }> {
  return tahpGet('/api/tahp/skills/list')
}

export function deleteAdaptSkill(skillId: string): Promise<{ deleted: string }> {
  return tahpRequest(`/api/tahp/skills/${encodeURIComponent(skillId)}`, { method: 'DELETE' })
}

export function fetchDynamicDomains(): Promise<{ domains: DynamicDomain[] }> {
  return tahpGet('/api/tahp/adapt/domains')
}
