import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { mkdtempSync, rmSync } from 'fs'
import { join } from 'path'
import { tmpdir } from 'os'

describe('secret-store', () => {
  let tmpHome: string
  let prevHome: string | undefined

  beforeEach(() => {
    vi.resetModules()
    tmpHome = mkdtempSync(join(tmpdir(), 'tahp-secrets-'))
    prevHome = process.env.TAHP_CONSOLE_HOME
    process.env.TAHP_CONSOLE_HOME = tmpHome
  })

  afterEach(() => {
    if (prevHome === undefined) delete process.env.TAHP_CONSOLE_HOME
    else process.env.TAHP_CONSOLE_HOME = prevHome
    try { rmSync(tmpHome, { recursive: true, force: true }) } catch { /* ignore */ }
  })

  it('stores and reads secret (b64 fallback when not win32, or DPAPI on win32)', async () => {
    const { setSecret, getSecret, hasSecret, getSecretsFilePath } = await import(
      '../../packages/server/src/services/tahp/secret-store'
    )
    expect(hasSecret('dify_api_key')).toBe(false)
    setSecret('dify_api_key', 'app-test-key-123')
    expect(hasSecret('dify_api_key')).toBe(true)
    expect(getSecret('dify_api_key')).toBe('app-test-key-123')
    expect(getSecretsFilePath()).toContain(tmpHome)
  }, 30000)
})
