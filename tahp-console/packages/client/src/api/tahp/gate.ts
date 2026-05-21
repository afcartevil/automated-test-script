import { tahpPost } from './client'

export interface GateCheckRequest {
  task_id?: string
  module?: string
  level?: 'P0' | 'P1' | 'P2' | 'all'
}

export interface GateCheckResult {
  result?: string
  violations?: Array<{
    level: string
    rule: string
    file?: string
    line?: number
    message: string
  }>
  score?: number
  [key: string]: unknown
}

export function runGateCheck(req: GateCheckRequest): Promise<GateCheckResult> {
  return tahpPost<GateCheckResult>('/api/tahp/gate-check', req)
}
