import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { existsSync, mkdtempSync, readFileSync, rmSync } from 'fs'
import { join } from 'path'
import { tmpdir } from 'os'
import {
  DEFAULT_GERRIT_HOST,
  getGerritConfig,
  getGerritConfigPublic,
  gerritConfigPath,
  gerritRuntimeCredPath,
  isGerritConfigured,
  saveGerritConfig,
  toGerritConfigPublic,
  writeRuntimeCredFile,
} from '../../packages/server/src/services/tahp/gerrit-credentials'

describe('gerrit-credentials', () => {
  let tempDir = ''

  beforeEach(() => {
    tempDir = mkdtempSync(join(tmpdir(), 'tahp-gerrit-cred-'))
    process.env.TAHP_GERRIT_CONFIG_DIR = tempDir
  })

  afterEach(() => {
    delete process.env.TAHP_GERRIT_CONFIG_DIR
    if (tempDir && existsSync(tempDir)) {
      rmSync(tempDir, { recursive: true, force: true })
    }
  })

  it('returns default public config when not saved', () => {
    expect(getGerritConfigPublic()).toEqual({
      host: DEFAULT_GERRIT_HOST,
      user: '',
      configured: false,
      passwordSet: false,
    })
    expect(isGerritConfigured()).toBe(false)
  })

  it('saves and reads gerrit config', async () => {
    const saved = await saveGerritConfig({
      host: 'https://gerrit.transsion.com',
      user: 'test.user',
      password: 'http-pass',
    })

    expect(saved).toEqual({
      host: 'https://gerrit.transsion.com',
      user: 'test.user',
      configured: true,
      passwordSet: true,
    })
    expect(existsSync(gerritConfigPath())).toBe(true)
    expect(getGerritConfig()).toEqual({
      host: 'https://gerrit.transsion.com',
      user: 'test.user',
      password: 'http-pass',
    })
    expect(isGerritConfigured()).toBe(true)
  })

  it('keeps existing password when save omits password', async () => {
    await saveGerritConfig({
      user: 'test.user',
      password: 'http-pass',
    })

    const saved = await saveGerritConfig({
      host: 'https://gerrit.example.com',
      user: 'test.user2',
    })

    expect(saved.user).toBe('test.user2')
    expect(saved.passwordSet).toBe(true)
    expect(getGerritConfig()?.password).toBe('http-pass')
    expect(getGerritConfig()?.host).toBe('https://gerrit.example.com')
  })

  it('writes runtime cred file for agent use', async () => {
    await saveGerritConfig({
      user: 'agent.user',
      password: 'secret',
    })

    const runtimePath = writeRuntimeCredFile()
    expect(runtimePath).toBe(gerritRuntimeCredPath())
    expect(existsSync(runtimePath)).toBe(true)

    const runtime = JSON.parse(readFileSync(runtimePath, 'utf-8')) as {
      host: string
      user: string
      password: string
    }
    expect(runtime.user).toBe('agent.user')
    expect(runtime.password).toBe('secret')
  })

  it('toGerritConfigPublic never exposes password field', () => {
    const pub = toGerritConfigPublic({
      host: DEFAULT_GERRIT_HOST,
      user: 'u',
      password: 'secret',
    })
    expect(pub).not.toHaveProperty('password')
    expect(pub.passwordSet).toBe(true)
  })
})
