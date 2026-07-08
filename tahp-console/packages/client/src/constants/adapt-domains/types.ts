export type AdaptFieldType = 'text' | 'select' | 'textarea' | 'checklist'

export interface AdaptFieldDef {
  name: string
  label: string
  type: AdaptFieldType
  placeholder?: string
  required: boolean
  options?: { label: string; value: string }[]
  /** 清单类型字段的默认内容（特性名<Tab>特性编码，每行一条） */
  defaultValue?: string
}

export interface AdaptDomainDef {
  id: string
  label: string
  icon: string
  color: string
  status: 'active' | 'done' | 'pending' | 'warn'
  fields: AdaptFieldDef[]
  relatedSkills: string[]
  module?: string
  /** 启用 Agent 人机协同（TAHP_USER_INPUT 弹窗 + 补充对话） */
  interactionMode?: boolean
}

export const ADAPT_WORKSPACE_IDS = ['adapt-debug', 'feature-adapt', 'carrier-config'] as const
export type AdaptWorkspaceId = (typeof ADAPT_WORKSPACE_IDS)[number]

export const DEFAULT_ADAPT_WORKSPACE: AdaptWorkspaceId = 'adapt-debug'

export interface AdaptWorkspaceDef {
  id: AdaptWorkspaceId
  label: string
  subtitle: string
  allowDynamicDomains: boolean
}

export function isAdaptWorkspaceId(value: string): value is AdaptWorkspaceId {
  return (ADAPT_WORKSPACE_IDS as readonly string[]).includes(value)
}
