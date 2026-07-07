/**
 * Gerrit Code Review API
 */
import { tahpPost } from './client'

export interface GerritReviewChatRequest {
  session_id?: string
  message: string
}

export interface GerritReviewChatResponse {
  session_id: string
  task_id: string
  status: string
}

export function sendGerritReviewMessage(
  req: GerritReviewChatRequest,
): Promise<GerritReviewChatResponse> {
  return tahpPost<GerritReviewChatResponse>('/api/tahp/gerrit-review/chat', req)
}

export interface RecommendedCase {
  caseKey: string
  caseName: string
  moduleLabel: string
  score: number
  reasons: string[]
}

export interface AiGeneratedCase {
  caseKey: string
  caseIndex: number
  caseName: string
  moduleLabel: string
  coveredP0Items: string[]
  reason: string
  manualSteps: string
  expectedResult: string
}

export type RecommendSource = 'llm' | 'rule'

export interface RecommendCasesResponse {
  recommended_cases: RecommendedCase[]
  source: RecommendSource
  coverage_score: number
  coverage_reason: string
  coverage_gaps: string[]
  ai_generated_cases: AiGeneratedCase[]
  ai_generation_error?: string
}

export function fetchRecommendCases(input: {
  p0_items: string[]
  modules?: string[]
}): Promise<RecommendCasesResponse> {
  return tahpPost<RecommendCasesResponse>(
    '/api/tahp/gerrit-review/recommend-cases',
    input,
  )
}

export function cancelGerritReviewTask(
  taskId: string,
): Promise<{ ok: boolean; action?: 'cancelled_pending' | 'interrupted_running'; error?: string }> {
  return tahpPost(`/api/tahp/gerrit-review/tasks/${encodeURIComponent(taskId)}/cancel`)
}
