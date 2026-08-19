/**
 * 中心用户 session 落盘（无密码）。供打开中心网页发 ticket、/task-notify 使用。
 * 路径：{TAHP工程根}/.tahp/central-user-session.json
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'fs'
import { join } from 'path'
import { tahpPaths } from './paths'

export type CentralUserSession = {
  username: string
  role: string
  token: string
  bound_at: string
}

function sessionDir(): string {
  const d = join(tahpPaths.projectRoot, '.tahp')
  if (!existsSync(d)) mkdirSync(d, { recursive: true })
  return d
}

export function centralUserSessionPath(): string {
  return join(sessionDir(), 'central-user-session.json')
}

export function readCentralUserSession(): CentralUserSession | null {
  const p = centralUserSessionPath()
  if (!existsSync(p)) return null
  try {
    const raw = JSON.parse(readFileSync(p, 'utf-8')) as Record<string, unknown>
    const username = String(raw.username || '').trim()
    const token = String(raw.token || '').trim()
    const role = String(raw.role || '').trim()
    if (!username || !token) return null
    return {
      username,
      role: role || 'business_owner',
      token,
      bound_at: typeof raw.bound_at === 'string' ? raw.bound_at : '',
    }
  } catch {
    return null
  }
}

export function writeCentralUserSession(input: {
  username: string
  role: string
  token: string
}): CentralUserSession {
  const record: CentralUserSession = {
    username: input.username.trim(),
    role: input.role,
    token: input.token,
    bound_at: new Date().toISOString(),
  }
  writeFileSync(centralUserSessionPath(), JSON.stringify(record, null, 2), 'utf-8')
  return record
}
