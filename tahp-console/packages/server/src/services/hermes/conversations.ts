/**
 * conversations types stub — Conversation memory service removed from TAHP.
 * These type definitions are retained so conversations-db.ts and sessions.ts compile.
 */

export type ConversationSummary = {
  id: string
  source: string
  model: string
  title: string | null
  started_at: number
  ended_at: number | null
  last_active: number
  message_count: number
  tool_call_count: number
  input_tokens: number
  output_tokens: number
  cache_read_tokens: number
  cache_write_tokens: number
  reasoning_tokens: number
  billing_provider: string | null
  estimated_cost_usd: number
  actual_cost_usd: number | null
  cost_status: string
  preview: string
  is_active: boolean
  thread_session_count: number
}

export type ConversationMessage = {
  id: number | string
  session_id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: number
}

export type ConversationDetail = {
  session_id: string
  messages: ConversationMessage[]
  visible_count: number
  thread_session_count: number
}

export type ConversationListOptions = {
  humanOnly?: boolean
  source?: string
  limit?: number
}
