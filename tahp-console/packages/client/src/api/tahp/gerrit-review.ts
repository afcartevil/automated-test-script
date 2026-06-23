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
