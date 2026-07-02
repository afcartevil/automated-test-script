import { isAdaptWorkspaceId, type AdaptWorkspaceId } from '../adapt-layout/types'
import { adaptDebugPromptProfile } from './adapt-debug'
import { carrierConfigPromptProfile } from './carrier-config'
import { featureAdaptPromptProfile } from './feature-adapt'
import { buildSystemPrompt, buildUserPrompt } from './shared'
import type { AdaptAgentPromptInput, AdaptWorkspacePromptProfile } from './types'

export type { AdaptAgentPromptInput, AdaptWorkspacePromptProfile } from './types'
export { ADAPT_AUDIT_SKILL_ID } from './constants'
export { adaptDebugPromptProfile } from './adapt-debug'
export { featureAdaptPromptProfile } from './feature-adapt'
export { carrierConfigPromptProfile } from './carrier-config'

const PROFILES: Record<AdaptWorkspaceId, AdaptWorkspacePromptProfile> = {
  'adapt-debug': adaptDebugPromptProfile,
  'feature-adapt': featureAdaptPromptProfile,
  'carrier-config': carrierConfigPromptProfile,
}

export function getAdaptWorkspacePromptProfile(workspaceId?: string): AdaptWorkspacePromptProfile {
  const id = workspaceId?.trim()
  if (id && isAdaptWorkspaceId(id)) return PROFILES[id]
  return PROFILES['adapt-debug']
}

/** 构建将发往 Agent Bridge 的最终提示词（按工作区分文件维护） */
export function buildAdaptAgentPrompts(input: AdaptAgentPromptInput): {
  systemPrompt: string
  userPrompt: string
} {
  const profile = getAdaptWorkspacePromptProfile(input.workspaceId)
  const userPrompt = buildUserPrompt(profile, input)
  const systemPrompt = buildSystemPrompt(profile, input, userPrompt)
  return { systemPrompt, userPrompt }
}

export function buildAdaptAgentUserMessage(input: AdaptAgentPromptInput): string {
  const profile = getAdaptWorkspacePromptProfile(input.workspaceId)
  return buildUserPrompt(profile, input)
}

export function buildAdaptAgentInstructions(
  input: AdaptAgentPromptInput,
  userMessage: string,
): string {
  const profile = getAdaptWorkspacePromptProfile(input.workspaceId)
  return buildSystemPrompt(profile, input, userMessage)
}
