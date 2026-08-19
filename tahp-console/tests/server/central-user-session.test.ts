import { describe, expect, it, beforeEach, afterEach } from 'vitest'
import { existsSync, rmSync, mkdirSync, readFileSync } from 'fs'
import { join } from 'path'
import { tahpPaths } from '../../packages/server/src/services/tahp/paths'
import {
  centralUserSessionPath,
  readCentralUserSession,
  writeCentralUserSession,
} from '../../packages/server/src/services/tahp/central-user-session'

describe('central-user-session', () => {
  const sessionPath = centralUserSessionPath()

  beforeEach(() => {
    mkdirSync(join(tahpPaths.projectRoot, '.tahp'), { recursive: true })
    if (existsSync(sessionPath)) rmSync(sessionPath, { force: true })
  })

  afterEach(() => {
    if (existsSync(sessionPath)) rmSync(sessionPath, { force: true })
  })

  it('writes session without password field', () => {
    const rec = writeCentralUserSession({
      username: 'jira.user',
      role: 'business_owner',
      token: 'sess-token',
    })
    expect(rec.username).toBe('jira.user')
    expect(rec.bound_at).toBeTruthy()
    const raw = JSON.parse(readFileSync(sessionPath, 'utf-8')) as Record<string, unknown>
    expect(raw.password).toBeUndefined()
    expect(readCentralUserSession()?.token).toBe('sess-token')
  })
})
