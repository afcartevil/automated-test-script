import type { AdaptWorkspaceId } from '../adapt-layout/types'
import type { TahpSkillScenario } from '../context-injector'

export interface AdaptAgentPromptInput {
  domainId: string
  domainLabel: string
  module: string
  relatedSkills: string[]
  formData: Record<string, string>
  formFields?: Array<{ name: string; label: string; required?: boolean }>
  userNotes?: string
  workspaceId?: string
  interactionMode?: boolean
}

/** 单个工作区的提示词配置（系统 + 用户），便于分文件维护 */
export interface AdaptWorkspacePromptProfile {
  workspaceId: AdaptWorkspaceId
  /** 控制台工作区显示名 */
  workspaceLabel: string
  /** 注入 buildFullTahpSystemContext 的场景标识 */
  contextScenario: TahpSkillScenario
  isInteractive(input: AdaptAgentPromptInput): boolean
  buildRoleIntro(input: AdaptAgentPromptInput): string
  buildWorkflowHint(domainId: string, primarySkill: string): string
  buildUserTitle(input: AdaptAgentPromptInput): string
  buildUserClosingLines(input: AdaptAgentPromptInput, interactive: boolean): string[]
}
