import { tahpGet } from './client'

export interface SelfCheckItem {
  name: string
  detail: string
  state: 'ok' | 'warn' | 'err'
  label: string
}

export interface SelfCheckCategory {
  title: string
  icon: string
  items: SelfCheckItem[]
}

export interface SelfCheckResult {
  score: number
  level: string
  updated: string
  pass: number
  warn: number
  fail: number
  total: number
  categories: SelfCheckCategory[]
  history: Array<{ time: string; score: number; note: string }>
}

export function fetchSelfCheck(): Promise<SelfCheckResult> {
  return tahpGet<SelfCheckResult>('/api/tahp/self-check')
}
