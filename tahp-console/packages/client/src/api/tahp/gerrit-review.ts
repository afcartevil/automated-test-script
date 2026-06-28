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

export function fetchRecommendCases(input: {
  p0_items: string[]
  modules?: string[]
}): Promise<{ recommended_cases: RecommendedCase[] }> {
  return tahpPost<{ recommended_cases: RecommendedCase[] }>(
    '/api/tahp/gerrit-review/recommend-cases',
    input,
  )
}

export function cancelGerritReviewTask(
  taskId: string,
): Promise<{ ok: boolean; action?: 'cancelled_pending' | 'interrupted_running' }> {
  return tahpPost(`/api/tahp/gerrit-review/tasks/${encodeURIComponent(taskId)}/cancel`)
}
