import { describe, expect, it, beforeEach, afterEach } from 'vitest'
import { existsSync, rmSync, writeFileSync, mkdirSync } from 'fs'
import { join } from 'path'
import { tahpPaths } from '../../packages/server/src/services/tahp/paths'
import {
  jiraUserConfigPath,
  readJiraUserConfig,
  resolveJiraConfig,
  writeJiraUserConfig,
} from '../../packages/server/src/services/tahp/jira-user-config'

describe('jira-user-config', () => {
  const configPath = jiraUserConfigPath()

  beforeEach(() => {
    mkdirSync(join(tahpPaths.projectRoot, '.tahp'), { recursive: true })
    writeFileSync(configPath, JSON.stringify({
      username: 'page.user',
      password: 'page-pass',
      base_url: 'http://jira.example.com',
    }), 'utf-8')
  })

  afterEach(() => {
    if (existsSync(configPath)) rmSync(configPath, { force: true })
  })

  it('reads stored page credentials', () => {
    const rec = readJiraUserConfig()
    expect(rec?.username).toBe('page.user')
    expect(rec?.password).toBe('page-pass')
  })

  it('prefers request header override over stored file', () => {
    const cfg = resolveJiraConfig({ username: 'header.user', password: 'header-pass' })
    expect(cfg.username).toBe('header.user')
    expect(cfg.password).toBe('header-pass')
  })

  it('uses stored file when no header override', () => {
    const cfg = resolveJiraConfig()
    expect(cfg.username).toBe('page.user')
    expect(cfg.password).toBe('page-pass')
    expect(cfg.baseUrl).toBe('http://jira.example.com')
  })

  it('writes credentials with timestamp', () => {
    const rec = writeJiraUserConfig({ username: 'new.user', password: 'new-pass' })
    expect(rec.username).toBe('new.user')
    expect(rec.updated_at).toBeTruthy()
    expect(readJiraUserConfig()?.username).toBe('new.user')
  })
})
